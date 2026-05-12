"""9-slot assembler: character JSON + global preset → LLM-ready messages[].

Implements the assembly logic from docs/character-prompt-storage.md §4 in Python.
Mirrors RisuAI's `process/index.svelte.ts` `unformated` slot builder + formatingOrder
serialization. Single-scenario PoC: supports {{char}} and {{user}} macros only.
{{#if_pure}}, {{getvar::}}, etc. are NOT evaluated (would need a full parser).

Output is a {"messages": [...], "meta": {...}} dict that can be fed directly to
Anthropic / OpenAI chat API.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent

# Macros we evaluate. Anything else (e.g. {{#if_pure}}, {{getvar::}}) is left as-is
# and counted in meta.unevaluated_macros so the caller can see what was skipped.
_VAR_RE = re.compile(r"\{\{(char|user)\}\}", re.IGNORECASE)
_UNEVAL_RE = re.compile(r"\{\{#?[^}]+\}\}")


def evaluate_macros(text: str, vars: dict[str, str]) -> tuple[str, list[str]]:
    """Replace {{char}} and {{user}} in `text`. Return (replaced, unevaluated_markers).

    Unevaluated markers (anything still wrapped in {{ ... }} after var substitution)
    are returned so the caller can decide whether to warn or fail.
    """
    def _sub(m: re.Match) -> str:
        key = m.group(1).lower()
        return vars.get(key, m.group(0))

    out = _VAR_RE.sub(_sub, text)
    leftover = _UNEVAL_RE.findall(out)
    return out, leftover


def _trim(text: str | None) -> str:
    return (text or "").strip()


def assemble_messages(
    character: dict[str, Any],
    preset: dict[str, Any],
    *,
    user_name: str = "User",
    jailbreak_toggle: bool = True,
    persona_prompt: str = "",
) -> dict[str, Any]:
    """Build LLM-ready messages[] from character v2 JSON + global preset.

    Args:
        character: parsed character v2 JSON (e.g. from outputs/백서희.opus.v2.json).
        preset: global preset dict (e.g. from raw/global-presets.json[0]) with
            mainPrompt, jailbreak, formatingOrder, globalNote.
        user_name: value for {{user}} macro.
        jailbreak_toggle: whether to include preset.jailbreak in jailbreak slot.
        persona_prompt: user persona text (RisuAI root-level personaPrompt slot input).

    Returns:
        {
            "messages": [{role, content}, ...],
            "meta": {
                "char_name": str,
                "user_name": str,
                "format_order": [str, ...],
                "slot_message_counts": {slot: int, ...},
                "unevaluated_macros": [str, ...],  # leftover {{...}} markers
                "total_chars": int,
            }
        }
    """
    char_name = character["name"]
    macro_vars = {"char": char_name, "user": user_name}
    unevaluated: list[str] = []

    def _eval(text: str) -> str:
        out, leftover = evaluate_macros(text, macro_vars)
        if leftover:
            unevaluated.extend(leftover)
        return out

    # ── Slot builders ──────────────────────────────────────────────────────

    def slot_main() -> list[dict[str, str]]:
        sp = _trim(character.get("systemPrompt"))
        global_main = _trim(preset.get("mainPrompt"))
        text = sp.replace("{{original}}", global_main) if sp else global_main
        if not text:
            return []
        return [{"role": "system", "content": _eval(text)}]

    def slot_description() -> list[dict[str, str]]:
        parts = []
        prefix = _trim(preset.get("descriptionPrefix")) if preset.get("promptPreprocess") else ""
        if prefix:
            parts.append(prefix)
        desc = _trim(character.get("desc"))
        if desc:
            parts.append(desc)
        personality = _trim(character.get("personality"))
        if personality:
            parts.append(f"Description of {{{{char}}}}: {personality}")
        scenario = _trim(character.get("scenario"))
        if scenario:
            parts.append(f"Circumstances and context of the dialogue: {scenario}")
        if not parts:
            return []
        return [{"role": "system", "content": _eval("\n\n".join(parts))}]

    def slot_persona_prompt() -> list[dict[str, str]]:
        text = _trim(persona_prompt)
        if not text:
            return []
        return [{"role": "system", "content": _eval(text)}]

    def slot_chats() -> list[dict[str, str]]:
        # PoC: chats[] is empty (fresh session), prepend firstMessage as first assistant
        # message. Real RisuAI would also inject depth_prompt at specified depth, but
        # 백서희 has depth_prompt={"depth":0,"prompt":""} so we skip.
        first = _trim(character.get("firstMessage"))
        if not first:
            return []
        return [{"role": "assistant", "content": _eval(first)}]

    def slot_last_chat() -> list[dict[str, str]]:
        # Cull-protection slot for the latest user message. Empty in fresh session.
        return []

    def slot_jailbreak() -> list[dict[str, str]]:
        if not jailbreak_toggle:
            return []
        jb = _trim(preset.get("jailbreak"))
        if not jb:
            return []
        return [{"role": "system", "content": _eval(jb)}]

    def slot_lorebook() -> list[dict[str, str]]:
        # Only alwaysActive=true entries activate in a fresh session (no keyword
        # matching against chat history yet). Sort by insertorder descending.
        entries = character.get("globalLore", [])
        active = [e for e in entries if e.get("alwaysActive")]
        active.sort(key=lambda e: -int(e.get("insertorder", 0)))
        msgs = []
        for e in active:
            content = _eval(_trim(e.get("content", "")))
            if content:
                msgs.append({"role": "system", "content": content})
        return msgs

    def slot_global_note() -> list[dict[str, str]]:
        replace = _trim(character.get("replaceGlobalNote"))
        if replace:
            note = replace.replace("{{original}}", _trim(preset.get("globalNote", "")))
        else:
            note = _trim(preset.get("globalNote"))
        if not note:
            return []
        return [{"role": "system", "content": _eval(note)}]

    def slot_author_note() -> list[dict[str, str]]:
        post = _trim(character.get("postHistoryInstructions"))
        if not post:
            return []
        return [{"role": "system", "content": _eval(post)}]

    def slot_post_everything() -> list[dict[str, str]]:
        # CoT / group-instruction injection. Off for 백서희 PoC.
        return []

    SLOT_BUILDERS = {
        "main":          slot_main,
        "description":   slot_description,
        "personaPrompt": slot_persona_prompt,
        "chats":         slot_chats,
        "lastChat":      slot_last_chat,
        "jailbreak":     slot_jailbreak,
        "lorebook":      slot_lorebook,
        "globalNote":    slot_global_note,
        "authorNote":    slot_author_note,
        "postEverything": slot_post_everything,
    }

    format_order = preset.get("formatingOrder") or [
        "main", "description", "personaPrompt", "chats", "lastChat",
        "jailbreak", "lorebook", "globalNote", "authorNote",
    ]
    # RisuAI auto-appends postEverything at the end.
    if "postEverything" not in format_order:
        format_order = list(format_order) + ["postEverything"]

    # ── Assemble ───────────────────────────────────────────────────────────
    messages: list[dict[str, str]] = []
    slot_counts: dict[str, int] = {}
    for slot in format_order:
        builder = SLOT_BUILDERS.get(slot)
        if builder is None:
            slot_counts[slot] = 0
            continue
        slot_msgs = builder()
        slot_counts[slot] = len(slot_msgs)
        messages.extend(slot_msgs)

    total_chars = sum(len(m["content"]) for m in messages)
    return {
        "messages": messages,
        "meta": {
            "char_name": char_name,
            "user_name": user_name,
            "jailbreak_toggle": jailbreak_toggle,
            "format_order": format_order,
            "slot_message_counts": slot_counts,
            "unevaluated_macros": sorted(set(unevaluated)),
            "total_chars": total_chars,
            "message_count": len(messages),
        },
    }


def _load_default_preset() -> dict[str, Any]:
    """Load the global preset (mainPrompt/jailbreak/globalNote/formatingOrder).

    Source: references/default-preset.json — a curated subset of the user's
    RisuAI app preset, with secret-prone fields (aiModel, apiKey, etc.) stripped.
    """
    path = ROOT / "references" / "default-preset.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("character_json", type=Path,
                        help="Path to character v2 JSON (e.g. outputs/백서희.opus.v2.json)")
    parser.add_argument("--preset", type=Path, default=None,
                        help="Path to global preset JSON. Default: raw/global-presets.json[0]")
    parser.add_argument("--user-name", default="User",
                        help="Value for {{user}} macro (default: User)")
    parser.add_argument("--no-jailbreak", action="store_true",
                        help="Disable jailbreak slot")
    parser.add_argument("--persona-prompt", default="",
                        help="User persona text for personaPrompt slot")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path. Default: <input>.assembled.json next to input")
    args = parser.parse_args()

    character = json.loads(args.character_json.read_text(encoding="utf-8"))
    if args.preset:
        preset = json.loads(args.preset.read_text(encoding="utf-8"))
        if isinstance(preset, list):
            preset = preset[0]
    else:
        preset = _load_default_preset()

    result = assemble_messages(
        character,
        preset,
        user_name=args.user_name,
        jailbreak_toggle=not args.no_jailbreak,
        persona_prompt=args.persona_prompt,
    )

    out = args.output
    if out is None:
        stem = args.character_json.stem  # e.g. "백서희.opus.v2"
        if stem.endswith(".v2"):
            stem = stem[:-3]
        out = args.character_json.parent / f"{stem}.assembled.json"

    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    meta = result["meta"]
    print(
        f"[{meta['char_name']}] messages={meta['message_count']} "
        f"chars={meta['total_chars']} "
        f"slots={meta['slot_message_counts']} "
        f"-> {out.name}"
    )
    if meta["unevaluated_macros"]:
        print(f"  WARN unevaluated macros (literal in output): "
              f"{meta['unevaluated_macros'][:5]}{'...' if len(meta['unevaluated_macros'])>5 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
