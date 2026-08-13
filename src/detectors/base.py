from abc import ABC, abstractmethod
from typing import List

from src.models import PIIMatch

# Explicit detector priority for semantically stronger matches when resolving overlaps.
# Higher number represents higher priority.
PII_TYPE_PRIORITY = {
    "CREDIT_CARD": 9,
    "SSN": 8,
    "EMAIL": 7,
    "COMPANY": 6,
    "PERSON": 5,
    "ADDRESS": 4,
    "PHONE": 3,
    "IP_ADDRESS": 2,
    "DATE_OF_BIRTH": 1,
}


class BaseDetector(ABC):
    """
    Abstract base class for all PII detectors.
    Every detector must implement the `detect` interface.
    """

    @abstractmethod
    def detect(self, text: str) -> List[PIIMatch]:
        """
        Scans the input text for target PII matches.
        Must never modify the input text.
        """
        pass


def resolve_overlaps(matches: List[PIIMatch]) -> List[PIIMatch]:
    """
    Deterministically resolves overlapping PII matches using the following priority order:
      1. Higher confidence (descending)
      2. Explicit detector priority (descending, semantically stronger types first)
      3. Longer span length (descending)
      4. Earlier start offset (ascending)

    Returns a clean, non-overlapping list of matches.
    """
    # Sort matches based on the priority criteria
    sorted_matches = sorted(
        matches,
        key=lambda m: (
            -m.confidence,
            -PII_TYPE_PRIORITY.get(m.pii_type, 0),
            -(m.end - m.start),
            m.start
        )
    )

    accepted: List[PIIMatch] = []

    for candidate in sorted_matches:
        # Check if the candidate overlaps with any already accepted match
        overlaps = False
        for active in accepted:
            if candidate.start < active.end and active.start < candidate.end:
                overlaps = True
                break
        
        if not overlaps:
            accepted.append(candidate)

    # Sort accepted matches by start offset for convenience
    return sorted(accepted, key=lambda m: m.start)
