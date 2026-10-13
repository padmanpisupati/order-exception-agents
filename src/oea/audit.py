"""Append-only, hash-chained audit log (JSONL). Tampering breaks `verify()`."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.records: list[dict] = []
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

    def append(self, event: str, case_id: str, payload: dict[str, Any]) -> dict:
        prev = self.records[-1]["hash"] if self.records else GENESIS
        body = {"seq": len(self.records), "event": event, "case_id": case_id,
                "payload": payload, "prev_hash": prev}
        body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str)
                                      .encode()).hexdigest()
        self.records.append(body)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(body, default=str) + "\n")
        return body

    def verify(self) -> bool:
        prev = GENESIS
        for r in self.records:
            body = {k: v for k, v in r.items() if k != "hash"}
            if body["prev_hash"] != prev:
                return False
            h = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
            if h != r["hash"]:
                return False
            prev = h
        return True
