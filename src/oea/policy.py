"""Policy gate: evaluated before ANY ERP write. Policy-as-code, versioned, and
each rule has an id that lands in the audit log."""
from __future__ import annotations

from .models import ActionType, Decision, ExceptionType, Order, PolicyResult, Proposal

POLICY_VERSION = "2026.10-ref"
AUTO_LIMITS = {  # max value an agent may action without a human
    ActionType.RELEASE_CREDIT_HOLD: 1000.0,
    ActionType.RESCHEDULE: 2500.0,
    ActionType.SPLIT_SHIPMENT: 2500.0,
    ActionType.UPGRADE_SHIPPING: 750.0,
}
MIN_CONFIDENCE = 0.75
MAX_AUTO_DELAY_DAYS = 5


def evaluate(p: Proposal, o: Order) -> PolicyResult:
    r = PolicyResult(Decision.ALLOW)

    def bump(d: Decision, rid: str, why: str):
        order = [Decision.ALLOW, Decision.REQUIRE_APPROVAL, Decision.DENY]
        if order.index(d) > order.index(r.decision):
            r.decision = d
        r.rule_ids.append(rid); r.reasons.append(why)

    if p.action == ActionType.CANCEL_ORDER:
        bump(Decision.DENY, "P-001", "Agents may never cancel orders")
    if p.exception == ExceptionType.FRAUD_REVIEW and p.action != ActionType.ESCALATE:
        bump(Decision.DENY, "P-002", "Fraud cases are human-only")
    if o.order_status in {"CANCELED", "CLOSED", "COMPLETE"} and p.action != ActionType.ESCALATE:
        bump(Decision.DENY, "P-003", f"Order is {o.order_status}; no writes")
    if p.action == ActionType.PRICE_OVERRIDE_REQUEST:
        bump(Decision.REQUIRE_APPROVAL, "P-010", "Price changes always need pricing approval (SoD)")
    if p.confidence < MIN_CONFIDENCE:
        bump(Decision.REQUIRE_APPROVAL, "P-020", f"Confidence {p.confidence} < {MIN_CONFIDENCE}")
    lim = AUTO_LIMITS.get(p.action)
    if lim is not None and p.value_at_stake > lim:
        bump(Decision.REQUIRE_APPROVAL, "P-030", f"Value {p.value_at_stake:.2f} > auto limit {lim}")
    if p.params.get("delay_days", 0) > MAX_AUTO_DELAY_DAYS:
        bump(Decision.REQUIRE_APPROVAL, "P-040", f"Delay > {MAX_AUTO_DELAY_DAYS} days")
    if p.action == ActionType.RELEASE_CREDIT_HOLD and p.params["credit"]["max_overdue_days"] > 0:
        bump(Decision.REQUIRE_APPROVAL, "P-050", "Customer has overdue balance")
    if not r.rule_ids:
        r.rule_ids.append("P-000"); r.reasons.append("Within autonomous envelope")
    return r
