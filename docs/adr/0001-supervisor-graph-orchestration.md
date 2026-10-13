# ADR-0001: Supervisor + specialist graph instead of one general agent

**Status:** Superseded by [ADR-0006](0006-governed-workflow-over-multi-agent.md) (2026-10). Kept for the decision history. The supervisor/specialist implementation is preserved at commit `68e5e44`, which is also the version pinned by the eval harness (package 2).

**Context.** Order exceptions belong to different owners: credit control, supply planning, logistics, and pricing. Each has its own data, tolerances, and approvers. One general-purpose agent would merge those responsibilities, make failures hard to attribute, and give a single prompt write access to everything.

**Decision.** A supervisor detects the exceptions, ranks them (fraud > credit > pricing > inventory > logistics), and routes each one to a narrow specialist. Specialists can only read; they return a typed `Proposal`. The workflow is an explicit state graph built with LangGraph `StateGraph`. A dependency-free `MiniGraph` with the same semantics is included, and a test checks that the two engines produce identical outcomes.

**Consequences.** + Each specialist has its own owner, eval set, and rollout flag, which mirrors how ERP process ownership is split. + Paths are deterministic and inspectable. − Exceptions that interact (for example, a credit release that changes ATP priority) are handled one after another, not jointly optimized. Joint optimization is a candidate for package 4.
