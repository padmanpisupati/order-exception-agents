# ADR-0003: Human-in-the-loop as a first-class workflow step

**Status:** Accepted

**Context.** Approvals are where automated workflows either earn trust or create rework. Approvers need the proposal, the evidence, and the rule that triggered the review, routed to the role that owns the decision.

**Decision.** `human_review` is a workflow step behind an `Approver` interface. It routes by action (pricing_manager, credit_controller, order_desk_lead). A rejection results in no write and records an outcome. Each approval event is audited with the role and comment. The demo uses a deterministic `SimulatedApprover`. In production the node would map to an ERP workflow inbox or ticket task and use LangGraph interrupt/checkpointing to persist the case while it waits.

**Consequences.** + Approval rate, override rate, and time-to-decision can be measured for each rule, which drives decisions to widen autonomy. − Asynchronous approvals need durable checkpointing. That is not implemented in this reference.
