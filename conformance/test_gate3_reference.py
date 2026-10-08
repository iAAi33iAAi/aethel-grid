from gate3_reference import canonical_preimage, qdiv, sha256_hex, split_transfer
import pytest


def test_qdiv_truncates_toward_zero():
    assert qdiv(199, 100) == 1
    assert qdiv(-199, 100) == -1


def test_split_non_divisible_gross_is_conservative():
    assert split_transfer(101) == (1, 50, 50)
    assert split_transfer(199) == (1, 99, 99)
    assert sum(split_transfer(199)) == 199


def test_preimage_is_exactly_ten_fields():
    preimage = canonical_preimage(
        "7", "alice", "node-001", 199, 1, 99, 99,
        "a" * 64, "2026-10-07T120000Z", "b" * 64,
    )
    assert len(preimage.decode("utf-8").split(":")) == 10
    assert sha256_hex(preimage) == (
        "3f8a79aeef1649686b85015a54c78b5b5c1796bef5fbed78fa41df1878d61f35"
    )


def test_timestamp_delimiter_collision_fails_closed():
    with pytest.raises(ValueError, match="FIELD_DELIMITER_COLLISION"):
        canonical_preimage(
            "7", "alice", "node-001", 199, 1, 99, 99,
            "a" * 64, "2026-10-07T12:00:00Z", "b" * 64,
        )
