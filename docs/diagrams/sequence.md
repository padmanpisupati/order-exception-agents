# Sequence: one order with a credit hold and a pricing mismatch

```mermaid
sequenceDiagram
  autonumber
  participant W as Workflow
  participant HF as Handler functions
  participant G as Policy gate
  participant H as Approver (credit / pricing)
  participant E as ERP adapter
  participant A as Audit log
  W->>E: read_order (status ON_HOLD)
  W->>A: intake + detected [credit_hold, pricing_mismatch] (priority order)
  W->>A: dispatch credit_hold -> handle_credit_hold
  W->>HF: handle_credit_hold(order)
  HF->>E: check_credit(customer)
  E-->>HF: limit, exposure, overdue days
  HF-->>W: Proposal(release_credit_hold, value, confidence)
  W->>G: evaluate(proposal)
  G->>A: decision + rule ids + policy version
  alt within autonomous envelope
    W->>E: release_credit_hold
  else over threshold or overdue balance
    W->>H: approval task
    H-->>W: approve / reject (+role, comment)
    W->>E: write only if approved
  end
  E->>A: erp_write (before/after snapshot)
  W->>HF: handle_pricing_mismatch(order)
  HF->>E: list_price(product)
  HF-->>W: Proposal(price_override_request)
  W->>G: evaluate -> always approval (P-010 segregation of duties)
  W->>H: approval task
  H-->>W: decision
  W->>E: write if approved
  W->>A: case_closed + outcomes
```
