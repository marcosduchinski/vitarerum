"""Use cases for the Document Templates context.

Commands mutate the catalog (staff-only at the presentation boundary); queries
read it for the public submission screen and the management UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.document_templates.application.ports import (
    Clock,
    DocumentTemplateRepository,
    FileStorage,
)
from app.document_templates.domain.models import (
    DocumentTemplate,
    DocumentTemplateId,
    DocumentTemplateNotFound,
)
from app.shared.kernel import PermissionId, UseType


def _new_id() -> DocumentTemplateId:
    return DocumentTemplateId(str(uuid4()))


def _file_reference(template_id: str, file_name: str) -> str:
    return f"document_templates/{template_id}/{file_name}"


@dataclass(frozen=True, slots=True)
class DownloadedTemplate:
    content: bytes
    file_name: str


# ── Commands ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PublishDocumentTemplateInput:
    use_type: UseType
    title: str
    description: str
    mandatory: bool
    active: bool
    display_order: int
    file_name: str
    content: bytes
    uploaded_by: PermissionId


class PublishDocumentTemplate:
    def __init__(
        self,
        repository: DocumentTemplateRepository,
        file_storage: FileStorage,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._storage = file_storage
        self._clock = clock

    async def execute(
        self, data: PublishDocumentTemplateInput
    ) -> DocumentTemplate:
        template_id = _new_id()
        reference = await self._storage.save(
            data.content, _file_reference(template_id, data.file_name)
        )
        template = DocumentTemplate(
            id=template_id,
            use_type=data.use_type,
            title=data.title,
            description=data.description,
            mandatory=data.mandatory,
            active=data.active,
            display_order=data.display_order,
            file_name=data.file_name,
            file_reference=reference,
            uploaded_by=data.uploaded_by,
            uploaded_at=self._clock.now(),
        )
        # If persistence fails the just-written file would be orphaned; drop it.
        # A commit failure in the caller is cleaned up there (it holds the ref).
        try:
            await self._repo.add(template)
        except Exception:
            await self._storage.delete(reference)
            raise
        return template


@dataclass(frozen=True, slots=True)
class UpdateDocumentTemplateMetadataInput:
    template_id: DocumentTemplateId
    title: str
    description: str
    mandatory: bool
    active: bool
    display_order: int


class UpdateDocumentTemplateMetadata:
    def __init__(self, repository: DocumentTemplateRepository) -> None:
        self._repo = repository

    async def execute(
        self, data: UpdateDocumentTemplateMetadataInput
    ) -> DocumentTemplate:
        template = await self._repo.get_by_id(data.template_id)
        if template is None:
            raise DocumentTemplateNotFound(data.template_id)
        template.update_metadata(
            title=data.title,
            description=data.description,
            mandatory=data.mandatory,
            active=data.active,
            display_order=data.display_order,
        )
        await self._repo.save(template)
        return template


@dataclass(frozen=True, slots=True)
class ReplaceDocumentTemplateFileInput:
    template_id: DocumentTemplateId
    file_name: str
    content: bytes


class ReplaceDocumentTemplateFile:
    def __init__(
        self,
        repository: DocumentTemplateRepository,
        file_storage: FileStorage,
    ) -> None:
        self._repo = repository
        self._storage = file_storage

    async def execute(
        self, data: ReplaceDocumentTemplateFileInput
    ) -> tuple[DocumentTemplate, str]:
        """Returns the updated template and the *previous* file reference. The
        caller deletes the previous file only after it commits, so a failed
        commit never leaves the template pointing at a deleted file."""
        template = await self._repo.get_by_id(data.template_id)
        if template is None:
            raise DocumentTemplateNotFound(data.template_id)
        old_reference = template.file_reference
        new_reference = await self._storage.save(
            data.content, _file_reference(template.id, data.file_name)
        )
        template.replace_file(
            file_name=data.file_name, file_reference=new_reference
        )
        try:
            await self._repo.save(template)
        except Exception:
            if new_reference != old_reference:
                await self._storage.delete(new_reference)
            raise
        return template, old_reference


class DeleteDocumentTemplate:
    def __init__(
        self,
        repository: DocumentTemplateRepository,
        file_storage: FileStorage,
    ) -> None:
        self._repo = repository
        self._storage = file_storage

    async def execute(self, template_id: DocumentTemplateId) -> str:
        """Removes the record and returns its file reference. The caller deletes
        the file only after it commits, so a failed commit never leaves a
        committed record without its file."""
        template = await self._repo.get_by_id(template_id)
        if template is None:
            raise DocumentTemplateNotFound(template_id)
        await self._repo.delete(template_id)
        return template.file_reference


# ── Queries ───────────────────────────────────────────────────────────────────


class ListDocumentTemplates:
    def __init__(self, repository: DocumentTemplateRepository) -> None:
        self._repo = repository

    async def execute(
        self, use_type: UseType | None, active_only: bool
    ) -> list[DocumentTemplate]:
        if active_only:
            if use_type is None:
                raise ValueError("use_type is required for the public listing")
            return await self._repo.list_by_use_type(use_type, active_only=True)
        return await self._repo.list_all(use_type)


class GetDocumentTemplateFile:
    def __init__(
        self,
        repository: DocumentTemplateRepository,
        file_storage: FileStorage,
    ) -> None:
        self._repo = repository
        self._storage = file_storage

    async def execute(
        self, template_id: DocumentTemplateId, active_only: bool = False
    ) -> DownloadedTemplate:
        template = await self._repo.get_by_id(template_id)
        if template is None or (active_only and not template.active):
            raise DocumentTemplateNotFound(template_id)
        content = await self._storage.read(template.file_reference)
        return DownloadedTemplate(content=content, file_name=template.file_name)
