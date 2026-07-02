"""SQLAlchemy adapter for the document template repository."""

from __future__ import annotations

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_templates.domain.models import (
    DocumentTemplate,
    DocumentTemplateId,
)
from app.document_templates.infrastructure.models import DocumentTemplateRecord
from app.shared.kernel import PermissionId, UseType


def _to_domain(record: DocumentTemplateRecord) -> DocumentTemplate:
    return DocumentTemplate(
        id=DocumentTemplateId(record.id),
        use_type=UseType(record.use_type),
        title=record.title,
        description=record.description,
        mandatory=record.mandatory,
        active=record.active,
        display_order=record.display_order,
        file_name=record.file_name,
        file_reference=record.file_reference,
        uploaded_by=PermissionId(record.uploaded_by),
        uploaded_at=record.uploaded_at,
    )


def _apply(record: DocumentTemplateRecord, t: DocumentTemplate) -> None:
    record.id = t.id
    record.use_type = t.use_type.value
    record.title = t.title
    record.description = t.description
    record.mandatory = t.mandatory
    record.active = t.active
    record.display_order = t.display_order
    record.file_name = t.file_name
    record.file_reference = t.file_reference
    record.uploaded_by = t.uploaded_by
    record.uploaded_at = t.uploaded_at


class SqlAlchemyDocumentTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, template: DocumentTemplate) -> None:
        record = DocumentTemplateRecord()
        _apply(record, template)
        self._session.add(record)
        await self._session.flush()

    async def get_by_id(
        self, template_id: DocumentTemplateId
    ) -> DocumentTemplate | None:
        record = await self._session.get(DocumentTemplateRecord, template_id)
        return _to_domain(record) if record is not None else None

    async def list_by_use_type(
        self, use_type: UseType, active_only: bool
    ) -> list[DocumentTemplate]:
        stmt = select(DocumentTemplateRecord).where(
            DocumentTemplateRecord.use_type == use_type.value
        )
        if active_only:
            stmt = stmt.where(DocumentTemplateRecord.active.is_(True))
        stmt = stmt.order_by(
            DocumentTemplateRecord.display_order, DocumentTemplateRecord.title
        )
        result = await self._session.execute(stmt)
        return [_to_domain(record) for record in result.scalars().all()]

    async def list_all(
        self, use_type: UseType | None
    ) -> list[DocumentTemplate]:
        stmt = select(DocumentTemplateRecord)
        if use_type is not None:
            stmt = stmt.where(DocumentTemplateRecord.use_type == use_type.value)
        stmt = stmt.order_by(
            DocumentTemplateRecord.use_type,
            DocumentTemplateRecord.display_order,
            DocumentTemplateRecord.title,
        )
        result = await self._session.execute(stmt)
        return [_to_domain(record) for record in result.scalars().all()]

    async def save(self, template: DocumentTemplate) -> None:
        record = await self._session.get(DocumentTemplateRecord, template.id)
        if record is None:
            raise LookupError(f"No document template with id {template.id}")
        _apply(record, template)
        await self._session.flush()

    async def delete(self, template_id: DocumentTemplateId) -> None:
        await self._session.execute(
            sa_delete(DocumentTemplateRecord).where(
                DocumentTemplateRecord.id == template_id
            )
        )
        await self._session.flush()
