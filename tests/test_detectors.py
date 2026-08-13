import pytest

from src.models import BlockLocation, DocumentBlock, PIIMatch
from src.detectors.base import resolve_overlaps
from src.detectors.structured import (
    EmailDetector,
    PhoneDetector,
    IPAddressDetector,
    SSNDetector,
    CreditCardDetector,
    DateOfBirthDetector,
)

# Helper to construct a DocumentBlock from text for testing
def make_block(text: str) -> DocumentBlock:
    return DocumentBlock(
        block_id=0,
        block_type="paragraph",
        text=text,
        location=BlockLocation(part_type="body", paragraph_index=0),
        element=None
    )


# =====================================================================
# 1. EMAIL DETECTOR TESTS
# =====================================================================
def test_email_detector():
    detector = EmailDetector()
    
    # Positive examples
    pos_text = "Reach us at test@example.com or john.doe@example.co.in or rashi.patil@gmail.com and person+support@example.org"
    matches = detector.detect(pos_text)
    assert len(matches) == 4
    assert matches[0].text == "test@example.com"
    assert matches[1].text == "john.doe@example.co.in"
    assert matches[2].text == "rashi.patil@gmail.com"
    assert matches[3].text == "person+support@example.org"
    assert all(m.confidence == 0.99 for m in matches)
    assert all(m.pii_type == "EMAIL" for m in matches)

    # Negative examples
    neg_text = "Invalid emails: hello@, @example.com, foo @ bar, and normal text without email."
    assert len(detector.detect(neg_text)) == 0


# =====================================================================
# 2. PHONE DETECTOR TESTS
# =====================================================================
def test_phone_detector():
    detector = PhoneDetector()

    # Positive examples with prefixes / keywords
    text_1 = "Contact us: +91 9876543210 or +91-9876543210 or +919876543210"
    matches_1 = detector.detect(text_1)
    assert len(matches_1) == 3
    assert all(m.confidence == 0.99 for m in matches_1)

    # Contextual matches (starts with 6-9, no +91, but has context word 'Mobile')
    text_2 = "My Mobile number is 9876543210. Underwriter landline: 020-67295100."
    matches_2 = detector.detect(text_2)
    assert len(matches_2) == 2
    assert matches_2[0].text == "9876543210"
    assert matches_2[0].confidence == 0.95
    assert matches_2[1].text == "020-67295100"
    assert matches_2[1].confidence == 0.95

    # Negative examples (no prefix, no context = ignore)
    text_neg = "Some random numbers: 9876543210 and 1234567890 and 0000000000."
    matches_neg = detector.detect(text_neg)
    assert len(matches_neg) == 0

    # Ensure boundaries prevent matching portions of larger numbers (e.g. 12-digit financial number)
    text_large = "Transaction amount: 998765432100 shares."
    assert len(detector.detect(text_large)) == 0


# =====================================================================
# 3. IP ADDRESS DETECTOR TESTS
# =====================================================================
def test_ip_detector():
    detector = IPAddressDetector()

    # Positive
    text_pos = "Servers at 192.168.1.1 and 10.0.0.1 and 8.8.8.8 and 1.1.1.1"
    matches = detector.detect(text_pos)
    assert len(matches) == 4
    assert matches[0].text == "192.168.1.1"
    assert matches[3].text == "1.1.1.1"

    # Negative (invalid octets, or version numbers)
    text_neg = "Invalid: 999.999.999.999. Heading: Section 1.2.3.4 or Clause 4.3.2.1. Version: 1.2.3.4.5"
    matches_neg = detector.detect(text_neg)
    assert len(matches_neg) == 0


# =====================================================================
# 4. SSN DETECTOR TESTS
# =====================================================================
def test_ssn_detector():
    detector = SSNDetector()

    # Positive (hyphenated)
    text_pos = "SSN is 123-45-6789."
    matches = detector.detect(text_pos)
    assert len(matches) == 1
    assert matches[0].text == "123-45-6789"
    assert matches[0].confidence == 0.99

    # Contextual raw 9-digit
    text_ctx = "Please supply your SSN: 123456789."
    matches_ctx = detector.detect(text_ctx)
    assert len(matches_ctx) == 1
    assert matches_ctx[0].text == "123456789"
    assert matches_ctx[0].confidence == 0.95

    # Negative (no context for raw 9-digit, or structurally invalid)
    text_neg = "Share count: 123456789. Bad SSN format: 000-45-6789 or 123-00-6789."
    assert len(detector.detect(text_neg)) == 0


