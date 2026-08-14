import re
import logging
from typing import List

from src.models import PIIMatch
from src.detectors.base import BaseDetector
from src.detectors.structured import has_sentence_boundary_between

logger = logging.getLogger(__name__)
# Suppress noisy Presidio analyzer mapping warnings
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)


def is_part_of_legislative_title(text: str, end: int, blacklist_words) -> bool:
    """
    Checks if a detected company candidate is part of a legislative or regulatory title
    by looking ahead for words like 'Act' or 'Regulations' within a continuous capitalized phrase.
    """
    after_part = text[end:end+100]
    pattern = r'\b(act|regulations?|rules?|notifications?|guidelines?)\b'
    m = re.search(pattern, after_part, re.IGNORECASE)
    if m:
        keyword_start = m.start()
        intermediate = after_part[:keyword_start].strip()
        if not intermediate:
            return True
        # Split intermediate text into words
        words = re.findall(r'\b\w+\b', intermediate)
        prepositions = {"and", "of", "the", "for", "on", "at", "in", "to", "by", "with", "or", "a", "an", "under"}
        all_cap_or_prep = True
        for w in words:
            if not (w[0].isupper() or w.lower() in prepositions):
                all_cap_or_prep = False
                break
        return all_cap_or_prep
    return False


class NLPDetector(BaseDetector):
    """
    PII Detector utilizing spaCy...
    """

    def __init__(self) -> None:
        # Load spaCy only once through Presidio's NLP engine.
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            configuration = {
                "nlp_engine_name": "spacy",
                "models": [
                    {
                        "lang_code": "en",
                        "model_name": "en_core_web_sm"
                    }
                ]
            }

            provider = NlpEngineProvider(
                nlp_configuration=configuration
            )

            nlp_engine = provider.create_engine()
            
            # Remove unused spaCy pipeline components to optimize speed
            nlp_model = nlp_engine.nlp.get("en")
            if nlp_model:
                for pipe in ["tagger", "parser", "attribute_ruler", "lemmatizer"]:
                    if pipe in nlp_model.pipe_names:
                        nlp_model.remove_pipe(pipe)

            self.analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                supported_languages=["en"]
            )

        except Exception as e:
            logger.exception(
                "Failed to initialize Presidio/spaCy NLP engine."
            )
            raise ValueError(
                f"Failed to initialize Presidio: {e}"
            ) from e

        # Compile context indicators for names
        self.person_context_rx = re.compile(
            r'\b(?:contact\s+person|chairman|managing\s+director|'
            r'independent\s+director|director|ceo|cfo|company\s+secretary|'
            r'compliance\s+officer|auditor|son\s+of|daughter\s+of|wife\s+of)\b',
            re.IGNORECASE
        )
        # Exclude public stock exchanges, regulators, and government departments from COMPANY
        self.non_company_rx = re.compile(
            r'\b(?:sebi|securities\s+and\s+exchange\s+board\s+of\s+india|securities\s+and\s+exchange\s+board|registrar\s+of\s+companies|roc|bse|nse|stock\s+exchange|stock\s+exchanges|ministry\s+of|department\s+of|sales\s+tax\s+department|central\s+processing\s+centre|government\s+of\s+india|government\s+ministries|government\s+departments|statutory\s+regulators?)\b',
            re.IGNORECASE
        )

        # Commercial corporate suffixes
        self.company_suffixes = [
            "limited", "ltd", "llp", "private limited", "pvt ltd", "corporation", "inc", "co", "associates"
        ]

        # Case-sensitive company regexes to avoid matching lowercase prepositions/verbs
        self.company_regex_capitalized = re.compile(
            r'\b(?:[A-Z][a-zA-Z0-9]*|&)(?:\s+(?:[A-Z][a-zA-Z0-9]*|&)){0,5}\s+(?:Limited|Ltd|LLP|Private\s+Limited|Pvt\s+Ltd|Corporation|Inc)\b'
        )
        self.company_regex_uppercase = re.compile(
            r'\b(?:[A-Z0-9]+|&)(?:\s+(?:[A-Z0-9]+|&)){0,5}\s+(?:LIMITED|LTD|LLP|PRIVATE\s+LIMITED|PVT\s+LTD|CORPORATION|INC)\b'
        )

        # Set of designative or heading words to exclude from PERSON detection
        self.person_blacklisted_words = {
            "director", "directors", "secretary", "officer", "officers", "auditor", "auditors",
            "underwriter", "underwriters", "banker", "bankers", "promoter", "promoters", "committee",
            "act", "companies", "board", "counsel", "advisor", "advisors", "designation", "contact",
            "strict", "redaction", "pii", "accuracy", "test", "date", "birth", "email", "phone",
            "address", "value", "company", "ssn", "ip", "card", "credit", "the", "managing", "independent",
            "and", "of", "for", "or", "with", "is", "at", "this", "that"
        }
        self.name_regex = re.compile(r'\b[A-Z][a-z]+\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]+\b')

        # Exact case-insensitive blacklist for PERSON
        self.person_exact_blacklist = {
            "registrar", "offer", "exchange", "exchanges", "company", "board", "sponsor",
            "underwriter", "underwriters", "committee", "secretary", "auditor", "auditors",
            "brlm", "managing director", "company secretary", "compliance officer", "director",
            "directors", "officer", "officers", "manager", "managers", "issue", "promoter", "promoters"
        }

        # Obvious address room/flat/plot units matching PERSON
        self.address_unit_rx = re.compile(
            r'^(?:[a-zA-Z]-\d+|\d+-[a-zA-Z]|flat\s+\d+|wing\s+[a-zA-Z]|plot\s+[a-zA-Z\d-]+)$',
            re.IGNORECASE
        )

        # Geographic location words to exclude from PERSON candidates
        self.location_words = {
            "pune", "mumbai", "maharashtra", "india", "delhi", "bangalore", "kolkata", 
            "chennai", "hyderabad", "chakan", "khed", "baner", "prabhadevi", "bandra", 
            "gurugram", "noida", "haryana", "karnataka", "tamil", "nadu", "bengal", "united", "states"
        }

        # COMPANY title exclusions
        self.company_blacklist_words = {"act", "regulations", "regulation", "rules", "notification", "guidelines"}

        # Address structural keywords and PIN code regex
        self.address_keywords = [
            "plot", "flat", "s. no", "survey", "floor", "building", "road", 
            "street", "nagar", "district", "state", "opposite", "opp", 
            "behind", "lane", "apartment", "society", "park", "complex", 
            "residency", "taluka", "industrial"
        ]
        self.pin_regex = re.compile(r'\b\d{3}\s?\d{3}\b|\b\d{6}\b')

    def detect(self, text: str) -> List[PIIMatch]:
        """
        Runs spaCy NER, Microsoft Presidio Analyzer, and custom filters over the input text block.
        Returns a list of block-relative PIIMatches for PERSON, COMPANY, and ADDRESS.
        """
        if not text or not any(c.isupper() for c in text):
            return []
        matches: List[PIIMatch] = []
        
        # 1. Run Presidio Analyzer for default entities
        try:
            results = self.analyzer.analyze(
                text=text,
                language="en",
                entities=["PERSON", "ORGANIZATION", "LOCATION"]
            )
        except Exception as e:
            logger.error(f"Presidio analyze failed: {e}")
            results = []

        # 2. Extract PERSON and COMPANY from NLP
        for res in results:
            if res.entity_type == "PERSON":
                matched_text = text[res.start:res.end].strip()
                if not matched_text:
                    continue

                start, end = res.start, res.end
                
                # Trim corporate roles/designations suffix (e.g. "Ravi Sharma, Managing Director" -> "Ravi Sharma")
                if "," in matched_text:
                    parts = matched_text.split(",")
                    designation_regex = re.compile(
                        r'^\s*(?:managing\s+director|independent\s+director|executive\s+director|director|company\s+secretary|compliance\s+officer|auditor|ceo|cfo|promoter|chairman|secretary|officer|underwriter|registrar)\b',
                        re.IGNORECASE
                    )
                    if designation_regex.search(parts[1]):
                        matched_text = parts[0].strip()
                        end = start + len(matched_text)

                # Trim corporate designations prefix (e.g. "Company Secretary: Shashank Kumar Chaubey" -> "Shashank Kumar Chaubey")
                if ":" in matched_text:
                    parts = matched_text.split(":", 1)
                    designation_regex = re.compile(
                        r'\b(?:managing\s+director|independent\s+director|executive\s+director|director|company\s+secretary|compliance\s+officer|auditor|ceo|cfo|promoter|chairman|secretary|officer|underwriter|registrar)\b',
                        re.IGNORECASE
                    )
                    if designation_regex.search(parts[0]):
                        matched_text = parts[1].strip()
                        start = end - len(matched_text)

                # Clean leading/trailing punctuations
                while matched_text and matched_text[0] in ",. -/\n\t:":
                    matched_text = matched_text[1:]
                    start += 1
                while matched_text and matched_text[-1] in ",. -/\n\t:":
                    matched_text = matched_text[:-1]
                    end -= 1

                if not matched_text:
                    continue

                # Expand to the left to capture adjacent capitalized words that spaCy split (e.g. "Shashank" split as ORG)
                stop_words = {
                    "company", "secretary", "director", "managing", "independent", "compliance", "officer", 
                    "chairman", "auditor", "underwriter", "registrar", "offer", "exchange", "exchanges", 
                    "board", "sponsor", "committee", "mr", "ms", "mrs", "dr", "and", "of", "the", "to", "for"
                }
                curr_start = start
                while True:
                    m_prev = re.search(r'([A-Za-z0-9]+)\s*$', text[:curr_start])
                    if not m_prev:
                        break
                    word = m_prev.group(1)
                    word_start = m_prev.start(1)
                    if word[0].isupper() and word.lower() not in stop_words and not word.isdigit():
                        curr_start = word_start
                    else:
                        break
                
                if curr_start != start:
                    start = curr_start
                    matched_text = text[start:end].strip()

                # Clean words in matched text
                words = [w.lower() for w in re.findall(r'\b\w+\b', matched_text)]
                if any(w in self.person_blacklisted_words for w in words):
                    continue

                # Reject location-only PERSON predictions
                if any(w in self.location_words for w in words):
                    continue

                # Avoid matching company names as PERSON
                if any(suffix in matched_text.lower() for suffix in ["limited", "ltd", "llp"]):
                    continue

                # Clean matched text to strictly check against exact blacklist
                clean_lower = re.sub(r'[^a-z0-9]', '', matched_text.lower())
                if clean_lower in self.person_exact_blacklist:
                    continue

                # Reject address flat/wing/plot components
                if self.address_unit_rx.match(matched_text.strip()):
                    continue

                # Query Presidio results to see if this candidate overlaps with LOCATION
                is_loc_gpe = False
                for other_res in results:
                    if other_res.entity_type == "LOCATION":
                        if max(start, other_res.start) < min(end, other_res.end):
                            is_loc_gpe = True
                            break

                # Contextual check: Boost confidence if professional keyword is in proximity
                has_context = False
                for m in self.person_context_rx.finditer(text):
                    kw_start, kw_end = m.start(), m.end()
                    # Check distance
                    if max(0, start - 50) <= kw_start <= end + 50:
                        # Ensure no sentence boundary splits the context
                        if kw_start < start:
                            boundary = has_sentence_boundary_between(text, kw_end, start)
                        else:
                            boundary = has_sentence_boundary_between(text, end, kw_start)
                        if not boundary:
                            has_context = True
                            break

                # Reject location-only PERSON predictions unless there is strong context
                if is_loc_gpe and not has_context:
                    continue

                confidence = 0.95 if has_context else 0.85
                matches.append(
                    PIIMatch(
                        pii_type="PERSON",
                        text=matched_text,
                        start=start,
                        end=end,
                        confidence=confidence,
                        detector="nlp_presidio_person"
                    )
                )

            elif res.entity_type == "ORGANIZATION":
                matched_text = text[res.start:res.end].strip()
                if not matched_text:
                    continue

                # Clean leading/trailing punctuation
                start, end = res.start, res.end
                while matched_text and matched_text[0] in ",. -/\n\t":
                    matched_text = matched_text[1:]
                    start += 1
                while matched_text and matched_text[-1] in ",. -/\n\t":
                    matched_text = matched_text[:-1]
                    end -= 1

                # Apply Company redaction policy: reject government, stock exchanges, and regulators
                if self.non_company_rx.search(matched_text):
                    continue

                # Reject legislative act/regulations titles
                matched_words = set(w.lower() for w in re.findall(r'\b\w+\b', matched_text))
                if matched_words.intersection(self.company_blacklist_words):
                    continue

                # Reject matches that are part of legislative act titles
                if is_part_of_legislative_title(text, end, self.company_blacklist_words):
                    continue

                # Commercial indicators
                has_suffix = any(
                    re.search(r'\b' + re.escape(suffix) + r'\b', matched_text, re.IGNORECASE)
                    for suffix in self.company_suffixes
                )
                has_context = any(
                    kw in matched_text.lower()
                    for kw in [
                        "bank", "securities", "capital", "wealth", "investment",
                        "industry", "technology", "financial", "solutions"
                    ]
                )

                if has_suffix:
                    confidence = 0.95
                elif has_context:
                    confidence = 0.90
                else:
                    confidence = 0.70  # Low confidence ORG

                # Only redact high/medium confidence commercial entities
                if confidence >= 0.90:
                    matches.append(
                        PIIMatch(
                            pii_type="COMPANY",
                            text=matched_text,
                            start=start,
                            end=end,
                            confidence=confidence,
                            detector="nlp_presidio_company"
                        )
                    )

        # 3. Custom Company Regex Scanner (Fallback for NLP recall gaps)
        for regex in (self.company_regex_capitalized, self.company_regex_uppercase):
            for m in regex.finditer(text):
                matched_text = m.group().strip()
                if self.non_company_rx.search(matched_text):
                    continue
                matched_words = set(w.lower() for w in re.findall(r'\b\w+\b', matched_text))
                if matched_words.intersection(self.company_blacklist_words):
                    continue
                if is_part_of_legislative_title(text, m.end(), self.company_blacklist_words):
                    continue
                matches.append(
                    PIIMatch(
                        pii_type="COMPANY",
                        text=matched_text,
                        start=m.start(),
                        end=m.end(),
                        confidence=0.98,
                        detector="regex_company_fallback"
                    )
                )

        # 4. Custom ADDRESS detector
        # Collect geographic nodes (LOCATION/GPE)
        loc_results = [r for r in results if r.entity_type in ("LOCATION", "GPE")]
        # Match Indian PIN codes
        pin_matches = list(self.pin_regex.finditer(text))
        # Match structural keywords
        text_lower = text.lower()
        keyword_hits = [kw for kw in self.address_keywords if re.search(r'\b' + re.escape(kw) + r'\b', text_lower)]

        # Supporting geographic context from Presidio results
        spacy_locs = [r for r in results if r.entity_type == "LOCATION"]
        has_geo_context = len(loc_results) > 0 or len(spacy_locs) > 0

        is_address = False
        score = 0.0

        # Address structural and PIN constraints
        if len(keyword_hits) >= 1:
            if pin_matches:
                is_address = True
                score = 0.95  # High confidence
            elif len(keyword_hits) + len(loc_results) + len(spacy_locs) >= 2:
                is_address = True
                score = 0.85  # Medium confidence
        elif pin_matches and has_geo_context:
            is_address = True
            score = 0.85

        if is_address:
            # Aggregate all token offsets
            indices = []
            for kw in self.address_keywords:
                for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text_lower):
                    indices.append((m.start(), m.end()))
            for res in loc_results:
                indices.append((res.start, res.end))
            for ent in spacy_locs:
                indices.append((ent.start, ent.end))
            for m in pin_matches:
                indices.append((m.start(), m.end()))

            if indices:
                start = min(idx[0] for idx in indices)
                end = max(idx[1] for idx in indices)

                # Trim leading/trailing punctuation/whitespaces
                span_text = text[start:end]
                while span_text and span_text[0] in ",. -/\n\t":
                    span_text = span_text[1:]
                    start += 1
                while span_text and span_text[-1] in ",. -/\n\t":
                    span_text = span_text[:-1]
                    end -= 1

                # Discard standalone states, cities, countries, or numbers
                if len(span_text.strip()) > 3 and span_text.lower() not in [
                    "india", "pune", "mumbai", "maharashtra", "united states", 
                    "chakan, maharashtra", "chakan"
                ]:
                    matches.append(
                        PIIMatch(
                            pii_type="ADDRESS",
                            text=span_text,
                            start=start,
                            end=end,
                            confidence=score,
                            detector="custom_address_rules"
                        )
                    )

        # Run custom name regex candidate finder to catch missed names
        for m in self.name_regex.finditer(text):
            candidate = m.group()
            start, end = m.start(), m.end()
            
            # Check overlap with LOCATION/ORGANIZATION entities from Presidio
            is_non_person_ent = False
            for other_res in results:
                if other_res.entity_type in ("LOCATION", "ORGANIZATION"):
                    if max(start, other_res.start) < min(end, other_res.end):
                        is_non_person_ent = True
                        break
            if is_non_person_ent:
                continue
                
            # Exclude if overlaps with ANY existing matches (including PERSON to avoid duplicates)
            overlaps_existing = False
            for existing in matches:
                if max(start, existing.start) < min(end, existing.end):
                    overlaps_existing = True
                    break
            if overlaps_existing:
                continue

            matches.append(
                PIIMatch(
                    pii_type="PERSON",
                    text=candidate,
                    start=start,
                    end=end,
                    confidence=0.85,
                    detector="regex_person_fallback"
                )
            )

        # 5. Overlap resolution between COMPANY and ADDRESS
        # If an ADDRESS candidate overlaps with a COMPANY candidate, prefer COMPANY
        company_matches = [m for m in matches if m.pii_type == "COMPANY"]
        filtered_matches = []
        for m in matches:
            if m.pii_type == "ADDRESS":
                overlaps_company = False
                for c in company_matches:
                    if max(m.start, c.start) < min(m.end, c.end):
                        overlaps_company = True
                        break
                if overlaps_company:
                    continue
            
            # Apply post-filtering for PERSON type
            if m.pii_type == "PERSON":
                if any(c.isdigit() for c in m.text):
                    continue
                text_for_words = m.text.replace('_', ' ')
                words = [w.lower() for w in re.findall(r'\b\w+\b', text_for_words)]
                if any(w in self.person_blacklisted_words for w in words):
                    continue
                if any(w in self.location_words for w in words):
                    continue
                    
            filtered_matches.append(m)

        return filtered_matches
