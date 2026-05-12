"""v2 Merger: Reference-based Pass-1 .md → RisuAI native JSON.

Design doc: docs/specs/2026-05-12-character-converter-v2-design.md
Key principle (A안): LLM does NOT rewrite long prose. The merger parses
Pass-1 .md by heading and inserts text directly into the RisuAI JSON shape.
No content is ever round-tripped through a JSON-encoded string field, so
markdown escapes, newlines, and quotes survive without LLM transcription loss.

Heading regimen (Pass-1 .md):
  # 캐릭터: <name>             → name
  ## desc                      → desc body  → globalLore[0].content (Marin pattern)
  ## firstMessage              → firstMessage body
  ## globalLore                → container; each ### <title> is one lorebook entry
  ## postHistoryInstructions   → postHistoryInstructions body (or "" if "(비어있음)")

Default policy:
  desc field is EMPTY (Marin pattern); all character info goes into
  globalLore[0] as alwaysActive=true with insertorder=400.
  Episodes (### entries in ## globalLore) become separate lorebook entries,
  insertorder=399, 398, ... in declaration order.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

_HEADER_RE = re.compile(r"^# 캐릭터:\s*(.+?)\s*$", re.MULTILINE)
_H2_SPLIT_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_H3_SPLIT_RE = re.compile(r"^### (.+?)\s*$", re.MULTILINE)
_TRAILING_HR_RE = re.compile(r"\n*---\s*$")

# Section IDs the merger understands. Anything else in a ## heading triggers
# a parse error so silent corruption is impossible.
_KNOWN_H2 = {"desc", "firstMessage", "globalLore", "postHistoryInstructions",
             "프롬프트"}  # 프롬프트 = legacy v1 summary table, ignored

_EMPTY_MARKERS = {"(비어있음)", "없음", ""}

DEFAULT_LORE_SETTINGS = {
    "tokenBudget": 99999,
    "scanDepth": 5,
    "recursiveScanning": False,
    "fullWordMatching": False,
}


def _clean(text: str) -> str:
    return _TRAILING_HR_RE.sub("", text).strip()


def parse_pass1_md(md_text: str) -> dict[str, Any]:
    """Parse a Pass-1 .md into a structured index.

    Returns:
        {
            "name": str,
            "desc": str,                      # full ## desc body (may include ### subheadings)
            "firstMessage": str,
            "globalLore_entries": [{"title": str, "content": str}, ...],
            "postHistoryInstructions": str,
        }

    Raises ValueError on missing header or unknown ## headings.
    """
    name_match = _HEADER_RE.search(md_text)
    if not name_match:
        raise ValueError("Missing `# 캐릭터: <name>` header")
    name = name_match.group(1).strip()

    parts = _H2_SPLIT_RE.split(md_text)
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        if not heading:
            continue
        key = heading.split()[0]
        if key not in _KNOWN_H2:
            raise ValueError(
                f"Unknown ## heading: {heading!r}. "
                f"Known: {sorted(_KNOWN_H2)}. "
                f"Heading regimen violation — merger refuses to silently drop content."
            )
        sections[key] = body

    desc_body = _clean(sections.get("desc", ""))
    first_message = _clean(sections.get("firstMessage", ""))
    post_history_raw = _clean(sections.get("postHistoryInstructions", ""))
    post_history = "" if post_history_raw in _EMPTY_MARKERS else post_history_raw

    lore_entries = _parse_episode_entries(sections.get("globalLore", ""))

    return {
        "name": name,
        "desc": desc_body,
        "firstMessage": first_message,
        "globalLore_entries": lore_entries,
        "postHistoryInstructions": post_history,
    }


def _parse_episode_entries(lore_md: str) -> list[dict[str, str]]:
    """Split `## globalLore` body by `### <title>` into entries.

    Entries are returned in declaration order. Each gets:
        {"title": "<재회>", "content": "200~400자 본문..."}
    """
    if not lore_md.strip():
        return []
    parts = _H3_SPLIT_RE.split(lore_md)
    entries: list[dict[str, str]] = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        content = _clean(parts[i + 1]) if i + 1 < len(parts) else ""
        if not title:
            continue
        entries.append({"title": title, "content": content})
    return entries


def assemble_risu_json(parsed: dict[str, Any]) -> dict[str, Any]:
    """Build a RisuAI-native character JSON from a parsed Pass-1 .md.

    Marin pattern:
      - desc field is "" (empty)
      - globalLore[0] = alwaysActive=true block containing the entire ## desc body
      - globalLore[1..N] = episode entries from ### subheadings under ## globalLore
    """
    name = parsed["name"]
    desc_body = parsed["desc"]
    episodes = parsed["globalLore_entries"]

    global_lore: list[dict[str, Any]] = []

    # Entry 0: character body (Marin pattern). insertorder=400 (highest).
    if desc_body:
        global_lore.append(_make_lore_entry(
            comment=name,
            content=desc_body,
            insertorder=400,
            always_active=True,
        ))

    # Entries 1..N: episodes from ### subheadings.
    for idx, ep in enumerate(episodes):
        global_lore.append(_make_lore_entry(
            comment=ep["title"],
            content=ep["content"],
            insertorder=399 - idx,
            always_active=True,
        ))

    return {
        # ── core identity ──
        "name": name,
        "nickname": "",
        "image": "",

        # ── prompt slots (Marin pattern: all empty, info lives in globalLore) ──
        "desc": "",
        "personality": "",
        "scenario": "",
        "systemPrompt": "",
        "postHistoryInstructions": parsed["postHistoryInstructions"],

        # ── greetings ──
        "firstMessage": parsed["firstMessage"],
        "alternateGreetings": [],
        "exampleMessage": "",

        # ── depth_prompt (unused in v2) ──
        "depth_prompt": {"depth": 0, "prompt": ""},

        # ── lorebook ──
        "globalLore": global_lore,
        "loreSettings": dict(DEFAULT_LORE_SETTINGS),
        "loreExt": {},
        "lorePlus": False,

        # ── chat container (RisuAI requires this exist) ──
        "chats": [{
            "message": [],
            "note": "",
            "name": "Chat 1",
            "localLore": [],
            "fmIndex": -1,
            "id": str(uuid.uuid4()),
            "scriptstate": {},
            "lastMemory": "NewChat",
        }],
        "chatPage": 0,

        # ── misc RisuAI defaults ──
        "emotionImages": [],
        "bias": [],
        "viewScreen": "none",
        "chaId": str(uuid.uuid4()),
        "sdData": [],
        "creatorNotes": "",
        "replaceGlobalNote": "",
        "additionalAssets": [],
        "ttsMode": "",
        "ttsSpeech": "",
        "creator": "",
        "characterVersion": "v2-converter-1.0",
        "tags": [],
        "type": "character",
    }


def _make_lore_entry(
    *,
    comment: str,
    content: str,
    insertorder: int,
    always_active: bool,
    key: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "comment": comment,
        "content": content,
        "mode": "normal",
        "insertorder": insertorder,
        "alwaysActive": always_active,
        "secondkey": "",
        "selective": False,
        "useRegex": False,
        "bookVersion": 2,
    }


def convert_md_to_risu_json(md_path: Path) -> dict[str, Any]:
    md_text = md_path.read_text(encoding="utf-8")
    parsed = parse_pass1_md(md_text)
    return assemble_risu_json(parsed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path,
                        help="Pass-1 .md path (omit with --all)")
    parser.add_argument("--all", action="store_true",
                        help="Process every outputs/*.md and write .v2.json next to it")
    parser.add_argument("--outdir", type=Path, default=None,
                        help="Override output directory (default: same as input)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent

    if args.all:
        outputs_dir = root / "outputs"
        files = sorted(outputs_dir.glob("*.md"))
        if not files:
            print(f"No .md files in {outputs_dir}", file=sys.stderr)
            return 1
        for p in files:
            _convert_one(p, args.outdir)
        return 0

    if args.input is None:
        parser.error("provide a .md path or use --all")
    _convert_one(args.input, args.outdir)
    return 0


def _convert_one(md_path: Path, outdir: Path | None) -> None:
    data = convert_md_to_risu_json(md_path)
    target_dir = outdir or md_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{md_path.stem}.v2.json"
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    n_lore = len(data["globalLore"])
    name = data["name"]
    print(f"[{name}] globalLore={n_lore} entries -> {out.relative_to(Path.cwd()) if out.is_absolute() else out}")


if __name__ == "__main__":
    sys.exit(main())
