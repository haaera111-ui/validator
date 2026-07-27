"""
API endpoints for Phase 1.

Endpoints:
- POST /api/upload - Upload resume file
- GET /api/candidates/{candidate_id} - Get candidate with all related data
- GET /api/resumes/{resume_id} - Get resume details
- POST /api/batch-upload - Batch upload multiple resumes
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional, List
from pathlib import Path
import tempfile

from database.db import get_db
from services.ingestion_service import get_ingestion_service
from app.models.candidate import Candidate, Resume, ParsedData

router = APIRouter(prefix="/api", tags=["resumes"])


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    candidate_name: str = Form(...),
    candidate_email: Optional[str] = Form(None),
    candidate_phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload and process a single resume.
    
    Supported formats: PDF, DOCX, PNG, JPG
    
    Returns:
        {
            "candidate_id": int,
            "resume_id": int,
            "status": "parsed",
            "filename": "resume.pdf",
            "extracted_text_preview": "..."
        }
    """
    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)
        
        # Ingest resume
        service = get_ingestion_service(db)
        resume, parsed_data = service.ingest_resume(
            file_path=tmp_path,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_phone=candidate_phone,
        )
        
        # Clean up temp file
        tmp_path.unlink()
        
        return {
            "candidate_id": resume.candidate_id,
            "resume_id": resume.id,
            "status": resume.status.value,
            "filename": resume.original_filename,
            "message": "Resume processed successfully",
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
):
    """
    Get candidate profile with all related data.
    
    Returns:
        {
            "id": int,
            "name": str,
            "email": str,
            "phone": str,
            "skills": [{"id": int, "skill_name": str}, ...],
            "education": [{"id": int, "institution_name": str, ...}, ...],
            "experience": [{"id": int, "company_name": str, ...}, ...],
            "resumes": [{"id": int, "status": str, ...}, ...]
        }
    """
    candidate = db.query(Candidate).filter_by(id=candidate_id).first()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    return {
        "id": candidate.id,
        "name": candidate.name,
        "email": candidate.email,
        "phone": candidate.phone,
        "skills": [
            {"id": s.id, "skill_name": s.skill_name, "proficiency_level": s.proficiency_level}
            for s in candidate.skills
        ],
        "education": [
            {
                "id": e.id,
                "institution_name": e.institution_name,
                "degree_name": e.degree_name,
                "field_of_study": e.field_of_study,
                "start_year": e.start_year,
                "end_year": e.end_year,
            }
            for e in candidate.education
        ],
        "experience": [
            {
                "id": ex.id,
                "company_name": ex.company_name,
                "job_title": ex.job_title,
                "description": ex.description,
                "start_date": ex.start_date,
                "end_date": ex.end_date,
                "is_current": bool(ex.is_current),
            }
            for ex in candidate.experience
        ],
        "resumes": [
            {
                "id": r.id,
                "filename": r.original_filename,
                "file_type": r.file_type,
                "status": r.status.value,
                "created_at": r.created_at.isoformat(),
                "parsed_at": r.parsed_at.isoformat() if r.parsed_at else None,
            }
            for r in candidate.resumes
        ],
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }


@router.get("/resumes/{resume_id}")
def get_resume(
    resume_id: int,
    db: Session = Depends(get_db),
):
    """
    Get resume details with parsed data.
    
    Returns:
        {
            "id": int,
            "candidate_id": int,
            "filename": str,
            "status": str,
            "parsed_data": {
                "raw_text": str,
                "structured_json": {...}
            }
        }
    """
    resume = db.query(Resume).filter_by(id=resume_id).first()
    
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    parsed_data = db.query(ParsedData).filter_by(resume_id=resume_id).first()
    
    return {
        "id": resume.id,
        "candidate_id": resume.candidate_id,
        "filename": resume.original_filename,
        "file_type": resume.file_type,
        "status": resume.status.value,
        "created_at": resume.created_at.isoformat(),
        "parsed_at": resume.parsed_at.isoformat() if resume.parsed_at else None,
        "parsed_data": {
            "raw_text": parsed_data.raw_text if parsed_data else None,
            "structured_json": parsed_data.structured_json if parsed_data else None,
        } if parsed_data else None,
    }


@router.get("/health")
def health_check():
    """
    Health check endpoint.
    
    Returns:
        {"status": "ok"}
    """
    return {"status": "ok"}
