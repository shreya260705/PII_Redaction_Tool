import pytest

from src.models import PIIMatch
from src.detectors.base import resolve_overlaps
from src.detectors.nlp import NLPDetector
from src.detectors.structured import EmailDetector, PhoneDetector


@pytest.fixture(scope="module")
def nlp_detector():
    """Initializes the NLP detector once for the entire test session."""
    try:
        return NLPDetector()
    except ValueError as e:
        pytest.skip(f"NLP model or Presidio setup is missing: {e}")


# =====================================================================
# 1. PERSON DETECTOR TESTS
# =====================================================================
def test_person_positive(nlp_detector):
    # Ravi Sharma (designation trimmed)
    text_1 = "Ravi Sharma, Managing Director"
    matches_1 = nlp_detector.detect(text_1)
    person_matches = [m for m in matches_1 if m.pii_type == "PERSON"]
    assert len(person_matches) == 1
    assert person_matches[0].text == "Ravi Sharma"
    assert person_matches[0].confidence == 0.95
    assert text_1[person_matches[0].start:person_matches[0].end] == "Ravi Sharma"

    # Contact Person case
    text_2 = "Contact Person: Anita Verma"
    matches_2 = nlp_detector.detect(text_2)
    person_matches2 = [m for m in matches_2 if m.pii_type == "PERSON"]
    assert len(person_matches2) == 1
    assert person_matches2[0].text == "Anita Verma"
    assert person_matches2[0].confidence == 0.95

    # Title prefix case
    text_3 = "Mr. Rahul Singh is present."
    matches_3 = nlp_detector.detect(text_3)
    person_matches3 = [m for m in matches_3 if m.pii_type == "PERSON"]
    assert len(person_matches3) >= 1
    assert any("Rahul" in m.text for m in person_matches3)

    # Company Secretary case (prefix trimmed)
    text_4 = "Company Secretary: Shashank Kumar Chaubey"
    matches_4 = nlp_detector.detect(text_4)
    person_matches4 = [m for m in matches_4 if m.pii_type == "PERSON"]
    assert len(person_matches4) == 1
    assert person_matches4[0].text == "Shashank Kumar Chaubey"
    assert person_matches4[0].confidence == 0.95
    assert text_4[person_matches4[0].start:person_matches4[0].end] == "Shashank Kumar Chaubey"


def test_person_negative(nlp_detector):
    negatives = [
        "Registrar",
        "Offer",
        "Exchange(s)",
        "Exchange",
        "Exchanges",
        "Managing Director",
        "Company Secretary",
        "Compliance Officer",
        "C-101",
        "A-203",
        "Flat 12",
        "Wing B",
        "Plot F-223",
        "Baner Pune",
        "The Managing Director is busy.",
        "Pursuant to the Companies Act, 2013.",
        "Check HDFC Bank Limited and Kirtane & Pandit LLP.",
        "BOARD OF DIRECTORS"
    ]
    for text in negatives:
        matches = nlp_detector.detect(text)
        person_matches = [m for m in matches if m.pii_type == "PERSON"]
        # None of these should be matched as PERSON
        assert len(person_matches) == 0, f"Expected no PERSON match for: '{text}', but got: {[m.text for m in person_matches]}"


# =====================================================================
# 2. COMPANY DETECTOR TESTS
# =====================================================================
def test_company_positive(nlp_detector):
    companies = [
        "HDFC Bank Limited",
        "ICICI Securities Limited",
        "Kirtane & Pandit LLP",
        "Nuvama Wealth Management Limited"
    ]
    for co in companies:
        text = f"We have partnered with {co}."
        matches = nlp_detector.detect(text)
        co_matches = [m for m in matches if m.pii_type == "COMPANY"]
        assert len(co_matches) >= 1
        assert any(co in m.text or m.text in co for m in co_matches)
        assert all(m.confidence >= 0.90 for m in co_matches)


def test_company_negative(nlp_detector):
    non_companies = [
        "SEBI",
        "BSE",
        "NSE",
        "Registrar of Companies",
        "Securities and Exchange Board of India",
        "Issue of Capital and Disclosure Requirements Regulations",
        "Ministry of Finance",
        "Pursuant to the Companies Act, 2013."
    ]
    for non_co in non_companies:
        text = f"Approved by {non_co}."
        matches = nlp_detector.detect(text)
        co_matches = [m for m in matches if m.pii_type == "COMPANY"]
        assert len(co_matches) == 0, f"Expected no COMPANY match for: '{non_co}', but got: {[m.text for m in co_matches]}"


# =====================================================================
# 3. ADDRESS DETECTOR TESTS
# =====================================================================
def test_address_positive(nlp_detector):
    addresses = [
        "Flat No. 102, ABC Complex, Pune - 411 030",
        "Plot No. F-223, Industrial Park, Pune, Maharashtra - 411 004",
        "5th Floor, XYZ House, MG Road, Pune - 411 038"
    ]
    for addr in addresses:
        text = f"Registered office: {addr}."
        matches = nlp_detector.detect(text)
        addr_matches = [m for m in matches if m.pii_type == "ADDRESS"]
        assert len(addr_matches) >= 1
        assert any(m.text in addr or addr in m.text for m in addr_matches)
        # PIN code address gets high confidence
        assert any(m.confidence == 0.95 for m in addr_matches)


