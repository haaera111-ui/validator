"""
Timeline Module — Foundation for experience & education verification.

Responsibilities:
1. Merge Education and Experience rows into one chronological timeline
2. Detect overlaps between date ranges
3. Classify overlaps as plausible or implausible
4. Flag gaps over configurable threshold
5. Return normalized timeline for downstream modules to reuse

Input: Candidate object with related education and experience rows
Output: (timeline: List[TimelineEvent], result: VerificationResult)

This module does NOT judge fraud — it surfaces overlaps and gaps.
The logic is: "Here's what we found. Overlapping full-time jobs at unrelated
companies is uncommon; a part-time job during a degree is not."
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel
from dateutil import parser as date_parser
import logging

from app.models.candidate import Candidate, Experience, Education
from schemas.verification_result import VerificationResult, VerificationResultEnum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Type of timeline event."""
    EDUCATION = "education"
    EXPERIENCE = "experience"
    UNKNOWN = "unknown"


class TimelineEvent(BaseModel):
    """Normalized event in a candidate's timeline."""
    
    event_type: EventType
    title: str  # degree name or job title
    organization: str  # institution or company
    start_date: Optional[date]
    end_date: Optional[date]  # None means "ongoing"
    is_current: bool  # True if end_date is None
    source_id: int  # Original Education.id or Experience.id
    raw_start: Optional[str] = None  # Original string for audit
    raw_end: Optional[str] = None


class TimelineAnalysis(BaseModel):
    """Result of timeline analysis."""
    
    events: List[TimelineEvent]
    overlaps: List[Dict[str, Any]]  # {event1_idx, event2_idx, overlap_days, overlap_start, overlap_end, is_plausible}
    gaps: List[Dict[str, Any]]  # {gap_start, gap_end, gap_days}


