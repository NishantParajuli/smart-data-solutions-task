from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/documents")
async def documents(request: Request) -> list[dict[str, object]]:
    return await request.app.state.repository.list_documents()
