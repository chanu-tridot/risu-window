# 작가→Risu 변환기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 작가 캐릭터 시트(한국어 `.md`)를 입력받아 RisuAI 스타일 분석 문서(`.md`)와 RisuAI native JSON(`.json`)을 페어로 출력하는 PoC를 만든다.

**Architecture:** Single-shot LLM 호출. Python 스크립트가 `prompt.md` + few-shot 예시(neta, marin) + 입력 작가 시트를 합쳐 Claude API에 보내 `.md`를 받고, 결정론적 파서가 `.md`를 `.json`으로 변환한다. 모든 변환 로직은 `prompt.md`에 들어가며 코드는 얇은 wrapper.

**Tech Stack:** Python 3.10+, `anthropic` SDK, pytest, Claude Opus 4.7.

**Spec:** `docs/specs/2026-05-11-author-to-risu-converter-design.md`

---

## File Structure

작업은 `character-converter/` 폴더 안에서 진행한다 (risu-window 워크스페이스 루트 기준).

```
character-converter/
├── README.md                  # 실행법 + 변환 흐름 + 팀 리뷰 가이드
├── prompt.md                  # 메타 프롬프트 (few-shot 슬롯 포함)
├── examples/
│   ├── neta.md                # 출력 포맷 레퍼런스 1
│   └── kitagawa-marin.md      # 출력 포맷 레퍼런스 2
├── inputs/
│   ├── 차아진.md
│   ├── 이연.md
│   └── 백서희.md
├── outputs/                   # 스크립트가 생성 (.md + .json 페어)
├── tests/
│   ├── fixtures/
│   │   └── expected-output.md # 파서 테스트용 합성 fixture
│   └── test_md_to_json.py
├── md_to_json.py              # `.md` → `.json` 결정론적 파서
├── convert.py                 # LLM 호출 + 파일 저장
├── requirements.txt
└── .env.example
```

각 파일 책임:
- `prompt.md`: 변환 규칙 전체. 코드 수정 없이 이 파일만 고쳐서 품질 튜닝.
- `md_to_json.py`: 단일 함수 `parse_md_to_json(md_text) -> dict`. 정규식 기반.
- `convert.py`: CLI 진입점. 환경변수 → API 호출 → `.md` 저장 → 파서 호출 → `.json` 저장.
- `examples/`: 기존 워크스페이스의 `neta.md`/`kitagawa-marin.md` 사본. 프롬프트 변경 없이 레퍼런스 업데이트 가능.

---

## Task 1: 프로젝트 스켈레톤 + 입력 파일 분리

**Files:**
- Create: `character-converter/requirements.txt`
- Create: `character-converter/.env.example`
- Create: `character-converter/examples/neta.md` (워크스페이스 루트 `neta.md` 복사)
- Create: `character-converter/examples/kitagawa-marin.md` (워크스페이스 루트 `kitagawa-marin.md` 복사)
- Create: `character-converter/inputs/차아진.md`
- Create: `character-converter/inputs/이연.md`
- Create: `character-converter/inputs/백서희.md`

- [ ] **Step 1: 폴더 + requirements.txt 생성**

`character-converter/requirements.txt`:
```
anthropic>=0.40.0
pytest>=8.0.0
```

`character-converter/.env.example`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

- [ ] **Step 2: examples/ 채우기**

워크스페이스 루트의 `neta.md`와 `kitagawa-marin.md`를 `character-converter/examples/`에 그대로 복사. 내용 수정하지 말 것.

PowerShell:
```powershell
Copy-Item "neta.md" "character-converter\examples\neta.md"
Copy-Item "kitagawa-marin.md" "character-converter\examples\kitagawa-marin.md"
```

- [ ] **Step 3: 작가 시트를 캐릭터별로 분리**

`author-input.md`(합본)를 읽고 각 캐릭터 섹션을 잘라 `character-converter/inputs/<이름>.md`로 저장. 분리 규칙:
- 합본의 `# 1. 차아진`, `# 2. 이연`, `# 3. 백서희` 헤더 기준 분할
- 각 파일의 최상단은 `# <이름>` (번호 제거)
- "1장 끝" 줄까지 포함
- 출처 안내·이미지 첨부 마크다운(`![...](attachment:...)`)은 제거
- 합본의 헤더 메타데이터(`> 출처:`, `> 변환 대상:`, `> 입력 형태:`)는 각 파일에 포함하지 않음

