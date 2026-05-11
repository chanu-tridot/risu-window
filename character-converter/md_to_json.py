"""Parse RisuAI-style .md output into RisuAI native JSON dict."""
from __future__ import annotations

import re
from typing import Any

_HEADER_RE = re.compile(r"^# 캐릭터:\s*(.+?)\s*$", re.MULTILINE)
_SECTION_SPLIT_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_LORE_ENTRY_SPLIT_RE = re.compile(r"^### (.+?)\s*$", re.MULTILINE)


def parse_md_to_json(md_text: str) -> dict[str, Any]:
    """Convert a Risu-style markdown document to RisuAI native JSON shape."""
    name = _extract_name(md_text)
    sections = _split_sections(md_text)

    desc = sections.get("desc", "").strip()
    first_message = sections.get("firstMessage", "").strip()
    global_lore_md = sections.get("globalLore", "")
    post_history_raw = sections.get("postHistoryInstructions", "").strip()
    post_history = "" if post_history_raw in {"(비어있음)", ""} else post_history_raw

    return {
        "name": name,
        "desc": desc,
        "firstMessage": first_message,
        "globalLore": _parse_lore_entries(global_lore_md),
        "postHistoryInstructions": post_history,
        "systemPrompt": "",
        "personality": "",
        "scenario": "",
    }


def _extract_name(md_text: str) -> str:
    m = _HEADER_RE.search(md_text)
    if not m:
        raise ValueError("Header `# 캐릭터: <name>` not found")
    return m.group(1).strip()


def _split_sections(md_text: str) -> dict[str, str]:
    """Split markdown by `## heading` lines into {first_token: body} dict.

    Body is everything between this `## heading` and the next `## heading`
    (or EOF). Sections are keyed by the heading's first whitespace-delimited
    token, so multi-word headings like `## 프롬프트 구조 요약` simply key
    under `"프롬프트"` and are ignored by callers that look up `"desc"`,
    `"firstMessage"`, etc.
    """
    parts = _SECTION_SPLIT_RE.split(md_text)
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        if heading:
            key = heading.split()[0]
            sections[key] = body
    return sections


def _parse_lore_entries(lore_md: str) -> list[dict[str, str]]:
    parts = _LORE_ENTRY_SPLIT_RE.split(lore_md)
    entries: list[dict[str, str]] = []
    for i in range(1, len(parts), 2):
        key = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        entries.append({"key": key, "content": content})
    return entries
