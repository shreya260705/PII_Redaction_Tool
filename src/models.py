from dataclasses import dataclass
from typing import Any, List, Optional

@dataclass
class BlockLocation:
    """
    Coordinates representing the location of a block in the Word document.
    These coordinates serve as the stable source of truth for deserialization,
    mapping spans back to original DOCX paragraphs or cells.
    """
    part_type: str  # "body", "header", "footer"
    section_index: Optional[int] = None
    header_footer_type: Optional[str] = None  # "default", "first_page", "even_page"
    paragraph_index: Optional[int] = None
    table_index: Optional[int] = None
    row_index: Optional[int] = None
    cell_index: Optional[int] = None

    def to_dict(self) -> dict:
        """Returns a dict representation containing only non-None fields."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class DocumentBlock:
    """
    Represents an ordered, extracted block of text along with its location
    and the underlying python-docx elements.
    """
    block_id: int  # Incremental document order index
    block_type: str  # "paragraph", "table_cell", "header_paragraph", "footer_paragraph", etc.
    text: str
    location: BlockLocation
    element: Any = None  # Optional python-docx in-memory object (Paragraph or _Cell)


@dataclass
class DocumentMetadata:
    """
    Summary stats and metadata of the extracted document.
    """
    source_file: str
    paragraph_count: int
    table_count: int
    table_cell_count: int
    header_footer_block_count: int
    total_text_length: int


@dataclass
class ExtractedDocument:
    """
    Container representing the entire extracted document structure.
    """
    metadata: DocumentMetadata
    blocks: List[DocumentBlock]
