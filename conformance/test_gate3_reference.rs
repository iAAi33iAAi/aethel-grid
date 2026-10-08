#[path = "gate3_reference.rs"]
mod gate3;

#[test]
fn qdiv_truncates_toward_zero() {
    assert_eq!(gate3::qdiv(199, 100), 1);
    assert_eq!(gate3::qdiv(-199, 100), -1);
}

#[test]
fn split_is_conservative_for_non_divisible_gross() {
    assert_eq!(gate3::split_transfer(101), (1, 50, 50));
    assert_eq!(gate3::split_transfer(199), (1, 99, 99));
}

#[test]
fn preimage_is_ten_fields_and_digest_matches() {
    let a = "a".repeat(64);
    let b = "b".repeat(64);
    let fields = [
        "7", "alice", "node-001", "199", "1", "99", "99",
        a.as_str(), "2026-10-07T120000Z", b.as_str(),
    ];
    let bytes = gate3::canonical_preimage(&fields).expect("valid preimage");
    assert_eq!(bytes.split(|b| *b == b':').count(), 10);

    let path = std::env::temp_dir().join(format!("aethel-gate3-{}.bin", std::process::id()));
    std::fs::write(&path, &bytes).expect("write temporary digest input");
    let output = std::process::Command::new("sha256sum")
        .arg(&path)
        .output()
        .expect("sha256sum must be available in the CI environment");
    let _ = std::fs::remove_file(&path);
    assert!(output.status.success(), "sha256sum failed");
    let line = String::from_utf8(output.stdout).expect("sha256sum output must be UTF-8");
    let digest = line.split_whitespace().next().expect("digest missing");
    assert_eq!(
        digest,
        "3f8a79aeef1649686b85015a54c78b5b5c1796bef5fbed78fa41df1878d61f35"
    );
}

#[test]
fn timestamp_delimiter_collision_fails_closed() {
    let a = "a".repeat(64);
    let b = "b".repeat(64);
    let fields = [
        "7", "alice", "node-001", "199", "1", "99", "99",
        a.as_str(), "2026-10-07T12:00:00Z", b.as_str(),
    ];
    assert_eq!(
        gate3::canonical_preimage(&fields),
        Err("FIELD_DELIMITER_COLLISION")
    );
}
