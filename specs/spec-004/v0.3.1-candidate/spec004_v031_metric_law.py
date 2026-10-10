Q = 1_000_000
T_PROCEED = 100_000
T_REVIEW = 900_000

ROTATION_TABLE = {
    0: (1_000_000, 0), 15: (965_926, 258_819), 30: (866_025, 500_000),
    45: (707_107, 707_107), 60: (500_000, 866_025), 90: (0, 1_000_000),
    180: (-1_000_000, 0), 270: (0, -1_000_000),
}

def qdiv(numerator: int, denominator: int) -> int:
    if denominator == 0:
        raise ZeroDivisionError
    return (abs(numerator) // abs(denominator)) * (
        -1 if (numerator < 0) ^ (denominator < 0) else 1
    )

def derive_state(evidence, density, transform):
    if len(evidence) != 6 or len(density) != 6:
        raise ValueError("six domains required")
    state = []
    for d, e in zip(density, evidence):
        state.extend((d, e))
    if transform == "none":
        return state
    angle = int(transform.rsplit("_", 1)[1])
    c, s = ROTATION_TABLE[angle]
    r, i = state[2], state[3]
    state[2] = qdiv(c*r - s*i, Q)
    state[3] = qdiv(s*r + c*i, Q)
    return state

def compute_u_metric(evidence, density, state):
    v_h = sum(max(Q, abs(e)) + d for e, d in zip(evidence, density))
    a_h = qdiv(v_h, 100)
    delta = sum(abs(state[2*i] - Q) + abs(state[2*i+1] - Q) for i in range(6))
    c = qdiv(delta * Q, v_h)
    u_raw = qdiv(c * (v_h + a_h), v_h)
    u = max(0, min(Q, u_raw))
    return {"V_h": v_h, "A_h": a_h, "delta": delta, "C": c, "u_raw": u_raw, "u_metric": u}

def decision_from_u(u_metric):
    if u_metric <= T_PROCEED:
        return "PROCEED"
    if u_metric <= T_REVIEW:
        return "REVIEW"
    return "BLOCK"
