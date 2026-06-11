#!/usr/bin/env python
"""Bootstrap and seed the Postgres repository backend."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = BACKEND_ROOT / "src"
for path in (BACKEND_SRC, BACKEND_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def main() -> None:
    from core.settings import get_settings, load_env_files  # noqa: PLC0415
    from infrastructure.repositories.postgres.database import (
        PostgresRepositoryDatabase,  # noqa: PLC0415
    )
    from infrastructure.repositories.postgres.migrations import (
        apply_repository_migrations,  # noqa: PLC0415
    )
    from infrastructure.repositories.postgres.seeding import (
        seed_repository_data,  # noqa: PLC0415
    )

    load_env_files()  # populate os.environ from .env for standalone execution
    settings = get_settings()
    database = PostgresRepositoryDatabase.from_settings(settings)
    apply_repository_migrations(database)
    seed_repository_data(database)

    print(f"Repository schema ready: {database.schema}")


if __name__ == "__main__":
    main()
