"""v2 merger tests — parse + assemble, ref-based, no LLM."""
from __future__ import annotations

import pytest

from merger import (
    DEFAULT_LORE_SETTINGS,
    assemble_risu_json,
    parse_pass1_md,
)


MINIMAL_MD = """# 캐릭터: 테스트

## desc
### Basic Info
- 이름: 테스트
- 직업: QA

### Personality
간결한 성격.

## firstMessage
{{user}}와의 첫 만남.

엘리베이터에서.

## globalLore

### <에피소드 하나>
첫 번째 사건.

### <에피소드 둘>
두 번째 사건.

## postHistoryInstructions
(비어있음)
"""


def test_parse_extracts_name():
    parsed = parse_pass1_md(MINIMAL_MD)
    assert parsed["name"] == "테스트"


def test_parse_keeps_desc_body_with_subheadings():
    parsed = parse_pass1_md(MINIMAL_MD)
    assert "Basic Info" in parsed["desc"]
    assert "간결한 성격" in parsed["desc"]


def test_parse_splits_episodes():
    parsed = parse_pass1_md(MINIMAL_MD)
    eps = parsed["globalLore_entries"]
    assert len(eps) == 2
    assert eps[0]["title"] == "<에피소드 하나>"
    assert eps[0]["content"] == "첫 번째 사건."
    assert eps[1]["title"] == "<에피소드 둘>"


def test_parse_treats_empty_marker_as_empty():
    parsed = parse_pass1_md(MINIMAL_MD)
    assert parsed["postHistoryInstructions"] == ""


def test_parse_raises_on_missing_header():
    with pytest.raises(ValueError, match="header"):
        parse_pass1_md("## desc\nno header here")


def test_parse_raises_on_unknown_heading():
    bad = "# 캐릭터: x\n## bogus_heading\nbody"
    with pytest.raises(ValueError, match="Unknown ## heading"):
        parse_pass1_md(bad)


def test_assemble_keeps_desc_field_empty():
    """Marin pattern: desc is empty, all info lives in globalLore[0]."""
    parsed = parse_pass1_md(MINIMAL_MD)
    risu = assemble_risu_json(parsed)
    assert risu["desc"] == ""
    assert risu["personality"] == ""
    assert risu["scenario"] == ""
    assert risu["systemPrompt"] == ""


def test_assemble_globallore_body_at_400():
    parsed = parse_pass1_md(MINIMAL_MD)
    risu = assemble_risu_json(parsed)
    body = risu["globalLore"][0]
    assert body["comment"] == "테스트"
    assert body["insertorder"] == 400
    assert body["alwaysActive"] is True
    assert "Basic Info" in body["content"]


def test_assemble_episodes_descending_insertorder():
    parsed = parse_pass1_md(MINIMAL_MD)
    risu = assemble_risu_json(parsed)
    lore = risu["globalLore"]
    assert len(lore) == 3  # body + 2 episodes
    assert lore[1]["insertorder"] == 399
    assert lore[2]["insertorder"] == 398
    assert lore[1]["comment"] == "<에피소드 하나>"


def test_assemble_no_lore_when_desc_and_episodes_empty():
    md = "# 캐릭터: x\n## firstMessage\n안녕.\n"
    parsed = parse_pass1_md(md)
    risu = assemble_risu_json(parsed)
    assert risu["globalLore"] == []


def test_assemble_default_lore_settings():
    risu = assemble_risu_json(parse_pass1_md(MINIMAL_MD))
    assert risu["loreSettings"] == DEFAULT_LORE_SETTINGS


def test_assemble_has_chat_container():
    """RisuAI requires chats[] to exist with at least one Chat."""
    risu = assemble_risu_json(parse_pass1_md(MINIMAL_MD))
    assert len(risu["chats"]) == 1
    assert risu["chats"][0]["name"] == "Chat 1"
    assert "id" in risu["chats"][0]


def test_assemble_unique_chaid_per_call():
    risu1 = assemble_risu_json(parse_pass1_md(MINIMAL_MD))
    risu2 = assemble_risu_json(parse_pass1_md(MINIMAL_MD))
    assert risu1["chaId"] != risu2["chaId"]


def test_assemble_preserves_firstmessage_verbatim():
    """Reference-based: firstMessage body is inserted byte-for-byte, no LLM rewrite."""
    parsed = parse_pass1_md(MINIMAL_MD)
    risu = assemble_risu_json(parsed)
    assert "{{user}}와의 첫 만남" in risu["firstMessage"]
    assert "엘리베이터에서" in risu["firstMessage"]
