# Agent instructions â€” careeros-profile-service

Read README.md, docs/overview.md and SECURITY.md before changing this repository.

## Required invariants

- Keep this service inside its documented responsibility boundary.
- Never add a secret, token, real CV, real application or personal data.
- Use fictitious fixtures and placeholder environment values only.
- Authenticate every operation and enforce ownership/tenant isolation server-side.
- Document public API or event changes and update contract tests.
- Add or update tests with every behavioral change.
- Do not trigger external messages, applications or destructive actions without explicit user approval at action time.

Consult the central workspace skills for architecture, contracts, events, security, testing and documentation work.

## Code Review Rules

- Domain and application modules may depend only on core-owned types and ports; flag imports of FastAPI, SQLAlchemy, Alembic or concrete adapters.
- Use cases receive ports through constructor injection. Concrete engines, migration runners and adapters are created only in the composition root.
- Migration configuration, revisions and runners belong under the migration adapter, never at repository root. Startup must apply and verify every expected migration head before serving traffic.
