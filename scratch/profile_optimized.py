import os
import sys
import time

sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.document_reader import DocumentReader
from src.detectors.base import resolve_overlaps, BaseDetector
from src.detectors.structured import (
    EmailDetector,
    PhoneDetector,
    IPAddressDetector,
    SSNDetector,
    CreditCardDetector,
    DateOfBirthDetector,
)
from src.detectors.nlp import NLPDetector
from src.redactor import RedactionMapper, redact_block

# Let's subclass or patch the detectors to add fast pre-checks
class OptimizedEmailDetector(EmailDetector):
    def detect(self, text: str):
        if "@" not in text:
            return []
        return super().detect(text)

class OptimizedPhoneDetector(PhoneDetector):
    def detect(self, text: str):
        # Indian phone numbers need at least 8 digits
        digit_count = 0
        for c in text:
            if c.isdigit():
                digit_count += 1
                if digit_count >= 8:
                    break
        if digit_count < 8:
            return []
        return super().detect(text)

class OptimizedIPAddressDetector(IPAddressDetector):
    def detect(self, text: str):
        if "." not in text:
            return []
        return super().detect(text)

class OptimizedSSNDetector(SSNDetector):
    def detect(self, text: str):
        digit_count = 0
        for c in text:
            if c.isdigit():
                digit_count += 1
                if digit_count >= 9:
                    break
        if digit_count < 9:
            return []
        return super().detect(text)

class OptimizedCreditCardDetector(CreditCardDetector):
    def detect(self, text: str):
        digit_count = 0
        for c in text:
            if c.isdigit():
                digit_count += 1
                if digit_count >= 13:
                    break
        if digit_count < 13:
            return []
        return super().detect(text)

class OptimizedDateOfBirthDetector(DateOfBirthDetector):
    def detect(self, text: str):
        digit_count = 0
        for c in text:
            if c.isdigit():
                digit_count += 1
                if digit_count >= 2:
                    break
        if digit_count < 2:
            return []
        return super().detect(text)

class OptimizedNLPDetector(NLPDetector):
    def detect(self, text: str):
        # If there are no uppercase letters, it cannot contain PERSON, COMPANY, or ADDRESS
        if not any(c.isupper() for c in text):
            return []
            
        # Also let's run the analyzer directly without calling self.nlp(text)
        matches = []
        
        # Run Presidio Analyzer
        try:
            results = self.analyzer.analyze(
                text=text,
                language="en",
                entities=["PERSON", "ORGANIZATION", "LOCATION"]
            )
        except Exception as e:
            results = []

        # Process results
        for res in results:
            if res.entity_type == "PERSON":
                matched_text = text[res.start:res.end].strip()
                if not matched_text:
                    continue

                start, end = res.start, res.end
                
                # Trim corporate roles/designations suffix
                if "," in matched_text:
                    parts = matched_text.split(",")
                    designation_regex = self.person_context_rx # wait, we can compile it or reuse
                    # let's just use the self attributes
                    import re
                    designation_regex = re.compile(
                        r'^\s*(?:managing\s+director|independent\s+director|executive\s+director|director|company\s+secretary|compliance\s+officer|auditor|ceo|cfo|promoter|chairman|secretary|officer|underwriter|registrar)\b',
                        re.IGNORECASE
                    )
                    if designation_regex.search(parts[1]):
                        matched_text = parts[0].strip()
                        end = start + len(matched_text)

                # Trim corporate designations prefix
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

                # Expand to the left to capture adjacent capitalized words
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

                # Query spaCy tags to see if this candidate overlaps with GPE or LOC
                # Instead of doc.ents, we check other results with LOCATION/GPE from Presidio
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
                    if kw_start < start:
                         from src.detectors.structured import has_sentence_boundary_between
                         boundary = has_sentence_boundary_between(text, kw_end, start)
                    else:
                         from src.detectors.structured import has_sentence_boundary_between
                         boundary = has_sentence_boundary_between(text, end, kw_start)
                    if not boundary:
                        has_context = True
                        break

                # Reject location-only PERSON predictions unless there is strong context
                if is_loc_gpe and not has_context:
                    continue

                confidence = 0.95 if has_context else 0.85
                from src.models import PIIMatch
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
                import re
                matched_text = text[res.start:res.end].strip()
                if not matched_text:
                    continue

                start, end = res.start, res.end
                while matched_text and matched_text[0] in ",. -/\n\t":
                    matched_text = matched_text[1:]
                    start += 1
                while matched_text and matched_text[-1] in ",. -/\n\t":
                    matched_text = matched_text[:-1]
                    end -= 1

                if self.non_company_rx.search(matched_text):
                    continue

                matched_words = set(w.lower() for w in re.findall(r'\b\w+\b', matched_text))
                if matched_words.intersection(self.company_blacklist_words):
                    continue

                from src.detectors.nlp import is_part_of_legislative_title
                if is_part_of_legislative_title(text, end, self.company_blacklist_words):
                    continue

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
                    confidence = 0.70

                if confidence >= 0.90:
                    from src.models import PIIMatch
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

        # 3. Custom Company Regex Scanner
        for regex in (self.company_regex_capitalized, self.company_regex_uppercase):
            for m in regex.finditer(text):
                matched_text = m.group().strip()
                if self.non_company_rx.search(matched_text):
                    continue
                import re
                matched_words = set(w.lower() for w in re.findall(r'\b\w+\b', matched_text))
                if matched_words.intersection(self.company_blacklist_words):
                    continue
                from src.detectors.nlp import is_part_of_legislative_title
                if is_part_of_legislative_title(text, m.end(), self.company_blacklist_words):
                    continue
                from src.models import PIIMatch
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
        loc_results = [r for r in results if r.entity_type in ("LOCATION", "GPE")]
        pin_matches = list(self.pin_regex.finditer(text))
        text_lower = text.lower()
        import re
        keyword_hits = [kw for kw in self.address_keywords if re.search(r'\b' + re.escape(kw) + r'\b', text_lower)]

        has_geo_context = len(loc_results) > 0

        is_address = False
        score = 0.0

        if len(keyword_hits) >= 1:
            if pin_matches:
                is_address = True
                score = 0.95
            elif len(keyword_hits) + len(loc_results) >= 2:
                is_address = True
                score = 0.85
        elif pin_matches and has_geo_context:
            is_address = True
            score = 0.85

        if is_address:
            indices = []
            for kw in self.address_keywords:
                for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text_lower):
                    indices.append((m.start(), m.end()))
            for res in loc_results:
                indices.append((res.start, res.end))
            for m in pin_matches:
                indices.append((m.start(), m.end()))

            if indices:
                start = min(idx[0] for idx in indices)
                end = max(idx[1] for idx in indices)

                span_text = text[start:end]
                while span_text and span_text[0] in ",. -/\n\t":
                    span_text = span_text[1:]
                    start += 1
                while span_text and span_text[-1] in ",. -/\n\t":
                    span_text = span_text[:-1]
                    end -= 1

                if len(span_text.strip()) > 3 and span_text.lower() not in [
                    "india", "pune", "mumbai", "maharashtra", "united states", 
                    "chakan, maharashtra", "chakan"
                ]:
                    from src.models import PIIMatch
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

        # Custom name regex
        for m in self.name_regex.finditer(text):
            candidate = m.group()
            start, end = m.start(), m.end()
            
            is_non_person_ent = False
            for other_res in results:
                if other_res.entity_type in ("ORGANIZATION", "LOCATION"):
                    if max(start, other_res.start) < min(end, other_res.end):
                        is_non_person_ent = True
                        break
            if is_non_person_ent:
                continue
                
            overlaps_existing = False
            for existing in matches:
                if max(start, existing.start) < min(end, existing.end):
                    overlaps_existing = True
                    break
            if overlaps_existing:
                continue

            from src.models import PIIMatch
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

        # Overlap resolution between COMPANY and ADDRESS
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

