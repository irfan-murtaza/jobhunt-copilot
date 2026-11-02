"""Turn uploaded resume files into plain text.

Only PDF and DOCX are accepted. The type is decided from the file's magic bytes, not the
filename or the client-supplied content type, because both are trivially spoofed.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Literal

from docx import Document as DocxDocument
from pypdf import PdfReader
from pypdf.errors import PyPdfError

FileKind = Literal["pdf", "docx"]
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class UnsupportedFileError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


@dataclass(slots=True)
class ExtractedText:
    kind: FileKind
    text: str
    pages: int


def detect_kind(data: bytes) -> FileKind:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04") and _zip_has(data, "word/document.xml"):
        return "docx"
    raise UnsupportedFileError("Only PDF and DOCX files are supported")


def _zip_has(data: bytes, member: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return member in archive.namelist()
    except zipfile.BadZipFile:
        return False


def extract_text(data: bytes) -> ExtractedText:
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedFileError("File is larger than 5 MB")
    kind = detect_kind(data)
    text, pages = _extract_pdf(data) if kind == "pdf" else _extract_docx(data)
    text = normalise_whitespace(text)
    if len(text) < 50:
        raise EmptyDocumentError(
            "Could not find readable text. Scanned image PDFs are not supported; export a text PDF."
        )
    return ExtractedText(kind=kind, text=text, pages=pages)


def _extract_pdf(data: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(data))
        chunks = [page.extract_text() or "" for page in reader.pages]
    except PyPdfError as exc:
        raise UnsupportedFileError(f"Could not read PDF: {exc}") from exc
    return "\n\n".join(chunks), len(reader.pages)


def _extract_docx(data: bytes) -> tuple[str, int]:
    document = DocxDocument(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            lines.append(" | ".join(c for c in cells if c))
    return "\n".join(lines), 1


_BLANK_RUN = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t\xa0]+")


def normalise_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_RUN.sub("\n\n", text).strip()
