# character-converter

작가가 한국어로 작성한 캐릭터 시트를 RisuAI 네이티브 character JSON으로 자동 변환합니다. 빠진 필드(말투 예문·트리비아 등 FREE 영역)는 LLM이 채우고, 고유명사·수치(LOCKED 영역)는 입력에 있는 것만 보존합니다.

```
input/<이름>.md
   │
   ▼  Anthropic API (system=prompt.md + few-shot, user=<character sheet>)
   │
output/md/<이름>.md           ← 사람이 읽는 RisuAI 분석 문서 (팀 검수용)
   │
   ▼  merger.py (결정론적, 참조 기반, no-LLM)
   │
output/json/<이름>.json       ← 캐논 RisuAI character 인터페이스 JSON (32 필드)
   │
   ▼  assembler.py (옵션, --assemble 플래그)
   │
output/json/<이름>.assembled.json   ← LLM-ready messages[] (Anthropic API에 바로 던질 수 있음)
```

## 디렉토리 구조

```
character-converter/
├── main.py              # 진입점 — Anthropic API 호출 + 머저 + 어셈블러 트리거
├── merger.py            # md → RisuAI character JSON
├── assembler.py         # JSON + 글로벌 preset → LLM-ready messages[]
├── prompt.md            # 시스템 프롬프트 (LOCKED/FREE 정책 명시)
│
├── input/               # 작가 캐릭터 시트 (변환 입력)
│   ├── 백서희.md
│   ├── 차아진.md
│   └── 이연.md
│
├── output/              # 변환 결과 (재생성 가능, 커밋됨)
│   ├── md/<이름>.md             # RisuAI 분석 문서
│   └── json/<이름>.json         # 캐논 character 인터페이스 JSON
│       └── <이름>.assembled.json (옵션)
│
├── references/          # RisuAI 실 캐릭터 9종 (database.bin 추출)
│   ├── md/   # neta, kitagawa-marin (few-shot 사용), 그 외 7종 참고용
│   └── json/
│
├── scripts/qa_chat_test.py   # 변환물 실 챗 동작 검증용 (옵션)
├── tests/               # pytest (33 tests)
├── requirements.txt
├── .env.example
└── .gitignore
```

## 설정

```bash
cd character-converter
python -m venv .venv
source .venv/bin/activate              # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                    # PowerShell: Copy-Item .env.example .env
# .env 에 ANTHROPIC_API_KEY=sk-ant-... 채우기
```

## 사용법

### 단일 캐릭터 변환

```bash
python main.py 백서희                   # 기본 모델: opus
python main.py 백서희.md --model sonnet
python main.py input/백서희.md          # 절대/상대 경로도 OK
```

### 어셈블된 messages[] 까지

```bash
python main.py 백서희 --assemble        # output/json/백서희.assembled.json 추가 생성
```

### 일괄 처리

```bash
python main.py --all --assemble         # input/*.md 전부, 어셈블 포함
```

### 모델 선택

| `--model` | 모델 ID | 비용 (대략, 캐릭터당) | 특징 |
|-----------|---------|---------|------|
| `opus` (기본) | claude-opus-4-7 | ~$0.50 | Marin 패턴 충실도 ↑, 구조 라벨링(Johari Window 등) 우수 |
| `sonnet` | claude-sonnet-4-6 | ~$0.05 | 정보 밀도 ↑, 비용 1/10 |

## 입력 → 출력 매핑 (백서희 예시)

| 단계 | 파일 | 내용 |
|------|------|------|
| 입력 | `input/백서희.md` (13,574 bytes) | 작가 캐릭터 시트: 기본 프로필 + 내면 프로필 + 사건 5개 |
| 1단계 산출 | `output/md/백서희.md` (~13KB) | RisuAI 슬롯별 한국어 서술. `## desc`, `## firstMessage`, `## globalLore`, `## postHistoryInstructions` |
| 2단계 산출 | `output/json/백서희.json` (~15KB, 32 필드) | RisuAI `character` 인터페이스 캐논 JSON. `name`, `desc`, `globalLore[]`, `firstMessage`, `loreSettings`, `chaId` 등. RisuAI 앱이 그대로 import 가능 |
| 3단계 산출 (옵션) | `output/json/백서희.assembled.json` (~15KB) | LLM-ready `{messages, meta}`. 8개 메시지 (main + chats + jailbreak + lorebook×5). Anthropic API `system` + `messages` 파라미터로 바로 전송 가능 |

