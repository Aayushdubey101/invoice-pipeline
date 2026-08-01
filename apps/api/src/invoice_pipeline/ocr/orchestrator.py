import io
import structlog
from typing import Tuple

from invoice_pipeline.config import OCREngineName, settings
from invoice_pipeline.schemas import Page
from invoice_pipeline.ocr.preprocessing import ImagePreprocessor

log = structlog.get_logger()


class OCROrchestrator:
    def __init__(self):
        self.preprocessor = ImagePreprocessor()

    async def extract_pages(self, file_bytes: bytes, mime_type: str) -> Tuple[list[Page], list[bytes]]:
        """
        Extract text via OCR, with preprocessing and fallback logic.
        Returns: (pages, preprocessed_images_bytes)
        """
        import fitz
        from PIL import Image
        
        images = []
        if mime_type == "application/pdf":
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                    images.append(img)
        else:
            images.append(Image.open(io.BytesIO(file_bytes)).convert("RGB"))

        preprocessed_images_bytes = []
        pages = []
        engines = self._get_engine_fallbacks()

        for i, img in enumerate(images):
            # Preprocess
            prep_img, metrics = self.preprocessor.process(img)
            
            # Save preprocessed image to bytes
            img_byte_arr = io.BytesIO()
            prep_img.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            preprocessed_images_bytes.append(img_bytes)

            if metrics.get("is_blank", False):
                log.info("ocr_blank_page_skipped", page=i)
                pages.append(Page(page_num=i, text=""))
                continue

            page = await self._run_engines(img_bytes, i, engines)
            pages.append(page)

        return pages, preprocessed_images_bytes

    def _get_engine_fallbacks(self):
        from invoice_pipeline.ocr.tesseract import TesseractEngine
        
        engines = []
        if settings.OCR_ENGINE == OCREngineName.PADDLEOCR:
            try:
                from invoice_pipeline.ocr.paddle import PaddleOCREngine
                engines.append(("paddle", PaddleOCREngine()))
            except ImportError:
                log.warning("ocr_engine_fallback", reason="paddleocr not installed, using tesseract")
        
        engines.append(("tesseract", TesseractEngine()))
        return engines

    async def _run_engines(self, img_bytes: bytes, page_num: int, engines: list) -> Page:
        for i, (name, engine) in enumerate(engines):
            try:
                pages_out = await engine.extract_pages(img_bytes, "image/png")
                page = pages_out[0]
                page.page_num = page_num
                
                avg_conf = sum(w.confidence for w in page.words) / len(page.words) if page.words else 0.0
                is_last_engine = (i == len(engines) - 1)
                
                if avg_conf < 0.4 and not is_last_engine:
                    log.warning("ocr_low_confidence_fallback", engine=name, conf=avg_conf)
                    continue
                    
                return page
            except Exception as e:
                log.warning("ocr_engine_failed", engine=name, error=str(e))
                if i == len(engines) - 1:
                    raise
        
        return Page(page_num=page_num, text="")
