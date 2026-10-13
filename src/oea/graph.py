"""Workflow graph: supervisor -> specialist -> policy gate -> (execute | HITL | escalate)
-> back to supervisor until the exception queue is empty.

Uses LangGraph's StateGraph when installed; otherwise a minimal equivalent runner
with the same node/edge semantics (see ADR-0001).
"""
from __future__ import annotations
import time
from typing import Any, Callable, TypedDict

from .agents import (CreditAgent, FraudRouter, InventoryAgent, LateDeliveryAgent,
                     PricingAgent, detect_exceptions)
from .audit import AuditLog
from .erp import MockERP
from .hitl import Approver
from .llm import LLMClient
from . import policy as pol
from .models import ActionType, Decision, ExceptionType

END = "__end__"
try:  # pragma: no cover - exercised depending on environment
    from langgraph.graph import StateGraph, END as LG_END
    HAVE_LANGGRAPH = True
except Exception:  # noqa: BLE001
    HAVE_LANGGRAPH = False


class CaseState(TypedDict, total=False):
    case_id: str
    order_item_id: int
    queue: list[str]
    current: str | None
    proposal: dict | None
    policy: dict | None
    outcomes: list[dict]
    route: str


class MiniGraph:
    """Minimal StateGraph-compatible runner (subset used here)."""
    def __init__(self, _schema=None):
        self.nodes: dict[str, Callable] = {}
        self.edges: dict[str, str] = {}
        self.cond: dict[str, tuple[Callable, dict]] = {}
        self.entry = None

    def add_node(self, name, fn): self.nodes[name] = fn
    def add_edge(self, a, b): self.edges[a] = b
    def set_entry_point(self, n): self.entry = n
    def add_conditional_edges(self, a, fn, mapping): self.cond[a] = (fn, mapping)
    def compile(self): return self

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        state, node, steps = dict(state), self.entry, 0
        limit = (config or {}).get("recursion_limit", 100)
        while node != END:
            steps += 1
            if steps > limit:
                raise RuntimeError("recursion limit reached")
            state.update(self.nodes[node](state) or {})
            if node in self.cond:
                fn, mapping = self.cond[node]
                node = mapping[fn(state)]
            else:
                node = self.edges[node]
        return state


SPECIALIST_NODE = {
    ExceptionType.FRAUD_REVIEW.value: "fraud_router",
    ExceptionType.CREDIT_HOLD.value: "credit_agent",
    ExceptionType.PRICING_MISMATCH.value: "pricing_agent",
    ExceptionType.INVENTORY_SHORTFALL.value: "inventory_agent",
    ExceptionType.LATE_DELIVERY_RISK.value: "late_delivery_agent",
}


