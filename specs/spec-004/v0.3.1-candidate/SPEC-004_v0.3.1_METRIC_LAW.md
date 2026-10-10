# SPEC-004:v0.3.1_METRIC_LAW

Normative replacement for the orphaned SPEC-004 v0.3_RIGOR utility fixtures.

## Integer domain
Q = 1_000_000.
All normative arithmetic is signed integer arithmetic.
Cross-multiplication uses i128.
qdiv is truncation toward zero.
Final u is clamped to [0, Q].

## Six-domain state
S[2i] = density_i
S[2i+1] = evidence_i

Equilibrium for every domain:
E_i = (Q, Q)

## Human-value reference volume
W_i = max(Q, abs(evidence_i)) + density_i
V_h = sum_i W_i
A_h = qdiv(V_h, 100)

## Destabilization metric
delta_i = abs(S[2i] - Q) + abs(S[2i+1] - Q)
Delta = sum_i delta_i
C = qdiv(Delta * Q, V_h)
u_raw = qdiv(C * (V_h + A_h), V_h)
u = clamp(u_raw, 0, Q)

## Decision partition
u <= 100_000        -> PROCEED
100_000 < u <= 900_000 -> REVIEW
u > 900_000         -> BLOCK

The law is a deterministic engineering metric for systemic destabilization.
It is not claimed here as externally validated physical law.

Any change to Q, the state layout, equilibrium, V_h, the 1% factor, qdiv,
the metric equation, or the decision thresholds requires a new SPEC-004 version.
