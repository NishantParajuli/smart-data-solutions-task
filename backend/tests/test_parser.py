from app.ingestion.parser import DoclingParser, normalize_columns
from app.schemas import ElementType, ParsedElement


def test_parser_helpers_preserve_table_scale_page_and_parent() -> None:
    elements = [
        ParsedElement(
            id="scale",
            element_type=ElementType.TEXT,
            page=10,
            section=["Revenue"],
            content="Net sales in millions",
        ),
        ParsedElement(
            id="table",
            element_type=ElementType.TABLE,
            page=10,
            section=["Revenue"],
            content="| Services | 19,604 |",
            structured={"columns": ["Metric", "June 25, 2022"], "rows": []},
        ),
    ]
    DoclingParser._attach_scale_context(elements)
    with_parents = DoclingParser._add_narrative_parents("doc", elements)
    assert elements[1].structured["scale_context"] == "Net sales in millions"
    assert elements[1].page == 10
    assert elements[0].parent_id is not None
    assert any(item.structured.get("role") == "narrative_parent" for item in with_parents)
    assert normalize_columns(["Period", "Period"]) == ["Period", "Period [2]"]
