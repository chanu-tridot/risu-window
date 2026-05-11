import json
from pathlib import Path

import pytest

from md_to_json import parse_md_to_json

FIXTURE = Path(__file__).parent / "fixtures" / "expected-output.md"


@pytest.fixture
def parsed():
    return parse_md_to_json(FIXTURE.read_text(encoding="utf-8"))


def test_name_extracted(parsed):
    assert parsed["name"] == "테스트인물"


def test_desc_contains_basic_info_heading(parsed):
    assert "### Basic Info" in parsed["desc"]
    assert "테스트인물" in parsed["desc"]
    assert "\n## " not in parsed["desc"]  # 다음 ## 섹션 침범 안 됨


def test_first_message_contains_user_variable(parsed):
    assert "{{user}}" in parsed["firstMessage"]
    assert "안녕하세요" in parsed["firstMessage"]


def test_global_lore_has_two_entries(parsed):
    assert isinstance(parsed["globalLore"], list)
    assert len(parsed["globalLore"]) == 2


def test_global_lore_entry_shape(parsed):
    first = parsed["globalLore"][0]
    assert first["key"] == "<두 번째 만남>"
    assert "또 뵙네요" in first["content"]

    second = parsed["globalLore"][1]
    assert second["key"] == "<비밀의 공개>"
    assert "사실은" in second["content"]


def test_post_history_empty_string_when_marker(parsed):
    assert parsed["postHistoryInstructions"] == ""


def test_unused_fields_are_empty(parsed):
    assert parsed["systemPrompt"] == ""
    assert parsed["personality"] == ""
    assert parsed["scenario"] == ""


def test_output_is_json_serializable(parsed):
    text = json.dumps(parsed, ensure_ascii=False)
    assert "테스트인물" in text


def test_missing_header_raises():
    with pytest.raises(ValueError):
        parse_md_to_json("no header here")
