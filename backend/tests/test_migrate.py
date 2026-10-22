import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("migrate", ROOT / "deploy/scripts/migrate.py")


def _load():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def test_pending_versions_filters_applied_and_sorts(tmp_path):
    (tmp_path / "002_second.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("SELECT 1;", encoding="utf-8")

    pending = _load().pending_versions(tmp_path, {"002_second"})

    assert [path.name for path in pending] == ["001_first.sql", "003_third.sql"]
