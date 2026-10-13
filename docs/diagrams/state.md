# Case state machine (with human-in-the-loop)

```mermaid
stateDiagram-v2
  [*] --> Intake
  Intake --> Supervisor: exceptions detected and prioritized
  Supervisor --> Specialist: next exception in queue
  Supervisor --> Closed: queue empty
  Specialist --> PolicyGate: proposal
  Specialist --> Supervisor: cleared on check (no action)
  PolicyGate --> Execute: ALLOW
  PolicyGate --> HumanReview: REQUIRE_APPROVAL
  PolicyGate --> Escalated: DENY or escalate proposal
  HumanReview --> Execute: approved
  HumanReview --> Supervisor: rejected (no write)
  Execute --> Supervisor: write + snapshot audited
  Execute --> RolledBack: compensating action
  RolledBack --> Supervisor
  Escalated --> Supervisor
  Closed --> [*]
```
