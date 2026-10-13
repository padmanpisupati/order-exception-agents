from dataclasses import replace
from pathlib import Path

import pytest

from oea import policy
from oea.agents import detect_exceptions
from oea.audit import AuditLog
from oea.data import DATACO_COLUMNS, generate_synthetic, load_dataco, read_rows, to_order
from oea.erp import MockERP
from oea.graph import HAVE_LANGGRAPH, build_graph, run_case
from oea.hitl import AutoReject, SimulatedApprover
from oea.llm import RuleBasedLLM
from oea.models import ActionType, Decision, ExceptionType, Proposal

SAMPLE = Path(__file__).resolve().parents[1] / "data/sample/dataco_synthetic_sample.csv"


@pytest.fixture
def base():
    return replace(to_order(generate_synthetic(1, seed=1)[0]), order_status="PROCESSING")


def mk(base, **kw):
    return replace(base, **kw)


def app_for(orders, approver=None, engine=None):
    erp, audit = MockERP(orders), AuditLog()
    app, _ = build_graph(erp, RuleBasedLLM(), approver or SimulatedApprover(), audit,
                         use_langgraph=engine)
    return app, erp, audit


# --- data ---
def test_sample_has_dataco_schema_and_is_labelled_synthetic():
    rows = read_rows(SAMPLE)
    assert set(DATACO_COLUMNS) <= set(rows[0])
    assert all(r["_synthetic"] == "1" for r in rows)


def test_generator_is_deterministic():
    assert generate_synthetic(20, 7) == generate_synthetic(20, 7)


def test_loader_rejects_non_dataco(tmp_path):
    p = tmp_path / "x.csv"; p.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        load_dataco(p)


# --- detection ---
def test_fraud_short_circuits(base):
    o = mk(base, order_status="SUSPECTED_FRAUD", late_delivery_risk=1)
    assert detect_exceptions(o) == [ExceptionType.FRAUD_REVIEW]


def test_priority_ordering(base):
    o = mk(base, order_status="ON_HOLD", late_delivery_risk=1, quantity=1,
           discount_rate=0.25, item_total=round(base.unit_price * 0.75, 2))
    assert detect_exceptions(o) == [ExceptionType.CREDIT_HOLD, ExceptionType.PRICING_MISMATCH,
                                    ExceptionType.LATE_DELIVERY_RISK]


# --- policy gate ---
def _p(action, value=100.0, conf=0.9, exc=ExceptionType.LATE_DELIVERY_RISK, **params):
    return Proposal(exc, action, params, "t", conf, value, "t")


def test_cancel_always_denied(base):
    assert policy.evaluate(_p(ActionType.CANCEL_ORDER), base).decision == Decision.DENY


def test_price_override_always_needs_approval(base):
    r = policy.evaluate(_p(ActionType.PRICE_OVERRIDE_REQUEST, value=1), base)
    assert r.decision == Decision.REQUIRE_APPROVAL and "P-010" in r.rule_ids


def test_value_threshold(base):
    assert policy.evaluate(_p(ActionType.RESCHEDULE, 100), base).decision == Decision.ALLOW
    assert policy.evaluate(_p(ActionType.RESCHEDULE, 9999), base).decision == Decision.REQUIRE_APPROVAL


def test_low_confidence_needs_approval(base):
    assert policy.evaluate(_p(ActionType.RESCHEDULE, conf=0.5), base).decision == Decision.REQUIRE_APPROVAL


def test_no_writes_on_closed_orders(base):
    o = mk(base, order_status="COMPLETE")
    assert policy.evaluate(_p(ActionType.RESCHEDULE), o).decision == Decision.DENY


# --- end-to-end graph ---
def test_fraud_never_writes(base):
    o = mk(base, order_status="SUSPECTED_FRAUD")
    app, erp, audit = app_for([o])
    out = run_case(app, o.order_item_id)
    assert erp.write_log == []
    assert out["outcomes"][0]["status"] == "escalated"


def test_rejected_approval_means_no_write(base):
    o = mk(base, order_status="PROCESSING", quantity=1, late_delivery_risk=0,
           discount_rate=0.25, item_total=round(base.unit_price * 0.75, 2))
    app, erp, audit = app_for([o], approver=AutoReject())
    out = run_case(app, o.order_item_id)
    assert erp.write_log == []
    assert out["outcomes"][0]["status"] == "rejected_by_human"
    assert any(r["event"] == "approval" for r in audit.records)


def test_every_write_preceded_by_policy_event(base):
    orders = load_dataco(SAMPLE)
    app, erp, audit = app_for(orders)
    for o in orders:
        run_case(app, o.order_item_id)
    last_policy = {}
    for r in audit.records:
        if r["event"] == "policy":
            last_policy[r["case_id"]] = r["payload"]["decision"]
        if r["event"] == "erp_write":
            assert last_policy.get(r["case_id"]) in {"allow", "require_approval"}
    assert len(erp.write_log) > 0 and audit.verify()


def test_audit_tamper_detected(base):
    a = AuditLog()
    a.append("x", "c", {"v": 1}); a.append("y", "c", {"v": 2})
    a.records[0]["payload"]["v"] = 99
    assert not a.verify()


def test_rollback_restores_state(base):
    o = mk(base, order_status="PROCESSING")
    erp = MockERP([o])
    rec = erp.execute(_p(ActionType.RESCHEDULE, new_days_scheduled=9), o.order_item_id)
    assert erp.read_order(o.order_item_id).days_scheduled == 9
    erp.rollback(rec)
    assert erp.read_order(o.order_item_id) == o


def test_erp_refuses_cancel(base):
    with pytest.raises(PermissionError):
        MockERP([base]).execute(_p(ActionType.CANCEL_ORDER), base.order_item_id)


@pytest.mark.skipif(not HAVE_LANGGRAPH, reason="langgraph not installed")
def test_langgraph_and_minigraph_agree():
    orders = load_dataco(SAMPLE)
    res = {}
    for eng in (True, False):
        app, _, _ = app_for(orders, engine=eng)
        res[eng] = [run_case(app, o.order_item_id)["outcomes"] for o in orders]
    assert res[True] == res[False]
