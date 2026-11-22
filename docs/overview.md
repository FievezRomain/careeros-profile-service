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

## Non-goals

This service does not absorb responsibilities owned by another CareerOS service. Cross-service workflows are coordinated through explicit contracts rather than shared databases.

## Security and privacy

Persist the minimum data required, record provenance, define retention, redact logs and use synthetic examples in this public repository.