### Pass 1 md 출력 구조 (모든 헤더 항상 출력, 빈 섹션은 `없음`)

```markdown
# 캐릭터: <이름>

## 프롬프트 구조 요약
| 필드 | 상태 |
...

## desc
### Basic Info
...
### Appearance
없음                                    ← 입력에 없으면 정확히 "없음"
### Personality
...
### Background
...
### Preference
...
### Speech Pattern
...
### Trivia
...

## firstMessage
...

## globalLore
### <사건 2 원제>
...

## postHistoryInstructions
없음
```

머저는 `없음`을 빈 문자열로 정규화하여 RisuAI JSON에 반영합니다.

## 새 캐릭터 추가

1. `input/<새이름>.md` 작성. 권장 섹션:
   ```markdown
   # <이름>

   ## 기본 프로필
   - 이름, 성별, 생년월일, 직업, 키·체형, 혈액형, MBTI 등

   ## 내면 프로필
   인격·심리·관계·갈등 산문 (한 단락 이상)

   ## 사건
   **1. <사건 제목>**
   400-600자 줄거리 + 핵심 대사 1-2줄 인용
   ...
   **5. <사건 5>**
   ```

2. `python main.py <새이름> --assemble` 실행
3. `output/md/<새이름>.md`, `output/json/<새이름>.json`, `output/json/<새이름>.assembled.json` 확인

## Gap-fill 정책 (prompt.md)

**LOCKED — AI가 절대 추가·발명하지 않음**:
- 외모 측정치 (cm/kg 단위)
- 인물 고유명 (가족·친구·동료·정략혼 상대 등)
- 기관·장소 고유명 (학교명·회사명·도시명)
- 수치 (나이·생일·금액·MBTI·혈액형)
- 입력에 없는 새 인물 등장

**FREE — AI가 입력의 톤·세계관 안에서 자유롭게 합성**:
- `### Speech Pattern` 예문 1-3개
- `### Trivia` 불릿 3-6개
- `### Personality Keywords` (Johari Window 라벨링)
- `### Background` 산문 정돈
- `### Preference` 9 카테고리 분류
- firstMessage 분위기·소품 묘사

## 참고 캐릭터 (references/)

`database.bin`에서 추출한 실 RisuAI 캐릭터 9종:
`hayan`, `kang-sieun`, `kitagawa-marin`, `meruru`, `mio`, `neta`, `ovento`, `seo-yunha`, `yeongyeong-family`

이 중 `neta` (Pattern A, desc 집중형) 와 `kitagawa-marin` (Pattern B, lorebook 분리형) 두 캐릭이 prompt.md의 few-shot 레퍼런스로 슬롯됩니다. 나머지 7종은 팀이 "실제 RisuAI 캐릭터가 어떤 모양인지" 직접 보기 위한 참조 데이터.

자신의 RisuAI 앱에서 새 캐릭터를 추출해 `references/`에 추가하려면 [`docs/RisuAI-internals.md`](docs/RisuAI-internals.md) 의 PowerShell 추출 워크플로우 참조.

## 테스트

```bash
python -m pytest tests/ -q    # 33 tests
```

세 모듈 테스트:
- `test_merger.py` — md → JSON 머저 (14 tests)
- `test_assembler.py` — JSON → messages[] 어셈블러 (19 tests)

## 산출물 실 챗 검증 (옵션)

`scripts/qa_chat_test.py` — 세 캐릭터에 컨텍스트 적절한 사용자 메시지를 던져 실제로 in-character로 작동하는지 검증.

```bash
python scripts/qa_chat_test.py
```

결과: 응답 텍스트는 `.gstack/qa-reports/chat-test-results.json`에 저장.

## 비교 리포트

- `docs/comparison/2026-05-12-baekseohee-ab.md` — Opus 4.7 vs Sonnet 4.6 사이드-바이-사이드, Marin 레퍼런스 대비 분석, 잠금 룰 위반 검사.
- `docs/specs/2026-05-12-character-converter-v2-design.md` — 설계 문서.
- `docs/character-prompt-storage.md` — RisuAI 슬롯 매핑 진실의 원천.
