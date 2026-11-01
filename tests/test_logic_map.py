"""docs/logic-map.md names real modules: a rename that forgets the map fails here."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "ollama_rename_files"
MAPS = [ROOT / "docs" / "logic-map.md", ROOT / "docs" / "logic-map.ru.md"]


def _module_refs(path: Path) -> list[str]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("Module:")]
    return [ref for line in lines for ref in re.findall(r"`([^`]+)`", line)]


def _exists(ref: str) -> bool:
    # `rename_files` → a .py module; `static/script.js` → a file named as is
    return (PACKAGE / f"{ref}.py").is_file() or (PACKAGE / ref).exists()


def test_every_module_line_points_to_an_existing_module() -> None:
    for path in MAPS:
        refs = _module_refs(path)
        assert refs, f"no Module: lines in {path.name}"
        assert [ref for ref in refs if not _exists(ref)] == [], path.name
