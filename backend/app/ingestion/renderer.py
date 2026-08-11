import hashlib
from pathlib import Path

import pymupdf

from app.schemas import BoundingBox


class EvidenceRenderer:
    def __init__(self, output_dir: Path, dpi: int = 150) -> None:
        self.output_dir = output_dir
        self.dpi = dpi

    def render(
        self,
        source_path: str,
        document_id: str,
        evidence_id: str,
        page: int,
        bbox: BoundingBox | None,
    ) -> Path:
        identity = hashlib.sha256(f"{page}:{bbox}:{self.dpi}".encode()).hexdigest()[:10]
        destination = self.output_dir / document_id / f"{evidence_id}-{identity}.png"
        if destination.exists():
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(source_path) as pdf:
            if not 1 <= page <= pdf.page_count:
                raise ValueError("Evidence page is outside the source PDF")
            pdf_page = pdf.load_page(page - 1)
            clip = None
            if bbox:
                rect = pymupdf.Rect(bbox.left, bbox.top, bbox.right, bbox.bottom)
                if "bottom" in bbox.coordinate_origin.lower():
                    rect = pymupdf.Rect(
                        bbox.left,
                        pdf_page.rect.height - bbox.top,
                        bbox.right,
                        pdf_page.rect.height - bbox.bottom,
                    ).normalize()
                clip = (rect + (-16, -16, 16, 16)) & pdf_page.rect
            pdf_page.get_pixmap(dpi=self.dpi, clip=clip, alpha=False).save(destination)
        return destination
