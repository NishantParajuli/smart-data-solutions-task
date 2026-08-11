from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from pydantic import ValidationError

from app.config import Settings
from app.schemas import Citation, Evidence, GeneratedResponse

SYSTEM_PROMPT = """You answer only from the supplied filing evidence.
Cite only the provided evidence IDs. If the evidence does not answer the
question, mark it as insufficient. Never calculate in prose: emit a typed
calculation request instead."""


class AnswerProvider(ABC):
    @abstractmethod
    async def generate(self, question: str, evidence: list[Evidence]) -> GeneratedResponse: ...

    @staticmethod
    def validate(response: GeneratedResponse, evidence: list[Evidence]) -> GeneratedResponse:
        allowed = {item.evidence_id for item in evidence}
        valid_ids = list(dict.fromkeys(item for item in response.citation_ids if item in allowed))
        if response.insufficient_evidence or not response.answer.strip() or not valid_ids:
            return GeneratedResponse(
                answer="The retrieved filing evidence is insufficient to answer that question.",
                insufficient_evidence=True,
            )
        return response.model_copy(update={"citation_ids": valid_ids})

    @staticmethod
    def citations(response: GeneratedResponse, evidence: list[Evidence]) -> list[Citation]:
        by_id = {item.evidence_id: item for item in evidence}
        return [
            Citation(
                evidence_id=evidence_id,
                page=by_id[evidence_id].page,
                section=" > ".join(by_id[evidence_id].section) or None,
                image_url=by_id[evidence_id].image_url,
            )
            for evidence_id in response.citation_ids
            if evidence_id in by_id
        ]


class ExtractiveProvider(AnswerProvider):
    async def generate(self, question: str, evidence: list[Evidence]) -> GeneratedResponse:
        if not evidence:
            return self.validate(GeneratedResponse(answer="", insufficient_evidence=True), evidence)
        terms = self._terms(question)
        ranked = sorted(
            evidence,
            key=lambda item: (
                self._lexical_score(item, terms, question),
                -len(" ".join(item.section)),
                -len(item.content),
            ),
            reverse=True,
        )
        best = ranked[0]
        if self._lexical_score(best, terms, question) == 0:
            return GeneratedResponse(
                answer="The retrieved filing evidence is insufficient to answer that question.",
                insufficient_evidence=True,
            )
        answer = " ".join(best.content.split())
        if len(answer) > 900:
            answer = answer[:897].rsplit(" ", 1)[0] + "…"
        return self.validate(
            GeneratedResponse(answer=f"From the filing: {answer}", citation_ids=[best.evidence_id]),
            evidence,
        )

    @staticmethod
    def _terms(value: str) -> set[str]:
        ignored = {
            "a",
            "an",
            "and",
            "apple",
            "did",
            "do",
            "for",
            "from",
            "in",
            "is",
            "of",
            "on",
            "the",
            "this",
            "to",
            "was",
            "were",
            "what",
            "which",
            "with",
            "quarter",
            "third",
            "2021",
            "2022",
        }
        return {
            token
            for token in re.findall(r"[a-z][a-z0-9-]+", value.casefold())
            if token not in ignored and len(token) > 2
        }

    @classmethod
    def _lexical_score(cls, item: Evidence, terms: set[str], question: str) -> int:
        content = item.content.casefold()
        section = " ".join(item.section).casefold()
        score = sum(min(content.count(term), 3) for term in terms)
        score += 3 * sum(term in section for term in terms)
        if item.element_type.startswith("table") and re.search(
            r"\b(?:what were|how much|how many|percentage)\b", question, re.I
        ):
            score += 5
        return score


class GoogleProvider(AnswerProvider):
    def __init__(self, settings: Settings) -> None:
        from google import genai
        from google.genai import types

        self.client = genai.Client(api_key=settings.llm_api_key)
        self.model = settings.llm_model
        self.generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeneratedResponse,
            temperature=0,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )

    async def generate(self, question: str, evidence: list[Evidence]) -> GeneratedResponse:
        evidence_text = "\n\n".join(
            f"[{item.evidence_id}] PDF page {item.page}\n{item.content}" for item in evidence
        )
        prompt = f"{SYSTEM_PROMPT}\n\nQuestion: {question}\n\nEvidence:\n{evidence_text}"
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self.generation_config,
        )
        try:
            parsed = (
                response.parsed
                if isinstance(response.parsed, GeneratedResponse)
                else GeneratedResponse.model_validate(
                    response.parsed or json.loads(response.text or "")
                )
            )
        except (json.JSONDecodeError, ValidationError, TypeError):
            return self.validate(
                GeneratedResponse(answer="", insufficient_evidence=True), evidence
            )
        return self.validate(parsed, evidence)


def build_provider(settings: Settings) -> AnswerProvider:
    if settings.llm_provider == "google" and settings.llm_api_key:
        return GoogleProvider(settings)
    return ExtractiveProvider()
