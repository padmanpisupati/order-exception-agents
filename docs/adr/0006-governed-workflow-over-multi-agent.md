# ADR-0006: A deterministic governed workflow instead of a supervisor plus specialist agents

**Status:** Accepted (2026-10). Supersedes [ADR-0001](0001-supervisor-graph-orchestration.md).

**Context.** Version 0.1 used a supervisor that routed each exception to a specialist "agent" (credit, inventory, late delivery, pricing, fraud). Looking at how that version actually ran:
- **The specialists shared one context.** Every one of them read the same order line and the same handful of ERP lookups. None needed its own memory, planning loop, or conversation, so they were functions in all but name.
- **The supervisor had nothing to decide.** It routed by a fixed priority table (fraud > credit > pricing > inventory > logistics). A component that only looks things up in a table is a `for` loop, and calling it an agent overstated the autonomy and the risk.
- **Coordination costs more than it returns.** In a real LLM deployment, a supervisor plus agents adds model calls per case, hand-off prompts, state passing, and new ways to fail (bad routing, loops, agents disagreeing). For order exceptions, which are mostly rule-bound, that spends cost and latency without improving decisions.
- **Determinism is a control requirement.** Auditors and the eval harness both need the same input to give the same path and the same writes. A fixed workflow makes that true by construction.

**Decision.** The primary path is one deterministic workflow:

`intake/detect → for each exception in priority order: handler → policy gate → (HITL if required) → execute or escalate → audit → close case`

- Exception logic lives in plain, read-only **handler functions** (`handlers.py`) selected through a static `HANDLERS` table. They return a typed `Proposal` and cannot write.
- `next_exception` is a cursor over the prioritized list. It makes no judgement calls.
- The policy gate, HITL step, ERP whitelist, and hash-chained audit are unchanged (ADR-0002 to ADR-0004).
- LangGraph stays as an **optional** engine for this workflow. The dependency-free `MiniGraph` runner is the fallback, and a parity test checks that both engines give identical outcomes.
- The only LLM touchpoint is the optional `LLMClient` hook (ADR-0005). If more model involvement is needed, it would be a single LLM with read-only tools behind that hook, not cooperating agents.
- Handlers that need slow reads (credit bureau, ATP) can run as **parallel read-only context steps** before the gate without changing the control flow. That isn't needed at reference scale.

**Triggers that would justify going multi-agent later** (any one of these, backed by eval evidence):
1. **Context that really diverges.** A domain needs its own large, unstructured context (contracts, carrier emails, customer correspondence) that would crowd out a shared prompt.
2. **Open-ended, multi-step reasoning.** Resolution needs planning and tool exploration that a fixed handler can't express, for example negotiating a substitute with supply planning across several plants.
3. **Joint optimization across exceptions.** Interacting exceptions (a credit release that changes ATP allocation) need agents to negotiate a plan, and the eval harness shows the sequential workflow losing measurable value.
4. **Separate ownership and release cadence.** Different teams must own, deploy, and evaluate parts independently, so a module boundary is no longer enough.
5. **A measured gap.** Package 2's harness shows a multi-agent variant beats this workflow on accuracy or value recovered by more than its added cost, latency, and guardrail risk.

Even then, multi-agent would sit *inside* the same policy gate, HITL, and audit boundary. Agents would propose; they would never write.

**Consequences.**
+ Fewer moving parts. In an LLM deployment that means at most one model call per case instead of a router call plus one per specialist, so lower cost and latency.
+ The same input always takes the same path and makes the same writes, which makes audit replay and regression evals simple.
+ The governance story is easier to explain: there is exactly one place where writes can happen.
+ Demo outcomes are identical to v0.1: same 212 outcomes, 176 writes, and 1,094 audit records.
− Exceptions are still handled one after another, not jointly optimized. Trigger 3 covers this.
− The eval harness (package 2) still pins v0.1 at commit `68e5e44`. Its metrics hold because outcomes are identical, but its vendored code still uses the old naming.
