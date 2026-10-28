"""Markdown chunking: sections by heading, blocks (paragraphs, list items, tables, code), packed to size.

- Every heading (H2, H3, H4) starts a section; the title of a chunk is the heading path.
- Sections longer than the size budget are split on block boundaries. Tables repeat their header row in
  every part; prose parts start with a short overlap (the end of the previous part).
- Rule IDs, test IDs and the [P]/[S]/[U] marks are extracted into fields.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from versoml.knowledge.text import marks_in, rule_ids_in, sentences, slugify, test_ids_in, weakest_mark
from versoml.shared.privacy.text import normalize_ro

CHUNKER_VERSION = "5"
MAX_CHARS = 1600      # body size budget (about 300-400 tokens); the embedding input adds the title
OVERLAP_CHARS = 200

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+")
_RULE_LINE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_LEGAL_REF = re.compile(
    r"(?i)(?<![a-z])(art\.|alin\.|legea|l209|l129|oug|regulamentul|reg\. bnr|cjue|curia|c[\-‑]70/25|cpc|cpf|"
    r"gdpr|directiva|ai act|psd2|amlr|visa core rules|codul)(?![a-z])"
)


@dataclass
class Chunk:
    id: str
    kind: str
    title: str
    text: str
    source: str
    confidence: str | None = None
    rule_ids: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def embed_text(self) -> str:
        """What is embedded and indexed: the title path, then the text (the title once)."""
        return self.text if self.text.startswith(self.title) else f"{self.title}\n{self.text}"

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, row: dict) -> "Chunk":
        return cls(id=row["id"], kind=row["kind"], title=row["title"], text=row["text"], source=row["source"],
                   confidence=row.get("confidence"), rule_ids=list(row.get("rule_ids") or []),
                   meta=dict(row.get("meta") or {}))


@dataclass
class Section:
    path: list[str]
    level: int
    lines: list[str]


@dataclass
class Block:
    kind: str          # para | list | table | code
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def clean_inline(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    return re.sub(r"[*_`]+", "", text).strip()


def short_title(h1: str, max_len: int = 70) -> str:
    """Shorter document title for heading paths: cut at the first colon, then at a word boundary."""
    title = clean_inline(h1)
    if ":" in title[:max_len + 20]:
        title = title.split(":", 1)[0].strip()
    if len(title) > max_len:
        title = title[:max_len].rsplit(" ", 1)[0].rstrip(",;—- ")
    return title


def parse_sections(markdown: str) -> list[Section]:
    """Split on headings (outside code fences). The text before the first H2 belongs to the H1 section."""
    sections: list[Section] = []
    path: list[tuple[int, str]] = []
    current = Section(path=[], level=0, lines=[])
    in_fence = False
    for line in normalize_ro(markdown).splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            current.lines.append(line)
            continue
        m = None if in_fence else _HEADING.match(line)
        if m:
            sections.append(current)
            level = len(m.group(1))
            path = [(lvl, t) for lvl, t in path if lvl < level] + [(level, clean_inline(m.group(2)))]
            current = Section(path=[t for _, t in path], level=level, lines=[])
            continue
        current.lines.append(line)
    sections.append(current)
    return [s for s in sections if s.path and any(line.strip() for line in s.lines)]


def split_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    current: Block | None = None
    in_fence = False

    def close() -> None:
        nonlocal current
        if current and any(line.strip() for line in current.lines):
            blocks.append(current)
        current = None

    for line in lines:
        if in_fence:
            current.lines.append(line)  # type: ignore[union-attr]
            if _FENCE.match(line):
                in_fence = False
                close()
            continue
        if _FENCE.match(line):
            close()
            current = Block("code", [line])
            in_fence = True
            continue
        stripped = line.strip()
        if not stripped:  # a blank line ends the paragraph, list item or table
            close()
            continue
        if _RULE_LINE.match(line):
            close()
            continue
        if stripped.startswith("|"):
            if not current or current.kind != "table":
                close()
                current = Block("table", [])
            current.lines.append(stripped)
            continue
        if _LIST_ITEM.match(line):
            close()
            current = Block("list", [line.rstrip()])
            continue
        if current is None or current.kind == "table":
            close()
            current = Block("para", [line.rstrip()])
        else:
            current.lines.append(line.rstrip())
    if current and in_fence:
        blocks.append(current)  # an unclosed code fence still counts as code
    else:
        close()
    return blocks


def _split_long_prose(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    cur = ""
    for piece in re.split(r"(?<=[.!?;])\s+", text):
        if cur and len(cur) + 1 + len(piece) > max_chars:
            parts.append(cur)
            cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        parts.append(cur)
    # a single sentence longer than the budget is cut at word boundaries
    out: list[str] = []
    for p in parts:
        while len(p) > max_chars * 1.5:
            cut = p[:max_chars].rsplit(" ", 1)[0]
            out.append(cut)
            p = p[len(cut):].strip()
        out.append(p)
    return out


def _pieces(block: Block, max_chars: int) -> list[tuple[str, str]]:
    """(kind, text) pieces no longer than the budget (a single long table row stays whole)."""
    if block.kind == "table":
        header = block.lines[:2] if len(block.lines) >= 2 and set(block.lines[1]) <= set("|-: ") else block.lines[:1]
        rows = block.lines[len(header):]
        if not rows:
            return [("table", "\n".join(header))]
        out: list[tuple[str, str]] = []
        cur: list[str] = []
        size = sum(len(h) + 1 for h in header)
        for row in rows:
            if cur and size + len(row) + 1 > max_chars:
                out.append(("table", "\n".join(header + cur)))
                cur, size = [], sum(len(h) + 1 for h in header)
            cur.append(row)
            size += len(row) + 1
        if cur:
            out.append(("table", "\n".join(header + cur)))
        return out
    if block.kind == "code":
        fence_open = block.lines[0]
        fence_close = block.lines[-1] if len(block.lines) > 1 and _FENCE.match(block.lines[-1]) else "```"
        body = block.lines[1:-1] if len(block.lines) > 1 and _FENCE.match(block.lines[-1]) else block.lines[1:]
        out, cur, size = [], [], 0
        for line in body:
            if cur and size + len(line) + 1 > max_chars - 20:
                out.append(("code", "\n".join([fence_open, *cur, fence_close])))
                cur, size = [], 0
            cur.append(line)
            size += len(line) + 1
        if cur:
            out.append(("code", "\n".join([fence_open, *cur, fence_close])))
        return out
    return [(block.kind, p) for p in _split_long_prose(block.text, max_chars)]


def _tail(text: str, max_chars: int = OVERLAP_CHARS) -> str | None:
    """The end of a prose piece, for the overlap: the last sentence(s) within the budget."""
    sents = [s for s in re.split(r"(?<=[.!?;])\s+", text.strip()) if s]
    out = ""
    for sent in reversed(sents):
        if len(out) + len(sent) + 1 > max_chars:
            break
        out = f"{sent} {out}".strip()
    return out or None


def pack_blocks(blocks: list[Block], max_chars: int = MAX_CHARS) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_kinds: list[str] = []
    size = 0
    for block in blocks:
        for kind, piece in _pieces(block, max_chars):
            if cur and size + len(piece) + 1 > max_chars:
                chunks.append("\n".join(cur))
                tail = _tail(cur[-1]) if cur_kinds[-1] in ("para", "list") and kind in ("para", "list") else None
                cur, cur_kinds, size = ([f"… {tail}"], ["overlap"], len(tail) + 2) if tail else ([], [], 0)
            cur.append(piece)
            cur_kinds.append(kind)
            size += len(piece) + 1
    if cur and any(k != "overlap" for k in cur_kinds):
        chunks.append("\n".join(cur))
    return chunks


def chunk_kind(text: str, rule_ids: list[str]) -> str:
    """"law" when the chunk names rules or cites legal texts, else "guidance"."""
    if rule_ids or len(_LEGAL_REF.findall(text)) >= 2:
        return "law"
    return "guidance"


def chunk_markdown(path: Path, *, root: Path, id_prefix: str = "ctx", kind: str | None = None,
                   max_chars: int = MAX_CHARS) -> list[Chunk]:
    """Chunks of one markdown file: ids `<prefix>:<file-stem>#<slug>[-n]`, source = the repo-relative path."""
    markdown = path.read_text(encoding="utf-8")
    sections = parse_sections(markdown)
    source = path.relative_to(root).as_posix()
    doc_title = short_title(sections[0].path[0]) if sections and sections[0].path else path.stem
    used: set[str] = set()
    chunks: list[Chunk] = []
    for section in sections:
        heading = section.path[-1]
        if _BIBLIOGRAPHY.match(heading):
            continue  # source lists: URLs and titles that only add noise to retrieval
        slug = "intro" if section.level == 1 else slugify(heading)
        if slug in used and len(section.path) > 1:
            slug = f"{slugify(section.path[-2], 30)}--{slug}"
        base, n = slug, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        title = " > ".join([doc_title, *section.path[1:]]) if section.level > 1 else doc_title
        blocks = split_blocks(section.lines)
        bodies = pack_blocks(blocks, max_chars)
        bodies = [b for b in bodies if not _code_only(b)]  # program code and data samples; diagrams stay
        for i, body in enumerate(bodies, start=1):
            chunk_id = f"{id_prefix}:{path.stem}#{slug}" + (f"-{i}" if i > 1 else "")
            rule_ids = rule_ids_in(f"{heading}\n{body}")
            marks = marks_in(f"{heading}\n{body}")
            chunks.append(Chunk(
                id=chunk_id, kind=kind or chunk_kind(body, rule_ids), title=title, text=body, source=source,
                confidence=weakest_mark(marks), rule_ids=rule_ids,
                meta={"section": section.path[1:], "anchor": slug, "part": i, "parts": len(bodies),
                      "marks": {k: v for k, v in marks.items() if v}, "test_ids": test_ids_in(body)},
            ))
    return chunks


_BIBLIOGRAPHY = re.compile(r"(?i)^\s*(?:\d+(?:\.\d+)*\.?\s+)?(surse|sources|bibliografie)\b")
_FENCED = re.compile(r"(```|~~~)([^\n]*)\n.*?(?:\1|\Z)", re.S)


def _code_only(body: str) -> bool:
    """True when a part is program code or data with almost no prose (mermaid diagrams are kept)."""
    langs = [m.group(2).strip().lower() for m in _FENCED.finditer(body)]
    if not langs or all(lang == "mermaid" for lang in langs):
        return False
    prose = _FENCED.sub("", body)
    prose = re.sub(r"^…\s.*$", "", prose, flags=re.M)  # the overlap line does not count
    return len(prose.strip()) < 120


def chunk_case_studies(path: Path, *, root: Path) -> list[Chunk]:
    """docs/03: one chunk per numbered case (`case:<section>#<n>`), plus the pattern notes of each section."""
    markdown = path.read_text(encoding="utf-8")
    sections = parse_sections(markdown)
    source = path.relative_to(root).as_posix()
    doc_title = short_title(sections[0].path[0]) if sections and sections[0].path else path.stem
    chunks: list[Chunk] = []
    for section in sections:
        sec_slug = "intro" if section.level == 1 else slugify(section.path[-1], 40)
        title_base = " > ".join([doc_title, *section.path[1:]]) if section.level > 1 else doc_title
        blocks = split_blocks(section.lines)
        rest: list[Block] = []
        groups: list[tuple[str, list[Block]]] = []
        current: tuple[str, list[Block]] | None = None
        for block in blocks:
            m = _NUMBERED.match(block.lines[0]) if block.kind == "list" else None
            if m:
                current = (m.group(1), [block])
                groups.append(current)
            elif current is not None and block.kind == "list" and block.lines[0].startswith((" ", "\t")):
                current[1].append(block)   # an indented sub-list belongs to the numbered case above it
            else:
                current = None
                rest.append(block)
        for number, group in groups:
            body = "\n".join(b.text for b in group)
            first = clean_inline(group[0].lines[0])
            label = re.sub(r"^\d+[.)]\s*", "", first).split(".")[0][:90]
            urls = re.findall(r"\((https?://[^)\s]+)\)", body)
            chunks.append(_case_chunk(f"case:{sec_slug}#{number}", f"{title_base} > {number}. {label}", body,
                                      source, {"section": section.path[1:], "case_number": int(number),
                                               "urls": urls}))
        for i, body in enumerate(pack_blocks(rest), start=1):
            suffix = "tipar" if body.lstrip().startswith("**Tipar") else ("intro" if section.level == 1 else "notes")
            chunk_id = f"case:{sec_slug}#{suffix}" + (f"-{i}" if i > 1 else "")
            urls = re.findall(r"\((https?://[^)\s]+)\)", body)
            chunks.append(_case_chunk(chunk_id, title_base, body, source, {"section": section.path[1:], "urls": urls}))
    return chunks


def _case_chunk(chunk_id: str, title: str, body: str, source: str, meta: dict) -> Chunk:
    marks = marks_in(body)
    return Chunk(id=chunk_id, kind="case_study", title=title, text=body, source=source,
                 confidence=weakest_mark(marks), rule_ids=rule_ids_in(body), meta=meta)


def chunk_sentences(chunk: Chunk) -> list[str]:
    return sentences(chunk.text)
