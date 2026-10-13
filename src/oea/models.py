"""Typed domain objects shared across agents, tools, policy and audit."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class ExceptionType(str, Enum):
    FRAUD_REVIEW = "fraud_review"          # never automated; always human
    CREDIT_HOLD = "credit_hold"
    PRICING_MISMATCH = "pricing_mismatch"
    INVENTORY_SHORTFALL = "inventory_shortfall"
    LATE_DELIVERY_RISK = "late_delivery_risk"


# Lower number = handled first. Commercial/financial blockers before logistics.
PRIORITY = {
    ExceptionType.FRAUD_REVIEW: 0,
    ExceptionType.CREDIT_HOLD: 1,
    ExceptionType.PRICING_MISMATCH: 2,
    ExceptionType.INVENTORY_SHORTFALL: 3,
    ExceptionType.LATE_DELIVERY_RISK: 4,
}


class ActionType(str, Enum):
    RELEASE_CREDIT_HOLD = "release_credit_hold"
    PRICE_OVERRIDE_REQUEST = "price_override_request"
    SPLIT_SHIPMENT = "split_shipment"
    RESCHEDULE = "reschedule"
    UPGRADE_SHIPPING = "upgrade_shipping"
    ESCALATE = "escalate"                 # no ERP write; routes to a human queue
    CANCEL_ORDER = "cancel_order"         # agents may propose, policy always denies


class Decision(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass
class Order:
    order_id: int
    order_item_id: int
    customer_id: int
    customer_segment: str
    market: str
    order_region: str
    order_status: str
    payment_type: str
    shipping_mode: str
    days_scheduled: int
    days_real: int
    late_delivery_risk: int
    product_card_id: int
    product_name: str
    category_name: str
    unit_price: float
    quantity: int
    discount_rate: float
    item_total: float
    order_date: str

    @property
    def gross(self) -> float:
        return round(self.unit_price * self.quantity, 2)


@dataclass
class Proposal:
    exception: ExceptionType
    action: ActionType
    params: dict[str, Any]
    rationale: str
    confidence: float
    value_at_stake: float
    agent: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["exception"] = self.exception.value
        d["action"] = self.action.value
        return d


@dataclass
class PolicyResult:
    decision: Decision
    rule_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
