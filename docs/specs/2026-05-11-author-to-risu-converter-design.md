# 작가 캐릭터 시트 → RisuAI 스타일 프롬프트 변환기 (PoC)

**작성일**: 2026-05-11
**담당**: 찬우
**대상 레포**: github.com/tridot-io/ai-poc (PoC 단계는 risu-window 워크스페이스에서 진행)

---

## 1. 배경

작가가 한국어로 작성한 캐릭터 시트(Notion)를 입력받아, RisuAI 스타일의 구조화된 캐릭터 프롬프트 설계 문서로 변환한다. 동시에 RisuAI native JSON 형태의 구조화 데이터도 함께 산출해, 후속 단계(실제 Risu import, 다른 파이프라인 연계)에 활용할 수 있게 한다.

지영님 트랙(작가 시트 → avadot.com 입력용 JSON)과 병행되는 자매 PoC.

## 2. 목표 / 비목표

### 목표
- 작가 시트 한 장을 입력으로 받아 RisuAI 스타일 `.md` 분석 문서 + RisuAI native `.json` 페어를 자동 생성
- 작가님 캐릭터 3종(차아진/이연/백서희)을 변환해 PoC 산출물로 제시
- 팀원이 결과물을 보고 변환 품질·전략을 평가할 수 있도록 git diff 친화적인 평문 출력
- 프롬프트 수정만으로 변환 품질을 튜닝할 수 있는 구조 (코드 수정 최소화)

### 비목표
- 실제 RisuAI에 import 가능한 `.png` character card 패키징 (다음 단계)
- TavernAI v2 호환 (다음 단계)
- 다국어 출력
- 작가 시트의 Notion API 직접 연동 (입력은 `.md` 평문으로 한정)
- 변환 결과의 자동 품질 평가 (LLM-as-judge 같은 것)

## 3. 입력 포맷

작가 시트 1캐릭터를 1개 `.md` 파일로 저장. 구조 예시:

```markdown
# <이름>

## 기본 프로필
- 이름: ...
- 생년월일: ...
- 직업: ...
- (기타 bullet list 필드)

## 내면 프로필
<한국어 자유 서술. 1000~2000자. 성격·배경·심리·관계>

## 사건
**1. <사건 제목>**
<단락 서술>

**2. <사건 제목>**
...

(통상 5개 사건)
```

레퍼런스: `author-input.md` (3캐릭터 합본 — PoC에서는 캐릭터당 1파일로 분리)

## 4. 출력 포맷

### 4-1. `.md` (팀 리뷰용 분석 문서)

기존 `neta.md` / `kitagawa-marin.md` 형식을 따른다. 한국어 본문, 영어 헤딩.

```markdown
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
- 이름: ...
- 나이: ...
### Appearance
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
<사건 1번을 RP 시작 시점으로 각색한 한국어 서술. {{user}} 변수 사용>

## globalLore

### <사건 2 원제>
<200~400자 요약 + 핵심 대사 보존>

### <사건 3 원제>
...

## postHistoryInstructions
(비어있음)
```

### 4-2. `.json` (RisuAI native 스키마)

`database.bin` 내부 캐릭터 JSON 구조를 그대로 따른다 (CLAUDE.md 참조).

```json
{
  "name": "차아진",
  "desc": "### Basic Info\n- 이름: 차아진\n...",
  "firstMessage": "<사건1 각색 한국어 텍스트>",
  "globalLore": [
    {"key": "재회", "content": "..."},
    {"key": "새벽의 체온", "content": "..."},
    {"key": "아진의 이면", "content": "..."},
    {"key": "디스패치", "content": "..."}
  ],
  "postHistoryInstructions": "",
  "systemPrompt": "",
  "personality": "",
  "scenario": ""
}
```

빈 필드는 명시적으로 빈 문자열/배열로 둔다. 누락하지 않는다.

## 5. 아키텍처

### 5-1. 파일 구조

