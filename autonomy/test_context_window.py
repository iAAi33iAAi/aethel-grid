from pathlib import Path

from autonomy.context_window import ContextWindow


def test_context_window_excludes_secret_and_generated_files(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules/pkg").mkdir(parents=True)
    (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
    (tmp_path / "src/main.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "node_modules/pkg/a.py").write_text("print('generated')", encoding="utf-8")

    result = ContextWindow(tmp_path).build()
    paths = {item["path"] for item in result["files"]}
    assert "src/main.py" in paths
    assert ".env" not in paths
    assert "node_modules/pkg/a.py" not in paths
    assert len(result["context_digest"]) == 64
