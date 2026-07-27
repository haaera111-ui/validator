"""
Shared verification result schema.
All verification modules (Phase 2-4) return exactly this shape.
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Dict, Any, List


class VerificationResultEnum(str, Enum):
    """Possible outcomes for a verification check."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    UNABLE_TO_VERIFY = "unable_to_verify"


class VerificationResult(BaseModel):
    """
    Standard output schema for all verification modules.
    
    Every module (Phase 2-4) returns exactly one or more of these.
    The orchestrator in Phase 5 aggregates all results into a final Trust Score.
    """
    
    module_name: str = Field(
        ...,
        description="Name of the verification module (e.g., 'timeline', 'experience', 'education', 'company')"
    )
    
    result: VerificationResultEnum = Field(
        ...,
        description="Overall result: pass, fail, warning, or unable_to_verify"
    )
    
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How confident the module is in this result (0-1)"
    )
    
    risk_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="This module's contribution to fraud likelihood (0-100)"
    )
    
    evidence: List[str] = Field(
        default_factory=list,
        description="Plain-language findings that explain the result. Human-readable for reports."
    )
    
    raw_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Debug data: dates, overlaps, gaps, API responses, etc. Used for audit trail."
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "module_name": self.module_name,
            "result": self.result.value,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "evidence": self.evidence,
            "raw_data": self.raw_data,
        }