```
character-converter/
├── README.md                  # 실행법 + 변환 흐름 + 팀 리뷰 가이드
├── prompt.md                  # 메타 프롬프트 (system part, few-shot 슬롯 포함)
├── examples/
│   ├── neta.md                # desc 집중형 출력 레퍼런스
│   └── kitagawa-marin.md      # 페르소나 이중성 + lorebook 분리형 레퍼런스
├── inputs/
│   ├── 차아진.md
│   ├── 이연.md
│   └── 백서희.md
├── outputs/
│   ├── 차아진.md
│   ├── 차아진.json
│   ├── 이연.md
│   ├── 이연.json
│   ├── 백서희.md
│   └── 백서희.json
├── convert.py                 # LLM 호출 + .md 생성 + .json 파싱
├── md_to_json.py              # .md → .json 결정론적 파서 (convert.py에서 import)
├── requirements.txt           # anthropic
└── .env.example
```

### 5-2. 데이터 흐름

```
inputs/<이름>.md
    │
    ▼ (convert.py)
prompt.md + examples/* + 입력 .md
    │
    ▼ Claude API (single-shot)
LLM이 .md 텍스트 생성
    │
    ├──► outputs/<이름>.md  (그대로 저장)
    │
    └──► md_to_json.py로 파싱
            │
            ▼
        outputs/<이름>.json
```

LLM 호출은 캐릭터당 1회. `.json`은 LLM 출력을 결정론적으로 파싱해서 생성하므로 추가 호출 없음.

## 6. 메타 프롬프트 설계

### 6-1. System 파트 핵심 내용

