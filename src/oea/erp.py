"""Mock ERP adapter. Tool interfaces mirror what the workflow (or an optional LLM tool-caller) would call against a real
ERP (order read, credit check, ATP, reschedule/split, price-override request).

Reads are free; writes are only reachable through `execute()`, which the graph
calls *after* the policy gate (and approval when required). Every write returns a
compensating action so it can be rolled back (see ADR-0004).

Credit limits and on-hand stock are NOT in DataCo; they are derived
deterministically from ids here and are explicitly simulated.
"""
from __future__ import annotations
import copy
import hashlib
from typing import Any

from .models import ActionType, Order, Proposal


def _h(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


class MockERP:
    def __init__(self, orders: list[Order]):
        self._orders = {o.order_item_id: copy.deepcopy(o) for o in orders}
        self.write_log: list[dict] = []

    # ---------- read tools ----------
    def read_order(self, order_item_id: int) -> Order:
        return copy.deepcopy(self._orders[order_item_id])

    def check_credit(self, customer_id: int) -> dict:
        limit = 2000 + (_h("limit", customer_id) % 9) * 1000
        exposure = sum(o.item_total for o in self._orders.values()
                       if o.customer_id == customer_id
                       and o.order_status in {"PENDING", "PROCESSING", "PENDING_PAYMENT", "ON_HOLD"})
        overdue_days = [0, 0, 0, 15, 45][_h("overdue", customer_id) % 5]
        return {"customer_id": customer_id, "credit_limit": float(limit),
                "open_exposure": round(exposure, 2),
                "available": round(limit - exposure, 2), "max_overdue_days": overdue_days,
                "simulated": True}

    def check_atp(self, product_card_id: int, qty: int) -> dict:
        on_hand = _h("atp", product_card_id) % 6          # 0..5 units now
        next_receipt_days = 3 + _h("rcpt", product_card_id) % 8
        return {"product_card_id": product_card_id, "requested": qty,
                "available_now": on_hand, "shortfall": max(0, qty - on_hand),
                "next_receipt_in_days": next_receipt_days, "simulated": True}

    def list_price(self, product_card_id: int) -> float:
        return next(o.unit_price for o in self._orders.values()
                    if o.product_card_id == product_card_id)

    # ---------- write tools (gated) ----------
    def execute(self, p: Proposal, order_item_id: int) -> dict:
        o = self._orders[order_item_id]
        before = copy.deepcopy(o)
        a = p.action
        if a == ActionType.RELEASE_CREDIT_HOLD:
            o.order_status = "PROCESSING"
        elif a == ActionType.RESCHEDULE:
            o.days_scheduled = int(p.params["new_days_scheduled"])
        elif a == ActionType.UPGRADE_SHIPPING:
            o.shipping_mode = p.params["new_mode"]
            o.days_scheduled = int(p.params["new_days_scheduled"])
        elif a == ActionType.SPLIT_SHIPMENT:
            o.quantity = int(p.params["ship_now_qty"])
        elif a == ActionType.PRICE_OVERRIDE_REQUEST:
            o.item_total = float(p.params["corrected_total"])
        elif a == ActionType.ESCALATE:
            pass  # routing only
        else:
            raise PermissionError(f"Action {a} is not executable by the ERP adapter")
        rec = {"order_item_id": order_item_id, "action": a.value,
               "before": before.__dict__, "after": copy.deepcopy(o).__dict__}
        self.write_log.append(rec)
        return rec

    def rollback(self, rec: dict) -> None:
        """Compensating action: restore the pre-write snapshot."""
        self._orders[rec["order_item_id"]] = Order(**rec["before"])
