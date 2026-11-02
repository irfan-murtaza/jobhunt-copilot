from pathlib import Path

import pytest

from helpers import build_pdf
from jobhunt.services.text_extraction import (
    EmptyDocumentError,
    UnsupportedFileError,
    detect_kind,
    extract_text,
    normalise_whitespace,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_pdf_text_is_extracted() -> None:
    result = extract_text((FIXTURES / "resume.pdf").read_bytes())
    assert result.kind == "pdf"
    assert result.pages == 1
    assert "Northwind Analytics" in result.text
    assert "Kafka" in result.text


def test_docx_text_includes_paragraphs_and_tables() -> None:
    result = extract_text((FIXTURES / "resume.docx").read_bytes())
    assert result.kind == "docx"
    assert "Led migration of a Django monolith" in result.text
    assert "Python | FastAPI | PostgreSQL" in result.text


def test_type_is_detected_from_magic_bytes_not_name() -> None:
    assert detect_kind(b"%PDF-1.7 garbage") == "pdf"
    with pytest.raises(UnsupportedFileError):
        detect_kind(b"PK\x03\x04 not really a docx")
    with pytest.raises(UnsupportedFileError):
        detect_kind(b"<html>nope</html>")


def test_oversized_file_rejected() -> None:
    with pytest.raises(UnsupportedFileError):
        extract_text(b"%PDF-" + b"0" * (5 * 1024 * 1024 + 1))


def test_pdf_without_text_is_reported() -> None:
    with pytest.raises(EmptyDocumentError):
        extract_text(build_pdf([]))


def test_corrupt_pdf_is_an_unsupported_file_not_a_crash() -> None:
    with pytest.raises(UnsupportedFileError):
        extract_text(b"%PDF-1.4\n1 0 obj << /Type /Catalog >>\n" + b"x" * 100)


def test_whitespace_normalisation() -> None:
    assert normalise_whitespace("a \t b\r\n\n\n\n  c  ") == "a b\n\nc"
