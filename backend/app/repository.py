from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select

from app.db import Database
from app.models import DocumentRecord, ElementRecord
from app.schemas import (
    BoundingBox,
    ElementType,
    Evidence,
    ParsedDocument,
    ParsedElement,
    RetrievedChunk,
)


class DocumentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def list_documents(self) -> list[dict[str, object]]:
        async with self.database.session() as session:
            rows = (
                await session.scalars(select(DocumentRecord).order_by(DocumentRecord.created_at))
            ).all()
            return [
                {
                    "id": row.id,
                    "title": row.title,
                    "filename": row.filename,
                    "page_count": row.page_count,
                    "status": row.status,
                    "sha256": row.sha256,
                }
                for row in rows
            ]

    async def get_document(self, document_id: str) -> DocumentRecord | None:
        async with self.database.session() as session:
            return await session.get(DocumentRecord, document_id)

    async def load_parsed(self, document_id: str) -> ParsedDocument | None:
        async with self.database.session() as session:
            document = await session.get(DocumentRecord, document_id)
            if document is None:
                return None
            rows = (
                await session.scalars(
                    select(ElementRecord)
                    .where(ElementRecord.document_id == document_id)
                    .order_by(ElementRecord.page, ElementRecord.id)
                )
            ).all()
            return ParsedDocument(
                id=document.id,
                filename=document.filename,
                sha256=document.sha256,
                source_path=document.source_path,
                title=document.title,
                page_count=document.page_count,
                metadata=document.document_metadata,
                elements=[
                    ParsedElement(
                        id=row.id,
                        element_type=ElementType(row.element_type),
                        page=row.page,
                        section=row.section,
                        content=row.content,
                        structured=row.structured,
                        bbox=BoundingBox.model_validate(row.bbox) if row.bbox else None,
                        parent_id=row.parent_id,
                    )
                    for row in rows
                ],
            )

    async def matching_ready_document(
        self, sha256: str, parser_version: str, chunker_version: str
    ) -> DocumentRecord | None:
        async with self.database.session() as session:
            return await session.scalar(
                select(DocumentRecord).where(
                    DocumentRecord.sha256 == sha256,
                    DocumentRecord.parser_version == parser_version,
                    DocumentRecord.chunker_version == chunker_version,
                    DocumentRecord.status == "ready",
                )
            )

    async def store_canonical(
        self, document: ParsedDocument, parser_version: str, chunker_version: str
    ) -> None:
        async with self.database.session() as session, session.begin():
            record = await session.get(DocumentRecord, document.id)
            values = {
                "filename": document.filename,
                "sha256": document.sha256,
                "source_path": document.source_path,
                "title": document.title,
                "page_count": document.page_count,
                "status": "indexing",
                "parser_version": parser_version,
                "chunker_version": chunker_version,
                "document_metadata": document.metadata,
            }
            if record is None:
                record = DocumentRecord(id=document.id, **values)
                session.add(record)
            else:
                for key, value in values.items():
                    setattr(record, key, value)
                await session.execute(
                    delete(ElementRecord).where(ElementRecord.document_id == document.id)
                )
            session.add_all(
                [
                    ElementRecord(
                        id=item.id,
                        document_id=document.id,
                        parent_id=item.parent_id,
                        element_type=item.element_type.value,
                        page=item.page,
                        section=item.section,
                        content=item.content,
                        structured=item.structured,
                        bbox=item.bbox.model_dump() if item.bbox else None,
                    )
                    for item in document.elements
                ]
            )

    async def set_status(self, document_id: str, status: str) -> None:
        async with self.database.session() as session, session.begin():
            record = await session.get(DocumentRecord, document_id)
            if record is None:
                raise LookupError(document_id)
            record.status = status

    async def expand(self, children: Sequence[RetrievedChunk]) -> list[Evidence]:
        parent_ids = {
            item.chunk.parent_id
            for item in children
            if item.chunk.metadata.get("evidence_mode", "parent") == "parent"
        }
        parents: dict[str, ElementRecord] = {}
        if parent_ids:
            async with self.database.session() as session:
                rows = (
                    await session.scalars(
                        select(ElementRecord).where(ElementRecord.id.in_(parent_ids))
                    )
                ).all()
                parents = {row.id: row for row in rows}

        evidence: list[Evidence] = []
        for item in children:
            chunk = item.chunk
            parent = parents.get(chunk.parent_id)
            if parent is not None:
                evidence.append(
                    Evidence(
                        evidence_id=parent.id,
                        child_id=chunk.id,
                        document_id=chunk.document_id,
                        page=parent.page,
                        section=parent.section,
                        element_type=parent.element_type,
                        content=parent.content,
                        score=item.score,
                        bbox=BoundingBox.model_validate(parent.bbox) if parent.bbox else None,
                        structured=parent.structured,
                        image_url=f"/api/evidence/{parent.id}/image",
                    )
                )
            else:
                bbox = chunk.metadata.get("bbox")
                evidence.append(
                    Evidence(
                        evidence_id=chunk.id,
                        child_id=chunk.id,
                        document_id=chunk.document_id,
                        page=chunk.page,
                        section=chunk.section,
                        element_type=chunk.element_type,
                        content=chunk.evidence_content,
                        score=item.score,
                        bbox=BoundingBox.model_validate(bbox) if bbox else None,
                    )
                )
        return evidence

    async def evidence_source(
        self, evidence_id: str
    ) -> tuple[ElementRecord, DocumentRecord] | None:
        async with self.database.session() as session:
            element = await session.get(ElementRecord, evidence_id)
            if element is None:
                return None
            document = await session.get(DocumentRecord, element.document_id)
            return (element, document) if document else None