각 inputs/*.md 시작은 이런 형태:
```markdown
# 차아진

## 기본 프로필
- 이름: 차아진
- 성별: 여성
- 생년월일: 1997.02.06 (30세)
...
```

- [ ] **Step 4: 확인**

```powershell
Get-ChildItem character-converter -Recurse | Select-Object FullName
```
Expected: `requirements.txt`, `.env.example`, `examples/neta.md`, `examples/kitagawa-marin.md`, `inputs/차아진.md`, `inputs/이연.md`, `inputs/백서희.md` 7개 파일 존재.

```powershell
Get-Content character-converter\inputs\차아진.md -TotalCount 5
```
Expected: 첫 줄이 `# 차아진`.

- [ ] **Step 5: Commit**

```bash
git add character-converter/requirements.txt character-converter/.env.example character-converter/examples/ character-converter/inputs/
git commit -m "feat: scaffold character-converter PoC with inputs and example references"
```

---

## Task 2: 파서 테스트 fixture 작성

**Files:**
- Create: `character-converter/tests/fixtures/expected-output.md`

LLM 출력 포맷을 정확히 따르는 합성 fixture를 만든다. 이 fixture는 `md_to_json.py`가 spec대로 동작하는지 검증하는 기준점이다.

- [ ] **Step 1: fixture 작성**

`character-converter/tests/fixtures/expected-output.md`:
```markdown
# 캐릭터: 테스트인물

## 프롬프트 구조 요약
| 필드 | 상태 |
|------|------|
| desc | 채워짐 |
| systemPrompt | 비어있음 → 글로벌 mainPrompt 사용 |
| firstMessage | 사건 1번 기반 |
| globalLore | 사건 2~3번 |
| postHistoryInstructions | 비어있음 |

## desc
### Basic Info
- 이름: 테스트인물
- 나이: 25세
- 직업: 테스트용

### Personality
짧은 성격 설명.

### Background
짧은 배경 설명.

## firstMessage
{{user}}가 처음 테스트인물을 만나는 장면.

"안녕하세요." 그녀가 말했다.

## globalLore

### <두 번째 만남>
{{user}}와 테스트인물이 우연히 다시 마주친다.

"또 뵙네요."

### <비밀의 공개>
테스트인물이 자신의 진짜 정체를 밝힌다. "사실은…"

## postHistoryInstructions
(비어있음)
```

- [ ] **Step 2: 확인**

```powershell
Get-Content character-converter\tests\fixtures\expected-output.md -TotalCount 3
```
Expected: 첫 줄 `# 캐릭터: 테스트인물`.

- [ ] **Step 3: Commit**

```bash
git add character-converter/tests/fixtures/expected-output.md
git commit -m "test: add parser fixture matching spec output format"
```

---

## Task 3: 파서 테스트 작성 (실패 확인)

**Files:**
- Create: `character-converter/tests/test_md_to_json.py`

- [ ] **Step 1: 테스트 파일 작성**

`character-converter/tests/test_md_to_json.py`:
```python
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
    assert "## " not in parsed["desc"]  # 다음 ## 섹션 침범 안 됨


def test_first_message_contains_user_variable(parsed):
    assert "{{user}}" in parsed["firstMessage"]
    assert "안녕하세요" in parsed["firstMessage"]


def test_global_lore_has_two_entries(parsed):
    assert isinstance(parsed["globalLore"], list)
    assert len(parsed["globalLore"]) == 2


def test_global_lore_entry_shape(parsed):
    entry = parsed["globalLore"][0]
    assert entry["key"] == "<두 번째 만남>"
    assert "또 뵙네요" in entry["content"]


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
```

- [ ] **Step 2: 실패 확인**

`character-converter/` 안에서:
```powershell
python -m pytest tests/test_md_to_json.py -v
```
Expected: `ModuleNotFoundError: No module named 'md_to_json'` (아직 구현 안 함).

- [ ] **Step 3: Commit**

```bash
git add character-converter/tests/test_md_to_json.py
git commit -m "test: add failing tests for md_to_json parser"
```

---

## Task 4: 파서 구현 (테스트 통과)

**Files:**
- Create: `character-converter/md_to_json.py`

- [ ] **Step 1: 파서 구현**

`character-converter/md_to_json.py`:
```python
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
    """Split markdown by `## heading` lines into {heading: body} dict.

    Body is everything between this `## heading` and the next `## heading` (or EOF).
    Headings are matched by their first whitespace-delimited token so that
    `## desc`, `## firstMessage`, etc. map cleanly. Multi-word headings (e.g.
    `## 프롬프트 구조 요약`) are stored under their full text.
    """
    parts = _SECTION_SPLIT_RE.split(md_text)
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        key = heading.split()[0] if heading else heading
        sections[key] = body
        sections[heading] = body
    return sections


def _parse_lore_entries(lore_md: str) -> list[dict[str, str]]:
    parts = _LORE_ENTRY_SPLIT_RE.split(lore_md)
    entries: list[dict[str, str]] = []
    for i in range(1, len(parts), 2):
        key = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        entries.append({"key": key, "content": content})
    return entries
```

- [ ] **Step 2: 테스트 통과 확인**

```powershell
python -m pytest tests/test_md_to_json.py -v
```
Expected: 9 passed.

- [ ] **Step 3: Commit**

```bash
git add character-converter/md_to_json.py
git commit -m "feat: implement deterministic md → RisuAI native JSON parser"
```

---

## Task 5: 메타 프롬프트(`prompt.md`) 작성

**Files:**
- Create: `character-converter/prompt.md`

- [ ] **Step 1: 프롬프트 작성**

`character-converter/prompt.md`:
```markdown
당신은 RisuAI 캐릭터 프롬프트 변환 전문가입니다. 작가가 한국어로 작성한 캐릭터 시트를 RisuAI 스타일 `.md` 분석 문서로 변환합니다.

# 출력 포맷

다음 구조를 정확히 이 순서로 출력하세요. 인사·설명·코드블록 펜스 등 부가 텍스트는 절대 추가하지 마세요. 응답은 `# 캐릭터:`로 시작해야 합니다.

```
# 캐릭터: <이름>

## 프롬프트 구조 요약
| 필드 | 상태 |
|------|------|
| desc | 채워짐 |
| systemPrompt | 비어있음 → 글로벌 mainPrompt 사용 |
| firstMessage | 사건 1번 기반 |
| globalLore | 사건 2~5번 |
| postHistoryInstructions | 비어있음 |

## desc
### Basic Info
...
### Personality
...
### Background
...
### Preference
...
### Speech Pattern
...

## firstMessage
<3인칭 서술 + 직접 대사. {{user}} 변수 사용. 한국어.>

## globalLore

### <사건 2 원제 (꺾쇠 포함)>
<200~400자 요약 + 핵심 대사>

### <사건 3 원제>
...

## postHistoryInstructions
(비어있음)
```

# 필드별 매핑 규칙

## desc
- 헤딩은 영어 (`### Basic Info` / `Appearance` / `Personality` / `Background` / `Preference` / `Speech Pattern`). 본문은 한국어.
- 입력의 "기본 프로필" bullet 항목은 `### Basic Info` 아래 한국어 bullet로 옮긴다.
- 입력의 "내면 프로필"을 분해해 `### Personality`(성격·습관·반응), `### Background`(과거·가족·직업·관계), `### Preference`(좋아하는 것/싫어하는 것 — 입력에 명시된 것만), `### Speech Pattern`(말투·특징적 화법)에 재배치.
- `### Appearance`는 입력에 외모 묘사가 있을 때만 작성. 없으면 헤딩 자체를 생략.
- 입력에 외모 측정치(가슴·허리·키 외 둘레, 발 사이즈 등)·구체 이름(가족·학교·회사)이 없으면 절대 만들어내지 말 것.

## firstMessage
- 입력의 "사건 1번" 텍스트를 RP 시작 시점으로 각색.
- 3인칭 서술 + 직접 대사 인용 형식. 한국어.
- 사건 원문의 "플레이어"는 `{{user}}` 변수로 치환.
- 핵심 대사는 원문 그대로 보존. 분량은 자연스러운 RP 도입 길이(대략 500~1500자).

## globalLore
- 입력의 "사건 2번"부터 "사건 5번"까지 각각 1개 엔트리.
- 엔트리 헤딩은 사건 원제를 꺾쇠 포함해서 그대로 사용 (예: `### <재회>`).
- 본문은 200~400자 요약 + 핵심 대사 1~2개 보존.
- 사건 1번은 firstMessage에 들어가므로 globalLore에 중복 금지.
- 사건이 5개 미만이면 있는 만큼만, 5개 초과면 5번까지만.

## postHistoryInstructions
- 작가 시트에는 대응 필드가 없음. 항상 `(비어있음)`으로 출력.

## 프롬프트 구조 요약 표
- 위 예시 표의 형태를 그대로 사용. 실제 출력 상황(globalLore가 비면 "비어있음"으로)에 맞춰 우측 셀만 조정.

# 절대 금지 사항

1. 입력에 없는 사실(외모 측정치, 가족 이름, 학교명, 회사명, 친구 이름 등) 생성 금지.
2. 본문에 영어 사용 금지. 헤딩 키워드(`### Basic Info` 등)만 영어 허용.
3. 코드 블록 펜스(```)·안내 문구·메타 코멘트 출력 금지. 응답은 `# 캐릭터:`로 곧장 시작.
4. 사건 1번을 globalLore에 중복으로 넣지 말 것.
5. RisuAI의 조건부 템플릿(`{{#if_pure ...}}`)은 사용하지 말 것 — 이번 PoC는 단일 시나리오.

# Risu 출력 포맷 레퍼런스

아래 두 캐릭터는 RisuAI에서 실제 추출한 분석 문서입니다. 출력 구조·헤딩·톤·서술 스타일을 참고하세요.

**중요:** 레퍼런스의 영어 본문·구체 측정치·이름은 작가 시트에 없으면 절대 복사하지 마세요. 작가 시트에 있는 정보만 사용합니다.

## 레퍼런스 1 — neta (desc 집중형)

{{NETA_EXAMPLE}}

## 레퍼런스 2 — kitagawa-marin (페르소나 이중성 + lorebook 분리형)

{{MARIN_EXAMPLE}}
```

- [ ] **Step 2: 슬롯 확인**

```powershell
Select-String -Path character-converter\prompt.md -Pattern "{{NETA_EXAMPLE}}|{{MARIN_EXAMPLE}}"
```
Expected: 정확히 두 매치 (각 1번).

- [ ] **Step 3: Commit**

```bash
git add character-converter/prompt.md
git commit -m "feat: write meta prompt with field mapping rules and example slots"
```

---

## Task 6: `convert.py` 구현

**Files:**
- Create: `character-converter/convert.py`

- [ ] **Step 1: 스크립트 작성**

`character-converter/convert.py`:
```python
#!/usr/bin/env python
"""Convert an author character sheet (.md) into a RisuAI-style .md + .json pair.

Usage:
    python convert.py inputs/차아진.md           # single file
    python convert.py --all                       # process inputs/*.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic

from md_to_json import parse_md_to_json

ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompt.md"
EXAMPLES_DIR = ROOT / "examples"
INPUTS_DIR = ROOT / "inputs"
OUTPUTS_DIR = ROOT / "outputs"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000


def build_system_prompt() -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    neta = (EXAMPLES_DIR / "neta.md").read_text(encoding="utf-8")
    marin = (EXAMPLES_DIR / "kitagawa-marin.md").read_text(encoding="utf-8")
    return template.replace("{{NETA_EXAMPLE}}", neta).replace("{{MARIN_EXAMPLE}}", marin)


def convert_one(input_path: Path) -> None:
    sheet = input_path.read_text(encoding="utf-8")
    system_prompt = build_system_prompt()

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"<character_sheet>\n{sheet}\n</character_sheet>",
            }
        ],
    )
    md_text = response.content[0].text

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    md_path = OUTPUTS_DIR / f"{stem}.md"
    json_path = OUTPUTS_DIR / f"{stem}.json"

    md_path.write_text(md_text, encoding="utf-8")
    json_data = parse_md_to_json(md_text)
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[{stem}] in={response.usage.input_tokens}t "
        f"out={response.usage.output_tokens}t -> {md_path.name}, {json_path.name}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Single input .md path (omit when using --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every file matching inputs/*.md",
    )
    args = parser.parse_args()

    if args.all:
        files = sorted(INPUTS_DIR.glob("*.md"))
        if not files:
            print("No inputs found in inputs/", file=sys.stderr)
            return 1
        for path in files:
            convert_one(path)
        return 0

    if args.input is None:
        parser.error("provide an input file path or use --all")
    convert_one(args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: import 정합성만 확인 (네트워크 호출 없이)**

```powershell
python -c "import convert; print('ok')"
```
Expected: `ok` (ANTHROPIC_API_KEY 없이도 import 자체는 성공).

- [ ] **Step 3: Commit**

```bash
git add character-converter/convert.py
git commit -m "feat: implement convert.py CLI wrapping Claude API call and parser"
```

---

## Task 7: 단일 캐릭터 smoke test

**Files:**
- Modify: 없음 (실제 LLM 호출 + 결과물 검토)
- Create: `character-converter/outputs/차아진.md` (스크립트가 생성)
- Create: `character-converter/outputs/차아진.json` (스크립트가 생성)

- [ ] **Step 1: API 키 설정**

`character-converter/.env` 생성 (gitignore 처리, 커밋 금지):
```
ANTHROPIC_API_KEY=sk-ant-실제값
```
또는 PowerShell 세션에서:
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

- [ ] **Step 2: 차아진만 변환 실행**

`character-converter/` 안에서:
```powershell
python convert.py inputs/차아진.md
```
Expected stdout: `[차아진] in=NNNNt out=NNNNt -> 차아진.md, 차아진.json`. 에러 없음.

- [ ] **Step 3: 출력 구조 검수**

```powershell
Select-String -Path character-converter\outputs\차아진.md -Pattern "^# 캐릭터:|^## desc|^## firstMessage|^## globalLore|^## postHistoryInstructions"
```
Expected: 5개 매치 (헤더 1개 + 섹션 4개).

```powershell
python -c "import json; print(json.load(open('character-converter/outputs/차아진.json', encoding='utf-8'))['name'])"
```
Expected: `차아진`.

- [ ] **Step 4: 할루시네이션 수동 검수**

`character-converter/inputs/차아진.md`와 `character-converter/outputs/차아진.md`를 나란히 열어 다음을 확인:
- 출력에 입력에 없는 외모 측정치(가슴/허리 둘레 등)가 없는가
- 출력에 입력에 없는 가족·학교·회사·친구 이름이 없는가
- `## firstMessage` 본문이 "사건 1번" <엘리베이터 추락 사건>을 각색했는가
- `## globalLore`에 사건 2~5번(<재회>, <새벽의 체온>, <아진의 이면>, <디스패치>) 4개 엔트리가 있는가
- 사건 1번이 globalLore에 중복돼 있지 않은가
- 본문이 한국어인가 (영어 헤딩 키워드만 허용)

문제가 보이면 `prompt.md`를 수정한 뒤 Step 2부터 재실행. 만족스러우면 다음 단계.

- [ ] **Step 5: outputs/ .gitignore 정책 결정 + commit**

PoC 산출물이므로 outputs/도 함께 커밋해 팀이 git에서 바로 확인 가능하게 둔다.

`.env`만 ignore:
```powershell
Add-Content character-converter\.gitignore ".env`n__pycache__/`n*.pyc"
```

```bash
git add character-converter/.gitignore character-converter/outputs/차아진.md character-converter/outputs/차아진.json
git commit -m "feat: smoke test with 차아진 — first successful conversion"
```

---

## Task 8: 나머지 두 캐릭터 변환

**Files:**
- Create: `character-converter/outputs/이연.md`
- Create: `character-converter/outputs/이연.json`
- Create: `character-converter/outputs/백서희.md`
- Create: `character-converter/outputs/백서희.json`

- [ ] **Step 1: `--all` 실행**

```powershell
python convert.py --all
```
Expected stdout: 3개 캐릭터 각각 한 줄씩 로그. 차아진은 재처리되지만 같은 결과가 덮어쓰여도 무방.

- [ ] **Step 2: 3개 출력 모두 구조 검수**

```powershell
foreach ($name in @("차아진", "이연", "백서희")) {
    Write-Host "=== $name ==="
    Select-String -Path "character-converter\outputs\$name.md" -Pattern "^# 캐릭터:|^## desc|^## firstMessage|^## globalLore|^## postHistoryInstructions"
    python -c "import json; d = json.load(open(r'character-converter/outputs/$name.json', encoding='utf-8')); print('name:', d['name'], '| lore entries:', len(d['globalLore']))"
}
```
Expected per character: 5개 섹션 매치 + JSON load 성공 + globalLore 엔트리 ~4개.

- [ ] **Step 3: 할루시네이션 + 톤 수동 검수**

각 캐릭터에 대해 input과 output을 나란히 보고 Task 7 Step 4의 체크리스트 적용:
- **이연**: 낮/밤 페르소나 이중성이 desc에 잘 표현됐는지. 사건 1번 <낮의 미소>가 firstMessage에 들어갔는지. 사건 2~5(<밤의 이연>, <새벽의 온도>, <취기>, <도망친 마음>)가 globalLore에 4개 엔트리로 있는지.
- **백서희**: 양딸·정략결혼 상대 같은 핵심 관계가 desc Background에 보존됐는지. 사건 1번 <계약 연인>이 firstMessage에. 사건 2~5(<선택의 기준>, <가문의 균열>, <선언된 약혼>, <왕좌의 선택>)가 globalLore에.

문제가 있으면 `prompt.md` 조정 후 재실행. 만족하면 다음.

- [ ] **Step 4: Commit**

```bash
git add character-converter/outputs/
git commit -m "feat: generate Risu-style outputs for all three writer characters"
```

---

## Task 9: README + 팀 리뷰 가이드

**Files:**
- Create: `character-converter/README.md`

- [ ] **Step 1: README 작성**

`character-converter/README.md`:
```markdown
# character-converter (PoC)

작가 캐릭터 시트(한국어 `.md`)를 RisuAI 스타일 분석 문서(`.md`)와 RisuAI native JSON(`.json`)으로 변환하는 PoC.

## 무엇을 하는가

```
inputs/<이름>.md             ┐
prompt.md                    │
examples/neta.md             ├─► Claude API ─► outputs/<이름>.md ─► outputs/<이름>.json
examples/kitagawa-marin.md   │                  (LLM이 생성)         (결정론적 파서)
└─ 작가 시트 입력 ────────────┘
```

- **`.md`**: 사람이 읽기 좋은 분석 문서. 팀 리뷰는 이 파일을 본다.
- **`.json`**: RisuAI native 스키마(`database.bin` 내부 캐릭터 JSON과 동일 구조). 후속 단계(import, 다른 파이프라인 연계)용.
- 변환 로직은 100% `prompt.md`에 있음. 품질 튜닝은 `prompt.md`만 수정.

## 실행

```bash
cd character-converter
pip install -r requirements.txt
cp .env.example .env  # ANTHROPIC_API_KEY 채우기

python convert.py inputs/차아진.md   # 단일
python convert.py --all              # inputs/*.md 전부
```

PowerShell 사용자는 `cp` 대신 `Copy-Item`.

## 팀 리뷰 체크리스트

각 `outputs/<이름>.md`에 대해 다음을 확인:

1. **구조** — `# 캐릭터:` 헤더 + `## desc`, `## firstMessage`, `## globalLore`, `## postHistoryInstructions` 섹션이 모두 있는가? `outputs/<이름>.json`이 valid JSON인가?
2. **할루시네이션** — `inputs/<이름>.md`와 나란히 놓고 비교: 출력에 입력에 없는 사실(외모 측정치, 가족·학교·회사·친구 이름)이 추가되지 않았는가?
3. **톤** — `firstMessage`가 사건 1번 톤과 핵심 대사를 살렸는가? `globalLore` 각 엔트리가 원본 사건의 핵심 갈등·대사를 보존했는가?
4. **언어** — 본문이 한국어인가? 영어는 헤딩 키워드(`### Basic Info` 등)에만 있는가?
5. **중복 방지** — 사건 1번이 `globalLore`에 중복되지 않았는가?

## 파일

- `prompt.md` — 메타 프롬프트 (변환 규칙 + few-shot 슬롯)
- `examples/` — 출력 포맷 레퍼런스 (neta, kitagawa-marin)
- `inputs/` — 작가 캐릭터 시트 3종
- `outputs/` — 변환 결과 페어
- `convert.py` — CLI + Claude API 호출
- `md_to_json.py` — `.md` → RisuAI native JSON 파서
- `tests/` — 파서 단위 테스트

## 알려진 한계

- `outputs/`는 실제 RisuAI에 1클릭 import되는 형식이 아니다. `database.bin` 내부 캐릭터 JSON과 같은 모양일 뿐, `.png` character card 패키징은 후속 단계.
- 사건 5개를 모두 별 엔트리로 풀어쓰는 식이라 lorebook이 좀 크다. 실제 RP에서 context 비용을 보고 조정 필요.
- LLM 출력 포맷이 `prompt.md` 규칙을 살짝 벗어나면 `md_to_json.py` 파서가 깨질 수 있다. 출력이 이상하면 먼저 `outputs/<이름>.md`의 헤딩 구조를 눈으로 확인.

## 다음 단계

- TavernAI v2 호환 JSON 변환 → `.png` character card 패키징 → 실제 RisuAI import 테스트
- 첫 변환 결과를 추가 few-shot으로 넣어 품질 부스트
- 지영님 트랙(avadot.com JSON)과 공유 가능한 중간 표현 정의
```

- [ ] **Step 2: Commit**

```bash
git add character-converter/README.md
git commit -m "docs: add README with team review checklist and architecture"
```

---

## Task 10: 최종 self-check

**Files:** (없음 — 전체 검증)

- [ ] **Step 1: 전체 테스트 통과 확인**

```powershell
cd character-converter
python -m pytest tests/ -v
cd ..
```
Expected: 9 passed.

- [ ] **Step 2: 변환 결과 매니페스트 확인**

```powershell
Get-ChildItem character-converter\outputs\
```
Expected: 차아진.md, 차아진.json, 이연.md, 이연.json, 백서희.md, 백서희.json — 정확히 6개 파일.

- [ ] **Step 3: 모든 JSON 파일 valid 확인**

```powershell
foreach ($f in Get-ChildItem character-converter\outputs\*.json) {
    python -c "import json; json.load(open(r'$($f.FullName)', encoding='utf-8'))" 
    Write-Host "$($f.Name): OK"
}
```
Expected: 3개 파일 모두 OK.

- [ ] **Step 4: git status 깨끗한지 확인**

```bash
git status
```
Expected: working tree clean. 모든 작업이 커밋됨.

- [ ] **Step 5: 팀에 PR/리뷰 요청 준비**

ai-poc 레포로 옮길지 risu-window에서 검토 후 옮길지는 별도 결정. 이 plan 범위 밖.

---

## Self-Review 결과 (작성자가 작성 직후 확인)

**Spec coverage 매핑:**
- Spec §3 입력 포맷 → Task 1 Step 3 (작가 시트 분리)
- Spec §4-1 `.md` 출력 → Task 5 (프롬프트 규칙) + Task 7/8 (실제 생성)
- Spec §4-2 `.json` 스키마 → Task 4 (파서 구현)
- Spec §5 아키텍처/파일 구조 → Task 1 (스켈레톤) + 전체
- Spec §6 메타 프롬프트 → Task 5
- Spec §7-1 convert.py → Task 6
- Spec §7-2 md_to_json.py → Task 2~4
- Spec §8 검수 방법 → Task 7 Step 4, Task 8 Step 3, Task 9 (README 체크리스트), Task 10
- Spec §9 후속 단계 → Task 9 README의 "다음 단계"
- Spec §10 결정 사항 → 전 plan에 반영

**Placeholder scan:** TBD/TODO 없음. 모든 코드는 실행 가능한 완전체로 제시됨.

**Type consistency:** 
- `parse_md_to_json` signature: `md_to_json.py`(`(md_text: str) -> dict[str, Any]`), `convert.py`(`parse_md_to_json(md_text)` 호출), `test_md_to_json.py`(`parse_md_to_json(FIXTURE.read_text(...))`) — 일관.
- JSON 키: `name`/`desc`/`firstMessage`/`globalLore`/`postHistoryInstructions`/`systemPrompt`/`personality`/`scenario` — spec §4-2와 파서 구현과 테스트가 모두 일치.
- 슬롯 토큰: `{{NETA_EXAMPLE}}`/`{{MARIN_EXAMPLE}}` — `prompt.md`와 `convert.py` build_system_prompt가 동일 문자열 사용.
