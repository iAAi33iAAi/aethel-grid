# AETHEL Grid

**Deterministic Governance. Verifiable State. Human-Centered Infrastructure.**

AETHEL Grid is an open protocol for building systems where every decision is auditable, every state is reproducible, and no authority is hidden.

---

## What is AETHEL?

AETHEL is an event-sourced protocol. Every action in the system produces an immutable, signed event. State is never stored directly — it is always computed from the history of events.

The entire system reduces to one equation:

```
STATE(G) = fold(topo_order(closure(G)))
```

That is not a simplification. That is the complete runtime semantics.

What it means in plain language:

- Take every event that has ever happened
- Resolve their causal dependencies
- Order them deterministically
- Fold them into current state

Any two nodes that have the same events will compute the same state. There is no ambiguity, no hidden logic, no privileged authority that holds the real version.

---

## Why does it exist?

Most systems treat state as primary and history as secondary.

When you query a database, you get today's value — not the chain of decisions that produced it. When an institution makes a decision, you see the outcome — not the rules that were applied or whether they were followed correctly.

AETHEL inverts this.

History is primary. State is a consequence. Governance is transparent. Safety constraints are enforced structurally, not by trust.

The long-term goal is a common protocol layer for:

- Civic infrastructure and community governance
- Local energy, water, and logistics systems
- Cooperative economic networks
- Physical nodes operating under verifiable rules

The first physical anchor is **Node 001 — Bethel Acres, Oklahoma**.

---

## What works today?

| Component | Status |
|-----------|--------|
| Core algebra — closure, merge, topo_order, fold | Implemented |
| Event model — signed, hashed, canonical JSON | Implemented |
| Safety Kernel — QUIBIDT 4-gate pipeline | Implemented |
| Reference Validator — 7-stage pure function | Implemented |
| Compliance test vectors TV-001 through TV-007 | Implemented |
| Governance constitution engine | Implemented |
| Identity registry — AETHEL_ID | Implemented |
| MANNA economic distribution | Implemented |
| Node 001 physical deployment | In progress |

---

## How do I run it?

```bash
git clone https://github.com/iAAi33iAAi/aethel-grid.git
cd aethel-grid

# TypeScript — Reference Validator + compliance suite
cd sdk/typescript
npm install
npm test

# Python — Core algebra
pip install -e ./00_core
pytest tests/
```

---

## Why should I care?

**If you build infrastructure:**
AETHEL gives you a verifiable audit trail, deterministic state reconstruction, and governance constraints enforced by the protocol — not by policy documents.

**If you fund civic technology:**
The system is designed to operate community infrastructure — energy, logistics, housing, governance — with transparent economics and no extractive intermediary layer.

**If you care about sovereignty:**
Every community that runs a node owns its own history. State is computed locally. No central server holds the authoritative version.

**If you write code:**
The reference validator is a pure function. Any implementation in any language that passes the compliance suite is a conforming AETHEL node.

---

## Repository Structure

```
00_core/       Pure mathematics — closure, merge, topo_order, fold
01_safety/     QUIBIDT Safety Kernel — constitutional firewall
02_governance/ Governance runtime — constitution engine, policy packs
03_identity/   AETHEL_ID registry — universal addressing
04_economics/  MANNA distribution — 84% operations, 15% treasury, 1% community
05_domains/    Reality-to-event adapters — kiosk, logistics, construction
06_colony/     AI reasoning agents — propose only, never define truth
07_observatory/ DAG visualization — unified state projection
08_physical/   Physical infrastructure — Node 001, Bethel Acres
sdk/           TypeScript implementation — event model, validator, state reducer
tests/         Compliance suite — TV-001 through TV-007
docs/          Protocol specification, architecture, contributing guide
```

---

## Roadmap

**Phase 1 — Foundation** (current)
Reference validator, test vectors, compliance suite, safety kernel

**Phase 2 — Multi-language**
TypeScript, Python, Rust conformance across all test vectors

**Phase 3 — Pilot Deployments**
Node 001, construction workflows, logistics, community infrastructure

**Phase 4 — Federated Network**
Multi-node synchronization, distributed governance, cross-domain interoperability

---

## Founder

**John David Taylor Preston**
Founder-Architect | Bethel Acres, Oklahoma | Node 001

---

## License

License selection pending. Contributions, protocol review, and discussion are welcome.
