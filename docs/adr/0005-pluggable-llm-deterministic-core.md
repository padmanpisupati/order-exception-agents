# ADR-0005: Deterministic decision core behind a pluggable LLM interface

**Status:** Accepted

**Context.** The package has to run offline with no keys, reproducibly, in CI. In production, LLMs add value in triage, rationale drafting, and unstructured inputs such as customer emails, but they should not be the authority behind a write.

**Decision.** Handler functions apply rules to typed tool outputs. The `LLMClient` protocol supplies only rationale text, and `RuleBasedLLM` is the offline stub. A real model can be swapped in without changing the policy, HITL, or audit layers. If more model involvement is wanted, the next step is a *single* LLM with read-only tools behind this interface, not a set of cooperating agents (see ADR-0006).

**Consequences.** + Results are reproducible, so they can serve as a baseline for evals (package 2). + Model risk is contained to explanation and ranking. − Rule-based handlers cover only the exception patterns that are defined.
