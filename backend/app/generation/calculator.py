from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.schemas import CalculationRequest, CalculationResult, Evidence, LiteralOperation


class CalculationError(ValueError):
    pass


class Calculator:
    """Execute only typed, evidence-bound arithmetic with Decimal."""

    @classmethod
    def execute(cls, request: CalculationRequest, evidence: list[Evidence]) -> CalculationResult:
        if len(request.operands) != 2:
            raise CalculationError("Exactly two operands are required")
        evidence_by_id = {item.evidence_id: item for item in evidence}
        for operand in request.operands:
            cited = evidence_by_id.get(operand.evidence_id)
            if cited is None:
                raise CalculationError("Operand cites evidence outside the retrieved set")
            if not cls._value_appears(operand.value, cited.content):
                raise CalculationError(f"Operand value {operand.value} is absent from its evidence")
        left, right = (item.value for item in request.operands)
        if request.operation == LiteralOperation.ABSOLUTE_CHANGE:
            value = left - right
            expression = f"{left} - {right} = {value}"
        elif request.operation == LiteralOperation.PERCENTAGE:
            value = cls._divide(left, right) * Decimal(100)
            expression = f"({left} / {right}) × 100 = {cls._format(value)}%"
        elif request.operation == LiteralOperation.PERCENTAGE_CHANGE:
            value = cls._divide(left - right, right) * Decimal(100)
            expression = f"(({left} - {right}) / {right}) × 100 = {cls._format(value)}%"
        else:  # pragma: no cover - Pydantic rejects unknown operations
            raise CalculationError("Unsupported operation")
        rendered = cls._format(value)
        if request.operation != LiteralOperation.ABSOLUTE_CHANGE:
            rendered += "%"
        return CalculationResult(
            operation=request.operation,
            value=rendered,
            expression=expression,
            evidence_ids=list(dict.fromkeys(item.evidence_id for item in request.operands)),
        )

    @staticmethod
    def _divide(numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator == 0:
            raise CalculationError("Division by zero")
        try:
            return numerator / denominator
        except (InvalidOperation, OverflowError) as exc:
            raise CalculationError("Invalid operands") from exc

    @staticmethod
    def _format(value: Decimal) -> str:
        rounded = value.quantize(Decimal("0.01"))
        return format(rounded, "f").rstrip("0").rstrip(".") or "0"

    @staticmethod
    def _value_appears(value: Decimal, content: str) -> bool:
        wanted = value.normalize()
        for token in re.findall(r"(?<!\w)\(?-?\$?[\d,]+(?:\.\d+)?\)?%?", content):
            normalized = token.replace("$", "").replace(",", "").replace("%", "")
            negative = normalized.startswith("(") and normalized.endswith(")")
            normalized = normalized.strip("()")
            try:
                candidate = Decimal(normalized)
            except InvalidOperation:
                continue
            if (-(candidate) if negative else candidate).normalize() == wanted:
                return True
        return False
