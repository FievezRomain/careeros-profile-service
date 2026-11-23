# CareerOS Profile Service â€” service overview

## Responsibility

Professional profiles, verified experience, skills, preferences and consented personal settings.

## Data ownership

The canonical professional profile and provenance of user-supplied facts.

## Interfaces

- Inputs: User-approved profile changes and normalized imports.
- Outputs: Versioned profile snapshots and profile-change events.
- Dependencies: identity service for authorization.

## Contract rules

- APIs and events are versioned.
- Consumers must be idempotent where retries are possible.
- Correlation identifiers are propagated without logging sensitive payloads.
- Authorization and ownership are checked at the service boundary.

## Architecture and startup

Domain and application code depend only on core-owned ports. The HTTP composition root constructs SQLAlchemy persistence and Alembic migration adapters and injects them into application use cases. Migration configuration and revision history remain inside the migration adapter. Application startup applies all pending revisions, verifies every expected head and fails before accepting traffic when the schema cannot be brought current.

## Non-goals

This service does not absorb responsibilities owned by another CareerOS service. Cross-service workflows are coordinated through explicit contracts rather than shared databases.

## Security and privacy

Persist the minimum data required, record provenance, define retention, redact logs and use synthetic examples in this public repository.
