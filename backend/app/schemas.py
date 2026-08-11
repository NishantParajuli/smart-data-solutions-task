from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ElementType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    SECTION = "section"


class BoundingBox(BaseModel):
    left: float
    top: float
    right: float
    bottom: float
    coordinate_origin: str = "top-left"


class ParsedElement(BaseModel):
    id: str
    element_type: ElementType
    page: int
    section: list[str] = Field(default_factory=list)
    content: str
    structured: dict[str, Any] = Field(default_factory=dict)
    bbox: BoundingBox | None = None
    parent_id: str | None = None


class ParsedDocument(BaseModel):
    id: str
    filename: str
    sha256: str
    source_path: str
    title: str
    page_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    elements: list[ParsedElement] = Field(default_factory=list)


class Chunk(BaseModel):
    id: str
    document_id: str
    parent_id: str
    page: int
    section: list[str] = Field(default_factory=list)
    element_type: str
    text: str
    evidence_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float = 0.0
    rank: int


class Evidence(BaseModel):
    evidence_id: str
    child_id: str
    document_id: str
    page: int
    section: list[str] = Field(default_factory=list)
    element_type: str
    content: str
    score: float = 0.0
    bbox: BoundingBox | None = None
    structured: dict[str, Any] = Field(default_factory=dict)
    image_url: str | None = None


class Citation(BaseModel):
    evidence_id: str
    page: int
    section: str | None = None
    image_url: str | None = None


class CalculationOperand(BaseModel):
    value: Decimal
    evidence_id: str
    metric: str
    period: str
    unit: str


class LiteralOperation(StrEnum):
    PERCENTAGE_CHANGE = "percentage_change"
    ABSOLUTE_CHANGE = "absolute_change"
    PERCENTAGE = "percentage"


class CalculationRequest(BaseModel):
    operation: LiteralOperation
    operands: list[CalculationOperand]


class CalculationResult(BaseModel):
    operation: LiteralOperation
    value: str
    expression: str
    evidence_ids: list[str]


class GeneratedResponse(BaseModel):
    answer: str
    citation_ids: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    calculation_requests: list[CalculationRequest] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    document_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    insufficient_evidence: bool
    citations: list[Citation]
    retrieved_evidence: list[Evidence]
    calculations: list[CalculationResult] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
