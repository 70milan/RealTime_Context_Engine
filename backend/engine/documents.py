"""Text from uploaded .docx resumes."""
import os
import sys
import json
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from openai import AsyncOpenAI


def _docx_document():
    try:
        from docx import Document
        return Document
    except ModuleNotFoundError:
        return None


def _docx_text(content: bytes) -> str:
    """Text of a .docx in document order, including tables (resumes often keep skills in one)."""
    from io import BytesIO
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(BytesIO(content))
    lines = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            text = Paragraph(child, doc).text.strip()
            if text:
                lines.append(text)
        elif tag == 'tbl':
            for row in Table(child, doc).rows:
                cells = []
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and text not in cells:  # merged cells repeat their text
                        cells.append(text)
                if cells:
                    lines.append(" | ".join(cells))
    return "\n".join(lines)
