from app.schemas import ElementType, ParsedDocument, ParsedElement


def make_document(content: str = "Narrative evidence") -> ParsedDocument:
    element = ParsedElement(
        id="text-1",
        element_type=ElementType.TEXT,
        page=4,
        section=["Results"],
        content=content,
        parent_id="parent-1",
    )
    parent = ParsedElement(
        id="parent-1",
        element_type=ElementType.TEXT,
        page=4,
        section=["Results"],
        content=content,
        structured={"role": "narrative_parent"},
        parent_id="parent-1",
    )
    return ParsedDocument(
        id="aapl-2022-q3",
        filename="filing.pdf",
        sha256="a" * 64,
        source_path="filing.pdf",
        title="Apple filing",
        page_count=32,
        elements=[element, parent],
    )
