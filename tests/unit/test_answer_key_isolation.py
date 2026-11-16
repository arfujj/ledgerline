"""The app must never read the answer key. Only evals/ may."""

from pathlib import Path

import pytest

from ledgerline.core.paths import ForbiddenPathError, guard_read, iter_dataroom

SRC = Path(__file__).resolve().parents[2] / "src"


def test_no_source_reference_to_answer_key() -> None:
    needle = "_answer" + "_key"
    offenders = [p for p in SRC.rglob("*.py") if needle in p.read_text(encoding="utf-8")]
    assert offenders == [], f"App code references the answer key: {offenders}"


def test_guard_read_blocks(tmp_path: Path) -> None:
    with pytest.raises(ForbiddenPathError):
        guard_read(tmp_path / ("_answer" + "_key.json"))
    with pytest.raises(ForbiddenPathError):
        guard_read(Path("_private/x.md"))
    assert guard_read(Path("policies/aml.md")) == Path("policies/aml.md")


def test_iter_dataroom_skips_eval_files(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "aml.md").write_text("x")
    (tmp_path / ("_answer" + "_key.json")).write_text("{}")
    (tmp_path / "_eval").mkdir()
    (tmp_path / "_eval" / "y.md").write_text("y")
    (tmp_path / ".DS_Store").write_text("")
    assert [p.name for p in iter_dataroom(tmp_path)] == ["aml.md"]
