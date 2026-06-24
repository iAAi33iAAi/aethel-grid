# Node 001 Pilot Plan

**Bethel Acres, Oklahoma -- Genesis Deployment**

---

## Overview

Node 001 is the first physical and operational deployment target for AETHEL Grid.

Located in Bethel Acres, Oklahoma, Node 001 serves as the genesis environment for validating the protocol against real-world events.

The purpose of the pilot is not large-scale deployment.

The purpose is proving that deterministic event governance can successfully model and manage a real operational system -- and that:

```
STATE(G) = fold(topo_order(closure(G)))
```

is sufficient to derive and maintain operational state from real-world activity.

---

## Pilot Objectives

1. Event capture -- physical actions become signed protocol events
2. Event validation -- every event passes the 7-stage reference validator
3. State reconstruction -- current state derived from history, not stored directly
4. Governance workflows -- decisions traceable to authorized events
5. Operational observability -- dashboard shows live DAG state and audit trail

---

## Node 001 Subsystems

| Subsystem | Events Captured | Purpose |
|-----------|----------------|----------|
| Energy | ENERGY_PRODUCED, ENERGY_CONSUMED, METER_READING, BILL_SETTLED | Renewable production + metered distribution |
| Water | METER_READING, UTILITY_EVENT, MAINTENANCE_COMPLETED | Monitored utility operations |
| Greenhouse | MATERIAL_RECEIVED, HARVEST_RECORDED | Agricultural production + traceability |
| Housing | WORK_ORDER_CREATED, INSPECTION_COMPLETED | Community coordination |
| Fabrication | MATERIAL_RELEASED, TASK_COMPLETED, SAFETY_CHECK | Local manufacturing |

---

## Event Flow

```
Physical Action at Node 001
        |
        v
Event Construction (author_id=NODE-001, signed, hashed)
        |
        v
Safety Kernel (QUIBIDT 4-gate validation)
        |
        v
DAG Integration (causal_parents resolved)
        |
        v
Closure Resolution
        |
        v
Topological Ordering
        |
        v
State Fold
        |
        v
Observable State + Audit Trail
```

The resulting state must be reproducible from history alone.
No state is stored directly. Every value is a computed consequence of events.

---

## Success Criteria

### Technical
- Zero state divergence across replay attempts
- Deterministic replay: same events -> same state, every time
- 100% of pilot events pass reference validator
- Complete, unbroken audit trail from genesis event to current state

### Operational
- Real-world event capture running continuously
- Accurate project status visible through observatory dashboard
- Demonstrated reporting for any historical point in time

### Governance
- All governance actions recorded as signed events
- Decisions traceable from proposal -> vote -> execution
- Policy enforcement visible and auditable

---

## Deliverables

### Phase 1 -- Protocol Validation
- Event ingestion pipeline operational
- Reference validator executing on all incoming events
- State reconstruction confirmed against known history

### Phase 2 -- Operational Dashboard
- Live event feed with validation status
- DAG visualization (topology view)
- Current computed state per subsystem
- Full audit trail with search and replay

### Phase 3 -- Pilot Report
- Lessons learned from first real-world deployment
- Performance metrics (event throughput, validation latency, state size)
- Protocol improvements identified
- Deployment patterns for future nodes

---

## Budget Targets

| Tier | Amount | Focus |
|------|--------|-------|
| 1 | $25,000 | Specification freeze, validation tooling, pilot preparation, public demonstration |
| 2 | $100,000 | Full Node 001 deployment, all subsystems instrumented, dashboard live, independent review |
| 3 | $500,000 | Multi-node expansion, federation testing, community onboarding, production readiness |

---

## Timeline

| Milestone | Target | Tier |
|-----------|--------|------|
| Specification freeze | Q3 2026 | 1 |
| Validator tooling complete | Q3 2026 | 1 |
| Node 001 infrastructure online | Q4 2026 | 2 |
| All subsystems instrumented | Q4 2026 | 2 |
| Dashboard operational | Q4 2026 | 2 |
| Pilot report published | Q1 2027 | 2 |
| Node 002 onboarding begins | Q2 2027 | 3 |

---

## Long-Term Vision

Node 001 is the genesis reference node for a broader network of interoperable AETHEL deployments.

Each future node:
- Operates under compatible governance
- Produces events in AETHEL-001 format
- Can independently verify any other node's state
- Retains full sovereignty over its own history

---

## Contact

**John David Taylor Preston** -- Founder-Architect, Node 001
**Repository:** https://github.com/iAAi33iAAi/aethel-grid
