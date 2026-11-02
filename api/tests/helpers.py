import json
from pathlib import Path

from jobhunt.schemas.profile import ProfileDocument

SAMPLE = Path(__file__).parents[1] / "seeds" / "sample_profile.json"


def load_sample() -> ProfileDocument:
    """The fictional seed profile, validated."""
    raw = json.loads(SAMPLE.read_text())
    raw.pop("_comment", None)
    return ProfileDocument.model_validate(raw)


def build_pdf(lines: list[str]) -> bytes:
    """A minimal valid single-page PDF with the given text lines (no extra dependencies)."""
    body = "BT /F1 11 Tf 40 760 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)
