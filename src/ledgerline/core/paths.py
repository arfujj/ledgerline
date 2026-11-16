"""Path guards. The application must never read evaluation ground truth."""

from __future__ import annotations

from pathlib import Path

_FORBIDDEN_NAMES = frozenset({"_answer" + "_key.json"})


class ForbiddenPathError(PermissionError):
    pass


def is_hidden_from_app(path: Path) -> bool:
    """Files/dirs whose name starts with '_' are eval-only and invisible to the app."""
    return any(part.startswith("_") for part in path.parts if part not in (".", ".."))


def guard_read(path: Path) -> Path:
    """Call before opening any data-room file. Raises for eval-only material."""
    if path.name in _FORBIDDEN_NAMES or is_hidden_from_app(path):
        raise ForbiddenPathError(f"Application code may not read eval-only file: {path}")
    return path


def iter_dataroom(root: Path) -> list[Path]:
    """All readable data-room files, skipping eval-only and hidden material."""
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and not is_hidden_from_app(p.relative_to(root))
        and not p.name.startswith(".")
    )