- **출력 포맷 지시**: 섹션 순서·헤딩 명시 (4-1 그대로)
- **필드별 매핑 규칙**:
  - `desc`: 영어 헤딩(### Basic Info / Appearance / Personality / Background / Preference / Speech Pattern), 본문 한국어. 입력의 "기본 프로필" + "내면 프로필"을 압축·재구성.
  - `firstMessage`: 입력의 "사건 1번"을 RP 시작 시점 3인칭 서술 + 직접 대사로 각색. 한국어. {{user}} 변수 사용. 마린 firstMessage 톤 참조.
  - `globalLore`: 입력의 "사건 2~5번" 각각 1개 엔트리. 엔트리 제목은 사건 원제 그대로(예: `### <재회>`). 본문은 200~400자 요약 + 핵심 대사 보존.
- **할루시네이션 가드**: "입력에 없는 정보 생성 금지" — 외모 측정치·가족 이름·학교명·구체적 회사명 등 절대 추가하지 말 것.
- **중복 금지**: 사건 1번이 firstMessage가 되므로 globalLore에 중복 금지.
- **언어 강제**: 본문은 100% 한국어. 헤딩 키워드만 영어 허용.
- **Few-shot**: `examples/neta.md`, `examples/kitagawa-marin.md` 전체 내용을 "출력 포맷 레퍼런스"로 포함.

### 6-2. User 파트

```
<character_sheet>
{inputs/<이름>.md 전체 내용}
</character_sheet>
```

### 6-3. Few-shot 한계

`examples/*`는 "Risu 출력은 이런 모양"을 보여주는 **출력-only 레퍼런스**다. 입력→출력 매핑쌍이 아니다 (neta/marin은 작가 시트 입력이 없음). 따라서 매핑 로직은 6-1의 규칙 명시문에 의존한다. 첫 변환 결과(예: 차아진)가 잘 나오면, 그 입력-출력 쌍을 추가 few-shot으로 넣어 나머지 둘의 품질을 끌어올릴 수 있다 (선택적 후속 작업).

## 7. Python 스크립트 동작

### 7-1. convert.py

```python
# 의사 코드
import os, json, anthropic
from pathlib import Path
from md_to_json import parse_md_to_json

PROMPT_TEMPLATE = Path("prompt.md").read_text(encoding="utf-8")
NETA = Path("examples/neta.md").read_text(encoding="utf-8")
MARIN = Path("examples/kitagawa-marin.md").read_text(encoding="utf-8")

def convert(input_path: Path, output_dir: Path):
    sheet = input_path.read_text(encoding="utf-8")
    system_prompt = PROMPT_TEMPLATE.replace("{NETA_EXAMPLE}", NETA).replace("{MARIN_EXAMPLE}", MARIN)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": f"<character_sheet>\n{sheet}\n</character_sheet>"}],
    )
    md_text = response.content[0].text

    stem = input_path.stem
    (output_dir / f"{stem}.md").write_text(md_text, encoding="utf-8")

    json_data = parse_md_to_json(md_text)
    (output_dir / f"{stem}.json").write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"{stem}: input={response.usage.input_tokens}t, output={response.usage.output_tokens}t")
```

CLI:
- `python convert.py inputs/차아진.md` → outputs/ 에 페어 생성
- `python convert.py --all` → inputs/*.md 전부 일괄 처리

### 7-2. md_to_json.py — 결정론적 파서

`.md` 출력의 섹션 앵커를 기준으로 파싱:

- `# 캐릭터: <이름>` → `name`
- `## desc` ~ 다음 `##` 까지 → `desc`
- `## firstMessage` ~ 다음 `##` 까지 → `firstMessage`
- `## globalLore` 아래 각 `### <제목>` ~ 다음 `###` 까지 → `globalLore[].{key, content}`
- `## postHistoryInstructions` 아래 본문 → `postHistoryInstructions` (`(비어있음)`이면 빈 문자열)
- 누락 필드는 빈 문자열/배열로 채움

파서는 regex 기반 30~50줄 수준. LLM 출력이 포맷을 정확히 지키도록 프롬프트로 강제하는 게 전제. 포맷 어긋남이 발견되면 프롬프트를 더 엄격히 잡는 방향으로 대응 (파서를 robust하게 만들지 않음).

## 8. 검수 방법

PoC라 자동화된 quality gate는 없다. 팀 리뷰 시 다음 항목을 수동 확인:

1. **구조 검수 (스크립트 한 줄)**: 출력 `.md`에 필수 섹션(`## desc`, `## firstMessage`, `## globalLore`, `## postHistoryInstructions`)이 모두 있는지 grep. `.json`이 valid JSON인지 `python -m json.tool`로 확인.
2. **할루시네이션 검수 (수동)**: 입력 `.md`와 출력 `.md`를 나란히 놓고, 출력에 입력에 없는 사실(측정치·이름·기관)이 있는지 체크.
3. **톤 검수 (수동)**: `firstMessage`가 사건 1번 톤·핵심 대사를 살렸는지. `globalLore` 엔트리가 사건 원본의 갈등 구조·핵심 대사를 보존했는지.
4. **재현성 (선택)**: 동일 입력으로 2~3회 실행해 결과 편차 확인. temperature 기본값 사용.

README.md에 위 4가지를 짧은 체크리스트로 박아둠.

## 9. 후속 단계 (이번 PoC 범위 밖)

- `.png` character card 패키징 (RisuAI 실제 import 가능)
- TavernAI v2 호환 JSON 변환 (SillyTavern 호환)
- 첫 변환 결과를 추가 few-shot으로 넣어 품질 부스트
- 지영님 JSON 파이프라인과 공유 가능한 중간 표현 정의
- 자동 quality gate (할루시네이션 탐지, 필드 누락 탐지)
- Notion API 직접 연동

## 10. 정리된 결정 사항 요약

| 결정 항목 | 선택 |
|----------|------|
| 사건 매핑 | 사건1=firstMessage / 사건2~5=globalLore |
| 출력 언어 | 한국어 (헤딩 키워드만 영어) |
| PoC 범위 | 3캐릭터 전체 |
| 산출물 형태 | 프롬프트 + Python 스크립트 + 변환 결과 |
| 아키텍처 | Single-shot LLM (캐릭터당 1회 호출) |
| 출력 페어 | `.md` + `.json` |
| JSON 스키마 | RisuAI native (database.bin 내부 구조) |
| 생성 방식 | LLM → `.md` → 결정론적 파서 → `.json` |
| 모델 | Claude Opus 4.7 (1차) / Sonnet 4.6 비교 가능 |
