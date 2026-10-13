# ADR-0004: Hash-chained audit log and compensating actions

**Status:** Accepted

**Context.** Auditors and controllers need to know who or what changed an order, why, and under which policy. They also need a way to reverse a change.

**Decision.** Every step (intake, route, proposal, policy, approval, erp_write, escalation, case_closed) appends a record to a JSONL log. Each record is SHA-256 chained to the previous one, and `verify()` detects tampering. Each ERP write stores before and after snapshots, and `rollback()` applies the compensating restore.

**Consequences.** + The decision trail is ready for SOX-style review, and the same log feeds observability. − Snapshot restore is a simplification. Real ERPs need document-specific reversal transactions, such as re-blocking a delivery or reversing a condition record.