def build_graph(erp: MockERP, llm: LLMClient, approver: Approver, audit: AuditLog,
                use_langgraph: bool | None = None):
    agents = {"credit_agent": CreditAgent(erp, llm), "inventory_agent": InventoryAgent(erp, llm),
              "late_delivery_agent": LateDeliveryAgent(erp, llm),
              "pricing_agent": PricingAgent(erp, llm), "fraud_router": FraudRouter()}
    proposals: dict[str, Any] = {}  # case_id -> live Proposal object

    def intake(s: CaseState):
        o = erp.read_order(s["order_item_id"])
        q = [e.value for e in detect_exceptions(o)]
        audit.append("intake", s["case_id"], {"order_status": o.order_status, "exceptions": q})
        return {"queue": q, "outcomes": [], "current": None}

    def supervisor(s: CaseState):
        if not s["queue"]:
            return {"route": "done", "current": None}
        cur, rest = s["queue"][0], s["queue"][1:]
        audit.append("route", s["case_id"], {"exception": cur, "to": SPECIALIST_NODE[cur]})
        return {"current": cur, "queue": rest, "route": SPECIALIST_NODE[cur]}

    def make_specialist(name):
        def node(s: CaseState):
            o = erp.read_order(s["order_item_id"])
            p = agents[name].propose(o)
            if p is None:
                audit.append("no_action", s["case_id"], {"agent": name, "exception": s["current"]})
                outs = s["outcomes"] + [{"exception": s["current"], "status": "cleared_on_check"}]
                return {"proposal": None, "outcomes": outs}
            proposals[s["case_id"]] = p
            audit.append("proposal", s["case_id"], p.to_dict())
            return {"proposal": p.to_dict()}
        return node

    def policy_gate(s: CaseState):
        if s.get("proposal") is None:
            return {"route": "supervisor"}
        p = proposals[s["case_id"]]
        r = pol.evaluate(p, erp.read_order(s["order_item_id"]))
        audit.append("policy", s["case_id"], {"decision": r.decision.value, "rules": r.rule_ids,
                                              "reasons": r.reasons, "version": pol.POLICY_VERSION})
        if p.action == ActionType.ESCALATE and r.decision != Decision.DENY:
            route = "escalate"
        else:
            route = {Decision.ALLOW: "execute", Decision.REQUIRE_APPROVAL: "human_review",
                     Decision.DENY: "escalate"}[r.decision]
        return {"policy": {"decision": r.decision.value, "rules": r.rule_ids}, "route": route}

    def human_review(s: CaseState):
        p = proposals[s["case_id"]]
        ok, role, comment = approver.review(p, None)  # type: ignore[arg-type]
        audit.append("approval", s["case_id"], {"approved": ok, "role": role, "comment": comment})
        if ok:
            return {"route": "execute"}
        outs = s["outcomes"] + [{"exception": p.exception.value, "action": p.action.value,
                                 "status": "rejected_by_human", "role": role,
                                 "value_at_stake": p.value_at_stake}]
        return {"route": "supervisor", "outcomes": outs}

    def execute(s: CaseState):
        p = proposals[s["case_id"]]
        t0 = time.perf_counter()
        rec = erp.execute(p, s["order_item_id"])
        audit.append("erp_write", s["case_id"], {"action": p.action.value, "after": rec["after"],
                                                 "ms": round((time.perf_counter() - t0) * 1e3, 3)})
        status = "auto_executed" if s["policy"]["decision"] == "allow" else "executed_after_approval"
        outs = s["outcomes"] + [{"exception": p.exception.value, "action": p.action.value,
                                 "status": status, "value_at_stake": p.value_at_stake}]
        return {"outcomes": outs}

    def escalate(s: CaseState):
        p = proposals[s["case_id"]]
        q = p.params.get("queue") or "exception_desk"
        audit.append("escalation", s["case_id"], {"queue": q, "policy": s["policy"]})
        outs = s["outcomes"] + [{"exception": p.exception.value, "action": "escalate",
                                 "status": "escalated", "queue": q,
                                 "value_at_stake": p.value_at_stake}]
        return {"outcomes": outs}

    def finalize(s: CaseState):
        audit.append("case_closed", s["case_id"], {"outcomes": s["outcomes"]})
        return {}

    lg = HAVE_LANGGRAPH if use_langgraph is None else (use_langgraph and HAVE_LANGGRAPH)
    g = StateGraph(CaseState) if lg else MiniGraph(CaseState)
    end = LG_END if lg else END
    for n, fn in [("intake", intake), ("supervisor", supervisor), ("policy_gate", policy_gate),
                  ("human_review", human_review), ("execute", execute),
                  ("escalate", escalate), ("finalize", finalize)]:
        g.add_node(n, fn)
    for name in agents:
        g.add_node(name, make_specialist(name))
        g.add_edge(name, "policy_gate")
    g.set_entry_point("intake")
    g.add_edge("intake", "supervisor")
    g.add_conditional_edges("supervisor", lambda s: s["route"],
                            {**{a: a for a in agents}, "done": "finalize"})
    g.add_conditional_edges("policy_gate", lambda s: s["route"],
                            {"execute": "execute", "human_review": "human_review",
                             "escalate": "escalate", "supervisor": "supervisor"})
    g.add_conditional_edges("human_review", lambda s: s["route"],
                            {"execute": "execute", "supervisor": "supervisor"})
    g.add_edge("execute", "supervisor")
    g.add_edge("escalate", "supervisor")
    g.add_edge("finalize", end)
    return g.compile(), ("langgraph" if lg else "minigraph")


def run_case(app, order_item_id: int) -> dict:
    return app.invoke({"case_id": f"case-{order_item_id}", "order_item_id": order_item_id},
                      {"recursion_limit": 100})
