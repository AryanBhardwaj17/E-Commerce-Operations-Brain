E-Commerce Operations Brain backend package.

Repository storage backends:
- `REPOSITORY_BACKEND=postgres` is the default live backend. It bootstraps a schema in Postgres, seeds it from `src/data/seeds/application/`, and persists business data there.
- `REPOSITORY_BACKEND=mock` remains available as an explicit fallback for tests and offline-only work.

Seed data note:
- `src/data/seeds/application/` contains deterministic JSON seed fixtures. Those files are bootstrap input, not live operational storage.

Useful command:
- `python backend/scripts/seed_postgres.py` bootstraps the repository schema and seed data in the configured Postgres database.