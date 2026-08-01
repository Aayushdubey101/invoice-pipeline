import io
from typing import Any

import structlog

from invoice_pipeline.schemas import Page, Word

log = structlog.get_logger()


class PaddleOCREngine:
    def __init__(self) -> None:
        self._ocr = None

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return self._ocr

    async def extract_pages(self, file_bytes: bytes, mime_type: str) -> list[Page]:
        if mime_type == "application/pdf":
            return await self._extract_pdf(file_bytes)
        return [self._extract_image(file_bytes, 0)]

    async def _extract_pdf(self, file_bytes: bytes) -> list[Page]:
        import fitz

        pages: list[Page] = []
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                pages.append(self._extract_image(img_bytes, i))
        return pages

    def _extract_image(self, img_bytes: bytes, page_num: int) -> Page:
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_array = np.array(img)

        ocr = self._get_ocr()
        result = ocr.ocr(img_array, cls=True) or [[]]

        words: list[Word] = []
        lines: list[str] = []

        for line in result[0] or []:
            bbox_points, (text, conf) = line
            if not text.strip():
                continue
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            words.append(
                Word(
                    text=text,
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    page=page_num,
                    confidence=float(conf),
                )
            )
            lines.append(text)

        return Page(page_num=page_num, text="\n".join(lines), words=words)
