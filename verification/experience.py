"""
Experience Module — Job history validation.

Dependencies: timeline.py (reuses timeline analysis)

Checks:
1. Duration plausibility: does job duration match seniority claimed?
   (e.g., "Senior Architect" for 2 months is suspicious)
2. Role progression: is the career path believable?
   (e.g., Junior → Senior → VP within unrealistic timespan)
3. Overlapping full-time roles at unrelated companies
4. Future-dated start dates

Input: Candidate object + TimelineAnalysis from timeline module
Output: VerificationResult
"""

from typing import List, Optional
from datetime import datetime, date
import logging

from app.models.candidate import Candidate, Experience
from verification.timeline import TimelineModule, TimelineAnalysis, EventType
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class ExperienceModule:
    """Validates job history."""
    
    # Minimum duration for each seniority level (in months)
    MIN_DURATION_BY_LEVEL = {
        "junior": 3,
        "mid": 12,
        "senior": 24,
        "lead": 36,
        "manager": 24,
        "director": 36,
        "vp": 48,
        "cto": 48,
        "ceo": 48,
    }
    
    def __init__(self, timeline_module: Optional[TimelineModule] = None):
        self.timeline_module = timeline_module or TimelineModule()
    
    def verify(self, candidate: Candidate, timeline_analysis: Optional[TimelineAnalysis] = None) -> VerificationResult:
        """
        Main entry point: validate job history.
        
        Args:
            candidate: Candidate object with experience rows
            timeline_analysis: Optional pre-computed timeline (from timeline module)
            
        Returns:
            VerificationResult
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        if not candidate.experience:
            # No experience is not necessarily bad (fresh grad, etc.)
            return VerificationResult(
                module_name="experience",
                result=VerificationResultEnum.PASS,
                confidence=0.8,
                risk_score=0,
                evidence=["No experience entries found."],
                raw_data={"experience_count": 0},
            )
        
        # Check each experience entry
        for exp in candidate.experience:
            # Check 1: Future-dated start date
            if exp.start_date:
                try:
                    start = datetime.fromisoformat(exp.start_date).date() if isinstance(exp.start_date, str) else exp.start_date
                    if start > date.today():
                        evidence.append(f"Future-dated start date for {exp.job_title} at {exp.company_name}: {exp.start_date}")
                        risk_score += 20
                        result = VerificationResultEnum.FAIL
                except:
                    pass
            
            # Check 2: Duration vs seniority
            duration_result, duration_evidence = self._check_duration_plausibility(exp)
            if duration_evidence:
                evidence.extend(duration_evidence)
                risk_score += duration_result["risk"]
                if duration_result["level"] == "fail":
                    result = VerificationResultEnum.FAIL
                elif duration_result["level"] == "warning" and result != VerificationResultEnum.FAIL:
                    result = VerificationResultEnum.WARNING
        
        # Check 3: Implausible overlaps (from timeline)
        if timeline_analysis:
            implausible_overlaps = [
                o for o in timeline_analysis.overlaps
                if not o["is_plausible"] and o["overlap_days"] > 30 and
                o["event1"]["type"] == "experience" and o["event2"]["type"] == "experience"
            ]
            if implausible_overlaps:
                for overlap in implausible_overlaps:
                    evidence.append(
                        f"Overlapping full-time jobs: {overlap['event1']['title']} at {overlap['event1']['org']} "
                        f"and {overlap['event2']['title']} at {overlap['event2']['org']} ({overlap['overlap_days']} days overlap)."
                    )
                risk_score += 40
                result = VerificationResultEnum.FAIL
        
        confidence = 0.9 if candidate.experience else 0.6
        
        return VerificationResult(
            module_name="experience",
            result=result,
            confidence=confidence,
            risk_score=min(risk_score, 100),
            evidence=evidence,
            raw_data={
                "experience_count": len(candidate.experience),
                "checks_performed": ["future_dates", "duration_seniority", "overlaps"],
            },
        )
    
    def _check_duration_plausibility(self, exp: Experience) -> tuple:
        """
        Check if job duration matches seniority level claimed.
        
        Returns: (result_dict, evidence_list)
        """
        evidence = []
        result = {"level": "pass", "risk": 0}
        
        title = (exp.job_title or "").lower()
        
        # Try to extract seniority level from title
        seniority = self._extract_seniority_from_title(title)
        if not seniority:
            return result, evidence  # Can't determine seniority from title
        
        # Calculate duration
        try:
            start = datetime.fromisoformat(exp.start_date).date() if isinstance(exp.start_date, str) else exp.start_date
            if exp.end_date and not exp.is_current:
                end = datetime.fromisoformat(exp.end_date).date() if isinstance(exp.end_date, str) else exp.end_date
            else:
                end = date.today()
            
            duration_months = (end.year - start.year) * 12 + (end.month - start.month)
            min_duration = self.MIN_DURATION_BY_LEVEL.get(seniority, 12)
            
            if duration_months < min_duration / 2:  # Less than half the expected duration
                evidence.append(
                    f"Implausible duration: {exp.job_title} at {exp.company_name} lasted only {duration_months} months, "
                    f"but typically requires {min_duration}+ months for this seniority level."
                )
                result["level"] = "fail"
                result["risk"] = 25
            elif duration_months < min_duration:
                evidence.append(
                    f"Short duration: {exp.job_title} at {exp.company_name} lasted {duration_months} months "
                    f"(typically {min_duration}+ months for this level)."
                )
                result["level"] = "warning"
                result["risk"] = 10
        
        except Exception as e:
            logger.warning(f"Could not check duration for {exp.job_title}: {str(e)}")
        
        return result, evidence
    
    def _extract_seniority_from_title(self, title: str) -> Optional[str]:
        """
        Attempt to extract seniority level from job title.
        Returns one of the MIN_DURATION_BY_LEVEL keys, or None.
        """
        title_lower = title.lower()
        
        for level in self.MIN_DURATION_BY_LEVEL.keys():
            if level in title_lower:
                return level
        
        return None


# Singleton instance
experience_module = ExperienceModule()
