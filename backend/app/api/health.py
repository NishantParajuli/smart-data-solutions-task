from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    checks: dict[str, str] = {}
    try:
        async with request.app.state.database.session() as session:
            await session.execute(text("SELECT 1"))
        checks["mysql"] = "ok"
    except Exception:
        checks["mysql"] = "unavailable"
    checks["qdrant"] = "ok" if await request.app.state.store.healthy() else "unavailable"
    return {
        "status": "ok" if all(value == "ok" for value in checks.values()) else "degraded",
        "version": request.app.state.settings.app_version,
        "checks": checks,
    }