# =====================================================================
# 5. CREDIT CARD DETECTOR TESTS
# =====================================================================
def test_credit_card_detector():
    detector = CreditCardDetector()

    # Positive (valid Luhn number)
    valid_card = "4111 1111 1111 1111"
    text_pos = f"My card is {valid_card} and formatted: 4111-1111-1111-1111"
    matches = detector.detect(text_pos)
    assert len(matches) == 2
    assert matches[0].text == "4111 1111 1111 1111"
    assert matches[0].confidence == 0.95

    # Negative (invalid Luhn, or trivial repeats)
    invalid_card = "4111 1111 1111 1112"
    trivial_card = "1111 1111 1111 1111"
    text_neg = f"Invalid CC: {invalid_card} or fake: {trivial_card}."
    assert len(detector.detect(text_neg)) == 0


# =====================================================================
# 6. DATE OF BIRTH DETECTOR TESTS
# =====================================================================
def test_dob_detector():
    detector = DateOfBirthDetector()

    # Positive (valid dates with birth context close by)
    text_pos = "Name: John Doe, DOB: 15/08/1999. Jane was born 15 August 1999."
    matches = detector.detect(text_pos)
    assert len(matches) == 2
    assert matches[0].text == "15/08/1999"
    assert matches[1].text == "15 August 1999"
    assert all(m.confidence == 0.98 for m in matches)

    # Negative (valid date but no birth context in proximity)
    text_neg = "Report dated 15 August 2025. Financial period ended 31 March 2026. Company incorporated July 30, 1979."
    assert len(detector.detect(text_neg)) == 0

    # Negative (invalid dates)
    text_invalid = "DOB: 29/02/2025 (2025 is not leap year) or DOB: 31/04/1999 (April has 30 days)"
    assert len(detector.detect(text_invalid)) == 0


# =====================================================================
# 7. OVERLAP RESOLUTION TESTS
# =====================================================================
def test_overlap_resolution():
    # Construct overlapping matches manually to check sorting/greedy choice
    m1 = PIIMatch(pii_type="PHONE", text="9876543210", start=10, end=20, confidence=0.95, detector="test")
    m2 = PIIMatch(pii_type="CREDIT_CARD", text="9876543210123456", start=10, end=26, confidence=0.95, detector="test")
    
    # Overlap resolve should choose CREDIT_CARD because CC has higher priority (6 vs 3)
    resolved = resolve_overlaps([m1, m2])
    assert len(resolved) == 1
    assert resolved[0].pii_type == "CREDIT_CARD"

    # Confidences unequal: should choose higher confidence
    m3 = PIIMatch(pii_type="PHONE", text="9876543210", start=5, end=15, confidence=0.99, detector="test")
    m4 = PIIMatch(pii_type="DATE_OF_BIRTH", text="15 August 1999", start=10, end=24, confidence=0.98, detector="test")
    
    resolved2 = resolve_overlaps([m3, m4])
    assert len(resolved2) == 1
    assert resolved2[0].pii_type == "PHONE"


# =====================================================================
# 8. COMBINED TEXT DETECTION TEST
# =====================================================================
def test_combined_detection():
    detectors = [
        EmailDetector(),
        PhoneDetector(),
        IPAddressDetector(),
        SSNDetector(),
        CreditCardDetector(),
        DateOfBirthDetector(),
    ]
    
    text = "User john@example.com (DOB: 15/08/1999, SSN: 123-45-6789) connected from IP 10.0.0.1. Card: 4111-1111-1111-1111."
    
    raw_matches = []
    for d in detectors:
        raw_matches.extend(d.detect(text))
        
    resolved = resolve_overlaps(raw_matches)
    
    # We should have exactly 5 matches (EMAIL, DOB, SSN, IP, CC)
    # Phone detector might match the card or SSN numbers initially, but CC/SSN takes priority and resolves overlaps.
    assert len(resolved) == 5
    types = [m.pii_type for m in resolved]
    assert "EMAIL" in types
    assert "DATE_OF_BIRTH" in types
    assert "SSN" in types
    assert "IP_ADDRESS" in types
    assert "CREDIT_CARD" in types
