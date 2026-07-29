"""
Duplicate Detection Module — Find duplicate resumes via embedding similarity.

Dependencies: embeddings.py (for vector storage and querying)

Checks:
1. Embed new resume
2. Query against all previously stored resume embeddings
3. Flag matches above similarity threshold (0.92) as likely duplicates
4. Flag matches above lower threshold (0.80) as "similar but not identical"
5. Store embedding AFTER comparison (avoid self-matches)

Input: Candidate object with resume text
Output: VerificationResult

Design note: Must store embedding AFTER comparison, not before.
             Otherwise a resume will always match itself.
"""

import logging
from typing import Optional, List

from app.models.candidate import Candidate, Resume
from ai.embeddings import embeddings_client
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class DuplicateModule:
    """Detects duplicate or highly similar resumes."""
    
    # Similarity thresholds
    DUPLICATE_THRESHOLD = 0.92  # Likely exact duplicate or template clone
    SIMILAR_THRESHOLD = 0.80    # Similar but not identical (warning)
    
    def __init__(self):
        pass
    
    def verify(
        self,
        candidate: Candidate,
        current_resume_id: Optional[int] = None,
    ) -> VerificationResult:
        """
        Main entry point: check for duplicate resumes.
        
        Args:
            candidate: Candidate object
            current_resume_id: Resume ID to check (if None, uses most recent resume)
            
        Returns:
            VerificationResult
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        # Get the resume to check
        if current_resume_id:
            resume = next((r for r in candidate.resumes if r.id == current_resume_id), None)
        else:
            # Use most recent resume
            resume = max(candidate.resumes, key=lambda r: r.created_at) if candidate.resumes else None
        
        if not resume:
            return VerificationResult(
                module_name="duplicate",
                result=VerificationResultEnum.PASS,
                confidence=0.5,
                risk_score=0,
                evidence=["No resume found to check for duplicates."],
                raw_data={"resume_count": len(candidate.resumes)},
            )
        
        # Get parsed data
        from app.models.candidate import ParsedData
        parsed_data = next(
            (pd for pd in [resume.parsed_data] if pd),
            None
        )
        
        if not parsed_data or not parsed_data.raw_text:
            return VerificationResult(
                module_name="duplicate",
                result=VerificationResultEnum.PASS,
                confidence=0.3,
                risk_score=0,
                evidence=["No parsed text available for duplicate check."],
                raw_data={"resume_id": resume.id},
            )
        
        resume_text = parsed_data.raw_text
        
        # Step 1: Query for similar resumes (before storing this one)
        if embeddings_client:
            try:
                matches = embeddings_client.query_similar_resumes(
                    resume_text,
                    top_k=10,
                    min_similarity=self.SIMILAR_THRESHOLD,
                )
                
                # Filter out self-matches (same resume ID)
                matches = [(cid, rid, sim) for cid, rid, sim in matches if rid != resume.id]
                
                # Check for duplicates vs. similar
                duplicates = [m for m in matches if m[2] >= self.DUPLICATE_THRESHOLD]
                similar = [m for m in matches if self.SIMILAR_THRESHOLD <= m[2] < self.DUPLICATE_THRESHOLD]
                
                if duplicates:
                    for cid, rid, sim in duplicates:
                        evidence.append(
                            f"Duplicate detected: Resume matches previously submitted resume "
                            f"(resume_id={rid}, candidate_id={cid}) with {sim:.1%} similarity."
                        )
                    risk_score = 95
                    result = VerificationResultEnum.FAIL
                
                elif similar:
                    for cid, rid, sim in similar[:3]:  # Only mention top 3
                        evidence.append(
                            f"Similar resume: Matches resume (resume_id={rid}, candidate_id={cid}) "
                            f"with {sim:.1%} similarity. May be template-based."
                        )
                    risk_score = 30
                    result = VerificationResultEnum.WARNING
                
                else:
                    evidence.append(f"No duplicate matches found. Checked against {len(matches) + 1} resume(s).")
                
                logger.debug(f"Duplicate check: {len(duplicates)} duplicates, {len(similar)} similar")
            
            except Exception as e:
                logger.error(f"Duplicate check failed: {str(e)}")
                # On error, can't verify, but that's not a failure
                result = VerificationResultEnum.UNABLE_TO_VERIFY
                evidence.append(f"Could not perform duplicate check: {str(e)}")
        
        else:
            # No embeddings client available
            result = VerificationResultEnum.UNABLE_TO_VERIFY
            evidence.append("Embeddings service not available for duplicate detection.")
        
        # Step 2: Store this resume's embedding (after comparison)
        if embeddings_client and result != VerificationResultEnum.FAIL:
            try:
                embeddings_client.store_resume_embedding(
                    resume_id=resume.id,
                    candidate_id=candidate.id,
                    text=resume_text,
                    metadata={
                        "candidate_name": candidate.name,
                        "filename": resume.original_filename,
                    },
                )
                logger.debug(f"Stored embedding for resume {resume.id}")
            except Exception as e:
                logger.warning(f"Failed to store embedding for resume {resume.id}: {str(e)}")
        
        confidence = 0.9 if embeddings_client else 0.3
        
        return VerificationResult(
            module_name="duplicate",
            result=result,
            confidence=confidence,
            risk_score=risk_score,
            evidence=evidence,
            raw_data={
                "resume_id": resume.id,
                "collection_stats": embeddings_client.get_collection_stats() if embeddings_client else {},
            },
        )


# Singleton instance
duplicate_module = DuplicateModule()
