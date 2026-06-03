import io

import structlog

from invoice_pipeline.schemas import Page, Word

log = structlog.get_logger()


class TesseractEngine:
    async def extract_pages(self, file_bytes: bytes, mime_type: str) -> list[Page]:

        if mime_type == "application/pdf":
            return await self._extract_pdf(file_bytes)
        return [self._extract_image(file_bytes, 0)]

    async def _extract_pdf(self, file_bytes: bytes) -> list[Page]:
        import fitz  # PyMuPDF

        pages: list[Page] = []
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                pages.append(self._extract_image(img_bytes, i))
        return pages

    def _extract_image(self, img_bytes: bytes, page_num: int) -> Page:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img)

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        words: list[Word] = []
        for i, word_text in enumerate(data["text"]):
            if not word_text.strip():
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            words.append(
                Word(
                    text=word_text,
                    bbox=(float(x), float(y), float(x + w), float(y + h)),
                    page=page_num,
                )
            )

        return Page(page_num=page_num, text=text.strip(), words=words)
