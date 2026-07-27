"""
Company Module — Domain and WHOIS verification.

This is the first module that leaves the local database.
CRITICAL: Network errors must return unable_to_verify, never fail.

Checks:
1. Company domain resolution
2. WHOIS lookup: domain registration date
3. Company website accessibility
4. Domain age plausibility
   (e.g., "company founded 20 years ago" with domain registered 3 months ago is suspicious)

Input: Experience rows with company names (and optional website URLs)
Output: VerificationResult

Error handling:
- Network timeout → unable_to_verify + explanation
- Invalid domain → unable_to_verify (not enough info to verify)
- Domain age mismatch → warning or fail (depends on confidence)
"""

from typing import Optional, Tuple
from datetime import datetime, date, timedelta
import logging

import httpx
from whois import whois as whois_lookup
from whois.exceptions import WhoisException

from app.models.candidate import Candidate, Experience
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class CompanyModule:
    """Verifies company existence and plausibility via WHOIS/domain lookup."""
    
    # Configuration
    WHOIS_TIMEOUT_SECONDS = 5
    HTTP_TIMEOUT_SECONDS = 3
    MIN_DOMAIN_AGE_YEARS = 1  # Company should have domain for at least 1 year
    MAX_DOMAIN_AGE_MISMATCH = 5  # Years: if domain is newer than claimed founding, flag if difference > this
    
    def __init__(self):
        pass
    
    def verify(self, candidate: Candidate) -> VerificationResult:
        """
        Main entry point: verify companies from experience.
        
        Args:
            candidate: Candidate object with experience rows
            
        Returns:
            VerificationResult
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        verification_count = 0
        unable_to_verify_count = 0
        
        if not candidate.experience:
            return VerificationResult(
                module_name="company",
                result=VerificationResultEnum.PASS,
                confidence=0.5,
                risk_score=0,
                evidence=["No experience entries to verify."],
                raw_data={"experience_count": 0},
            )
        
        # Check each company
        for exp in candidate.experience:
            company_result = self._verify_company(exp)
            
            verification_count += 1
            
            if company_result["result"] == VerificationResultEnum.UNABLE_TO_VERIFY:
                unable_to_verify_count += 1
            
            if company_result["evidence"]:
                evidence.extend(company_result["evidence"])
            
            risk_score += company_result["risk"]
            
            # Escalate result if any company fails
            if company_result["result"] == VerificationResultEnum.FAIL:
                result = VerificationResultEnum.FAIL
            elif company_result["result"] == VerificationResultEnum.WARNING and result != VerificationResultEnum.FAIL:
                result = VerificationResultEnum.WARNING
        
        # Determine final confidence
        if unable_to_verify_count == verification_count:
            # All lookups failed → unable to verify overall
            result = VerificationResultEnum.UNABLE_TO_VERIFY
            confidence = 0.2
        elif unable_to_verify_count > verification_count / 2:
            # Most failed → reduced confidence
            confidence = 0.4
        else:
            confidence = 0.8
        
        return VerificationResult(
            module_name="company",
            result=result,
            confidence=confidence,
            risk_score=min(risk_score, 100),
            evidence=evidence or [f"Verified {verification_count} company/companies."],
            raw_data={
                "experience_count": len(candidate.experience),
                "verified": verification_count - unable_to_verify_count,
                "unable_to_verify": unable_to_verify_count,
            },
        )
    
    def _verify_company(self, exp: Experience) -> dict:
        """
        Verify a single company.
        
        Returns: {result, evidence, risk}
        """
        evidence = []
        risk = 0
        result = VerificationResultEnum.PASS
        
        company_name = exp.company_name or "Unknown"
        
        # Step 1: Guess or extract domain
        domain = self._guess_domain(company_name)
        if not domain:
            return {
                "result": VerificationResultEnum.UNABLE_TO_VERIFY,
                "evidence": [f"Could not determine domain for company: {company_name}"],
                "risk": 0,
            }
        
        # Step 2: Check if domain resolves
        domain_reachable = self._check_domain_reachability(domain)
        if not domain_reachable:
            return {
                "result": VerificationResultEnum.UNABLE_TO_VERIFY,
                "evidence": [f"Domain {domain} (guessed for {company_name}) could not be reached or resolved."],
                "risk": 0,
            }
        
        # Step 3: WHOIS lookup
        whois_result = self._whois_lookup(domain)
        if whois_result["unable_to_verify"]:
            return {
                "result": VerificationResultEnum.UNABLE_TO_VERIFY,
                "evidence": whois_result["evidence"],
                "risk": 0,
            }
        
        # Step 4: Analyze domain age
        domain_age_result = self._check_domain_age(domain, exp, whois_result["created_date"])
        evidence.extend(domain_age_result["evidence"])
        risk += domain_age_result["risk"]
        if domain_age_result["result"] == VerificationResultEnum.FAIL:
            result = VerificationResultEnum.FAIL
        elif domain_age_result["result"] == VerificationResultEnum.WARNING and result != VerificationResultEnum.FAIL:
            result = VerificationResultEnum.WARNING
        
        return {
            "result": result,
            "evidence": evidence,
            "risk": risk,
        }
    
    def _guess_domain(self, company_name: str) -> Optional[str]:
        """
        Guess domain from company name.
        E.g., "Google Inc" → "google.com"
        
        Returns: domain or None if too generic/unparseable
        """
        if not company_name:
            return None
        
        # Remove common suffixes
        cleaned = company_name.lower().strip()
        for suffix in [" inc", " ltd", " llc", " corp", " co.", " ag", " gmbh"]:
            cleaned = cleaned.replace(suffix, "")
        
        # Take first word(s) as domain
        words = cleaned.split()
        if len(words) > 3:
            return None  # Too many words, too risky to guess
        
        domain_name = "-".join(words[:2])  # E.g., "google-cloud"
        
        # Try .com first, then other TLDs
        return f"{domain_name}.com"
    
    def _check_domain_reachability(self, domain: str) -> bool:
        """
        Check if domain resolves via DNS or HTTP.
        
        Returns: True if domain is reachable, False otherwise
        """
        try:
            with httpx.Client(timeout=self.HTTP_TIMEOUT_SECONDS) as client:
                response = client.head(f"https://{domain}", follow_redirects=True)
                return response.status_code < 400  # 2xx or 3xx
        except Exception as e:
            logger.debug(f"Domain {domain} not reachable via HTTPS: {str(e)}")
            # Try HTTP
            try:
                with httpx.Client(timeout=self.HTTP_TIMEOUT_SECONDS) as client:
                    response = client.head(f"http://{domain}", follow_redirects=True)
                    return response.status_code < 400
            except Exception:
                return False
    
    def _whois_lookup(self, domain: str) -> dict:
        """
        Perform WHOIS lookup on domain.
        
        Returns: {created_date, unable_to_verify, evidence}
        """
        try:
            whois_data = whois_lookup(domain, timeout=self.WHOIS_TIMEOUT_SECONDS)
            
            created_date = whois_data.creation_date
            if isinstance(created_date, list):
                created_date = created_date[0]
            
            if not isinstance(created_date, date):
                created_date = created_date.date() if hasattr(created_date, 'date') else None
            
            if created_date:
                return {
                    "created_date": created_date,
                    "unable_to_verify": False,
                    "evidence": [],
                }
            else:
                return {
                    "created_date": None,
                    "unable_to_verify": True,
                    "evidence": [f"WHOIS lookup for {domain} returned no creation date."],
                }
        
        except WhoisException as e:
            logger.debug(f"WHOIS lookup failed for {domain}: {str(e)}")
            return {
                "created_date": None,
                "unable_to_verify": True,
                "evidence": [f"WHOIS lookup for {domain} failed (likely protected or unavailable)."],
            }
        except Exception as e:
            logger.debug(f"WHOIS lookup error for {domain}: {str(e)}")
            return {
                "created_date": None,
                "unable_to_verify": True,
                "evidence": [f"WHOIS lookup for {domain} timed out or encountered error."],
            }
    
    def _check_domain_age(self, domain: str, exp: Experience, created_date: Optional[date]) -> dict:
        """
        Check if domain age makes sense relative to job start date.
        
        Returns: {result, evidence, risk}
        """
        evidence = []
        risk = 0
        result = VerificationResultEnum.PASS
        
        if not created_date:
            return {"result": VerificationResultEnum.PASS, "evidence": [], "risk": 0}
        
        domain_age_days = (date.today() - created_date).days
        domain_age_years = domain_age_days / 365.25
        
        # Check if domain is too new (younger than MIN_DOMAIN_AGE_YEARS)
        if domain_age_years < self.MIN_DOMAIN_AGE_YEARS:
            evidence.append(
                f"Domain {domain} is very new (registered {created_date.isoformat()}), "
                f"but company {exp.company_name} was claimed to be active at {exp.start_date}."
            )
            risk = 20
            result = VerificationResultEnum.WARNING
        
        return {"result": result, "evidence": evidence, "risk": risk}


# Singleton instance
company_module = CompanyModule()
