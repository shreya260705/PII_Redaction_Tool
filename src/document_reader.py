import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Any, Generator, List, Union

import docx
from docx.text.paragraph import Paragraph
from docx.table import Table

from src.models import BlockLocation, DocumentBlock, DocumentMetadata, ExtractedDocument

# Configure logger for this module
logger = logging.getLogger(__name__)


class DocumentReader:
    """
    Reads and extracts text blocks from a DOCX file while preserving physical
    document layout order and mapping precise structural location coordinates.
    """

    @staticmethod
    def _iter_container_elements(container: Any, parent: Any) -> Generator[Union[Paragraph, Table], None, None]:
        """
        Yields Paragraph or Table objects in physical order from a BlockItemContainer
        (such as Document, _Cell, _Header, or _Footer).
        """
        # Document body elements are stored in element.body
        # Header, Footer, and Cell elements are in _element
        if hasattr(container, 'element') and hasattr(container.element, 'body'):
            element = container.element.body
        elif hasattr(container, '_element'):
            element = container._element
        else:
            element = container

        for child in element.iterchildren():
            tag = child.tag
            if tag.endswith('p'):
                yield Paragraph(child, parent)
            elif tag.endswith('tbl'):
                yield Table(child, parent)

    @classmethod
    def read(cls, file_path: Union[str, Path]) -> ExtractedDocument:
        """
        Reads a DOCX file and returns a structured ExtractedDocument containing
        all paragraphs, tables, headers, and footers in order.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not a valid DOCX.
        """
        path = Path(file_path)
        logger.info(f"Initiating extraction on: {path}")

        if not path.exists():
            logger.error(f"File not found: {path}")
            raise FileNotFoundError(f"The file '{path}' does not exist.")

        if path.suffix.lower() != '.docx':
            logger.error(f"Invalid file extension: {path.suffix}")
            raise ValueError(f"Invalid file format: '{path.name}'. Only '.docx' files are supported.")

        try:
            doc = docx.Document(path)
        except Exception as e:
            logger.exception(f"Exception raised while opening docx file {path}")
            raise ValueError(f"Unreadable or corrupted Word document: {e}") from e

        blocks: List[DocumentBlock] = []
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

                # Read elements in order inside this header/footer container
                for child in cls._iter_container_elements(hf_container, hf_container):
                    if isinstance(child, Paragraph):
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

                    elif isinstance(child, Table):
                        for r_idx, row in enumerate(child.rows):
                            for c_idx, cell in enumerate(row.cells):
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
            if isinstance(child, Paragraph):
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

            elif isinstance(child, Table):
                for r_idx, row in enumerate(child.rows):
                    for c_idx, cell in enumerate(row.cells):
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

        logger.info(f"Extraction complete for {path.name}. Total blocks: {len(blocks)}")
        return ExtractedDocument(metadata=metadata, blocks=blocks)


def main() -> None:
    """CLI utility entrypoint."""
    parser = argparse.ArgumentParser(description="Inspect and extract text from a DOCX file.")
    parser.add_argument("path", type=str, help="Path to the DOCX file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose log output.")
    args = parser.parse_args()

    # Setup simple logging to stdout
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")

    try:
        doc = DocumentReader.read(args.path)
        print(f"Document: {args.path}")
        print(f"Paragraphs (Body): {doc.metadata.paragraph_count}")
        print(f"Tables (Body): {doc.metadata.table_count}")
        print(f"Table Cells (Body): {doc.metadata.table_cell_count}")
        print(f"Header/Footer Blocks: {doc.metadata.header_footer_block_count}")
        print(f"Total Text Length: {doc.metadata.total_text_length} chars")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
