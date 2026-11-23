"""Owner-scoped professional profile item use cases."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from uuid import UUID

from careeros_profile.application.ports.profile import (
    EducationRepository,
    ExperienceRepository,
    ProfileItemPage,
    ProfileItemReader,
    ProfileOwner,
)
from careeros_profile.domain.education import Education
from careeros_profile.domain.experience import Experience, ExperienceDraft
from careeros_profile.domain.profile_item import (
    ProfileItem,
    ProfileItemDraft,
    ProfileItemKind,
)


class ProfileItemNotFound(Exception):
    """The item is absent or outside the authenticated ownership scope."""


class InvalidCursor(ValueError):
    """The opaque pagination cursor is malformed."""


class ManageProfileItems:
    """Coordinate item CRUD through explicit owner-scoped ports."""

    def __init__(
        self,
        reader: ProfileItemReader,
        experiences: ExperienceRepository,
        educations: EducationRepository,
    ) -> None:
        self._reader = reader
        self._experiences = experiences
        self._educations = educations

    def list(
        self,
        owner: ProfileOwner,
        *,
        page_size: int = 25,
        cursor: str | None = None,
        kind: ProfileItemKind | None = None,
    ) -> ProfileItemPage:
        offset = self._decode_cursor(cursor)
        result = self._reader.list(owner, offset=offset, limit=page_size, kind=kind)
        next_cursor = self._encode_cursor(offset + page_size) if result.has_more else None
        return ProfileItemPage(items=result.items, next_cursor=next_cursor)

    def get(self, owner: ProfileOwner, item_id: UUID) -> ProfileItem:
        item = self._reader.get(owner, item_id)
        if item is None:
            raise ProfileItemNotFound
        return item

    def create(self, owner: ProfileOwner, draft: ProfileItemDraft) -> ProfileItem:
        if isinstance(draft, ExperienceDraft):
            return self._experiences.create(owner, draft)
        return self._educations.create(owner, draft)

    def replace(self, owner: ProfileOwner, item_id: UUID, draft: ProfileItemDraft) -> ProfileItem:
        item: Experience | Education | None
        if isinstance(draft, ExperienceDraft):
            item = self._experiences.replace(owner, item_id, draft)
        else:
            item = self._educations.replace(owner, item_id, draft)
        if item is None:
            raise ProfileItemNotFound
        return item

    def delete(self, owner: ProfileOwner, item_id: UUID) -> None:
        item = self.get(owner, item_id)
        deleted = (
            self._experiences.delete(owner, item_id)
            if isinstance(item, Experience)
            else self._educations.delete(owner, item_id)
        )
        if not deleted:
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
        if offset < 0 or ManageProfileItems._encode_cursor(offset) != cursor:
            raise InvalidCursor
        return offset
