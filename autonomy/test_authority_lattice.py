from pathlib import Path
import json

from autonomy.authority_lattice import AuthorityLattice


def test_model_cannot_execute(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "autonomy/authority_lattice.json").write_text(json.dumps({
        "principals": [
            {
                "principal_id":"model",
                "authority":10,
                "capabilities":["propose"],
                "boundary":"proposal-only"
            }
        ]
    }), encoding="utf-8")
    lattice = AuthorityLattice(tmp_path)
    ok, reason = lattice.authorize("model", "execute")
    assert ok is False
    assert reason == "capability-not-granted"


def test_human_has_final_authority(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "autonomy/authority_lattice.json").write_text(json.dumps({
        "principals": [
            {
                "principal_id":"human",
                "authority":50,
                "capabilities":["human-final","execute"],
                "boundary":"explicit"
            }
        ]
    }), encoding="utf-8")
    ok, reason = AuthorityLattice(tmp_path).authorize("human", "human-final")
    assert ok is True
    assert reason == "authorized"
