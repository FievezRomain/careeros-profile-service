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

OIDC verification is an inbound adapter behind the application-owned `TokenVerifier` port. Experience CRUD is coordinated by an application use case behind an owner-scoped repository port. The SQLAlchemy adapter joins every item operation to the owning profile and filters on both the trusted tenant and account identifiers. FastAPI, JWT, SQLAlchemy and Alembic do not cross into the domain or application layers.

## V1 profile API

- `GET /v1/profile/items` lists owned experiences with bounded cursor pagination.
- `POST /v1/profile/items` creates a validated experience.
- `GET`, `PUT` and `DELETE /v1/profile/items/{itemId}` operate only inside the authenticated ownership scope.
- `profile:read` protects reads and `profile:write` protects mutations.
- Authentication, authorization, validation and concealed ownership failures use stable problem responses without token or payload details.

## Non-goals

This service does not absorb responsibilities owned by another CareerOS service. Cross-service workflows are coordinated through explicit contracts rather than shared databases.

## Security and privacy

Persist the minimum data required, record provenance, define retention, redact logs and use synthetic examples in this public repository.