def test_address_negative(nlp_detector):
    negatives = [
        "Pune",
        "Maharashtra",
        "United States",
        "411 030",
        "Chakan, Maharashtra",
        "31 March 2025",
        "100000000 shares",
        "Dated 31 March 2025.",
        "Count: 10,000,000.",
        "Under Clause 1.2.3.4."
    ]
    for text in negatives:
        matches = nlp_detector.detect(text)
        addr_matches = [m for m in matches if m.pii_type == "ADDRESS"]
        assert len(addr_matches) == 0, f"Expected no ADDRESS match for: '{text}', but got: {[m.text for m in addr_matches]}"


# =====================================================================
# 4. COMBINED / OVERLAP TESTS
# =====================================================================
def test_combined_nlp_overlaps(nlp_detector):
    # Overlap resolution: HDFC Bank Limited must match as COMPANY, not ADDRESS
    text = "Verify details for HDFC Bank Limited, located at Flat No. 102, ABC Complex, Pune - 411 030."
    
    matches = nlp_detector.detect(text)
    resolved = resolve_overlaps(matches)

    # We should have exactly 1 COMPANY and 1 ADDRESS
    company_matches = [m for m in resolved if m.pii_type == "COMPANY"]
    address_matches = [m for m in resolved if m.pii_type == "ADDRESS"]
    
    assert len(company_matches) == 1
    assert len(address_matches) == 1
    assert company_matches[0].text == "HDFC Bank Limited"
    
    # Standalone locations ("Pune") inside the address are absorbed
    loc_matches = [m for m in resolved if m.pii_type == "LOCATION"]
    assert len(loc_matches) == 0


def test_overlapping_company_address_waterloo(nlp_detector):
    # Test specific overlap requirement: Waterloo Industrial Park VI Private Limited
    # Must match as COMPANY but should NOT trigger a sub-span ADDRESS on "Industrial Park"
    text = "Details are registered under WATERLOO INDUSTRIAL PARK VI PRIVATE LIMITED."
    matches = nlp_detector.detect(text)
    
    company_matches = [m for m in matches if m.pii_type == "COMPANY"]
    address_matches = [m for m in matches if m.pii_type == "ADDRESS"]
    
    assert len(company_matches) >= 1
    assert any("WATERLOO INDUSTRIAL PARK" in m.text for m in company_matches)
    # The sub-span "INDUSTRIAL PARK" must be filtered out
    assert not any("INDUSTRIAL PARK" == m.text for m in address_matches)


def test_combined_structured_nlp(nlp_detector):
    email_det = EmailDetector()
    phone_det = PhoneDetector()
    
    text = "Send credentials to rashi@gmail.com and call Sarthak Malvadkar (Company Secretary) at +91 9876543210."
    
    raw_matches = []
    raw_matches.extend(email_det.detect(text))
    raw_matches.extend(phone_det.detect(text))
    raw_matches.extend(nlp_detector.detect(text))

    resolved = resolve_overlaps(raw_matches)

    # Should detect: EMAIL (rashi@gmail.com), PERSON (Sarthak Malvadkar), and PHONE (+91 9876543210)
    pii_types = [m.pii_type for m in resolved]
    assert "EMAIL" in pii_types
    assert "PERSON" in pii_types
    assert "PHONE" in pii_types
    
    # Verify offsets
    email_match = next(m for m in resolved if m.pii_type == "EMAIL")
    assert email_match.text == "rashi@gmail.com"
    assert text[email_match.start:email_match.end] == "rashi@gmail.com"

    person_match = next(m for m in resolved if m.pii_type == "PERSON")
    assert person_match.text == "Sarthak Malvadkar"
    assert text[person_match.start:person_match.end] == "Sarthak Malvadkar"
    assert person_match.confidence == 0.95


def test_exact_offsets_and_duplicate_removal(nlp_detector):
    # Test duplicate removal and exact offset alignments
    text = "Ravi Sharma and Ravi Sharma are present here."
    matches = nlp_detector.detect(text)
    resolved = resolve_overlaps(matches)
    
    person_matches = [m for m in resolved if m.pii_type == "PERSON"]
    # We should have exactly 2 distinct person matches at different offsets
    assert len(person_matches) == 2
    assert person_matches[0].text == "Ravi Sharma"
    assert person_matches[1].text == "Ravi Sharma"
    assert person_matches[0].start != person_matches[1].start
    assert text[person_matches[0].start:person_matches[0].end] == "Ravi Sharma"
    assert text[person_matches[1].start:person_matches[1].end] == "Ravi Sharma"