def main():
    large_doc = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
    
    print("Reading document...")
    start_time = time.time()
    extracted = DocumentReader.read(large_doc)
    print(f"Read done in {time.time() - start_time:.2f} seconds.")
    
    print("Initializing optimized detectors...")
    start_time = time.time()
    email_det = OptimizedEmailDetector()
    phone_det = OptimizedPhoneDetector()
    ip_det = OptimizedIPAddressDetector()
    ssn_det = OptimizedSSNDetector()
    cc_det = OptimizedCreditCardDetector()
    dob_det = OptimizedDateOfBirthDetector()
    nlp_det = OptimizedNLPDetector()
    
    detectors = [email_det, phone_det, ip_det, ssn_det, cc_det, dob_det, nlp_det]
    validators = [
        ("EMAIL", email_det),
        ("PHONE", phone_det),
        ("IP_ADDRESS", ip_det),
        ("SSN", ssn_det),
        ("CREDIT_CARD", cc_det),
        ("DATE_OF_BIRTH", dob_det),
        ("PERSON", nlp_det),
        ("COMPANY", nlp_det),
        ("ADDRESS", nlp_det),
    ]
    mapper = RedactionMapper(validators=validators)
    print(f"Initialized in {time.time() - start_time:.2f} seconds.")
    
    print("Running optimized redaction loop...")
    start_time = time.time()
    
    total_replacements = 0
    processed_elements = set()
    
    for i, block in enumerate(extracted.blocks):
        if not block.text or not block.text.strip():
            continue
            
        if block.element is not None:
            element = getattr(block.element, "_element", block.element)
            element_id = id(element)
            if element_id in processed_elements:
                continue
            processed_elements.add(element_id)
            
        is_heading_or_title = False
        if block.block_type in ("paragraph", "header_paragraph", "footer_paragraph") and block.element is not None:
            try:
                style_name = block.element.style.name
                if style_name in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5", "Heading 6", "Heading 7", "Heading 8", "Heading 9"):
                    is_heading_or_title = True
            except Exception:
                pass
                
        block_matches = []
        for detector in detectors:
            if isinstance(detector, OptimizedNLPDetector) and is_heading_or_title:
                continue
            try:
                matches = detector.detect(block.text)
                block_matches.extend(matches)
            except Exception as e:
                pass
                
        resolved = resolve_overlaps(block_matches)
        applied = redact_block(block, resolved, mapper)
        total_replacements += len(applied)
        
        if i > 0 and i % 500 == 0:
            print(f"Processed {i} blocks... replacements so far: {total_replacements}")
            
    print(f"Redaction loop done in {time.time() - start_time:.2f} seconds!")
    print(f"Total replacements: {total_replacements}")

if __name__ == "__main__":
    main()
