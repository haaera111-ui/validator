"""
Core ingestion service - orchestrates the entire resume processing pipeline.

Responsibilities:
1. Accept resume files (PDF, DOCX, PNG, JPG)
2. Extract text via OCR (if scanned) or PyMuPDF (if native PDF)
3. Parse extracted text into structured fields using spaCy NER
4. Store in database (candidates, skills, education, experience)
5. Track processing status
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
import fitz  # PyMuPDF
from docx import Document

from app.models.candidate import (
    Candidate, Resume, ParsedData, Skill, Education, Experience, ResumeStatus
)
from ai.ocr_client import ocr_client
from core.config import settings


class IngestionService:
    """Orchestrates resume ingestion and parsing."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.storage_path = Path(settings.STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def ingest_resume(
        self,
        file_path: Path,
        candidate_name: str,
        candidate_email: Optional[str] = None,
        candidate_phone: Optional[str] = None,
    ) -> Tuple[Resume, ParsedData]:
        """
        Full ingestion pipeline for a single resume.

        Steps:
        1. Create/fetch candidate
        2. Store resume file metadata
        3. Extract text (OCR or native)
        4. Parse structured data
        5. Save to database

        Args:
            file_path: Path to uploaded resume file
            candidate_name: Name of candidate
            candidate_email: Optional email
            candidate_phone: Optional phone

        Returns:
            Tuple of (Resume, ParsedData) objects

        Raises:
            ValueError: If file type not supported
            Exception: If processing fails
        """
        try:
            # Step 1: Create or fetch candidate
            candidate = self._create_or_fetch_candidate(
                candidate_name, candidate_email, candidate_phone
            )

            # Step 2: Create Resume record
            file_type = file_path.suffix.lstrip(".").lower()
            if file_type not in ["pdf", "docx", "png", "jpg", "jpeg"]:
                raise ValueError(f"Unsupported file type: {file_type}")

            # Store file to storage folder
            stored_path = self._store_file(file_path, candidate.id)

            resume = Resume(
                candidate_id=candidate.id,
                original_filename=file_path.name,
                storage_path=str(stored_path),
                file_type=file_type,
                status=ResumeStatus.PARSING,
            )
            self.db.add(resume)
            self.db.flush()  # Get resume.id without committing

            # Step 3: Extract text
            extracted_text = self._extract_text(file_path, file_type)

            # Step 4: Parse structured data
            structured_data = self._parse_structured_data(extracted_text, candidate)

            # Step 5: Save ParsedData and update Resume status
            parsed_data = ParsedData(
                resume_id=resume.id,
                raw_text=extracted_text,
                structured_json=json.dumps(structured_data),
            )
            self.db.add(parsed_data)

            resume.status = ResumeStatus.PARSED
            resume.parsed_at = datetime.utcnow()

            self.db.commit()

            return resume, parsed_data

        except Exception as e:
            self.db.rollback()
            # Log failure
            raise Exception(f"Resume ingestion failed: {str(e)}")

    def _create_or_fetch_candidate(
        self, name: str, email: Optional[str], phone: Optional[str]
    ) -> Candidate:
        """Create new candidate or fetch existing by email."""
        if email:
            existing = self.db.query(Candidate).filter_by(email=email).first()
            if existing:
                return existing

        candidate = Candidate(name=name, email=email, phone=phone)
        self.db.add(candidate)
        self.db.flush()
        return candidate

    def _store_file(self, file_path: Path, candidate_id: int) -> Path:
        """Store uploaded file to storage folder."""
        candidate_folder = self.storage_path / f"candidate_{candidate_id}"
        candidate_folder.mkdir(parents=True, exist_ok=True)

        # Generate unique filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        stored_filename = f"{timestamp}_{file_path.name}"
        stored_path = candidate_folder / stored_filename

        # Copy file
        with open(file_path, "rb") as src:
            with open(stored_path, "wb") as dst:
                dst.write(src.read())

        return stored_path

    def _extract_text(self, file_path: Path, file_type: str) -> str:
        """Extract text from resume file."""
        if file_type == "pdf":
            return self._extract_text_from_pdf(file_path)
        elif file_type == "docx":
            return self._extract_text_from_docx(file_path)
        elif file_type in ["png", "jpg", "jpeg"]:
            return ocr_client.extract_text_from_image(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """
        Extract text from PDF.
        First try native text extraction (searchable PDFs).
        Fall back to OCR if no text found.
        """
        try:
            doc = fitz.open(pdf_path)
            full_text = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    full_text.append(text)

            doc.close()

            combined_text = "\n\n".join(full_text)
            if combined_text.strip():
                return combined_text

            # Fallback: use OCR for scanned PDFs
            print(f"[Ingestion] No native text in PDF, falling back to OCR: {pdf_path.name}")
            return ocr_client.extract_text_from_pdf_pages(pdf_path)

        except Exception as e:
            raise Exception(f"PDF extraction failed: {str(e)}")

    def _extract_text_from_docx(self, docx_path: Path) -> str:
        """Extract text from DOCX file."""
        try:
            doc = Document(docx_path)
            paragraphs = [para.text for para in doc.paragraphs]
            return "\n".join(paragraphs)
        except Exception as e:
            raise Exception(f"DOCX extraction failed: {str(e)}")

    def _parse_structured_data(self, text: str, candidate: Candidate) -> Dict[str, Any]:
        """
        Parse extracted text into structured fields.
        Currently: basic parsing with spaCy NER.
        Future: LLM-based extraction for higher accuracy.
        """
        import spacy

        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            print("[Ingestion] spaCy model not found. Install with: python -m spacy download en_core_web_sm")
            nlp = None

        structured = {
            "raw_text": text[:500],  # First 500 chars as preview
            "candidate_id": candidate.id,
            "skills": [],
            "education": [],
            "experience": [],
        }

        if nlp:
            doc = nlp(text)

            # Extract entities
            for ent in doc.ents:
                if ent.label_ == "ORG":
                    structured["experience"].append({"company": ent.text})
                elif ent.label_ == "DATE":
                    structured["experience"].append({"date": ent.text})
                elif ent.label_ == "GPE":
                    structured["experience"].append({"location": ent.text})

        # Save to database
        self._save_parsed_data_to_db(structured, candidate)

        return structured

    def _save_parsed_data_to_db(self, structured: Dict[str, Any], candidate: Candidate):
        """
        Save parsed structured data to database tables.
        Extracts skills, education, and experience from parsed data.
        """
        # Save skills
        for skill_name in structured.get("skills", []):
            skill = Skill(candidate_id=candidate.id, skill_name=skill_name.lower())
            self.db.add(skill)

        # Save education
        for edu in structured.get("education", []):
            education = Education(
                candidate_id=candidate.id,
                institution_name=edu.get("institution", ""),
                degree_name=edu.get("degree", ""),
                field_of_study=edu.get("field", ""),
            )
            self.db.add(education)

        # Save experience
        for exp in structured.get("experience", []):
            experience = Experience(
                candidate_id=candidate.id,
                company_name=exp.get("company", ""),
                job_title=exp.get("title", ""),
                description=exp.get("description", ""),
            )
            self.db.add(experience)

        self.db.flush()


# Singleton instance
_ingestion_service: Optional[IngestionService] = None


def get_ingestion_service(db: Session) -> IngestionService:
    """Factory function to get ingestion service instance."""
    return IngestionService(db)
