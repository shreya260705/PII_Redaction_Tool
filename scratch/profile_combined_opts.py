import sys
sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

import time
import docx
from docx.table import _Cell
from src.models import BlockLocation, DocumentBlock, DocumentMetadata, ExtractedDocument
from scratch.test_clean_prechecks import (
    SafeEmailDetector,
    SafePhoneDetector,
    SafeIPAddressDetector,
    SafeSSNDetector,
    SafeCreditCardDetector,
    SafeDateOfBirthDetector,
    SafeNLPDetector
)
from src.detectors.base import resolve_overlaps
from src.redactor import RedactionMapper, redact_block

class OptimizedDocumentReader:
    @staticmethod
    def _iter_container_elements(container, parent):
        if hasattr(container, 'element') and hasattr(container.element, 'body'):
            element = container.element.body
        elif hasattr(container, '_element'):
            element = container._element
        else:
            element = container

        for child in element.iterchildren():
            tag = child.tag
            if tag.endswith('p'):
                yield docx.text.paragraph.Paragraph(child, parent)
            elif tag.endswith('tbl'):
                yield docx.table.Table(child, parent)

    @classmethod
    def read(cls, file_path):
        import logging
        from pathlib import Path
        path = Path(file_path)
        doc = docx.Document(path)
        
        blocks = []
        block_id_counter = 0
        header_footer_block_count = 0
        body_paragraph_count = 0
        body_table_count = 0
        table_cell_count = 0
        total_text_length = 0

        # 1. Extract Headers and Footers section by section
        for s_idx, section in enumerate(doc.sections):
            hf_parts = [
                ("header", "default", section.header),
                ("header", "first_page", section.first_page_header),
                ("header", "even_page", section.even_page_header),
                ("footer", "default", section.footer),
                ("footer", "first_page", section.first_page_footer),
                ("footer", "even_page", section.even_page_footer),
            ]

            for part_type, hf_type, hf_container in hf_parts:
                if hf_container is None:
                    continue

                hf_p_idx = 0
                hf_t_idx = 0

                for child in cls._iter_container_elements(hf_container, hf_container):
                    if isinstance(child, docx.text.paragraph.Paragraph):
                        text = child.text
                        loc = BlockLocation(
                            part_type=part_type,
                            section_index=s_idx,
                            header_footer_type=hf_type,
                            paragraph_index=hf_p_idx
                        )
                        block = DocumentBlock(
                            block_id=block_id_counter,
                            block_type=f"{part_type}_paragraph",
                            text=text,
                            location=loc,
                            element=child
                        )
                        blocks.append(block)
                        block_id_counter += 1
                        header_footer_block_count += 1
                        total_text_length += len(text)
                        hf_p_idx += 1

                    elif isinstance(child, docx.table.Table):
                        for r_idx, row in enumerate(child.rows):
                            # OPTIMIZATION: use tc_lst to avoid grid columns traversal and duplicates
                            for c_idx, tc in enumerate(row._tr.tc_lst):
                                cell = _Cell(tc, child)
                                text = cell.text
                                loc = BlockLocation(
                                    part_type=part_type,
                                    section_index=s_idx,
                                    header_footer_type=hf_type,
                                    table_index=hf_t_idx,
                                    row_index=r_idx,
                                    cell_index=c_idx
                                )
                                block = DocumentBlock(
                                    block_id=block_id_counter,
                                    block_type=f"{part_type}_table_cell",
                                    text=text,
                                    location=loc,
                                    element=cell
                                )
                                blocks.append(block)
                                block_id_counter += 1
                                header_footer_block_count += 1
                                total_text_length += len(text)
                        hf_t_idx += 1

        # 2. Extract Main Body elements in order
        body_p_idx = 0
        body_t_idx = 0

        for child in cls._iter_container_elements(doc, doc):
            if isinstance(child, docx.text.paragraph.Paragraph):
                text = child.text
                loc = BlockLocation(
                    part_type="body",
                    paragraph_index=body_p_idx
                )
                block = DocumentBlock(
                    block_id=block_id_counter,
                    block_type="paragraph",
                    text=text,
                    location=loc,
                    element=child
                )
                blocks.append(block)
                block_id_counter += 1
                body_paragraph_count += 1
                total_text_length += len(text)
                body_p_idx += 1

            elif isinstance(child, docx.table.Table):
                for r_idx, row in enumerate(child.rows):
                    # OPTIMIZATION: use tc_lst to avoid grid columns traversal and duplicates
                    for c_idx, tc in enumerate(row._tr.tc_lst):
                        cell = _Cell(tc, child)
                        text = cell.text
                        loc = BlockLocation(
                            part_type="body",
                            table_index=body_t_idx,
                            row_index=r_idx,
                            cell_index=c_idx
                        )
                        block = DocumentBlock(
                            block_id=block_id_counter,
                            block_type="table_cell",
                            text=text,
                            location=loc,
                            element=cell
                        )
                        blocks.append(block)
                        block_id_counter += 1
                        table_cell_count += 1
                        total_text_length += len(text)
                body_table_count += 1

        metadata = DocumentMetadata(
            source_file=path.name,
            paragraph_count=body_paragraph_count,
            table_count=body_table_count,
            table_cell_count=table_cell_count,
            header_footer_block_count=header_footer_block_count,
            total_text_length=total_text_length
        )

        return ExtractedDocument(metadata=metadata, blocks=blocks, doc=doc)

def main():
    large_doc = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
    
    print("Reading document using OptimizedDocumentReader...")
    start_time = time.time()
    extracted = OptimizedDocumentReader.read(large_doc)
    print(f"Read done in {time.time() - start_time:.2f} seconds.")
    print(f"Total blocks extracted: {len(extracted.blocks)}")
    
    print("Initializing safe detectors...")
    start_time = time.time()
    email_det = SafeEmailDetector()
    phone_det = SafePhoneDetector()
    ip_det = SafeIPAddressDetector()
    ssn_det = SafeSSNDetector()
    cc_det = SafeCreditCardDetector()
    dob_det = SafeDateOfBirthDetector()
    nlp_det = SafeNLPDetector()
    
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
    
    print("Running combined optimized redaction loop...")
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
            if isinstance(detector, SafeNLPDetector) and is_heading_or_title:
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
