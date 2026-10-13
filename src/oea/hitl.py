"""Human-in-the-loop approver interface. Production: a task in a work queue
(ERP workflow inbox, ticketing, chat approval). Demo: a deterministic SIMULATED
approver so runs are reproducible."""
from __future__ import annotations
from typing import Protocol

from .models import ActionType, PolicyResult, Proposal


class Approver(Protocol):
    def review(self, p: Proposal, policy: PolicyResult) -> tuple[bool, str, str]:
        """Returns (approved, approver_role, comment)."""


ROLE = {ActionType.PRICE_OVERRIDE_REQUEST: "pricing_manager",
        ActionType.RELEASE_CREDIT_HOLD: "credit_controller"}


class SimulatedApprover:
    """Approves unless value is very large or price leakage exceeds 30% of booked."""
    def review(self, p: Proposal, policy: PolicyResult):
        role = ROLE.get(p.action, "order_desk_lead")
        if p.value_at_stake > 5000:
            return False, role, "simulated: value too high for desk, send to finance"
        if p.action == ActionType.PRICE_OVERRIDE_REQUEST:
            booked = p.params["booked_total"] or 1
            if abs(p.params["leakage"]) / booked > 0.30:
                return False, role, "simulated: needs commercial review"
        return True, role, "simulated: approved"


class AutoReject:
    def review(self, p, policy):
        return False, "test", "rejected"
