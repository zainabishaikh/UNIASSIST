"""
Policy Loader Module (policy_loader.py)
Ingests structured university policy circulars (.txt, .md, .pdf) into
metadata-tagged atomic JSON policy sections without severing multi-condition rules.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


SECTION_HEADER_RE = re.compile(
    r"^===\s*SECTION:\s*(?P<policy_id>[^|]+?)\s*\|\s*DEPT:\s*(?P<department>[^|]+?)\s*\|\s*ROLE:\s*(?P<target_role>[^|]+?)\s*\|\s*TITLE:\s*(?P<title>.+?)\s*===\s*$",
    re.MULTILINE,
)

VALID_DEPARTMENTS = {
    "ELIGIBILITY",
    "FEES",
    "SCHOLARSHIPS",
    "ADMISSIONS",
    "HOSTEL",
    "EXAMINATIONS",
}
VALID_ROLES = {"applicant", "student", "both"}


@dataclass
class PolicySection:
    """Atomic, metadata-tagged university policy section."""

    policy_id: str
    department: str
    target_role: str
    title: str
    content_text: str
    source_file: str = "university_policies.txt"

    def to_dict(self) -> dict:
        return asdict(self)


def extract_text_from_file(file_path: Path) -> str:
    """Extracts UTF-8 text from .txt, .md, or .pdf policy files."""
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError("pypdf is required to ingest .pdf policy files.")
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    raise ValueError(f"Unsupported policy file extension: {suffix}")


def _normalize_department(dept: str) -> str:
    cleaned = dept.strip().upper()
    if cleaned in {"EXAM", "EXAMS"}:
        cleaned = "EXAMINATIONS"
    elif cleaned in {"SCHOLARSHIP"}:
        cleaned = "SCHOLARSHIPS"
    elif cleaned in {"FEE"}:
        cleaned = "FEES"
    elif cleaned in {"ADMISSION"}:
        cleaned = "ADMISSIONS"
    return cleaned if cleaned in VALID_DEPARTMENTS else cleaned


def _normalize_role(role: str) -> str:
    cleaned = role.strip().lower()
    if cleaned in {"prospective", "prospective_applicant"}:
        return "applicant"
    if cleaned in {"enrolled", "current_student"}:
        return "student"
    return cleaned if cleaned in VALID_ROLES else "both"


def parse_policy_text(
    raw_text: str,
    source_file: str = "uploaded_circular.txt",
    default_department: str = "ADMISSIONS",
    default_role: str = "both",
) -> List[PolicySection]:
    """
    Segments policy text along explicit SECTION metadata delimiters.
    Falls back to markdown heading segmentation only if no explicit markers exist.
    """
    matches = list(SECTION_HEADER_RE.finditer(raw_text))
    sections: List[PolicySection] = []

    if matches:
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_text)
            body = raw_text[start:end].strip()
            if not body:
                continue
            sections.append(
                PolicySection(
                    policy_id=match.group("policy_id").strip(),
                    department=_normalize_department(match.group("department")),
                    target_role=_normalize_role(match.group("target_role")),
                    title=match.group("title").strip(),
                    content_text=body,
                    source_file=source_file,
                )
            )
        return sections

    # Fallback: split unmarked circulars on Markdown headings (# / ##) or blank-line blocks
    blocks = re.split(r"\n(?=#{1,3}\s+)", raw_text.strip())
    stem_tag = re.sub(r"[^A-Z0-9]+", "-", Path(source_file).stem.upper()).strip("-")[:10] or "CIRC"
    for idx, block in enumerate(blocks, start=1):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        heading = lines[0].lstrip("#").strip() if lines[0].startswith("#") else f"{Path(source_file).stem} Clause {idx}"
        content = "\n".join(lines[1:]).strip() if lines[0].startswith("#") and len(lines) > 1 else block
        sections.append(
            PolicySection(
                policy_id=f"POL-{stem_tag}-{idx:02d}",
                department=_normalize_department(default_department),
                target_role=_normalize_role(default_role),
                title=heading[:120],
                content_text=content,
                source_file=source_file,
            )
        )
    return sections


def load_policy_corpus(
    data_dir: str | Path,
    export_json_path: Optional[str | Path] = None,
) -> List[PolicySection]:
    """Loads and parses all .txt, .md, and .pdf files in data_dir into atomic PolicySection records."""
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Policy data directory not found: {data_path}")

    supported_exts = {".txt", ".md", ".pdf"}
    files = sorted(
        [p for p in data_path.iterdir() if p.is_file() and p.suffix.lower() in supported_exts]
    )

    all_sections: List[PolicySection] = []
    seen_ids = set()
    for file_path in files:
        raw_text = extract_text_from_file(file_path)
        parsed = parse_policy_text(raw_text, source_file=file_path.name)
        for sec in parsed:
            if sec.policy_id in seen_ids:
                sec.policy_id = f"{sec.policy_id}-{len(seen_ids)+1}"
            seen_ids.add(sec.policy_id)
            all_sections.append(sec)

    if export_json_path is not None:
        out_path = Path(export_json_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps([s.to_dict() for s in all_sections], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return all_sections
