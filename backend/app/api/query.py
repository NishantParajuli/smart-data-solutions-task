import time

from fastapi import APIRouter, HTTPException, Request

from app.generation.calculator import CalculationError, Calculator
from app.schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/api")


@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest, request: Request) -> QueryResponse:
    repository = request.app.state.repository
    document_id = payload.document_id
    if not document_id:
        ready = [item for item in await repository.list_documents() if item["status"] == "ready"]
        if not ready:
            raise HTTPException(409, "No ready document. Run the ingestion CLI first.")
        document_id = str(ready[0]["id"])
    document = await repository.get_document(document_id)
    if document is None or document.status != "ready":
        raise HTTPException(404, "Ready document not found")

    _, evidence, timings = await request.app.state.retrieval.retrieve(
        payload.question, document_id, payload.top_k
    )
    generation_started = time.perf_counter()
    generated = await request.app.state.provider.generate(payload.question, evidence)
    timings["generation"] = round((time.perf_counter() - generation_started) * 1000)
    calculations = []
    for calculation_request in generated.calculation_requests:
        try:
            calculations.append(Calculator.execute(calculation_request, evidence))
        except CalculationError:
            continue
    return QueryResponse(
        answer=generated.answer,
        insufficient_evidence=generated.insufficient_evidence,
        citations=request.app.state.provider.citations(generated, evidence),
        retrieved_evidence=evidence,
        calculations=calculations,
        timings_ms=timings,
    )
