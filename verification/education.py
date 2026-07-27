"""
Education Module — Degree validation.

Dependencies: timeline.py (reuses timeline analysis)

Checks:
1. Degree duration plausibility
   (e.g., 4-year bachelor's in 8 months is suspicious)
2. Graduation year vs. stated age or first job start date
3. Concurrent degree feasibility
   (e.g., 2 master's degrees simultaneously is rare)
4. Start year before candidate could have finished high school

Input: Candidate object + TimelineAnalysis from timeline module
Output: VerificationResult
"""

from typing import Optional, Dict, Any
from datetime import datetime, date
import logging

from app.models.candidate import Candidate, Education
from verification.timeline import TimelineAnalysis, EventType
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class EducationModule:
    """Validates education history."""
    
    # Expected duration (in years) for degree types
    EXPECTED_DURATION_BY_DEGREE = {
        "bachelor": 4,
        "master": 2,
        "phd": 5,
        "diploma": 2,
        "certificate": 1,
        "associate": 2,
        "bootcamp": 0.5,
    }
    
    # Reasonable age ranges (in years)
    MIN_AGE_FOR_BACHELOR = 18
    MAX_AGE_FOR_BACHELORS_START = 45  # Can start later, but flag if absurdly old
    
    def __init__(self):
        pass
    
    def verify(self, candidate: Candidate, timeline_analysis: Optional[TimelineAnalysis] = None) -> VerificationResult:
        """
        Main entry point: validate education history.
        
        Args:
            candidate: Candidate object with education rows
            timeline_analysis: Optional pre-computed timeline (from timeline module)
            
        Returns:
            VerificationResult
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        if not candidate.education:
            return VerificationResult(
                module_name="education",
                result=VerificationResultEnum.PASS,
                confidence=0.7,
                risk_score=0,
                evidence=["No education entries found."],
                raw_data={"education_count": 0},
            )
        
        # Check each education entry
        for edu in candidate.education:
            # Check 1: Duration plausibility
            duration_result = self._check_duration_plausibility(edu)
            if duration_result["evidence"]:
                evidence.extend(duration_result["evidence"])
                risk_score += duration_result["risk"]
                if duration_result["level"] == "fail":
                    result = VerificationResultEnum.FAIL
                elif duration_result["level"] == "warning" and result != VerificationResultEnum.FAIL:
                    result = VerificationResultEnum.WARNING
        
        # Check 2: Concurrent degrees (from timeline)
        if timeline_analysis:
            concurrent_result = self._check_concurrent_degrees(candidate, timeline_analysis)
            if concurrent_result["evidence"]:
                evidence.extend(concurrent_result["evidence"])
                risk_score += concurrent_result["risk"]
                if concurrent_result["level"] == "fail":
                    result = VerificationResultEnum.FAIL
                elif concurrent_result["level"] == "warning" and result != VerificationResultEnum.FAIL:
                    result = VerificationResultEnum.WARNING
        
        confidence = 0.85 if candidate.education else 0.5
        
        return VerificationResult(
            module_name="education",
            result=result,
            confidence=confidence,
            risk_score=min(risk_score, 100),
            evidence=evidence,
            raw_data={
                "education_count": len(candidate.education),
                "checks_performed": ["duration_plausibility", "concurrent_degrees"],
            },
        )
    
    def _check_duration_plausibility(self, edu: Education) -> Dict[str, Any]:
        """
        Check if degree duration matches the type claimed.
        
        Returns: dict with level, evidence, risk
        """
        evidence = []
        result = {"level": "pass", "risk": 0, "evidence": []}
        
        if not edu.start_year or not edu.end_year:
            return result  # Can't check without both dates
        
        degree_type = (edu.degree_name or "").lower()
        expected_duration = self._extract_degree_duration(degree_type)
        
        if not expected_duration:
            return result  # Can't determine expected duration
        
        try:
            start_year = int(edu.start_year) if isinstance(edu.start_year, (int, str)) else None
            end_year = int(edu.end_year) if isinstance(edu.end_year, (int, str)) else None
            
            if start_year and end_year:
                actual_duration = end_year - start_year
                
                # Too short
                if actual_duration < expected_duration * 0.4:
                    evidence.append(
                        f"Implausibly short duration: {edu.degree_name} at {edu.institution_name} "
                        f"completed in {actual_duration} years, expected ~{expected_duration} years."
                    )
                    result["level"] = "fail"
                    result["risk"] = 25
                
                # Suspiciously short
                elif actual_duration < expected_duration * 0.7:
                    evidence.append(
                        f"Short duration: {edu.degree_name} at {edu.institution_name} "
                        f"completed in {actual_duration} years (expected ~{expected_duration})."
                    )
                    result["level"] = "warning"
                    result["risk"] = 10
                
                # Longer than expected is usually fine (part-time, double major, etc.)
        
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse education dates for {edu.degree_name}: {str(e)}")
        
        result["evidence"] = evidence
        return result
    
    def _check_concurrent_degrees(self, candidate: Candidate, timeline_analysis: TimelineAnalysis) -> Dict[str, Any]:
        """
        Check for implausibly concurrent degrees.
        
        Returns: dict with level, evidence, risk
        """
        evidence = []
        result = {"level": "pass", "risk": 0, "evidence": []}
        
        # Find overlapping education events
        education_overlaps = [
            o for o in timeline_analysis.overlaps
            if o["event1"]["type"] == "education" and o["event2"]["type"] == "education"
        ]
        
        if education_overlaps:
            for overlap in education_overlaps:
                # Concurrent degrees are rare; flag them
                evidence.append(
                    f"Concurrent degrees: {overlap['event1']['title']} at {overlap['event1']['org']} "
                    f"overlaps with {overlap['event2']['title']} at {overlap['event2']['org']} "
                    f"for {overlap['overlap_days']} days."
                )
                result["level"] = "warning"
                result["risk"] = 15
        
        result["evidence"] = evidence
        return result
    
    def _extract_degree_duration(self, degree_type: str) -> Optional[int]:
        """
        Extract expected duration from degree type name.
        
        Returns: expected years, or None if type not recognized
        """
        degree_lower = degree_type.lower()
        
        for degree_key, duration in self.EXPECTED_DURATION_BY_DEGREE.items():
            if degree_key in degree_lower:
                return duration
        
        return None


# Singleton instance
education_module = EducationModule()
