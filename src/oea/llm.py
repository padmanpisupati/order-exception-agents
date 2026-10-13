"""Pluggable reasoning interface.

Handler functions call `LLMClient.reason(task, context)` to get a short rationale
string. This is the single optional LLM hook in the workflow: a production variant
could implement it as one LLM-with-tools call (read tools only) for triage or
rationale drafting. It never routes work, spawns sub-agents, or authorizes writes.
`RuleBasedLLM` is a deterministic offline stub (no API keys). Swap in a real
provider by implementing the same Protocol; decisions stay in typed tool calls +
policy, so the model only drafts explanations/ranking, never executes writes.
"""
from __future__ import annotations
from typing import Protocol, Any


class LLMClient(Protocol):
    name: str
    def reason(self, task: str, context: dict[str, Any]) -> str: ...


class RuleBasedLLM:
    name = "rule-based-stub"

    def reason(self, task: str, context: dict[str, Any]) -> str:
        facts = ", ".join(f"{k}={v}" for k, v in sorted(context.items()))
        return f"[{task}] {facts}"
