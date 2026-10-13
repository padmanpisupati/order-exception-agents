"""Pluggable reasoning interface.

Agents call `LLMClient.reason(task, context)` to get a short rationale string.
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
