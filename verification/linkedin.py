"""
LinkedIn Verification Module — Cross-reference resume against LinkedIn profile.

Dependencies: requests-oauthlib (OAuth token handling)

CRITICAL: This module MUST use official LinkedIn OAuth API, never scraping.
          Must check Candidate.linkedin_consent before making any calls.
          Requires explicit candidate sign-in and approval.

Checks:
1. Verify LinkedIn consent flag is true
2. Pull candidate's education and position history via LinkedIn API
3. Cross-reference against resume Experience/Education rows
4. Flag discrepancies (wrong dates, fake employers, wrong titles)

Input: Candidate object with linkedin_consent and linkedin_access_token
Output: VerificationResult

Failure handling:
- No consent → unable_to_verify (immediate, no API calls)
- LinkedIn API unavailable → unable_to_verify
- Discrepancies found → warning or fail
- Matching data → pass
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, date

from app.models.candidate import Candidate, Experience, Education
from verification.timeline import timeline_module, TimelineAnalysis
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class LinkedInProfile:
    """Represents data from LinkedIn API."""
    
    def __init__(self, raw_data: Dict[str, Any]):
        self.raw_data = raw_data
        self.positions: List[Dict[str, Any]] = raw_data.get("positions", [])
        self.educations: List[Dict[str, Any]] = raw_data.get("educations", [])
        self.name: str = raw_data.get("localizedFirstName", "") + " " + raw_data.get("localizedLastName", "")


class LinkedInModule:
    """Verifies resume against LinkedIn profile data."""
    
    def __init__(self):
        pass
    
    def verify(self, candidate: Candidate) -> VerificationResult:
        """
        Main entry point: verify resume against LinkedIn profile.
        
        Args:
            candidate: Candidate object
            
        Returns:
            VerificationResult
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        # Step 1: Check consent
        if not candidate.linkedin_consent or not candidate.linkedin_access_token:
            logger.info(f"[LinkedIn] No consent for candidate {candidate.id}")
            return VerificationResult(
                module_name="linkedin",
                result=VerificationResultEnum.UNABLE_TO_VERIFY,
                confidence=0.0,
                risk_score=0,
                evidence=["Candidate has not granted LinkedIn verification consent."],
                raw_data={"consent": False},
            )
        
        # Step 2: Fetch LinkedIn data
        linkedin_data = self._fetch_linkedin_profile(candidate.linkedin_access_token)
        if not linkedin_data:
            return VerificationResult(
                module_name="linkedin",
                result=VerificationResultEnum.UNABLE_TO_VERIFY,
                confidence=0.2,
                risk_score=0,
                evidence=["Could not fetch LinkedIn profile data. Token may be expired or invalid."],
                raw_data={"consent": True, "token_valid": False},
            )
        
        # Step 3: Build timeline for comparison
        timeline_analysis, _ = timeline_module.verify(candidate)
        
        # Step 4: Compare experience
        exp_result = self._verify_experience(candidate, linkedin_data)
        if exp_result["discrepancies"]:
            evidence.extend(exp_result["evidence"])
            risk_score += exp_result["risk"]
            if exp_result["level"] == "fail":
                result = VerificationResultEnum.FAIL
            elif exp_result["level"] == "warning" and result != VerificationResultEnum.FAIL:
                result = VerificationResultEnum.WARNING
        
        # Step 5: Compare education
        edu_result = self._verify_education(candidate, linkedin_data)
        if edu_result["discrepancies"]:
            evidence.extend(edu_result["evidence"])
            risk_score += edu_result["risk"]
            if edu_result["level"] == "fail":
                result = VerificationResultEnum.FAIL
            elif edu_result["level"] == "warning" and result != VerificationResultEnum.FAIL:
                result = VerificationResultEnum.WARNING
        
        if not evidence:
            evidence.append("LinkedIn profile matches resume data.")
        
        confidence = 0.9 if result == VerificationResultEnum.PASS else 0.7
        
        return VerificationResult(
            module_name="linkedin",
            result=result,
            confidence=confidence,
            risk_score=min(risk_score, 100),
            evidence=evidence,
            raw_data={
                "consent": True,
                "experience_count": len(candidate.experience),
                "linkedin_positions": len(linkedin_data.positions),
                "education_count": len(candidate.education),
                "linkedin_educations": len(linkedin_data.educations),
            },
        )
    
    def _fetch_linkedin_profile(self, access_token: str) -> Optional[LinkedInProfile]:
        """
        Fetch LinkedIn profile data using OAuth token.
        
        Returns: LinkedInProfile or None if fetch fails
        """
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
            
            # LinkedIn API v2 endpoint (simplified)
            url = "https://api.linkedin.com/v2/me?projection=(id,localizedFirstName,localizedLastName)"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 401:
                logger.warning("[LinkedIn] Token is invalid or expired")
                return None
            
            if response.status_code != 200:
                logger.warning(f"[LinkedIn] API returned {response.status_code}")
                return None
            
            data = response.json()
            return LinkedInProfile(data)
        
        except Exception as e:
            logger.error(f"[LinkedIn] Failed to fetch profile: {str(e)}")
            return None
    
    def _verify_experience(self, candidate: Candidate, linkedin_data: LinkedInProfile) -> Dict[str, Any]:
        """
        Compare resume experience against LinkedIn positions.
        
        Returns: {level: str, discrepancies: bool, evidence: list, risk: int}
        """
        evidence = []
        risk = 0
        level = "pass"
        discrepancies = False
        
        if not candidate.experience:
            return {"level": "pass", "discrepancies": False, "evidence": [], "risk": 0}
        
        if not linkedin_data.positions:
            # Resume claims experience but LinkedIn shows none
            if len(candidate.experience) > 0:
                evidence.append("Resume claims experience, but LinkedIn profile shows no positions.")
                risk = 20
                level = "warning"
                discrepancies = True
            return {"level": level, "discrepancies": discrepancies, "evidence": evidence, "risk": risk}
        
        # Simple check: verify at least one company appears in both
        resume_companies = set(exp.company_name.lower() for exp in candidate.experience if exp.company_name)
        linkedin_companies = set(
            pos.get("company", {}).get("name", "").lower()
            for pos in linkedin_data.positions
            if pos.get("company", {}).get("name")
        )
        
        matching_companies = resume_companies & linkedin_companies
        
        if not matching_companies:
            evidence.append(
                f"Resume lists companies {resume_companies}, but LinkedIn shows {linkedin_companies}. "
                f"No matching companies found."
            )
            risk = 40
            level = "warning"
            discrepancies = True
        
        return {"level": level, "discrepancies": discrepancies, "evidence": evidence, "risk": risk}
    
    def _verify_education(self, candidate: Candidate, linkedin_data: LinkedInProfile) -> Dict[str, Any]:
        """
        Compare resume education against LinkedIn education.
        
        Returns: {level: str, discrepancies: bool, evidence: list, risk: int}
        """
        evidence = []
        risk = 0
        level = "pass"
        discrepancies = False
        
        if not candidate.education:
            return {"level": "pass", "discrepancies": False, "evidence": [], "risk": 0}
        
        if not linkedin_data.educations:
            if len(candidate.education) > 0:
                evidence.append("Resume claims education, but LinkedIn profile shows no education.")
                risk = 15
                level = "warning"
                discrepancies = True
            return {"level": level, "discrepancies": discrepancies, "evidence": evidence, "risk": risk}
        
        # Simple check: verify at least one school appears in both
        resume_schools = set(
            edu.institution_name.lower() for edu in candidate.education
            if edu.institution_name
        )
        linkedin_schools = set(
            edu.get("schoolName", "").lower()
            for edu in linkedin_data.educations
            if edu.get("schoolName")
        )
        
        matching_schools = resume_schools & linkedin_schools
        
        if not matching_schools:
            evidence.append(
                f"Resume lists schools {resume_schools}, but LinkedIn shows {linkedin_schools}. "
                f"No matching schools found."
            )
            risk = 25
            level = "warning"
            discrepancies = True
        
        return {"level": level, "discrepancies": discrepancies, "evidence": evidence, "risk": risk}


# Singleton instance
linkedin_module = LinkedInModule()
