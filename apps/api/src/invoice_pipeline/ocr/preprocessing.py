import cv2
import numpy as np
from PIL import Image
import structlog
from typing import Tuple

log = structlog.get_logger()

class ImagePreprocessor:
    def __init__(self, target_dpi: int = 300):
        self.target_dpi = target_dpi

    def process(self, image: Image.Image) -> Tuple[Image.Image, dict]:
        """
        Runs the full preprocessing pipeline.
        Returns the preprocessed image and a metadata dict.
        """
        # Convert PIL to OpenCV format
        cv_img = np.array(image.convert("RGB"))
        # RGB to BGR for OpenCV
        cv_img = cv_img[:, :, ::-1].copy()

        metrics = {}

        # 1. Blank Page Detection (on original image)
        gray_initial = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        is_blank = self.is_blank_page(gray_initial)
        metrics["is_blank"] = is_blank
        
        if is_blank:
            return image, metrics

        # 2. Deskew
        cv_img, angle = self.deskew(cv_img)
        metrics["deskew_angle"] = angle

        # 3. Grayscale
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        # 4. Contrast Enhancement
        gray = self.enhance_contrast(gray)

        # 5. Noise Removal
        gray = self.remove_noise(gray)

        # 6. Resolution Optimization (Resize if too small)
        gray = self.optimize_resolution(gray)

        # Convert back to PIL
        out_img = Image.fromarray(gray)
        return out_img, metrics

    def deskew(self, image: np.ndarray) -> Tuple[np.ndarray, float]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) == 0:
            return image, 0.0
            
        angle = cv2.minAreaRect(coords)[-1]
        
        # Handle angle according to cv2 minAreaRect output
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
            
        if abs(angle) < 0.5:
            return image, 0.0

        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated, angle

    def enhance_contrast(self, gray: np.ndarray) -> np.ndarray:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def remove_noise(self, gray: np.ndarray) -> np.ndarray:
        # A lightweight noise removal
        return cv2.medianBlur(gray, 3)

    def is_blank_page(self, gray: np.ndarray) -> bool:
        # Use standard deviation of pixel intensities
        std_dev = np.std(gray)
        return std_dev < 15.0

    def optimize_resolution(self, gray: np.ndarray) -> np.ndarray:
        # Basic upscaling if the image is too small for good OCR
        h, w = gray.shape
        if h < 1000 or w < 1000:
            scale = 2.0
            return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return gray
