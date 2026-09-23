"""Form-aware section extraction from SEC filing HTML or complete submission text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser

from sec_filing_agent.models import FilingMetadata, ParsedSection

MAX_SECTION_CHARS = 15_000


@dataclass(frozen=True)
class SectionSpec:
    item_code: str
    label: str
    pattern: str
    required_part: str | None = None


@dataclass
class SectionParseResult:
    sections: list[ParsedSection]
    warnings: list[str]


class _FilingTextParser(HTMLParser):
    """Convert filing markup to readable block text without losing table row boundaries."""

    _BREAK_TAGS = {
        "address",
        "article",
        "blockquote",
        "br",
        "caption",
        "dd",
        "div",
        "dl",
        "dt",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "table",
        "tbody",
        "thead",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if normalized_tag in self._BREAK_TAGS:
            self.parts.append("\n")
        if normalized_tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if not self._ignored_depth and normalized_tag in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def extract_sections(
    content: str,
    filing: FilingMetadata,
    *,
    source_url: str,
    document_kind: str,
    max_chars: int | None = MAX_SECTION_CHARS,
) -> SectionParseResult:
    """Extract form-specific sections and explain every missing or ambiguous match.

    ``None`` preserves a complete section for durable storage. API callers keep the
    bounded default so a single filing cannot produce an unexpectedly large response.
    """

    if max_chars is not None and max_chars < 1:
        raise ValueError("max_chars must be positive or None")

    text = filing_text(content)
    specs = section_specs_for(filing.form_type)
    if not specs:
        return SectionParseResult([], [f"unsupported_form:{filing.form_type}"])

    warnings: list[str] = []
    selected: list[tuple[int, SectionSpec]] = []
    for spec in specs:
        matches = [
            match
            for match in re.finditer(spec.pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if _matches_part(text, match.start(), spec.required_part)
        ]
        if not matches:
            warnings.append(f"section_not_found:{spec.item_code}")
            continue
        if len(matches) > 1:
            warnings.append(f"duplicate_heading_ignored:{spec.item_code}:{len(matches) - 1}")
        # Repeated anchored headings are normally a table of contents followed by body text.
        # Cross-references inside paragraphs do not match because patterns are line-anchored.
        selected.append((matches[-1].start(), spec))

    selected.sort(key=lambda item: item[0])
    sections: list[ParsedSection] = []
    for index, (start, spec) in enumerate(selected):
        # The following recognized heading is a stable boundary even when a filing uses
        # inconsistent HTML nesting. Offsets refer to the normalized text below.
        end = selected[index + 1][0] if index + 1 < len(selected) else len(text)
        section_text = text[start:end].strip()
        if len(section_text) < 80:
            warnings.append(f"section_unusually_short:{spec.item_code}:{len(section_text)}")
        truncated = max_chars is not None and len(section_text) > max_chars
        if truncated:
            assert max_chars is not None
            section_text = f"{section_text[:max_chars].rstrip()}\n[... truncated for length ...]"
        sections.append(
            ParsedSection(
                filing_accession=filing.accession_number,
                form_type=filing.form_type,
                report_date=filing.report_date,
                item_code=spec.item_code,
                label=spec.label,
                text=section_text,
                source_url=source_url,
                source_start=start,
                source_end=end,
                truncated=truncated,
                document_kind=document_kind,  # type: ignore[arg-type]
            )
        )
    return SectionParseResult(sections, warnings)


def filing_text(content: str) -> str:
    """Normalize HTML into line-oriented text suitable for RAG chunking and citations."""

    parser = _FilingTextParser()
    parser.feed(content)
    parser.close()
    lines = []
    for line in "".join(parser.parts).replace("\r", "\n").split("\n"):
        # Lines retain paragraph/table row boundaries; whitespace is normalized only
        # within a line so the result is friendlier to later chunking and citation.
        normalized = re.sub(r"[\t\f\v ]+", " ", unescape(line)).strip()
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


def section_specs_for(form_type: str) -> tuple[SectionSpec, ...]:
    form = form_type.strip().upper()
    if form in {"10-K", "10-K/A", "10-KT"}:
        return _TEN_K_SPECS
    if form in {"10-Q", "10-Q/A"}:
        return _TEN_Q_SPECS
    if form in {"8-K", "8-K/A"}:
        return _EIGHT_K_SPECS
    if form in {"20-F", "20-F/A", "40-F", "40-F/A"}:
        return _FOREIGN_ANNUAL_SPECS
    if form in {"6-K", "6-K/A"}:
        return _SIX_K_SPECS
    if form in {"DEF 14A", "DEFR14A", "DEFA14A"}:
        return _PROXY_SPECS
    return ()


def _matches_part(text: str, position: int, required_part: str | None) -> bool:
    if required_part is None:
        return True
    prefix = text[:position]
    part_i = [match.start() for match in re.finditer(r"(?im)^\s*PART\s+I\b", prefix)]
    part_ii = [match.start() for match in re.finditer(r"(?im)^\s*PART\s+II\b", prefix)]
    last_i = part_i[-1] if part_i else -1
    last_ii = part_ii[-1] if part_ii else -1
    if required_part == "I":
        return last_i > last_ii
    return last_ii > last_i


def _item_pattern(item: str, heading: str = r".*") -> str:
    escaped = re.escape(item).replace(r"\ ", r"\s*")
    return rf"^\s*ITEM\s*{escaped}(?:[.\-–—\s]+){heading}$"


_TEN_K_SPECS = (
    SectionSpec("1", "Item 1 - Business", _item_pattern("1", r".*\bBUSINESS\b.*")),
    SectionSpec("1A", "Item 1A - Risk Factors", _item_pattern("1A", r".*\bRISK\b.*")),
    SectionSpec("7", "Item 7 - MD&A", _item_pattern("7", r".*(?:MANAGEMENT|MD&A).*")),
    SectionSpec("7A", "Item 7A - Market Risk", _item_pattern("7A", r".*\bMARKET\b.*")),
    SectionSpec("8", "Item 8 - Financial Statements", _item_pattern("8", r".*\bFINANCIAL\b.*")),
)

_TEN_Q_SPECS = (
    SectionSpec(
        "part_i_item_1",
        "Part I Item 1 - Financial Statements",
        _item_pattern("1", r".*\bFINANCIAL\b.*"),
        "I",
    ),
    SectionSpec(
        "part_i_item_2",
        "Part I Item 2 - MD&A",
        _item_pattern("2", r".*(?:MANAGEMENT|MD&A).*"),
        "I",
    ),
    SectionSpec(
        "part_ii_item_1a",
        "Part II Item 1A - Risk Factors",
        _item_pattern("1A", r".*\bRISK\b.*"),
        "II",
    ),
)

_EIGHT_K_SPECS = tuple(
    SectionSpec(code, f"Item {code}", _item_pattern(code, r".*"))
    for code in (
        "1.01",
        "1.02",
        "1.03",
        "2.01",
        "2.02",
        "2.03",
        "5.01",
        "5.02",
        "5.03",
        "7.01",
        "9.01",
    )
)

_FOREIGN_ANNUAL_SPECS = tuple(
    SectionSpec(code, f"Item {code}", _item_pattern(code, r".*")) for code in ("3", "4", "5", "18")
)

_SIX_K_SPECS = (
    SectionSpec(
        "earnings_results",
        "Earnings / Financial Results",
        r"^.*\b(?:EARNINGS|FINANCIAL RESULTS|RESULTS OF OPERATIONS|FINANCIAL RELEASE)\b.*$",
    ),
    SectionSpec("material_event", "Material Event", r"^.*\bMATERIAL EVENT\b.*$"),
)

_PROXY_SPECS = (
    SectionSpec("background", "Background", r"^\s*BACKGROUND\b.*$"),
    SectionSpec("proposal_1", "Proposal 1", r"^\s*PROPOSAL\s+1\b.*$"),
    SectionSpec(
        "compensation_discussion",
        "Compensation Discussion and Analysis",
        r"^\s*COMPENSATION DISCUSSION(?:\s+AND\s+ANALYSIS)?\b.*$",
    ),
    SectionSpec(
        "executive_compensation",
        "Executive Compensation",
        r"^\s*EXECUTIVE COMPENSATION\b.*$",
    ),
)
