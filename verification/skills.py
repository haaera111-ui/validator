"""
Skills Verification Module — Semantic skill validation.

Dependencies: embeddings.py (for semantic similarity)
              llm_client.py (for ambiguous cases)

Checks:
1. Hard-to-verify skills (e.g., "Machine Learning") against experience descriptions
2. Use semantic embedding to check if skill is mentioned in experience context
3. For ambiguous cases, query LLM with narrow, structured prompt
4. Flag skills with no supporting evidence

Input: Candidate object with Skill and Experience rows
Output: VerificationResult

Design note: Only checks against resume text, not external sources (GitHub, etc.)
             Cross-checking skills vs. actual GitHub activity is Phase 4's job.
"""

import logging
from typing import List, Dict, Any, Optional

from app.models.candidate import Candidate, Skill, Experience
from ai.embeddings import embeddings_client
from ai.llm_client import llm_client, LLMClientException, JSONParseException
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class SkillsModule:
    """Validates claimed skills against experience text."""
    
    # Skills that are hard to verify by keyword alone (require semantic check)
    HARD_TO_VERIFY_SKILLS = {
        "machine learning",
        "deep learning",
        "artificial intelligence",
        "data science",
        "leadership",
        "project management",
        "problem solving",
        "communication",
        "strategic thinking",
    }
    
    # Easy-to-verify skills (keywords are reliable)
    EASY_TO_VERIFY_KEYWORDS = {
        "python": ["python", "py"],
        "java": ["java"],
        "javascript": ["javascript", "js", "nodejs", "node.js"],
        "react": ["react", "reactjs"],
        "aws": ["aws", "amazon web services"],
        "docker": ["docker"],
        "kubernetes": ["kubernetes", "k8s"],
        "sql": ["sql", "postgresql", "mysql", "oracle"],
        "git": ["git", "github", "gitlab"],
        "linux": ["linux", "unix"],
    }
    
    def __init__(self):
        pass
    
    def verify(self, candidate: Candidate) -> VerificationResult:
        """
        Main entry point: validate skills.
        
        Args:
            candidate: Candidate object with skill and experience rows
            
        Returns:
            VerificationResult
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        if not candidate.skills:
            return VerificationResult(
                module_name="skills",
                result=VerificationResultEnum.PASS,
                confidence=0.7,
                risk_score=0,
                evidence=["No skills claimed."],
                raw_data={"skill_count": 0},
            )
        
        # Combine all experience text into one block
        experience_text = self._combine_experience_text(candidate)
        
        if not experience_text:
            # No experience to verify against
            return VerificationResult(
                module_name="skills",
                result=VerificationResultEnum.PASS,
                confidence=0.5,
                risk_score=0,
                evidence=["No experience to verify skills against."],
                raw_data={"skill_count": len(candidate.skills)},
            )
        
        # Check each skill
        unsupported_skills = []
        checked_skills = 0
        
        for skill in candidate.skills:
            skill_name = skill.skill_name.lower()
            
            # Check 1: Easy keyword-based check
            if self._check_keyword_match(skill_name, experience_text):
                checked_skills += 1
                continue  # Skill found via keywords
            
            # Check 2: Hard-to-verify skills need semantic/LLM check
            if skill_name in self.HARD_TO_VERIFY_SKILLS or len(skill_name) > 2:
                skill_check = self._check_skill_semantic(
                    skill_name,
                    experience_text,
                    candidate.name,
                )
                checked_skills += 1
                
                if not skill_check["supported"]:
                    unsupported_skills.append(skill)
                    evidence.append(skill_check["evidence"])
                    risk_score += skill_check["risk"]
        
        # Determine result
        if unsupported_skills:
            result = VerificationResultEnum.WARNING
            evidence.insert(0, f"Found {len(unsupported_skills)} skill(s) not clearly supported by experience.")
        
        confidence = 0.85 if checked_skills > 0 else 0.4
        
        return VerificationResult(
            module_name="skills",
            result=result,
            confidence=confidence,
            risk_score=min(risk_score, 100),
            evidence=evidence,
            raw_data={
                "skill_count": len(candidate.skills),
                "checked_skills": checked_skills,
                "unsupported_skills": len(unsupported_skills),
            },
        )
    
    def _combine_experience_text(self, candidate: Candidate) -> str:
        """
        Combine all experience descriptions into one text block.
        """
        parts = []
        for exp in candidate.experience:
            if exp.description:
                parts.append(exp.description)
            if exp.job_title:
                parts.append(f"Role: {exp.job_title}")
            if exp.company_name:
                parts.append(f"Company: {exp.company_name}")
        return " ".join(parts)
    
    def _check_keyword_match(self, skill_name: str, experience_text: str) -> bool:
        """
        Check if skill is mentioned by keywords in experience text.
        
        Returns: True if skill found, False otherwise
        """
        experience_lower = experience_text.lower()
        
        # Check if skill name itself is in experience
        if skill_name in experience_lower:
            return True
        
        # Check for known keywords for this skill
        for skill_key, keywords in self.EASY_TO_VERIFY_KEYWORDS.items():
            if skill_key == skill_name or skill_name.startswith(skill_key):
                for keyword in keywords:
                    if keyword in experience_lower:
                        return True
        
        return False
    
    def _check_skill_semantic(
        self,
        skill_name: str,
        experience_text: str,
        candidate_name: str,
    ) -> Dict[str, Any]:
        """
        Use embedding + LLM to check if skill is semantically supported.
        
        Returns: {supported: bool, evidence: str, risk: int}
        """
        # First try semantic similarity via embeddings
        if embeddings_client:
            try:
                skill_description = f"Experience with {skill_name}"
                matches = embeddings_client.query_similar_resumes(
                    skill_description,
                    top_k=1,
                    min_similarity=0.80,
                )
                
                # If we found a high similarity match in the experience, assume supported
                if matches:
                    logger.debug(f"Skill '{skill_name}' supported via semantic similarity")
                    return {"supported": True, "evidence": "", "risk": 0}
            except Exception as e:
                logger.debug(f"Semantic check failed for skill '{skill_name}': {str(e)}")
        
        # Fall back to LLM check for ambiguous cases
        if llm_client:
            try:
                prompt = (
                    f"Based on this experience: '{experience_text[:500]}',\n\n"
                    f"Does this plausibly demonstrate the skill '{skill_name}'?\n\n"
                    f"Respond with ONLY valid JSON: {{\"supported\": true/false, \"reason\": \"short explanation\"}}"
                )
                
                result = llm_client.query_json(
                    prompt,
                    system_prompt="You are a skills analyzer. Respond ONLY with JSON, no markdown."
                )
                
                supported = result.get("supported", False)
                reason = result.get("reason", "")
                
                if not supported:
                    return {
                        "supported": False,
                        "evidence": f"Skill '{skill_name}' not supported by experience: {reason}",
                        "risk": 15,
                    }
                else:
                    return {"supported": True, "evidence": "", "risk": 0}
            
            except (LLMClientException, JSONParseException) as e:
                logger.warning(f"LLM skill check failed for '{skill_name}': {str(e)}")
                # On LLM failure, give benefit of doubt (don't flag as unsupported)
                return {"supported": True, "evidence": "", "risk": 0}
        
        # No LLM or embeddings available, assume supported
        logger.debug(f"No LLM/embeddings available, assuming skill '{skill_name}' is supported")
        return {"supported": True, "evidence": "", "risk": 0}


# Singleton instance
skills_module = SkillsModule()
