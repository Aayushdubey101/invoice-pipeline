import io
import pytest
from unittest.mock import AsyncMock, patch
from PIL import Image, ImageDraw
import numpy as np
import cv2
from invoice_pipeline.ocr.preprocessing import ImagePreprocessor
from invoice_pipeline.ocr.orchestrator import OCROrchestrator
from invoice_pipeline.schemas import Page, Word

def create_dummy_image(text="Hello", size=(800, 600), blank=False):
    img = Image.new("RGB", size, (255, 255, 255))
    if not blank:
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), text, fill=(0, 0, 0))
        # Draw a large rectangle to ensure non_zero_ratio > 0.01
        draw.rectangle((50, 50, 400, 400), fill=(0, 0, 0))
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img, img_byte_arr.getvalue()


def test_preprocessor_blank_page():
    img, _ = create_dummy_image(blank=True)
    preprocessor = ImagePreprocessor()
    _, metrics = preprocessor.process(img)
    assert metrics["is_blank"] == True

def test_preprocessor_deskew():
    img, _ = create_dummy_image()
    # Rotate slightly
    img = img.rotate(5, expand=True, fillcolor=(255,255,255))
    
    preprocessor = ImagePreprocessor()
    prep_img, metrics = preprocessor.process(img)
    # The exact angle could vary, but it should detect some rotation
    assert "deskew_angle" in metrics

def test_preprocessor_resize():
    # Small image
    img, _ = create_dummy_image(size=(400, 300))
    preprocessor = ImagePreprocessor()
    prep_img, _ = preprocessor.process(img)
    assert prep_img.width >= 400

@pytest.mark.asyncio
async def test_orchestrator_blank_page():
    _, img_bytes = create_dummy_image(blank=True)
    orchestrator = OCROrchestrator()
    pages, prep = await orchestrator.extract_pages(img_bytes, "image/png")
    assert len(pages) == 1
    assert pages[0].text == ""

@pytest.mark.asyncio
async def test_orchestrator_fallback_low_confidence():
    _, img_bytes = create_dummy_image()
    
    orchestrator = OCROrchestrator()
    
    # Mock engines to simulate fallback
    mock_engine1 = AsyncMock()
    # Engine 1 returns low confidence
    mock_engine1.extract_pages.return_value = [Page(page_num=0, text="Bad", words=[Word(text="Bad", confidence=0.2)])]
    
    mock_engine2 = AsyncMock()
    mock_engine2.extract_pages.return_value = [Page(page_num=0, text="Good", words=[Word(text="Good", confidence=0.9)])]
    
    # override get engine
    orchestrator._get_engine_fallbacks = lambda: [("eng1", mock_engine1), ("eng2", mock_engine2)]
    
    pages, _ = await orchestrator.extract_pages(img_bytes, "image/png")
    
    assert len(pages) == 1
    assert pages[0].text == "Good"
    assert mock_engine1.extract_pages.called
    assert mock_engine2.extract_pages.called
