"""Convert job-description HTML into readable plain text without extra dependencies."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "section",
    "article",
    "blockquote",
    "pre",
}
_SKIP_TAGS = {"script", "style", "noscript", "head", "title"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "li":
            self._parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS and tag != "li":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


_MULTI_BLANK = re.compile(r"\n\s*\n\s*\n+")
_TRAILING = re.compile(r"[ \t]+\n")


def html_to_text(markup: str | None) -> str:
    if not markup:
        return ""
    # Greenhouse returns HTML with entities escaped twice; unescaping first is harmless otherwise.
    if "&lt;" in markup and "<" not in markup:
        markup = html.unescape(markup)
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    text = parser.text().replace("\xa0", " ")
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _TRAILING.sub("\n", text)
    return _MULTI_BLANK.sub("\n\n", text).strip()
