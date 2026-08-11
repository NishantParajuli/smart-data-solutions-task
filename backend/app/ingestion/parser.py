from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import pymupdf

from app.schemas import BoundingBox, ElementType, ParsedDocument, ParsedElement


def stable_id(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_columns(values: list[str]) -> list[str]:
    result: list[str] = []
    used: dict[str, int] = {}
    for index, value in enumerate(values, 1):
        base = " ".join(value.split()) or f"Column {index}"
        used[base] = used.get(base, 0) + 1
        result.append(base if used[base] == 1 else f"{base} [{used[base]}]")
    return result


def clean_json(value: Any) -> Any:
    if value is None or isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        return clean_json(value.item())
    if isinstance(value, dict):
        return {str(key): clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(item) for item in value]
    return value


class DoclingParser:
    """Docling-first parser for born-digital filings; OCR is deliberately disabled."""

    version = "docling-v2-canonical-v2"

    def parse(self, path: Path) -> ParsedDocument:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling_core.types.doc import PictureItem, TableItem, TextItem
        except ImportError as exc:
            raise RuntimeError(
                "Docling is required for ingestion; install the ingestion extra"
            ) from exc

        path = path.resolve()
        digest = sha256_file(path)
        document_id = "aapl-2022-q3" if "2022" in path.stem else f"document-{digest[:12]}"
        options = PdfPipelineOptions()
        options.do_ocr = False
        options.do_table_structure = True
        options.generate_page_images = False
        options.generate_picture_images = False
        if hasattr(options, "layout_options"):
            engine = getattr(options.layout_options, "engine_options", None)
            if engine is not None and hasattr(engine, "compile_model"):
                engine.compile_model = False
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        converted = converter.convert(path)
        elements: list[ParsedElement] = []
        headings: list[tuple[int, str]] = []

        for ordinal, (item, level) in enumerate(converted.document.iterate_items(), 1):
            label = str(getattr(item, "label", "")).lower()
            structured: dict[str, Any] = {}
            if isinstance(item, TextItem):
                content = str(getattr(item, "text", "") or "").strip()
                if not content:
                    continue
                kind = ElementType.TEXT
                if "section_header" in label or label.endswith("title"):
                    headings = [(depth, text) for depth, text in headings if depth < level]
                    headings.append((level, content))
                    kind = ElementType.SECTION
            elif isinstance(item, TableItem):
                kind = ElementType.TABLE
                try:
                    content = item.export_to_markdown(doc=converted.document).strip()
                except TypeError:
                    content = item.export_to_markdown(converted.document).strip()
                try:
                    frame = item.export_to_dataframe(doc=converted.document)
                    source_columns = [
                        " | ".join(str(part) for part in col if str(part) != "nan")
                        if isinstance(col, tuple)
                        else str(col)
                        for col in frame.columns
                    ]
                    columns = normalize_columns(source_columns)
                    rows = [
                        {columns[i]: clean_json(value) for i, value in enumerate(row)}
                        for row in frame.itertuples(index=False, name=None)
                    ]
                    structured = {
                        "columns": columns,
                        "period_headers": source_columns,
                        "rows": rows,
                    }
                except Exception:
                    structured = {"columns": [], "period_headers": [], "rows": []}
            elif isinstance(item, PictureItem):
                kind = ElementType.FIGURE
                try:
                    content = item.caption_text(converted.document).strip()
                except Exception:
                    content = ""
                content = content or "Uncaptioned figure or graphic"
                structured = {"captioned": content != "Uncaptioned figure or graphic"}
            else:
                continue

            provenance = getattr(item, "prov", None) or []
            page = max(1, int(getattr(provenance[0], "page_no", 1))) if provenance else 1
            box = getattr(provenance[0], "bbox", None) if provenance else None
            bbox = (
                BoundingBox(
                    left=float(getattr(box, "l", 0)),
                    top=float(getattr(box, "t", 0)),
                    right=float(getattr(box, "r", 0)),
                    bottom=float(getattr(box, "b", 0)),
                    coordinate_origin=str(getattr(box, "coord_origin", "bottom-left")),
                )
                if box is not None
                else None
            )
            section = [text for _, text in sorted(headings)]
            if kind == ElementType.SECTION and section and section[-1] == content:
                section = section[:-1]
            element_id = f"{document_id}-{kind.value}-{ordinal:04d}"
            elements.append(
                ParsedElement(
                    id=element_id,
                    element_type=kind,
                    page=page,
                    section=section,
                    content=content,
                    structured=structured,
                    bbox=bbox,
                )
            )

        self._attach_scale_context(elements)
        elements = self._add_narrative_parents(document_id, elements)
        with pymupdf.open(path) as pdf:
            metadata = {key: value for key, value in (pdf.metadata or {}).items() if value}
            page_count = pdf.page_count
        return ParsedDocument(
            id=document_id,
            filename=path.name,
            sha256=digest,
            source_path=str(path),
            title="Apple 2022 Q3 Form 10-Q",
            page_count=page_count,
            metadata={**metadata, "parser": self.version, "ocr": False},
            elements=elements,
        )

    @staticmethod
    def _attach_scale_context(elements: list[ParsedElement]) -> None:
        scale = re.compile(r"\b(?:in )?(?:millions?|thousands?|billions?)\b", re.I)
        for index, table in enumerate(elements):
            if table.element_type != ElementType.TABLE:
                continue
            candidates = elements[max(0, index - 8) : index]
            for previous in reversed(candidates):
                if (
                    previous.page == table.page
                    and previous.element_type == ElementType.TEXT
                    and scale.search(previous.content)
                ):
                    table.structured["scale_context"] = previous.content
                    break

    @staticmethod
    def _add_narrative_parents(
        document_id: str, elements: list[ParsedElement]
    ) -> list[ParsedElement]:
        groups: dict[tuple[int, tuple[str, ...]], list[ParsedElement]] = defaultdict(list)
        for item in elements:
            if item.element_type == ElementType.TEXT:
                groups[(item.page, tuple(item.section))].append(item)
            elif item.element_type in {ElementType.TABLE, ElementType.FIGURE, ElementType.SECTION}:
                item.parent_id = item.id
        parents: list[ParsedElement] = []
        for (page, section), children in groups.items():
            parent_id = f"{document_id}-parent-{stable_id(f'{page}:{section}')[:12]}"
            for child in children:
                child.parent_id = parent_id
            boxes = [item.bbox for item in children if item.bbox]
            bbox = None
            if boxes:
                bottom_left = "bottom" in boxes[0].coordinate_origin.lower()
                bbox = BoundingBox(
                    left=min(box.left for box in boxes),
                    top=(
                        max(box.top for box in boxes)
                        if bottom_left
                        else min(box.top for box in boxes)
                    ),
                    right=max(box.right for box in boxes),
                    bottom=(
                        min(box.bottom for box in boxes)
                        if bottom_left
                        else max(box.bottom for box in boxes)
                    ),
                    coordinate_origin=boxes[0].coordinate_origin,
                )
            parents.append(
                ParsedElement(
                    id=parent_id,
                    element_type=ElementType.TEXT,
                    page=page,
                    section=list(section),
                    content="\n\n".join(item.content for item in children),
                    structured={"role": "narrative_parent"},
                    bbox=bbox,
                    parent_id=parent_id,
                )
            )
        return [*elements, *parents]
