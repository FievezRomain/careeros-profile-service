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

OIDC verification is an inbound adapter behind the application-owned `TokenVerifier` port. Experience, Education and Skill mutations use distinct owner-scoped repository ports. Cross-kind confirmation and immutable snapshots have their own application-owned ports and use cases. A separate profile-item reader port merges all V1 kinds into one deterministic page without exposing SQLAlchemy to the application. The SQLAlchemy adapter joins every item operation to the owning profile and filters on both trusted tenant and account identifiers. FastAPI, JWT, SQLAlchemy and Alembic do not cross into the domain or application layers.

## V1 profile API

- `GET /v1/profile/items` lists owned experiences, education items and skills with bounded cross-kind cursor pagination and an optional kind filter.
- `POST /v1/profile/items` creates a validated experience, education item or skill.
- `GET`, `PUT` and `DELETE /v1/profile/items/{itemId}` operate only inside the authenticated ownership scope.
- Every item includes a provenance origin, optional source reference, server timestamp and validation status. Direct entry starts user-confirmed; imported and generated facts require explicit owner confirmation.
- `PUT /v1/profile/items/{itemId}/confirmation` idempotently marks an owned fact as user-confirmed. `PUT` replacement records `userCorrection` provenance server-side.
- `POST /v1/profile/snapshots` atomically creates or replays an immutable point-in-time profile using the required idempotency key. `GET /v1/profile/snapshots/{snapshotId}` reads only an owned snapshot.
- `PUT /v1/profile/search-criteria` activates an owned daily search with target roles, locations, remote policy, contract types, exclusions, threshold, IANA timezone and explicit daily window. `POST` pause/resume transitions create further immutable versions.
- `GET /v1/profile/search-criteria` returns the current owned version, and `GET /v1/profile/search-criteria/versions/{versionId}` preserves owner-scoped historical versions.
- Search mutations require an idempotency key and enqueue `profile.match-relevant-change.v1` with its event ID, schema version, correlation ID and minimum provider-neutral signature.
- Retrieval signatures normalize only roles, locations, remote policy, contract types and exclusions. They contain no threshold, contact data or raw profile facts, and only identical signature hashes are shareable.
- Experience, skill and search-criteria changes enqueue match-relevant events in the same database transaction as the owned mutation. Contact-only and presentation-only dimensions are deliberately excluded by the deterministic change policy.
- `profile:read` protects reads and `profile:write` protects mutations.
- Authentication, authorization, validation and concealed ownership failures use stable problem responses without token or payload details.
- Optional skill levels are exposed only with the derived level source `selfDeclared`; callers cannot claim certification or server-recorded correction provenance.

## Non-goals

This service does not absorb responsibilities owned by another CareerOS service. Cross-service workflows are coordinated through explicit contracts rather than shared databases.

## Security and privacy

Persist the minimum data required, record provenance, define retention, redact logs and use synthetic examples in this public repository.
