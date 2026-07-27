"""
OCR client wrapper for Tesseract.
Abstracts OCR engine so it can be swapped later (e.g., to EasyOCR).
All Tesseract-specific configuration and calls happen here.
"""

import pytesseract
from PIL import Image
from pathlib import Path
from typing import Union, Optional
import io

from core.config import settings


class OCRClient:
    """Wrapper around Tesseract OCR engine."""

    def __init__(self):
        """Initialize OCR client with Tesseract path from config."""
        if settings.TESSERACT_PATH:
            pytesseract.pytesseract.pytesseract_cmd = settings.TESSERACT_PATH
    
    def extract_text_from_image(self, image_path: Union[str, Path]) -> str:
        """
        Extract text from an image file using OCR.
        
        Args:
            image_path: Path to image file (PNG, JPG, etc.)
            
        Returns:
            Extracted text as string
            
        Raises:
            FileNotFoundError: If image doesn't exist
            Exception: If OCR fails (e.g., Tesseract not installed)
        """
        image_path = Path(image_path)
        
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            raise Exception(f"OCR failed on {image_path.name}: {str(e)}")
    
    def extract_text_from_bytes(self, image_bytes: bytes) -> str:
        """
        Extract text from image bytes (in-memory).
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Extracted text as string
            
        Raises:
            Exception: If OCR fails
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            raise Exception(f"OCR failed on byte stream: {str(e)}")
    
    def extract_text_from_pdf_pages(self, pdf_path: Union[str, Path]) -> str:
        """
        Extract text from all pages of a scanned PDF using OCR.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Concatenated text from all pages
            
        Raises:
            ImportError: If PyMuPDF not installed
            FileNotFoundError: If PDF doesn't exist
            Exception: If OCR fails
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF required for PDF OCR. Install with: pip install PyMuPDF")
        
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        try:
            doc = fitz.open(pdf_path)
            full_text = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                # Render page to image at high DPI for better OCR
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better OCR
                image_bytes = pix.tobytes("ppm")
                
                try:
                    text = self.extract_text_from_bytes(image_bytes)
                    if text:
                        full_text.append(text)
                except Exception as e:
                    print(f"[OCR] Warning: Page {page_num + 1} failed: {str(e)}")
            
            doc.close()
            return "\n\n".join(full_text)
        except Exception as e:
            raise Exception(f"PDF OCR failed on {pdf_path.name}: {str(e)}")


# Singleton instance
ocr_client = OCRClient()
