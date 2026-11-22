# CareerOS Profile Service

Professional profiles, verified experience, skills, preferences and consented personal settings.

## Scope

- **Owns:** The canonical professional profile and provenance of user-supplied facts.
- **Inputs:** User-approved profile changes and normalized imports.
- **Outputs:** Versioned profile snapshots and profile-change events.
- **Dependencies:** identity service for authorization.

## Safety baseline

This public repository must never contain secrets, real resumes, real applications or personal data. External communication and application submission always require explicit user approval.

## Documentation

See [docs/overview.md](docs/overview.md) and the central [CareerOS workspace](https://github.com/FievezRomain/careeros-workspace).

## Local development

The service requires Python 3.14 and `uv` 0.13.9. Run `uv sync --locked --all-groups`, copy `.env.example` to `.env`, then use `uv run alembic upgrade head` before starting `uv run uvicorn careeros_profile.adapters.http:create_app --factory`. `DATABASE_URL` must target the logical database owned only by this service; credentials remain environment-managed and are redacted by configuration models.

`GET /health` reports process liveness. `GET /ready` verifies the owned database with a minimal query and returns `503` without connection details when unavailable. These are the only public endpoints in this scaffold, intentionally require no authentication and propagate `X-Correlation-ID` without logging query values.

The domain and application layers do not import FastAPI, SQLAlchemy or Alembic. The application owns the persistence readiness port; SQLAlchemy and the initial reversible migration remain outbound adapter concerns. The initial `profiles` table stores only opaque identifiers and creation time. Profile CRUD and public business contracts are deferred to V1-013.

## Status

Python service scaffold with isolated persistence, reversible migrations and automated quality gates. Functional profile behavior will be added incrementally with tests and versioned contracts.

## License

Apache-2.0.
