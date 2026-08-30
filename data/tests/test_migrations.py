"""Regression checks for Alembic migration history."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


VERSIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations" / "versions"


def test_all_migration_modules_import_without_current_domain_models() -> None:
    migration_files = sorted(VERSIONS_DIR.glob("*.py"))
    assert migration_files, "no Alembic migration files found"

    for path in migration_files:
        spec = spec_from_file_location(f"migration_{path.stem}", path)
        assert spec is not None and spec.loader is not None
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        assert getattr(module, "revision", None), f"missing revision in {path.name}"
