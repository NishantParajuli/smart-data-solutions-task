from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from app.ingestion.parser import stable_id
from app.schemas import Chunk, ElementType, ParsedDocument, ParsedElement

Encoder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


def _context(document: ParsedDocument, element: ParsedElement, text: str) -> str:
    section = " > ".join(element.section) or "Document body"
    return f"Document: {document.title}\nPage: {element.page}\nSection: {section}\n{text}"


def _pieces(text: str, size: int, overlap: int = 0) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    result: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(len(text), cursor + size)
        if end < len(text):
            boundary = text.rfind(" ", cursor, end)
            if boundary > cursor + size // 2:
                end = boundary
        result.append(text[cursor:end].strip())
        if end == len(text):
            break
        cursor = max(cursor + 1, end - overlap)
    return result


def _ordered(document: ParsedDocument) -> list[ParsedElement]:
    return sorted(
        (
            item
            for item in document.elements
            if item.structured.get("role") != "narrative_parent"
            and item.element_type != ElementType.SECTION
        ),
        key=lambda item: (item.page, item.bbox.top if item.bbox else math.inf, item.id),
    )


class Chunker(ABC):
    version: str

    @abstractmethod
    def chunks(self, document: ParsedDocument) -> list[Chunk]: ...


class FixedChunker(Chunker):
    version = "fixed-2000-100-v1"

    def __init__(self, size: int = 2000, overlap: int = 100) -> None:
        if size <= 0 or overlap < 0 or overlap >= size:
            raise ValueError("Fixed chunk size/overlap is invalid")
        self.size, self.overlap = size, overlap

    def chunks(self, document: ParsedDocument) -> list[Chunk]:
        pages: dict[int, list[ParsedElement]] = defaultdict(list)
        for item in _ordered(document):
            pages[item.page].append(item)
        result: list[Chunk] = []
        for page, elements in pages.items():
            page_text = "\n\n".join(item.content for item in elements)
            for index, text in enumerate(_pieces(page_text, self.size, self.overlap)):
                chunk_id = stable_id(f"{self.version}:{document.id}:{page}:{index}")
                result.append(
                    Chunk(
                        id=chunk_id,
                        document_id=document.id,
                        parent_id=elements[0].id,
                        page=page,
                        element_type="fixed",
                        text=f"PDF page {page}\n{text}",
                        evidence_content=text,
                        metadata={
                            "strategy": "fixed",
                            "evidence_mode": "direct",
                            "overlap_characters": min(self.overlap, index * self.overlap),
                        },
                    )
                )
        return result


class DocumentAwareChunker(Chunker):
    version = "document-aware-1600-v1"

    def __init__(self, max_characters: int = 1600, overlap: int = 100) -> None:
        self.max_characters, self.overlap = max_characters, overlap

    def chunks(self, document: ParsedDocument) -> list[Chunk]:
        groups: dict[tuple[int, tuple[str, ...]], list[ParsedElement]] = defaultdict(list)
        structured: list[ParsedElement] = []
        for item in _ordered(document):
            if item.element_type == ElementType.TEXT:
                groups[(item.page, tuple(item.section))].append(item)
            else:
                structured.append(item)
        result: list[Chunk] = []
        for (_page, section), elements in groups.items():
            text = "\n\n".join(item.content for item in elements)
            for index, part in enumerate(_pieces(text, self.max_characters, self.overlap)):
                result.append(self._direct(document, elements[0], part, index, list(section)))
        for item in structured:
            parts = [item.content]
            if len(item.content) > self.max_characters and item.element_type != ElementType.TABLE:
                parts = _pieces(item.content, self.max_characters)
            for index, part in enumerate(parts):
                result.append(self._direct(document, item, part, index, item.section))
        return result

    def _direct(
        self,
        document: ParsedDocument,
        element: ParsedElement,
        content: str,
        index: int,
        section: list[str],
    ) -> Chunk:
        kind = element.element_type.value
        return Chunk(
            id=stable_id(f"{self.version}:{element.id}:{index}"),
            document_id=document.id,
            parent_id=element.id,
            page=element.page,
            section=section,
            element_type=f"{kind}_direct",
            text=_context(document, element, content),
            evidence_content=content,
            metadata={
                "strategy": "document_aware",
                "evidence_mode": "direct",
                "bbox": element.bbox.model_dump() if element.bbox else None,
                "structured": element.structured,
            },
        )


