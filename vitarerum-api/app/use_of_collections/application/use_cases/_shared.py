"""Shared helpers for the Use of Collections use cases.

Id/timestamp minting, reference-number generators and upload path building —
used across the proposal, project, journal and publication modules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.identity.public import Actor
from app.use_of_collections.application.ports import FileStoragePort
from app.use_of_collections.domain.models import (
    Attachment,
    CollectionUseObjectId,
    CollectionUseProject,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _new_id() -> str:
    return str(uuid4())


def _safe_name(file_name: str) -> str:
    """Reduce an uploaded filename to a safe, length-capped basename: strip any
    directory components and keep only filesystem-friendly characters."""
    base = file_name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in base)
    cleaned = cleaned.strip(". ") or "file"
    return cleaned[:120]


def _file_reference(subdir: str, owner_id: str, file_name: str) -> str:
    """Build the relative storage path for an upload: a readable
    ``<category>/<owner-id>/<uuid>_<safe-name>`` under the data directory."""
    return f"{subdir}/{owner_id}/{_new_id()}_{_safe_name(file_name)}"


def _new_reference_number() -> str:
    return f"CUP-{uuid4().hex[:8].upper()}"


def _new_access_log_reference_number() -> str:
    return f"OAL-{uuid4().hex[:8].upper()}"


def _new_occurrence_log_reference_number() -> str:
    return f"OOL-{uuid4().hex[:8].upper()}"


def _new_publication_log_reference_number() -> str:
    return f"PUB-{uuid4().hex[:8].upper()}"


def _actor_email(actor: Actor) -> str:
    return actor.email or f"{actor.id}@unknown.local"


def _validate_collection_use_object(
    project: CollectionUseProject,
    collection_use_object_id: CollectionUseObjectId,
) -> None:
    """An entry may only link to a CollectionUseObject owned by this project."""
    if not any(o.id == collection_use_object_id for o in project.objects):
        raise ValueError(
            f"Collection use object {collection_use_object_id} is not part of "
            "this project"
        )


async def _store_attachment(
    storage: FileStoragePort,
    subdir: str,
    entry_id: str,
    file_content: bytes,
    file_name: str,
    media_type: str,
    note: str | None,
) -> Attachment:
    """Persist an uploaded file and build the Attachment value object.

    The media type is parsed first so an invalid value fails before any file is
    written. Shared by the journal and publication attachment use cases."""
    from app.use_of_collections.domain.enums import MediaType

    parsed_media_type = MediaType(media_type)
    reference = _file_reference(subdir, entry_id, file_name)
    file_reference = await storage.save(file_content, reference)
    return Attachment(
        file_reference=file_reference,
        file_name=file_name,
        media_type=parsed_media_type,
        uploaded_at=_now(),
        note=note,
    )
