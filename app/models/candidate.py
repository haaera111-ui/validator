"""
SQLAlchemy ORM models for Phase 1.

Tables:
- Candidate: Central anchor - one per person
- Resume: One per uploaded file
- ParsedData: Full structured extraction for each resume
- Skill: Normalized skills (1:N per candidate)
- Education: Degrees and institutions (1:N per candidate)
- Experience: Job history entries (1:N per candidate)
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from database.db import Base


class Candidate(Base):
    """
    Central candidate entity - one row per person.
    All other tables reference this as the root entity.
    """
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="candidate", cascade="all, delete-orphan")
    education = relationship("Education", back_populates="candidate", cascade="all, delete-orphan")
    experience = relationship("Experience", back_populates="candidate", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Candidate(id={self.id}, name={self.name}, email={self.email})>"


class ResumeStatus(str, enum.Enum):
    """Status tracking for resume processing pipeline."""
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class Resume(Base):
    """
    One row per uploaded resume file.
    Tracks the file itself, its location, type, and parsing status.
    """
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    
    # File metadata
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)  # Relative path within storage folder
    file_type = Column(String(10), nullable=False)  # pdf, docx, png, jpg
    
    # Processing status
    status = Column(SQLEnum(ResumeStatus), default=ResumeStatus.UPLOADED, nullable=False)
    failure_reason = Column(Text, nullable=True)  # If status=failed, what went wrong
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    parsed_at = Column(DateTime, nullable=True)

    # Relationships
    candidate = relationship("Candidate", back_populates="resumes")
    parsed_data = relationship("ParsedData", back_populates="resume", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Resume(id={self.id}, candidate_id={self.candidate_id}, status={self.status})>"


class ParsedData(Base):
    """
    Full structured extraction output for one resume.
    Stores the complete JSON blob of what the parser extracted.
    This is the "master record" for the resume's content.
    """
    __tablename__ = "parsed_data"

    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False, unique=True, index=True)
    
    # Full extraction as JSON (name, email, phone, raw_text, any unstructured fields)
    raw_text = Column(Text, nullable=True)  # Original text extracted from document
    structured_json = Column(Text, nullable=False)  # Full JSON blob with all extracted fields
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    resume = relationship("Resume", back_populates="parsed_data")

    def __repr__(self):
        return f"<ParsedData(id={self.id}, resume_id={self.resume_id})>"


class Skill(Base):
    """
    Extracted skills - one row per skill per candidate.
    Skills are normalized (lowercased, deduplicated).
    """
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    
    skill_name = Column(String(255), nullable=False, index=True)  # Normalized: lowercased, deduplicated
    proficiency_level = Column(String(50), nullable=True)  # e.g., "beginner", "intermediate", "expert"
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    candidate = relationship("Candidate", back_populates="skills")

    def __repr__(self):
        return f"<Skill(id={self.id}, candidate_id={self.candidate_id}, skill={self.skill_name})>"


class Education(Base):
    """
    Education entries - one row per degree/institution.
    """
    __tablename__ = "education"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    
    institution_name = Column(String(255), nullable=False)
    degree_name = Column(String(255), nullable=True)  # e.g., "Bachelor of Science", "MBA"
    field_of_study = Column(String(255), nullable=True)  # e.g., "Computer Science"
    start_year = Column(Integer, nullable=True)
    end_year = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    candidate = relationship("Candidate", back_populates="education")

    def __repr__(self):
        return f"<Education(id={self.id}, institution={self.institution_name}, degree={self.degree_name})>"


class Experience(Base):
    """
    Work experience entries - one row per job.
    """
    __tablename__ = "experience"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    
    company_name = Column(String(255), nullable=False)
    job_title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(String(50), nullable=True)  # Stored as string to handle partial dates (e.g., "2020-01" or "January 2020")
    end_date = Column(String(50), nullable=True)  # NULL means "currently employed"
    is_current = Column(Integer, default=0, nullable=False)  # 1 if end_date is NULL/current
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    candidate = relationship("Candidate", back_populates="experience")

    def __repr__(self):
        return f"<Experience(id={self.id}, company={self.company_name}, title={self.job_title})>"