class SemanticChunker(DocumentAwareChunker):
    version = "semantic-adjacent-bge-v1"

    def __init__(self, encoder: Encoder | None = None, max_characters: int = 1600) -> None:
        super().__init__(max_characters=max_characters, overlap=0)
        self.encoder = encoder

    def _encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if self.encoder:
            return self.encoder(texts)
        from fastembed import TextEmbedding

        return list(TextEmbedding("BAAI/bge-small-en-v1.5").embed(list(texts)))

    @staticmethod
    def _similarity(left: Sequence[float], right: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        norms = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
        return dot / norms if norms else 0.0

    def chunks(self, document: ParsedDocument) -> list[Chunk]:
        groups: dict[tuple[int, tuple[str, ...]], list[ParsedElement]] = defaultdict(list)
        structured: list[ParsedElement] = []
        for item in _ordered(document):
            (
                groups[(item.page, tuple(item.section))]
                if item.element_type == ElementType.TEXT
                else structured
            ).append(item)
        result: list[Chunk] = []
        for (_, section), elements in groups.items():
            total = "\n\n".join(item.content for item in elements)
            if len(total) <= self.max_characters or len(elements) < 2:
                partitions = _pieces(total, self.max_characters)
            else:
                vectors = self._encode([item.content for item in elements])
                distances = [
                    1 - self._similarity(vectors[i - 1], vectors[i]) for i in range(1, len(vectors))
                ]
                threshold = sorted(distances)[max(0, int(0.8 * len(distances)) - 1)]
                partitions, current = [], ""
                for index, item in enumerate(elements):
                    should_break = index > 0 and (
                        len(current) + len(item.content) > self.max_characters
                        or distances[index - 1] >= threshold
                        and len(current) >= 300
                    )
                    if should_break and current:
                        partitions.extend(_pieces(current, self.max_characters))
                        current = ""
                    current = f"{current}\n\n{item.content}".strip()
                partitions.extend(_pieces(current, self.max_characters))
            for index, part in enumerate(partitions):
                result.append(self._direct(document, elements[0], part, index, list(section)))
        for item in structured:
            result.append(self._direct(document, item, item.content, 0, item.section))
        return result


class ParentChildChunker(Chunker):
    version = "parent-child-650-table-row-v1"

    def __init__(self, child_characters: int = 650) -> None:
        self.child_characters = child_characters

    def chunks(self, document: ParsedDocument) -> list[Chunk]:
        result: list[Chunk] = []
        for item in _ordered(document):
            if item.element_type == ElementType.TEXT:
                for index, text in enumerate(_pieces(item.content, self.child_characters)):
                    result.append(self._child(document, item, text, index, "text_child"))
            elif item.element_type == ElementType.TABLE:
                rows: list[dict[str, Any]] = item.structured.get("rows") or []
                scale = item.structured.get("scale_context", "")
                if rows:
                    for index, row in enumerate(rows):
                        facts = " | ".join(f"{key}: {value}" for key, value in row.items())
                        text = f"Table row. {scale}\n{facts}".strip()
                        result.append(self._child(document, item, text, index, "table_row_child"))
                else:
                    result.append(self._child(document, item, item.content, 0, "table_child"))
            elif item.element_type == ElementType.FIGURE:
                result.append(self._child(document, item, item.content, 0, "figure_child"))
        return result

    def _child(
        self,
        document: ParsedDocument,
        item: ParsedElement,
        text: str,
        index: int,
        kind: str,
    ) -> Chunk:
        parent_id = item.parent_id or item.id
        return Chunk(
            id=stable_id(f"{self.version}:{item.id}:{kind}:{index}"),
            document_id=document.id,
            parent_id=parent_id,
            page=item.page,
            section=item.section,
            element_type=kind,
            text=_context(document, item, text),
            evidence_content=item.content,
            metadata={
                "strategy": "parent_child",
                "evidence_mode": "parent",
                "source_element_id": item.id,
                "row_index": index if kind == "table_row_child" else None,
            },
        )


def build_chunker(name: str, semantic_encoder: Encoder | None = None) -> Chunker:
    options: dict[str, Chunker] = {
        "fixed": FixedChunker(),
        "document_aware": DocumentAwareChunker(),
        "semantic": SemanticChunker(semantic_encoder),
        "parent_child": ParentChildChunker(),
    }
    try:
        return options[name]
    except KeyError as exc:
        raise ValueError(f"Unknown chunking strategy: {name}") from exc