class TimelineModule:
    """Analyzes candidate's education and experience timeline."""
    
    # Configurable thresholds
    GAP_THRESHOLD_DAYS = 180  # 6 months: gaps larger than this are flagged
    OVERLAP_THRESHOLD_DAYS = 30  # 1 month: overlaps smaller than this are usually noise/transition
    
    # What makes an overlap "plausible"?
    PLAUSIBLE_OVERLAP_TYPES = {
        (EventType.EDUCATION, EventType.EXPERIENCE),
        (EventType.EXPERIENCE, EventType.EDUCATION),
    }
    
    def __init__(self):
        pass
    
    def verify(self, candidate: Candidate) -> Tuple[TimelineAnalysis, VerificationResult]:
        """
        Main entry point: analyze candidate's timeline.
        
        Returns:
            (timeline_analysis, verification_result)
            
            timeline_analysis is reused by experience.py and education.py.
            verification_result contains overlap/gap findings.
        """
        # Step 1: Build timeline from Education and Experience
        events = self._build_timeline(candidate)
        
        # Step 2: Detect overlaps
        overlaps = self._find_overlaps(events)
        
        # Step 3: Detect gaps
        gaps = self._find_gaps(events)
        
        # Step 4: Build timeline analysis
        timeline_analysis = TimelineAnalysis(
            events=events,
            overlaps=overlaps,
            gaps=gaps,
        )
        
        # Step 5: Generate verification result
        result = self._generate_result(timeline_analysis)
        
        return timeline_analysis, result
    
    def _build_timeline(self, candidate: Candidate) -> List[TimelineEvent]:
        """
        Convert Education and Experience rows into normalized TimelineEvents.
        Sort chronologically.
        """
        events: List[TimelineEvent] = []
        
        # Add education
        for edu in candidate.education:
            start = self._parse_date(edu.start_year if isinstance(edu.start_year, str) else str(edu.start_year) if edu.start_year else None)
            end = self._parse_date(edu.end_year if isinstance(edu.end_year, str) else str(edu.end_year) if edu.end_year else None)
            
            if start:  # Only add if we have at least a start date
                event = TimelineEvent(
                    event_type=EventType.EDUCATION,
                    title=edu.degree_name or "Degree",
                    organization=edu.institution_name or "Unknown",
                    start_date=start,
                    end_date=end,
                    is_current=end is None,
                    source_id=edu.id,
                    raw_start=str(edu.start_year),
                    raw_end=str(edu.end_year) if edu.end_year else None,
                )
                events.append(event)
        
        # Add experience
        for exp in candidate.experience:
            start = self._parse_date(exp.start_date)
            end = self._parse_date(exp.end_date) if not exp.is_current else None
            
            if start:  # Only add if we have at least a start date
                event = TimelineEvent(
                    event_type=EventType.EXPERIENCE,
                    title=exp.job_title or "Job",
                    organization=exp.company_name or "Unknown",
                    start_date=start,
                    end_date=end,
                    is_current=bool(exp.is_current) or end is None,
                    source_id=exp.id,
                    raw_start=exp.start_date,
                    raw_end=exp.end_date,
                )
                events.append(event)
        
        # Sort by start_date, then by end_date (descending, so ongoing roles last)
        events.sort(key=lambda e: (e.start_date or date(1900, 1, 1), e.end_date or date(9999, 12, 31)))
        
        return events
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """
        Parse various date formats using dateutil.
        Returns date object or None if unparseable.
        """
        if not date_str or date_str.lower() in ["present", "current", "ongoing"]:
            return None
        
        try:
            parsed = date_parser.parse(date_str, fuzzy=True, default=datetime(2000, 1, 1))
            return parsed.date()
        except Exception as e:
            logger.warning(f"Could not parse date: {date_str} ({str(e)})")
            return None
    
    def _find_overlaps(self, events: List[TimelineEvent]) -> List[Dict[str, Any]]:
        """
        Find all overlaps between date ranges.
        Return list of overlaps with plausibility assessment.
        """
        overlaps = []
        
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                e1, e2 = events[i], events[j]
                
                # Check if ranges overlap
                overlap_start = max(e1.start_date or date(1900, 1, 1), e2.start_date or date(1900, 1, 1))
                overlap_end = min(
                    e1.end_date or date(9999, 12, 31),
                    e2.end_date or date(9999, 12, 31),
                )
                
                if overlap_start <= overlap_end:
                    overlap_days = (overlap_end - overlap_start).days
                    
                    # Determine if plausible
                    is_plausible = (
                        (e1.event_type, e2.event_type) in self.PLAUSIBLE_OVERLAP_TYPES or
                        (e2.event_type, e1.event_type) in self.PLAUSIBLE_OVERLAP_TYPES or
                        overlap_days < self.OVERLAP_THRESHOLD_DAYS  # Very short overlaps are usually transitions
                    )
                    
                    overlaps.append({
                        "event1_idx": i,
                        "event2_idx": j,
                        "event1": {"type": e1.event_type.value, "title": e1.title, "org": e1.organization},
                        "event2": {"type": e2.event_type.value, "title": e2.title, "org": e2.organization},
                        "overlap_start": overlap_start.isoformat(),
                        "overlap_end": overlap_end.isoformat(),
                        "overlap_days": overlap_days,
                        "is_plausible": is_plausible,
                    })
        
        return overlaps
    
    def _find_gaps(self, events: List[TimelineEvent]) -> List[Dict[str, Any]]:
        """
        Find gaps in the timeline (periods with no education or employment).
        Flag gaps over GAP_THRESHOLD_DAYS.
        """
        gaps = []
        
        if len(events) < 2:
            return gaps
        
        for i in range(len(events) - 1):
            current_end = events[i].end_date
            next_start = events[i + 1].start_date
            
            # Skip if current is ongoing or next has no start
            if current_end is None or next_start is None:
                continue
            
            gap_days = (next_start - current_end).days
            
            if gap_days > self.GAP_THRESHOLD_DAYS:
                gaps.append({
                    "gap_start": current_end.isoformat(),
                    "gap_end": next_start.isoformat(),
                    "gap_days": gap_days,
                    "before": {"type": events[i].event_type.value, "title": events[i].title},
                    "after": {"type": events[i + 1].event_type.value, "title": events[i + 1].title},
                })
        
        return gaps
    
    def _generate_result(self, timeline: TimelineAnalysis) -> VerificationResult:
        """
        Generate VerificationResult from timeline analysis.
        This module SURFACES findings, doesn't judge them.
        """
        evidence = []
        risk_score = 0
        result = VerificationResultEnum.PASS
        
        # Check implausible overlaps (full-time jobs at unrelated companies)
        implausible_overlaps = [o for o in timeline.overlaps if not o["is_plausible"] and o["overlap_days"] > 30]
        if implausible_overlaps:
            for overlap in implausible_overlaps:
                evidence.append(
                    f"Implausible overlap: {overlap['event1']['title']} at {overlap['event1']['org']} "
                    f"overlaps with {overlap['event2']['title']} at {overlap['event2']['org']} "
                    f"by {overlap['overlap_days']} days."
                )
            risk_score += 30
            result = VerificationResultEnum.WARNING
        
        # Surface gaps (informational, not necessarily bad)
        if timeline.gaps:
            for gap in timeline.gaps:
                evidence.append(
                    f"Gap of {gap['gap_days']} days between {gap['before']['title']} "
                    f"(ended {gap['gap_start']}) and {gap['after']['title']} (started {gap['gap_end']})."
                )
        
        confidence = 0.95 if timeline.events else 0.5
        
        return VerificationResult(
            module_name="timeline",
            result=result,
            confidence=confidence,
            risk_score=risk_score,
            evidence=evidence,
            raw_data={
                "event_count": len(timeline.events),
                "overlap_count": len(timeline.overlaps),
                "gap_count": len(timeline.gaps),
                "implausible_overlaps": len(implausible_overlaps),
            },
        )


# Singleton instance
timeline_module = TimelineModule()
