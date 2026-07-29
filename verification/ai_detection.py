"""
AI Detection Module — Detect AI-generated resume text.

Approach: Lexical & structural signals, NOT relying on black-box detectors.

Signals checked:
1. Vocabulary diversity (unique word ratio)
2. Sentence structure uniformity (repetitive patterns)
3. Generic phrasing patterns (common LLM outputs)
4. Awkward transitions and list-like structure

Input: Raw resume text
Output: VerificationResult

CRITICAL: This module NEVER returns fail on its own.
          Always returns warning at most.
          This is intentional — not enough signal alone to reject a candidate.

Future: Could integrate embeddings to compare against known AI-generated corpus.
"""

import logging
import re
from typing import Dict, List, Tuple
from collections import Counter

from app.models.candidate import Candidate, ParsedData
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class AIDetectionModule:
    """Detects lexical/structural signals of AI-generated text."""
    
    # Generic phrases commonly found in LLM output
    GENERIC_PHRASES = {
        "passionate about",
        "drive innovation",
        "proven track record",
        "dynamic team",
        "leverage expertise",
        "scalable solutions",
        "collaborative environment",
        "results-driven",
        "cutting-edge technologies",
        "best practices",
        "streamline processes",
        "enhance efficiency",
        "maximize productivity",
        "synergize",
    }
    
    # Sentence starters common in LLM text
    REPETITIVE_STARTERS = [
        "developed",
        "implemented",
        "designed",
        "created",
        "managed",
        "led",
        "contributed",
    ]
    
    def __init__(self):
        pass
    
    def verify(self, candidate: Candidate) -> VerificationResult:
        """
        Main entry point: check for AI-generated text signals.
        
        Args:
            candidate: Candidate object
            
        Returns:
            VerificationResult (WARNING at most, never FAIL)
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        # Get most recent resume's parsed text
        if not candidate.resumes:
            return VerificationResult(
                module_name="ai_detection",
                result=VerificationResultEnum.PASS,
                confidence=0.3,
                risk_score=0,
                evidence=["No resume found."],
                raw_data={},
            )
        
        resume = max(candidate.resumes, key=lambda r: r.created_at)
        if not resume.parsed_data or not resume.parsed_data.raw_text:
            return VerificationResult(
                module_name="ai_detection",
                result=VerificationResultEnum.PASS,
                confidence=0.3,
                risk_score=0,
                evidence=["No parsed text available."],
                raw_data={},
            )
        
        text = resume.parsed_data.raw_text
        
        # Run all checks
        checks = {
            "generic_phrases": self._check_generic_phrases(text),
            "vocabulary_diversity": self._check_vocabulary_diversity(text),
            "sentence_structure": self._check_sentence_structure(text),
            "punctuation_uniformity": self._check_punctuation_uniformity(text),
        }
        
        # Aggregate signals
        ai_score = sum(checks.values()) / len(checks)
        
        # Determine risk level
        if ai_score > 0.7:
            evidence.append(
                f"Elevated AI-generated text signals detected (score: {ai_score:.2f}). "
                f"Text shows characteristics common in LLM output (generic phrasing, "
                f"uniform structure). NOT a standalone basis for rejection."
            )
            risk_score = 25  # Moderate risk, but not definitive
            result = VerificationResultEnum.WARNING
        
        elif ai_score > 0.5:
            evidence.append(
                f"Some AI-generated text signals present (score: {ai_score:.2f}). "
                f"Warrants further review, but inconclusive."
            )
            risk_score = 10
            result = VerificationResultEnum.WARNING
        
        else:
            evidence.append(f"Text shows natural variation in structure and phrasing (score: {ai_score:.2f}).")
        
        confidence = 0.6  # Low confidence on AI detection — this is a soft signal
        
        return VerificationResult(
            module_name="ai_detection",
            result=result,  # Never fail, max warning
            confidence=confidence,
            risk_score=risk_score,
            evidence=evidence,
            raw_data={
                "ai_detection_score": ai_score,
                "check_scores": {k: v for k, v in checks.items()},
                "text_length": len(text),
                "word_count": len(text.split()),
            },
        )
    
    def _check_generic_phrases(self, text: str) -> float:
        """
        Check for overuse of generic phrases.
        
        Returns: Score 0-1 (1 = highly generic)
        """
        text_lower = text.lower()
        text_words = text_lower.split()
        
        if not text_words:
            return 0.0
        
        generic_count = 0
        for phrase in self.GENERIC_PHRASES:
            if phrase in text_lower:
                generic_count += 1
        
        # Normalize: more than half the generic phrases is a strong signal
        return min(generic_count / len(self.GENERIC_PHRASES), 1.0)
    
    def _check_vocabulary_diversity(self, text: str) -> float:
        """
        Check for low vocabulary diversity (repetitive words).
        
        Returns: Score 0-1 (0 = diverse, 1 = repetitive)
        """
        words = text.lower().split()
        if not words or len(words) < 10:
            return 0.0
        
        unique_words = len(set(words))
        diversity_ratio = unique_words / len(words)
        
        # LLM text typically has lower diversity (more repetitive)
        # Natural text has diversity_ratio ~0.5-0.7
        # AI text often 0.3-0.5
        if diversity_ratio > 0.5:
            return 0.0  # Diverse vocabulary
        elif diversity_ratio < 0.3:
            return 1.0  # Very repetitive (likely AI)
        else:
            return (0.5 - diversity_ratio) / 0.2  # Scale between 0.3-0.5
    
    def _check_sentence_structure(self, text: str) -> float:
        """
        Check for uniform sentence structure (LLM characteristic).
        
        Returns: Score 0-1 (1 = highly uniform)
        """
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) < 3:
            return 0.0
        
        # Check for repetitive starting words
        starters = []
        for sentence in sentences[:10]:  # Check first 10 sentences
            words = sentence.split()
            if words:
                starter = words[0].lower()
                starters.append(starter)
        
        if not starters:
            return 0.0
        
        # Count repetition
        starter_counts = Counter(starters)
        most_common_count = starter_counts.most_common(1)[0][1]
        
        # If one starter appears in >40% of sentences, it's uniform
        uniformity = min(most_common_count / len(starters), 1.0)
        return max(uniformity - 0.25, 0.0)  # Threshold: >25% is suspicious
    
    def _check_punctuation_uniformity(self, text: str) -> float:
        """
        Check for uniform punctuation patterns (LLM characteristic).
        
        Returns: Score 0-1 (1 = highly uniform)
        """
        # Extract punctuation sequences
        punctuation_patterns = re.findall(r'[.!?,;:]+', text)
        
        if not punctuation_patterns:
            return 0.0
        
        # Most resumes use just periods and commas
        # LLM text often has more varied punctuation in uniform patterns
        pattern_counts = Counter(punctuation_patterns)
        
        # Count how many patterns appear exactly once (too varied) vs. repeated (uniform)
        unique_patterns = len(pattern_counts)
        total_punctuation = len(punctuation_patterns)
        
        if unique_patterns > total_punctuation / 2:
            return 0.0  # Very varied (natural)
        else:
            return 0.5  # Moderate uniformity


# Singleton instance
ai_detection_module = AIDetectionModule()
