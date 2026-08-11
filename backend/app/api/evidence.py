from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.schemas import BoundingBox

router = APIRouter(prefix="/api")


@router.get("/evidence/{evidence_id}/image", response_class=FileResponse)
async def evidence_image(evidence_id: str, request: Request) -> FileResponse:
    source = await request.app.state.repository.evidence_source(evidence_id)
    if source is None:
        raise HTTPException(404, "Evidence not found")
    element, document = source
    bbox = BoundingBox.model_validate(element.bbox) if element.bbox else None
    path = request.app.state.renderer.render(
        document.source_path, document.id, element.id, element.page, bbox
    )
    return FileResponse(path, media_type="image/png", filename=f"{evidence_id}.png")
