import os
import sys
import time
import re
import docx
from docx.table import _Cell

sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.models import BlockLocation, DocumentBlock, DocumentMetadata, ExtractedDocument
from src.detectors.base import resolve_overlaps
from src.redactor import RedactionMapper, redact_block
from scratch.test_precheck_safety import SuperSafeNLPDetector
from scratch.test_clean_prechecks import (
    SafeEmailDetector,
    SafePhoneDetector,
    SafeIPAddressDetector,
    SafeSSNDetector,
    SafeCreditCardDetector,
    SafeDateOfBirthDetector
)

class SuperOptimizedDocumentReader:
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

        # Unique parts cache
        unique_parts = set()
        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type'

        # 1. Extract Headers and Footers section by section (optimized using xpath & caching)
        for s_idx, section in enumerate(doc.sections):
            # Resolve headers defined in this section
            for ref in section._sectPr.xpath('w:headerReference'):
                t = ref.get(ns, 'default')
                hf_container = section.header if t == 'default' else section.first_page_header if t == 'first' else section.even_page_header
                
                if hf_container is None:
                    continue
                partname = hf_container.part.partname
                if partname in unique_parts:
                    continue
                unique_parts.add(partname)

                hf_p_idx = 0
                hf_t_idx = 0

                for child in cls._iter_container_elements(hf_container, hf_container):
                    if isinstance(child, docx.text.paragraph.Paragraph):
                        text = child.text
                        loc = BlockLocation(
                            part_type="header",
                            section_index=s_idx,
                            header_footer_type=t,
                            paragraph_index=hf_p_idx
                        )
                        block = DocumentBlock(
                            block_id=block_id_counter,
                            block_type="header_paragraph",
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
                            for c_idx, tc in enumerate(row._tr.tc_lst):
                                cell = _Cell(tc, child)
                                text = cell.text
                                loc = BlockLocation(
                                    part_type="header",
                                    section_index=s_idx,
                                    header_footer_type=t,
                                    table_index=hf_t_idx,
                                    row_index=r_idx,
                                    cell_index=c_idx
                                )
                                block = DocumentBlock(
                                    block_id=block_id_counter,
                                    block_type="header_table_cell",
                                    text=text,
                                    location=loc,
                                    element=cell
                                )
                                blocks.append(block)
                                block_id_counter += 1
                                header_footer_block_count += 1
                                total_text_length += len(text)
                        hf_t_idx += 1

            # Resolve footers defined in this section
            for ref in section._sectPr.xpath('w:footerReference'):
                t = ref.get(ns, 'default')
                hf_container = section.footer if t == 'default' else section.first_page_footer if t == 'first' else section.even_page_footer
                
                if hf_container is None:
                    continue
                partname = hf_container.part.partname
                if partname in unique_parts:
                    continue
                unique_parts.add(partname)

                hf_p_idx = 0
                hf_t_idx = 0

                for child in cls._iter_container_elements(hf_container, hf_container):
                    if isinstance(child, docx.text.paragraph.Paragraph):
                        text = child.text
                        loc = BlockLocation(
                            part_type="footer",
                            section_index=s_idx,
                            header_footer_type=t,
                            paragraph_index=hf_p_idx
                        )
                        block = DocumentBlock(
                            block_id=block_id_counter,
                            block_type="footer_paragraph",
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
                            for c_idx, tc in enumerate(row._tr.tc_lst):
                                cell = _Cell(tc, child)
                                text = cell.text
                                loc = BlockLocation(
                                    part_type="footer",
                                    section_index=s_idx,
                                    header_footer_type=t,
                                    table_index=hf_t_idx,
                                    row_index=r_idx,
                                    cell_index=c_idx
                                )
                                block = DocumentBlock(
                                    block_id=block_id_counter,
                                    block_type="footer_table_cell",
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
    
    print("Reading document using SuperOptimizedDocumentReader...")
    start_time = time.time()
    extracted = SuperOptimizedDocumentReader.read(large_doc)
    read_time = time.time() - start_time
    print(f"Read done in {read_time:.2f} seconds.")
    print(f"Total blocks extracted: {len(extracted.blocks)}")
    
    print("Initializing safe detectors...")
    start_time = time.time()
    email_det = SafeEmailDetector()
    phone_det = SafePhoneDetector()
    ip_det = SafeIPAddressDetector()
    ssn_det = SafeSSNDetector()
    cc_det = SafeCreditCardDetector()
    dob_det = SafeDateOfBirthDetector()
    nlp_det = SuperSafeNLPDetector()
    
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
    
    print("Running super optimized redaction loop...")
    start_time = time.time()
    
    total_replacements = 0
    replacements_by_type = {}
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
            except:
                pass
                
        block_matches = []
        for detector in detectors:
            if isinstance(detector, SuperSafeNLPDetector) and is_heading_or_title:
                continue
            try:
                matches = detector.detect(block.text)
                block_matches.extend(matches)
            except:
                pass
                
        resolved = resolve_overlaps(block_matches)
        applied = redact_block(block, resolved, mapper)
        total_replacements += len(applied)
        for m in applied:
            replacements_by_type[m.pii_type] = replacements_by_type.get(m.pii_type, 0) + 1
            
        if i > 0 and i % 500 == 0:
            print(f"Processed {i} blocks... replacements so far: {total_replacements}")
            
    redact_time = time.time() - start_time
    print(f"Redaction loop done in {redact_time:.2f} seconds!")
    print(f"Total replacements: {total_replacements}")
    for k, v in sorted(replacements_by_type.items()):
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
