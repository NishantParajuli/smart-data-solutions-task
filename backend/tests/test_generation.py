import pytest
from app.generation.calculator import CalculationError, Calculator
from app.generation.provider import AnswerProvider, ExtractiveProvider, GoogleProvider
from app.schemas import (
    CalculationOperand,
    CalculationRequest,
    Evidence,
    GeneratedResponse,
    LiteralOperation,
)


def evidence() -> list[Evidence]:
    return [
        Evidence(
            evidence_id="ev-1",
            child_id="child",
            document_id="doc",
            page=10,
            element_type="table",
            content="Services | 19,604 | 17,486",
        )
    ]


def test_citation_ids_are_limited_to_retrieved_evidence() -> None:
    response = AnswerProvider.validate(
        GeneratedResponse(answer="Services increased.", citation_ids=["ev-1", "invented"]),
        evidence(),
    )
    assert response.citation_ids == ["ev-1"]


def test_answer_without_valid_citation_abstains() -> None:
    response = AnswerProvider.validate(
        GeneratedResponse(answer="Unsupported", citation_ids=["invented"]), evidence()
    )
    assert response.insufficient_evidence is True
    assert response.citation_ids == []


@pytest.mark.asyncio
async def test_extractive_fallback_abstains_on_unrelated_question() -> None:
    response = await ExtractiveProvider().generate("What is the weather on Mars?", evidence())
    assert response.insufficient_evidence is True


@pytest.mark.asyncio
async def test_google_provider_uses_parsed_structured_response() -> None:
    generated = GeneratedResponse(answer="Supported answer", citation_ids=["ev-1"])
    provider = object.__new__(GoogleProvider)
    provider.model = "test-model"
    provider.generation_config = object()

    class Models:
        async def generate_content(self, **_: object) -> object:
            return type("Response", (), {"parsed": generated, "text": "ignored"})()

    provider.client = type(
        "Client", (), {"aio": type("Async", (), {"models": Models()})()}
    )()
    response = await provider.generate("question", evidence())
    assert response.answer == "Supported answer"
    assert response.citation_ids == ["ev-1"]


@pytest.mark.asyncio
async def test_google_provider_hides_malformed_output_behind_abstention() -> None:
    provider = object.__new__(GoogleProvider)
    provider.model = "test-model"
    provider.generation_config = object()

    class Models:
        async def generate_content(self, **_: object) -> object:
            return type("Response", (), {"parsed": None, "text": "not JSON"})()

    provider.client = type(
        "Client", (), {"aio": type("Async", (), {"models": Models()})()}
    )()
    response = await provider.generate("question", evidence())
    assert response.insufficient_evidence is True
    assert response.answer == (
        "The retrieved filing evidence is insufficient to answer that question."
    )


def test_calculator_executes_evidence_bound_percentage_change() -> None:
    request = CalculationRequest(
        operation=LiteralOperation.PERCENTAGE_CHANGE,
        operands=[
            CalculationOperand(
                value="19604",
                evidence_id="ev-1",
                metric="Services",
                period="2022",
                unit="USD million",
            ),
            CalculationOperand(
                value="17486",
                evidence_id="ev-1",
                metric="Services",
                period="2021",
                unit="USD million",
            ),
        ],
    )
    result = Calculator.execute(request, evidence())
    assert result.value == "12.11%"
    assert "19604" in result.expression


def test_calculator_rejects_value_absent_from_evidence() -> None:
    request = CalculationRequest(
        operation=LiteralOperation.PERCENTAGE,
        operands=[
            CalculationOperand(
                value="999", evidence_id="ev-1", metric="x", period="2022", unit="USD"
            ),
            CalculationOperand(
                value="17486", evidence_id="ev-1", metric="x", period="2021", unit="USD"
            ),
        ],
    )
    with pytest.raises(CalculationError):
        Calculator.execute(request, evidence())
