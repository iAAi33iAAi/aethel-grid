// Minimal Rust i128 reference for SPEC-004 Gate 3.

pub fn qdiv(numerator: i128, denominator: i128) -> i128 {
    assert!(denominator > 0);
    numerator / denominator // Rust signed integer division truncates toward zero.
}

pub fn split_transfer(gross: i128) -> (i128, i128, i128) {
    assert!(gross >= 0);
    let arch = qdiv(gross, 100);
    let remainder = gross - arch;
    let comm = qdiv(remainder, 2);
    let node = remainder - comm;
    assert_eq!(arch + comm + node, gross);
    (arch, comm, node)
}

pub fn canonical_preimage(fields: &[&str]) -> Result<Vec<u8>, &'static str> {
    if fields.len() != 10 {
        return Err("TEN_FIELDS_REQUIRED");
    }
    if fields.iter().any(|field| field.contains(':')) {
        return Err("FIELD_DELIMITER_COLLISION");
    }
    Ok(fields.join(":").into_bytes())
}
