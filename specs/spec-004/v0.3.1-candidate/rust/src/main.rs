use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

const Q: i128 = 1_000_000;
const T_PROCEED: i64 = 100_000;
const T_REVIEW: i64 = 900_000;
const CORPUS: &str = "../golden_corpus.json";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct InputBundle {
    evidence: [i64; 6],
    density: [i64; 6],
    source_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct AuditRecord {
    spec_version: String,
    prev_state_hash: String,
    timestamp: String,
    input_bundle: InputBundle,
    operator: String,
    operator_version: String,
    applied_transforms: Vec<String>,
    result_state: [i64; 12],
    u_metric: i64,
    decision: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Vector {
    id: String,
    audit_record: AuditRecord,
    audit_preimage: String,
    expected_sha256: String,
    derivation: Derivation,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Derivation {
    #[serde(rename = "V_h")]
    v_h: i128,
    #[serde(rename = "A_h")]
    a_h: i128,
    delta: i128,
    #[serde(rename = "C")]
    c: i128,
    u_raw: i128,
}

fn checked_i64(v: i128, label: &str) -> Result<i64, String> {
    i64::try_from(v).map_err(|_| format!("{label}: value outside i64 range"))
}

fn checked_i128(v: Option<i128>, label: &str) -> Result<i128, String> {
    v.ok_or_else(|| format!("{label}: i128 overflow"))
}

/// Signed integer division with truncation toward zero and checked exceptional cases.
fn qdiv(numerator: i128, denominator: i128) -> Result<i128, String> {
    if denominator == 0 {
        return Err("qdiv denominator is zero".into());
    }
    numerator
        .checked_div(denominator)
        .ok_or_else(|| "qdiv overflow (i128::MIN / -1)".into())
}

fn rotation_coefficients(angle: i32) -> Result<(i128, i128), String> {
    let pair = match angle {
        0 => (1_000_000, 0),
        15 => (965_926, 258_819),
        30 => (866_025, 500_000),
        45 => (707_107, 707_107),
        60 => (500_000, 866_025),
        90 => (0, 1_000_000),
        180 => (-1_000_000, 0),
        270 => (0, -1_000_000),
        _ => return Err(format!("unsupported transform angle: {angle}")),
    };
    Ok(pair)
}

fn validate_inputs(input: &InputBundle) -> Result<(), String> {
    if input.source_id.is_empty() {
        return Err("source_id must not be empty".into());
    }
    for (i, e) in input.evidence.iter().enumerate() {
        if *e < 0 {
            return Err(format!("evidence[{i}] must be nonnegative"));
        }
    }
    for (i, d) in input.density.iter().enumerate() {
        if *d < 0 || *d as i128 > Q {
            return Err(format!("density[{i}] must be within [0,Q]"));
        }
    }
    Ok(())
}

fn derive_result_state(record: &AuditRecord) -> Result<[i64; 12], String> {
    validate_inputs(&record.input_bundle)?;
    let mut state = [0_i64; 12];

    for i in 0..6 {
        state[2 * i] = record.input_bundle.density[i];
        state[2 * i + 1] = record.input_bundle.evidence[i];
    }

    match record.applied_transforms.as_slice() {
        [only] if only == "none" => return Ok(state),
        [name] => {
            let angle_text = name
                .strip_prefix("rotate_d1_")
                .ok_or_else(|| format!("unsupported transform: {name}"))?;
            if angle_text.is_empty() || !angle_text.bytes().all(|b| b.is_ascii_digit()) {
                return Err(format!("invalid canonical rotation angle: {name}"));
            }
            let angle: i32 = angle_text.parse().map_err(|_| "invalid rotation angle")?;
            if angle.to_string() != angle_text {
                return Err(format!("noncanonical rotation angle: {name}"));
            }
            let (c, s) = rotation_coefficients(angle)?;
            let real = state[2] as i128;
            let imag = state[3] as i128;
            let real_num = checked_i128(
                c.checked_mul(real).and_then(|x| s.checked_mul(imag).and_then(|y| x.checked_sub(y))),
                "rotation real numerator",
            )?;
            let imag_num = checked_i128(
                s.checked_mul(real).and_then(|x| c.checked_mul(imag).and_then(|y| x.checked_add(y))),
                "rotation imaginary numerator",
            )?;
            state[2] = checked_i64(qdiv(real_num, Q)?, "rotated density")?;
            state[3] = checked_i64(qdiv(imag_num, Q)?, "rotated evidence")?;
            Ok(state)
        }
        _ => Err("candidate law requires exactly one transform entry".into()),
    }
}

fn compute_metric(
    input: &InputBundle,
    state: &[i64; 12],
) -> Result<(i64, Derivation), String> {
    validate_inputs(input)?;

    let mut v_h: i128 = 0;
    for i in 0..6 {
        let evidence = input.evidence[i] as i128;
        let density = input.density[i] as i128;
        let w = std::cmp::max(Q, evidence.checked_abs().ok_or("abs(evidence) overflow")?)
            .checked_add(density)
            .ok_or("W_i overflow")?;
        v_h = checked_i128(v_h.checked_add(w), "V_h accumulation")?;
    }
    if v_h <= 0 {
        return Err("V_h must be positive".into());
    }

    let a_h = qdiv(v_h, 100)?;
    let mut delta: i128 = 0;
    for i in 0..6 {
        let d = (state[2 * i] as i128)
            .checked_sub(Q)
            .and_then(i128::checked_abs)
            .ok_or("density deviation overflow")?;
        let e = (state[2 * i + 1] as i128)
            .checked_sub(Q)
            .and_then(i128::checked_abs)
            .ok_or("evidence deviation overflow")?;
        delta = checked_i128(delta.checked_add(d).and_then(|x| x.checked_add(e)), "Delta accumulation")?;
    }

    let c_num = checked_i128(delta.checked_mul(Q), "Delta * Q")?;
    let c = qdiv(c_num, v_h)?;
    let adjusted_v_h = checked_i128(v_h.checked_add(a_h), "V_h + A_h")?;
    let raw_num = checked_i128(c.checked_mul(adjusted_v_h), "C * (V_h + A_h)")?;
    let u_raw = qdiv(raw_num, v_h)?;
    let u = u_raw.clamp(0, Q);

    let derivation = Derivation {
        v_h,
        a_h,
        delta,
        c,
        u_raw,
    };
    Ok((checked_i64(u, "u_metric")?, derivation))
}

fn decision_from_u(u: i64) -> Result<&'static str, String> {
    if !(0..=Q as i64).contains(&u) {
        return Err("u_metric must be within [0,Q]".into());
    }
    Ok(if u <= T_PROCEED {
        "PROCEED"
    } else if u <= T_REVIEW {
        "REVIEW"
    } else {
        "BLOCK"
    })
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn corpus_path() -> std::path::PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join(CORPUS)
}

fn load_corpus() -> Result<Vec<Vector>, String> {
    let text = fs::read_to_string(corpus_path()).map_err(|e| format!("read corpus: {e}"))?;
    serde_json::from_str(&text).map_err(|e| format!("parse corpus: {e}"))
}

fn verify_vector(v: &Vector) -> Result<(), String> {
    let state = derive_result_state(&v.audit_record)
        .map_err(|e| format!("{}: {e}", v.id))?;
    if state != v.audit_record.result_state {
        return Err(format!("{}: result_state mismatch", v.id));
    }

    let (metric, derivation) = compute_metric(&v.audit_record.input_bundle, &state)
        .map_err(|e| format!("{}: {e}", v.id))?;
    if metric != v.audit_record.u_metric {
        return Err(format!("{}: u_metric mismatch: computed {metric}, stored {}", v.id, v.audit_record.u_metric));
    }
    if derivation != v.derivation {
        return Err(format!("{}: metric derivation mismatch: computed {derivation:?}, stored {:?}", v.id, v.derivation));
    }
    let decision = decision_from_u(metric).map_err(|e| format!("{}: {e}", v.id))?;
    if decision != v.audit_record.decision {
        return Err(format!("{}: decision mismatch", v.id));
    }

    // Struct field declaration order is the candidate canonical JSON order.
    let preimage = serde_json::to_string(&v.audit_record)
        .map_err(|e| format!("{}: serialize audit: {e}", v.id))?;
    if preimage.as_bytes() != v.audit_preimage.as_bytes() {
        return Err(format!("{}: canonical audit preimage mismatch", v.id));
    }
    let digest = sha256_hex(preimage.as_bytes());
    if digest != v.expected_sha256 {
        return Err(format!("{}: SHA-256 mismatch: computed {digest}", v.id));
    }

    println!("{:<16} PASS metric={} decision={} sha256={}", v.id, metric, decision, digest);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_four_vectors_are_derived_from_raw_inputs() {
        let corpus = load_corpus().expect("candidate corpus must parse");
        assert_eq!(corpus.len(), 4);
        for vector in &corpus {
            verify_vector(vector).unwrap_or_else(|e| panic!("{e}"));
        }
    }

    #[test]
    fn decision_boundaries_are_exact() {
        assert_eq!(decision_from_u(0).unwrap(), "PROCEED");
        assert_eq!(decision_from_u(100_000).unwrap(), "PROCEED");
        assert_eq!(decision_from_u(100_001).unwrap(), "REVIEW");
        assert_eq!(decision_from_u(900_000).unwrap(), "REVIEW");
        assert_eq!(decision_from_u(900_001).unwrap(), "BLOCK");
        assert_eq!(decision_from_u(1_000_000).unwrap(), "BLOCK");
        assert!(decision_from_u(-1).is_err());
        assert!(decision_from_u(1_000_001).is_err());
    }

    #[test]
    fn qdiv_is_signed_truncation_toward_zero_and_checked() {
        assert_eq!(qdiv(-10, 3).unwrap(), -3);
        assert_eq!(qdiv(10, -3).unwrap(), -3);
        assert_eq!(qdiv(-10, -3).unwrap(), 3);
        assert_eq!(qdiv(1, 3).unwrap(), 0);
        assert_eq!(qdiv(-1, 3).unwrap(), 0);
        assert!(qdiv(1, 0).is_err());
        assert!(qdiv(i128::MIN, -1).is_err());
    }

    #[test]
    fn invalid_domains_and_transforms_fail_closed() {
        let mut vector = load_corpus().unwrap().remove(0);
        vector.audit_record.input_bundle.density[0] = -1;
        assert!(derive_result_state(&vector.audit_record).is_err());

        let mut vector = load_corpus().unwrap().remove(0);
        vector.audit_record.applied_transforms = vec![];
        assert!(derive_result_state(&vector.audit_record).is_err());

        let mut vector = load_corpus().unwrap().remove(0);
        vector.audit_record.applied_transforms = vec!["rotate_d1_17".into()];
        assert!(derive_result_state(&vector.audit_record).is_err());

        let mut vector = load_corpus().unwrap().remove(0);
        vector.audit_record.applied_transforms = vec!["rotate_d1_015".into()];
        assert!(derive_result_state(&vector.audit_record).is_err());
    }

    #[test]
    fn large_i64_evidence_uses_i128_metric_intermediates() {
        let input = InputBundle {
            evidence: [i64::MAX; 6],
            density: [Q as i64; 6],
            source_id: "i64-max-boundary".into(),
        };
        let mut state = [0_i64; 12];
        for i in 0..6 {
            state[2 * i] = Q as i64;
            state[2 * i + 1] = i64::MAX;
        }

        let (metric, derivation) = compute_metric(&input, &state).unwrap();
        assert_eq!(metric, Q as i64);
        assert_eq!(derivation, Derivation {
            v_h: 55340232221134654842_i128,
            a_h: 553402322211346548_i128,
            delta: 55340232221122654842_i128,
            c: 999999_i128,
            u_raw: 1009998_i128,
        });
    }

    #[test]
    fn unknown_fields_are_rejected_on_corpus_structures() {
        assert!(serde_json::from_str::<InputBundle>(
            r#"{"evidence":[1,1,1,1,1,1],"density":[1,1,1,1,1,1],"source_id":"s","unexpected":1}"#
        ).is_err());
    }
}

fn main() {
    let corpus = load_corpus().unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(corpus.len(), 4, "candidate corpus must contain exactly four vectors");
    for vector in &corpus {
        verify_vector(vector).unwrap_or_else(|e| panic!("{e}"));
    }
}
