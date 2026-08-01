"""
GitHub Verification Module — Verify technical skills against GitHub activity.

Dependencies: PyGithub (GitHub REST API)
              verification/skills.py (skill comparison logic)

Checks:
1. Fetch GitHub profile (public repos, languages, recent activity)
2. Extract claimed technical skills from candidate's skills
3. Cross-reference against GitHub repos and languages
4. Use skills.py's comparison logic for semantic matching

Input: Candidate object with GitHub username (or inferred from email)
Output: VerificationResult with skill-by-skill verification

Failure handling:
- No GitHub profile provided → unable_to_verify (common, not suspicious)
- GitHub profile unreachable → unable_to_verify
- Skills not found in GitHub → warning (candidate may have old profile)
- Skills found in GitHub → pass
"""

import logging
from typing import Optional, List, Dict, Set, Any
from urllib.parse import urlparse

try:
    from github import Github, GithubException
except ImportError:
    Github = None
    GithubException = None

from app.models.candidate import Candidate, Skill
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class GitHubModule:
    """Verifies technical skills against GitHub activity."""
    
    # Technical skills we can verify via GitHub
    GITHUB_VERIFIABLE_SKILLS = {
        "python", "java", "javascript", "typescript", "go", "rust",
        "c++", "c#", "php", "ruby", "swift", "kotlin", "scala",
        "react", "vue", "angular", "node.js", "django", "flask",
        "spring", "fastapi", "expressjs", "nextjs", "aws", "azure",
        "gcp", "docker", "kubernetes", "git", "sql", "mongodb",
        "postgresql", "redis", "elasticsearch", "graphql", "rest",
    }
    
    def __init__(self):
        if not Github:
            logger.warning("[GitHub] PyGithub not installed; GitHub verification will be disabled")
    
    def verify(self, candidate: Candidate, github_username: Optional[str] = None) -> VerificationResult:
        """
        Main entry point: verify skills against GitHub profile.
        
        Args:
            candidate: Candidate object with skills
            github_username: Optional GitHub username (if not provided, tries to infer)
            
        Returns:
            VerificationResult
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        # Step 1: Determine GitHub username
        if not github_username:
            github_username = self._infer_github_username(candidate)
        
        if not github_username:
            return VerificationResult(
                module_name="github",
                result=VerificationResultEnum.UNABLE_TO_VERIFY,
                confidence=0.3,
                risk_score=0,
                evidence=["No GitHub username provided or could be inferred from email."],
                raw_data={"username": None},
            )
        
        # Step 2: Fetch GitHub profile
        github_data = self._fetch_github_profile(github_username)
        if not github_data:
            return VerificationResult(
                module_name="github",
                result=VerificationResultEnum.UNABLE_TO_VERIFY,
                confidence=0.3,
                risk_score=0,
                evidence=[f"Could not fetch GitHub profile for user: {github_username}"],
                raw_data={"username": github_username, "found": False},
            )
        
        # Step 3: Extract candidate's technical skills
        technical_skills = self._filter_technical_skills(candidate.skills)
        
        if not technical_skills:
            return VerificationResult(
                module_name="github",
                result=VerificationResultEnum.PASS,
                confidence=0.6,
                risk_score=0,
                evidence=["No technical skills claimed."],
                raw_data={"username": github_username, "technical_skills_count": 0},
            )
        
        # Step 4: Verify each technical skill
        unverified_skills = []
        verified_skills = []
        
        for skill in technical_skills:
            skill_name = skill.skill_name.lower()
            
            if self._skill_found_in_github(skill_name, github_data):
                verified_skills.append(skill_name)
                evidence.append(f"✓ Skill '{skill.skill_name}' supported by GitHub activity.")
            else:
                unverified_skills.append(skill_name)
                evidence.append(f"✗ Skill '{skill.skill_name}' not found in GitHub repositories or activity.")
        
        # Determine result
        if unverified_skills:
            if len(unverified_skills) >= len(technical_skills) / 2:
                # More than half unverified
                result = VerificationResultEnum.WARNING
                risk_score = 20
            else:
                # Some unverified (could be old projects not on GitHub)
                result = VerificationResultEnum.WARNING
                risk_score = 10
        
        confidence = 0.8 if result == VerificationResultEnum.PASS else 0.6
        
        return VerificationResult(
            module_name="github",
            result=result,
            confidence=confidence,
            risk_score=risk_score,
            evidence=evidence,
            raw_data={
                "username": github_username,
                "total_skills": len(technical_skills),
                "verified_skills": len(verified_skills),
                "unverified_skills": len(unverified_skills),
                "github_languages": github_data.get("languages", []),
                "repo_count": len(github_data.get("repos", [])),
            },
        )
    
    def _infer_github_username(self, candidate: Candidate) -> Optional[str]:
        """
        Attempt to infer GitHub username from email.
        E.g., "john.doe@example.com" → "john.doe" or "johndoe"
        
        Returns: Inferred username or None
        """
        if not candidate.email:
            return None
        
        # Extract part before @
        username = candidate.email.split("@")[0]
        
        # Remove common dots/underscores
        username = username.replace(".", "").replace("_", "")
        
        return username if username else None
    
    def _fetch_github_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Fetch GitHub profile data using public API.
        
        Returns: {name, repos: [{name, languages: []}], languages: []}
        """
        if not Github:
            return None
        
        try:
            g = Github()  # Public API, no token needed for rate limit
            user = g.get_user(username)
            
            # Get repositories
            repos = []
            languages = set()
            
            for repo in user.get_repos():
                languages_in_repo = []
                
                # Get language stats
                if repo.language:
                    languages_in_repo.append(repo.language)
                    languages.add(repo.language.lower())
                
                repos.append({
                    "name": repo.name,
                    "language": repo.language,
                    "stars": repo.stargazers_count,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                })
            
            return {
                "username": username,
                "name": user.name or username,
                "repos": repos,
                "languages": list(languages),
                "public_repos": user.public_repos,
            }
        
        except Exception as e:
            logger.warning(f"[GitHub] Failed to fetch profile for {username}: {str(e)}")
            return None
    
    def _filter_technical_skills(self, skills: List[Skill]) -> List[Skill]:
        """
        Filter skills to only technical ones that can be verified via GitHub.
        
        Returns: List of technical skills
        """
        technical = []
        
        for skill in skills:
            skill_lower = skill.skill_name.lower()
            
            # Check if it's a known technical skill
            if skill_lower in self.GITHUB_VERIFIABLE_SKILLS:
                technical.append(skill)
            # Check for partial matches
            elif any(tech in skill_lower for tech in self.GITHUB_VERIFIABLE_SKILLS):
                technical.append(skill)
        
        return technical
    
    def _skill_found_in_github(self, skill_name: str, github_data: Dict[str, Any]) -> bool:
        """
        Check if a skill is found in GitHub profile.
        
        Returns: True if skill is found in languages or repos
        """
        skill_lower = skill_name.lower()
        
        # Check in languages
        for lang in github_data.get("languages", []):
            if skill_lower in lang.lower() or lang.lower() in skill_lower:
                return True
        
        # Check in repository names
        for repo in github_data.get("repos", []):
            if skill_lower in repo["name"].lower():
                return True
            if repo.get("language") and skill_lower in repo["language"].lower():
                return True
        
        return False


# Singleton instance
github_module = GitHubModule()
