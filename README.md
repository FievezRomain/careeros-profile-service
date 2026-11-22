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

## Status

Architecture and security baseline. Functional implementation will be added incrementally with tests and versioned contracts.

## License

Apache-2.0.