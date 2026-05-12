"""Tests for the 9-slot assembler — verifies LLM-ready messages[] assembly."""
from __future__ import annotations

import pytest

from assembler import assemble_messages, evaluate_macros


MIN_CHARACTER = {
    "name": "테스트",
    "nickname": "",
    "desc": "",
    "personality": "",
    "scenario": "",
    "systemPrompt": "",
    "firstMessage": "안녕, 나는 {{char}}야. {{user}}, 반가워.",
    "postHistoryInstructions": "",
    "replaceGlobalNote": "",
    "depth_prompt": {"depth": 0, "prompt": ""},
    "globalLore": [
        {
            "key": "",
            "comment": "body",
            "content": "{{char}}의 본체 본문.",
            "mode": "normal",
            "insertorder": 400,
            "alwaysActive": True,
        },
        {
            "key": "",
            "comment": "episode_1",
            "content": "사건 1.",
            "mode": "normal",
            "insertorder": 399,
            "alwaysActive": True,
        },
        {
            "key": "trigger_word",
            "comment": "keyword_only",
            "content": "키워드 매칭 엔트리(활성화 안 됨).",
            "mode": "normal",
            "insertorder": 398,
            "alwaysActive": False,
        },
    ],
}

MIN_PRESET = {
    "mainPrompt": "RP system instructions.",
    "jailbreak": "[System note: jailbreak text]",
    "globalNote": "",
    "formatingOrder": [
        "main", "description", "personaPrompt", "chats", "lastChat",
        "jailbreak", "lorebook", "globalNote", "authorNote",
    ],
}


# ── Macro evaluation ─────────────────────────────────────────────────────


def test_evaluate_replaces_char_and_user():
    text, leftover = evaluate_macros("{{char}}와 {{user}}", {"char": "테스트", "user": "Alice"})
    assert text == "테스트와 Alice"
    assert leftover == []


def test_evaluate_leaves_unknown_macros_and_reports():
    text, leftover = evaluate_macros(
        "{{char}} {{getvar::xyz}} {{#if_pure cond}}body{{/}}",
        {"char": "테스트", "user": "U"},
    )
    assert "테스트" in text
    assert "{{getvar::xyz}}" in text  # untouched
    assert any("getvar" in m for m in leftover)


# ── Slot builders ────────────────────────────────────────────────────────


def test_main_slot_uses_preset_when_systemprompt_empty():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    main_msgs = [m for m in result["messages"] if m["content"] == "RP system instructions."]
    assert len(main_msgs) == 1


def test_main_slot_uses_character_systemprompt_when_set():
    char = dict(MIN_CHARACTER, systemPrompt="Custom system for {{char}}.")
    result = assemble_messages(char, MIN_PRESET)
    main_contents = [m["content"] for m in result["messages"][:1]]
    assert main_contents[0] == "Custom system for 테스트."


def test_systemprompt_original_macro_embeds_preset_mainprompt():
    char = dict(MIN_CHARACTER, systemPrompt="<prefix>{{original}}<suffix>")
    result = assemble_messages(char, MIN_PRESET)
    assert result["messages"][0]["content"] == "<prefix>RP system instructions.<suffix>"


def test_description_slot_empty_for_marin_pattern():
    """Marin pattern: desc/personality/scenario all empty → no description message."""
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    assert result["meta"]["slot_message_counts"]["description"] == 0


def test_description_slot_populated_for_pattern_a():
    char = dict(MIN_CHARACTER, desc="캐릭터 설명", personality="간결함")
    result = assemble_messages(char, MIN_PRESET)
    desc_msg = result["messages"][1]  # after main
    assert "캐릭터 설명" in desc_msg["content"]
    assert "Description of 테스트" in desc_msg["content"]  # {{char}} substituted


def test_chats_slot_uses_firstmessage_with_macros_eval():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET, user_name="Alice")
    chats = [m for m in result["messages"] if m["role"] == "assistant"]
    assert len(chats) == 1
    assert "테스트" in chats[0]["content"]
    assert "Alice" in chats[0]["content"]


def test_jailbreak_slot_included_when_toggle_on():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET, jailbreak_toggle=True)
    jbs = [m for m in result["messages"] if "jailbreak text" in m["content"]]
    assert len(jbs) == 1


def test_jailbreak_slot_skipped_when_toggle_off():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET, jailbreak_toggle=False)
    jbs = [m for m in result["messages"] if "jailbreak text" in m["content"]]
    assert len(jbs) == 0


def test_lorebook_only_includes_alwaysactive_entries():
    """The keyword_only entry has alwaysActive=False → must not appear."""
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    contents = [m["content"] for m in result["messages"]]
    assert any("본체 본문" in c for c in contents)
    assert any("사건 1" in c for c in contents)
    assert not any("키워드 매칭" in c for c in contents)


def test_lorebook_sorted_by_insertorder_desc():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    contents = [m["content"] for m in result["messages"]]
    body_idx = next(i for i, c in enumerate(contents) if "본체 본문" in c)
    ep_idx = next(i for i, c in enumerate(contents) if "사건 1" in c)
    assert body_idx < ep_idx  # insertorder=400 comes before 399


def test_author_note_slot_skipped_when_empty():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    assert result["meta"]["slot_message_counts"]["authorNote"] == 0


def test_author_note_slot_populated_when_set():
    char = dict(MIN_CHARACTER, postHistoryInstructions="Write 3 paragraphs.")
    result = assemble_messages(char, MIN_PRESET)
    notes = [m for m in result["messages"] if "Write 3 paragraphs" in m["content"]]
    assert len(notes) == 1


def test_persona_prompt_injected_when_provided():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET,
                               persona_prompt="유저는 30대 회사원이다.")
    pps = [m for m in result["messages"] if "30대 회사원" in m["content"]]
    assert len(pps) == 1


# ── Slot ordering ────────────────────────────────────────────────────────


def test_format_order_strict_serialization():
    """Messages must come out in formatingOrder sequence."""
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    contents = [m["content"] for m in result["messages"]]
    # Expected order: main → (no description) → (no persona) → chats(firstMessage) →
    # (no lastChat) → jailbreak → lorebook×2 → (no globalNote) → (no authorNote)
    assert contents[0] == "RP system instructions."         # main
    assert "안녕, 나는 테스트야" in contents[1]               # chats (firstMessage)
    assert "jailbreak text" in contents[2]                    # jailbreak
    assert "본체 본문" in contents[3]                          # lorebook[0]
    assert "사건 1" in contents[4]                            # lorebook[1]


# ── Meta diagnostics ─────────────────────────────────────────────────────


def test_meta_reports_unevaluated_macros():
    char = dict(MIN_CHARACTER, firstMessage="{{char}} {{getvar::lang}}")
    result = assemble_messages(char, MIN_PRESET)
    assert any("getvar" in m for m in result["meta"]["unevaluated_macros"])


def test_meta_total_chars_matches_messages():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    actual = sum(len(m["content"]) for m in result["messages"])
    assert result["meta"]["total_chars"] == actual


def test_postEverything_auto_appended_to_format_order():
    result = assemble_messages(MIN_CHARACTER, MIN_PRESET)
    assert "postEverything" in result["meta"]["format_order"]
