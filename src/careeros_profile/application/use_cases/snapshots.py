"""Owner-scoped immutable profile snapshot use cases."""

from hashlib import sha256
from uuid import UUID

from careeros_profile.application.ports.profile import (
    ProfileOwner,
    ProfileSnapshotRepository,
)
from careeros_profile.domain.snapshot import ProfileSnapshot


class ProfileSnapshotNotFound(Exception):
    """The snapshot is absent or outside the authenticated ownership scope."""


class IdempotencyKeyConflict(Exception):
    """The key was already used for a different effective request."""


class ManageProfileSnapshots:
    """Coordinate immutable snapshots without exposing persistence technology."""

    _EMPTY_REQUEST_FINGERPRINT = sha256(b"{}").hexdigest()

    def __init__(self, snapshots: ProfileSnapshotRepository) -> None:
        self._snapshots = snapshots

    def create(self, owner: ProfileOwner, idempotency_key: str) -> ProfileSnapshot:
        result = self._snapshots.create(
            owner,
            idempotency_key=idempotency_key,
            request_fingerprint=self._EMPTY_REQUEST_FINGERPRINT,
        )
        if result.outcome == "conflict":
            raise IdempotencyKeyConflict
        if result.snapshot is None:
            raise RuntimeError("snapshot repository returned no snapshot")
        return result.snapshot

    def get(self, owner: ProfileOwner, snapshot_id: UUID) -> ProfileSnapshot:
        snapshot = self._snapshots.get(owner, snapshot_id)
        if snapshot is None:
            raise ProfileSnapshotNotFound
        return snapshot
