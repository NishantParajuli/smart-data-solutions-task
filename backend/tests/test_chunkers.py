from app.ingestion.chunkers import DocumentAwareChunker, FixedChunker, ParentChildChunker
from app.schemas import ElementType, ParsedDocument, ParsedElement
from conftest import make_document


def test_fixed_chunks_are_page_local_with_exact_overlap() -> None:
    document = make_document("a" * 2500)
    chunks = FixedChunker(size=2000, overlap=100).chunks(document)
    assert len(chunks) == 2
    assert chunks[0].page == chunks[1].page == 4
    first = chunks[0].evidence_content
    second = chunks[1].evidence_content
    assert first[-100:] == second[:100]


def test_parent_child_table_rows_point_to_canonical_table() -> None:
    table = ParsedElement(
        id="table-1",
        element_type=ElementType.TABLE,
        page=10,
        section=["Revenue"],
        content="| Service | 2022 | 2021 |",
        structured={
            "scale_context": "in millions",
            "rows": [
                {"Metric": "Services", "2022": "19,604", "2021": "17,486"},
                {"Metric": "iPhone", "2022": "40,665", "2021": "39,570"},
            ],
        },
        parent_id="table-1",
    )
    document = ParsedDocument(
        id="doc",
        filename="x.pdf",
        sha256="a" * 64,
        source_path="x.pdf",
        title="Filing",
        page_count=10,
        elements=[table],
    )
    chunks = ParentChildChunker().chunks(document)
    assert len(chunks) == 2
    assert all(item.parent_id == "table-1" for item in chunks)
    assert "Services" in chunks[0].text and "19,604" in chunks[0].text


def test_document_aware_keeps_small_table_atomic() -> None:
    table = ParsedElement(
        id="table", element_type=ElementType.TABLE, page=2, content="| A | B |", parent_id="table"
    )
    document = ParsedDocument(
        id="doc",
        filename="x.pdf",
        sha256="b" * 64,
        source_path="x.pdf",
        title="Filing",
        page_count=2,
        elements=[table],
    )
    chunks = DocumentAwareChunker().chunks(document)
    assert len(chunks) == 1
    assert chunks[0].evidence_content == table.content
