# ADR-0002: A policy gate, not the agent, authorizes every ERP write

**Status:** Accepted

**Context.** In an ERP, a wrong write (a released hold, a changed price) has financial and audit consequences. Prompt instructions are not a control.

**Decision.** Every proposal goes through `policy.evaluate()`, a set of versioned rules expressed as code. Each rule has a stable id (P-0xx) and returns ALLOW, REQUIRE_APPROVAL, or DENY; the strictest result wins. Hard rules: agents never cancel orders (P-001), fraud cases are human-only (P-002), closed orders are never written (P-003), and price changes always need a pricing approver for segregation of duties (P-010). Soft rules: confidence floor, value limits per action type, maximum automatic delay, and overdue customer balance. As defense in depth, the ERP adapter also refuses non-whitelisted actions.

**Consequences.** + Business users can read and own the autonomy envelope, and widen it as eval evidence builds up. + Every decision lists the rule ids and policy version that applied. − Thresholds need calibration with process owners. The current values are illustrative placeholders.
