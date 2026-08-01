"""
Certificate model for storing certificate records.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database.db import Base


class Certificate(Base):
    """
    Certificate record for a candidate.
    Stores certificate metadata and verification status.
    """
    
    __tablename__ = "certificates"
    
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Certificate details
    certificate_name = Column(String(255), nullable=False)
    issuing_body = Column(String(255), nullable=False)  # e.g., "AWS", "Google"
    certificate_id = Column(String(255), nullable=True)  # Certificate ID/number from issuer
    issue_date = Column(DateTime, nullable=True)
    expiration_date = Column(DateTime, nullable=True)
    
    # Verification
    verification_status = Column(String(50), default="unverified")  # unverified, verified, failed, unable_to_verify
    verification_timestamp = Column(DateTime, nullable=True)
    verification_notes = Column(Text, nullable=True)
    
    # QR code
    qr_code_url = Column(String(500), nullable=True)  # URL from QR code if present
    qr_code_present = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship
    candidate = relationship("Candidate", back_populates="certificates")


# Add to Candidate model
from app.models.candidate import Candidate as _Candidate
if not hasattr(_Candidate, 'certificates'):
    _Candidate.certificates = relationship("Certificate", back_populates="candidate", cascade="all, delete-orphan")
    _Candidate.linkedin_consent = Column(Boolean, default=False)
    _Candidate.linkedin_access_token = Column(String(500), nullable=True)  # Encrypted in production
