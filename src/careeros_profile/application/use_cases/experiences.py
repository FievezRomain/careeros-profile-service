"""Owner-scoped professional experience use cases."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from uuid import UUID

from careeros_profile.application.ports.profile import (
    ExperiencePage,
    ExperienceRepository,
    ProfileOwner,
)
from careeros_profile.domain.experience import Experience, ExperienceDraft


class ProfileItemNotFound(Exception):
    """The item is absent or outside the authenticated ownership scope."""


class InvalidCursor(ValueError):
    """The opaque pagination cursor is malformed."""


class ManageExperiences:
    """Coordinate experience CRUD through an injected persistence port."""

    def __init__(self, repository: ExperienceRepository) -> None:
        self._repository = repository

    def list(
        self, owner: ProfileOwner, *, page_size: int = 25, cursor: str | None = None
    ) -> ExperiencePage:
        offset = self._decode_cursor(cursor)
        result = self._repository.list(owner, offset=offset, limit=page_size)
        next_cursor = self._encode_cursor(offset + page_size) if result.has_more else None
        return ExperiencePage(items=result.items, next_cursor=next_cursor)

    def get(self, owner: ProfileOwner, item_id: UUID) -> Experience:
        item = self._repository.get(owner, item_id)
        if item is None:
            raise ProfileItemNotFound
        return item

    def create(self, owner: ProfileOwner, draft: ExperienceDraft) -> Experience:
        return self._repository.create(owner, draft)

    def replace(self, owner: ProfileOwner, item_id: UUID, draft: ExperienceDraft) -> Experience:
        item = self._repository.replace(owner, item_id, draft)
        if item is None:
            raise ProfileItemNotFound
        return item

    def delete(self, owner: ProfileOwner, item_id: UUID) -> None:
        if not self._repository.delete(owner, item_id):
            raise ProfileItemNotFound

    @staticmethod
    def _encode_cursor(offset: int) -> str:
        return urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            raw = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            offset = int(raw)
        except (Base64Error, UnicodeDecodeError, ValueError):
            raise InvalidCursor from None
        if offset < 0 or ManageExperiences._encode_cursor(offset) != cursor:
            raise InvalidCursor
        return offset
