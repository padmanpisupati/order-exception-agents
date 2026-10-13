"""Exception detection and deterministic handler functions.

Handlers are plain, read-only functions: each calls ERP *read* tools and returns a
typed `Proposal` (or None when the exception clears on check). They are steps in
one governed workflow, not autonomous agents: they cannot write, route, or call
each other. Only the workflow's execute step writes, and only after the policy
gate (and a human, where policy requires).
"""
from __future__ import annotations

from typing import Callable

from .erp import MockERP
from .llm import LLMClient
from .models import ActionType, ExceptionType, Order, PRIORITY, Proposal

MAX_STD_DISCOUNT = 0.20
PRICE_TOLERANCE = 0.02  # 2% gap between expected and booked total
FASTER_MODE = {"Standard Class": ("Second Class", 2), "Second Class": ("First Class", 1),
               "First Class": ("Same Day", 0)}


def detect_exceptions(o: Order) -> list[ExceptionType]:
    ex: list[ExceptionType] = []
    if o.order_status == "SUSPECTED_FRAUD":
        return [ExceptionType.FRAUD_REVIEW]
    if o.order_status in {"ON_HOLD", "PENDING_PAYMENT", "PAYMENT_REVIEW"}:
        ex.append(ExceptionType.CREDIT_HOLD)
    expected = o.gross * (1 - o.discount_rate)
    if o.discount_rate > MAX_STD_DISCOUNT or (
            expected and abs(expected - o.item_total) / expected > PRICE_TOLERANCE):
        ex.append(ExceptionType.PRICING_MISMATCH)
    if o.quantity >= 3:  # only multi-unit lines are ATP-checked in the demo
        ex.append(ExceptionType.INVENTORY_SHORTFALL)
    if o.late_delivery_risk == 1:
        ex.append(ExceptionType.LATE_DELIVERY_RISK)
    return sorted(ex, key=PRIORITY.get)


Handler = Callable[[Order, MockERP, LLMClient], "Proposal | None"]


def handle_credit_hold(o: Order, erp: MockERP, llm: LLMClient) -> Proposal:
    c = erp.check_credit(o.customer_id)
    ok = c["available"] >= 0 and c["max_overdue_days"] <= 30
    action = ActionType.RELEASE_CREDIT_HOLD if ok else ActionType.ESCALATE
    conf = 0.9 if ok and c["max_overdue_days"] == 0 else (0.75 if ok else 0.6)
    return Proposal(ExceptionType.CREDIT_HOLD, action,
                    {"credit": c, "queue": None if ok else "credit_controller"},
                    llm.reason("credit", {"available": c["available"],
                                          "overdue": c["max_overdue_days"]}),
                    conf, o.item_total, "credit_handler")


def handle_inventory_shortfall(o: Order, erp: MockERP, llm: LLMClient) -> Proposal | None:
    atp = erp.check_atp(o.product_card_id, o.quantity)
    if atp["shortfall"] == 0:
        return None  # no real exception
    if atp["available_now"] > 0:
        action, params = ActionType.SPLIT_SHIPMENT, {
            "ship_now_qty": atp["available_now"], "backorder_qty": atp["shortfall"],
            "backorder_eta_days": atp["next_receipt_in_days"]}
    else:
        action, params = ActionType.RESCHEDULE, {
            "new_days_scheduled": o.days_scheduled + atp["next_receipt_in_days"],
            "delay_days": atp["next_receipt_in_days"]}
    return Proposal(ExceptionType.INVENTORY_SHORTFALL, action, params,
                    llm.reason("atp", {"short": atp["shortfall"],
                                       "eta": atp["next_receipt_in_days"]}),
                    0.85, round(o.unit_price * atp["shortfall"], 2), "inventory_handler")


def handle_late_delivery(o: Order, erp: MockERP, llm: LLMClient) -> Proposal:
    slip = max(1, o.days_real - o.days_scheduled)
    if o.shipping_mode in FASTER_MODE and o.item_total >= 150:
        mode, days = FASTER_MODE[o.shipping_mode]
        return Proposal(ExceptionType.LATE_DELIVERY_RISK, ActionType.UPGRADE_SHIPPING,
                        {"new_mode": mode, "new_days_scheduled": days, "slip_days": slip},
                        llm.reason("expedite", {"slip": slip, "value": o.item_total}),
                        0.8, o.item_total, "late_delivery_handler")
    return Proposal(ExceptionType.LATE_DELIVERY_RISK, ActionType.RESCHEDULE,
                    {"new_days_scheduled": o.days_scheduled + slip, "delay_days": slip,
                     "notify_customer": True},
                    llm.reason("repromise", {"slip": slip}), 0.85, o.item_total,
                    "late_delivery_handler")


def handle_pricing_mismatch(o: Order, erp: MockERP, llm: LLMClient) -> Proposal:
    list_price = erp.list_price(o.product_card_id)
    disc = min(o.discount_rate, MAX_STD_DISCOUNT)
    corrected = round(list_price * o.quantity * (1 - disc), 2)
    leakage = round(corrected - o.item_total, 2)
    return Proposal(ExceptionType.PRICING_MISMATCH, ActionType.PRICE_OVERRIDE_REQUEST,
                    {"booked_total": o.item_total, "corrected_total": corrected,
                     "booked_discount": o.discount_rate, "capped_discount": disc,
                     "leakage": leakage},
                    llm.reason("price", {"leakage": leakage}),
                    0.7, abs(leakage), "pricing_handler")


def handle_fraud(o: Order, erp: MockERP, llm: LLMClient) -> Proposal:
    return Proposal(ExceptionType.FRAUD_REVIEW, ActionType.ESCALATE,
                    {"queue": "fraud_review"}, "Suspected fraud: human-only path.",
                    1.0, o.item_total, "fraud_escalation")


# Static dispatch table: exception type -> handler. No routing decisions are made
# at run time; the order of work is fixed by PRIORITY in detect_exceptions().
HANDLERS: dict[ExceptionType, Handler] = {
    ExceptionType.FRAUD_REVIEW: handle_fraud,
    ExceptionType.CREDIT_HOLD: handle_credit_hold,
    ExceptionType.PRICING_MISMATCH: handle_pricing_mismatch,
    ExceptionType.INVENTORY_SHORTFALL: handle_inventory_shortfall,
    ExceptionType.LATE_DELIVERY_RISK: handle_late_delivery,
}
