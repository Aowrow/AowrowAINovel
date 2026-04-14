from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class MarkdownSection:
    level: int
    title: str
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
NUMBERED_RE = re.compile(r"^\s*\d+[.)、]\s+(.+?)\s*$")
KV_RE = re.compile(r"^\s*[-*]?\s*([^:：]{1,40})[:：]\s*(.+?)\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_DIVIDER_RE = re.compile(r"^\s*\|?\s*[:\- ]+\|\s*[:\- |]+\s*$")


def parse_sections(markdown: str) -> list[MarkdownSection]:
    sections: list[MarkdownSection] = []
    current = MarkdownSection(level=0, title="__root__", lines=[])

    for raw in markdown.splitlines():
        match = HEADING_RE.match(raw)
        if match:
            if current.title != "__root__" or current.lines:
                sections.append(current)
            level = len(match.group(1))
            title = match.group(2).strip()
            current = MarkdownSection(level=level, title=title, lines=[])
            continue
        current.lines.append(raw.rstrip())

    if current.title != "__root__" or current.lines:
        sections.append(current)
    return sections


def extract_backticks(markdown: str) -> list[str]:
    return [item.strip() for item in re.findall(r"`([^`]{4,500})`", markdown) if item.strip()]


def extract_bullets(lines: Iterable[str]) -> list[str]:
    results: list[str] = []
    for line in lines:
        m = BULLET_RE.match(line)
        if m:
            results.append(clean_sentence(m.group(1)))
    return [x for x in results if x]


def extract_numbered(lines: Iterable[str]) -> list[str]:
    results: list[str] = []
    for line in lines:
        m = NUMBERED_RE.match(line)
        if m:
            results.append(clean_sentence(m.group(1)))
    return [x for x in results if x]


def first_nonempty_line(lines: Iterable[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return clean_sentence(stripped)
    return ""


def clean_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = cleaned.strip("-*+")
    return cleaned.strip()


def parse_key_values(lines: Iterable[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in lines:
        m = KV_RE.match(line)
        if not m:
            continue
        key = normalize_key(m.group(1))
        value = clean_sentence(m.group(2))
        if key and value:
            data[key] = value
    return data


def normalize_key(key: str) -> str:
    key = key.strip().lower()
    key = key.replace("（", "(").replace("）", ")")
    key = re.sub(r"\s+", "_", key)
    return key


def parse_markdown_table(lines: list[str]) -> list[dict[str, str]]:
    rows: list[list[str]] = []
    for line in lines:
        if not TABLE_ROW_RE.match(line):
            continue
        if TABLE_DIVIDER_RE.match(line):
            continue
        cells = [clean_sentence(part) for part in line.strip().strip("|").split("|")]
        if any(cells):
            rows.append(cells)

    if len(rows) < 2:
        return []

    headers = [normalize_key(h) for h in rows[0]]
    records: list[dict[str, str]] = []
    for raw in rows[1:]:
        record: dict[str, str] = {}
        for idx, value in enumerate(raw):
            if idx >= len(headers):
                break
            if headers[idx]:
                record[headers[idx]] = value
        if record:
            records.append(record)
    return records

