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

The service requires Python 3.14 and `uv` 0.13.9. Run `uv sync --locked --all-groups`, copy `.env.example` to `.env`, then start it with `uv run uvicorn careeros_profile.adapters.http:create_app --factory`. Before accepting traffic, the application injects the adapter-owned migration runner into the startup use case, applies every pending revision and verifies that all migration heads are current. Startup fails if migration execution or verification fails. `DATABASE_URL` must target the logical database owned only by this service; credentials remain environment-managed and are redacted by configuration models.

`GET /health` reports process liveness. `GET /ready` verifies the owned database with a minimal query and returns `503` without connection details when unavailable. These are the only public endpoints in this scaffold, intentionally require no authentication and propagate `X-Correlation-ID` without logging query values.

The domain and application layers do not import FastAPI, SQLAlchemy, JWT or Alembic. Application use cases depend only on authentication, persistence and migration ports and receive them through constructor injection. Concrete OIDC, SQLAlchemy and Alembic implementations are assembled only in `adapters/http.py`. Migration configuration and revisions remain under `adapters/migrations`, so a database adapter can be replaced without moving infrastructure into the core.

`/v1/profile/items` currently exposes the first V1-013 vertical slice: owner-scoped Experience CRUD. Every request requires a validated OIDC bearer token and the appropriate `profile:read` or `profile:write` scope. Tenant and account identifiers come only from verified claims, and every database query applies both ownership dimensions. An absent item and an item owned by another account both return the same `404` problem response. Education and Skill variants follow as additive slices of the same versioned contract.

## Status

Python service with isolated persistence, startup-enforced reversible migrations, authenticated Experience CRUD and automated quality gates.

## License

Apache-2.0.
