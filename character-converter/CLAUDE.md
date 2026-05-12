# character-converter — Claude/AI 작업 지침

작가가 한국어로 적은 캐릭터 시트를 **RisuAI 네이티브 `character` JSON** 으로 자동 변환하는 도구. 빠진 필드는 LLM 이 채우고, 고유명사·수치는 입력에 있는 것만 보존.

자세한 사용 설명은 [README.md](README.md). RisuAI 내부 포맷·DB 추출·슬롯 매핑 자세히는 [docs/RisuAI-internals.md](docs/RisuAI-internals.md). 본 파일은 이 코드베이스에서 작업하는 AI 가 알아야 할 **불변(invariant)·관례·함정** 만 추립니다.

## 아키텍처 한 그림

```
input/<이름>.md
   │
   ▼  main.py        (Anthropic API, system=prompt.md + few-shot)
   │
output/md/<이름>.md   (Pass 1: 사람 검수용 마크다운)
   │
   ▼  merger.py      (결정론적, no LLM, 참조 기반)
   │
output/json/<이름>.json  (RisuAI character 인터페이스, 32 필드)
   │
   ▼  assembler.py   (옵션, --assemble)
   │
output/json/<이름>.assembled.json  (LLM-ready messages[])
```

3개 모듈은 단일 책임 분리:
- `main.py` — API 호출 + 머저·어셈블러 트리거
- `merger.py` — 헤딩 파싱 + 본문 직접 박기 (LLM 통과 없음)
- `assembler.py` — 9-슬롯 직렬화 + `{{char}}`/`{{user}}` 매크로

## 불변 사항 (변경 시 신중)

### 1. Marin 패턴 출력 형태
`character` JSON 의 `desc`/`personality`/`scenario`/`systemPrompt` 는 **항상 빈 문자열**. 모든 캐릭터 본문은 `globalLore[0]` (alwaysActive=true, insertorder=400) 에 들어가고 에피소드는 `globalLore[1..N]` (insertorder=399, 398, ...).

이유: RisuAI 토큰 cull 정책에서 description 슬롯은 보호 영역이라 큰 본문이 들어가면 토큰 폭주. lorebook 엔트리는 보호되면서도 향후 키워드 활성화·매크로 분기 도입 자연스러움.

이걸 바꾸려면 prompt.md + merger.py + tests/test_merger.py 셋 다 같이.

### 2. 헤딩 = 섹션 ID 계약 (silent corruption 방지)
Pass 1 .md 의 `##`/`###` 헤딩은 머저가 파싱하는 stable ID. 다음만 인정:
- `## desc` / `## firstMessage` / `## globalLore` / `## postHistoryInstructions` / `## 프롬프트`
- `## desc` 안의 `###` 서브헤더 7개: `Basic Info`, `Appearance`, `Personality`, `Background`, `Preference`, `Speech Pattern`, `Trivia`
- `## globalLore` 안의 `### <에피소드 제목>`

LLM 이 위 화이트리스트 밖 `##` 헤더를 만들면 `merger.parse_pass1_md` 가 즉시 `ValueError` raise. 절대 silent drop 안 함.

### 3. 빈 섹션 표기 = `없음`
Pass 1 출력에서 헤더는 7개 모두 항상 적되, 빈 섹션은 본문에 `없음` 한 줄. `(비어있음)` 도 인정(legacy). 머저의 `_EMPTY_MARKERS = {"(비어있음)", "없음", ""}` 에서 정규화.

빈 섹션을 헤더째 생략하면 안 됨 — "빠진 게 아니라 없는 것" 임을 명시해야 함.

### 4. LOCKED / FREE 정책 (prompt.md)
**LOCKED — AI 가 절대 추가·발명 안 함**:
- 외모 측정치 (cm/kg)
- 인물 고유명 (가족·친구·동료)
- 기관·장소 고유명 (학교명·회사명·도시명)
- 수치 (나이·생일·금액·MBTI·혈액형)
- 입력에 없는 새 인물

**FREE — AI 가 입력 톤·세계관 안에서 자유 합성**:
- Speech Pattern 예문
- Trivia 불릿
- Personality Keywords 라벨링
- Background·Description 산문 정돈
- Preference 카테고리화
- firstMessage 분위기 묘사

prompt.md 의 `# Gap-fill 정책` 섹션이 진실의 원천.

### 5. 어셈블러 매크로 평가 범위
`assembler.py` 는 `{{char}}` / `{{user}}` 만 평가. `{{#if_pure}}` / `{{getvar::}}` / `{{equal::}}` / `{{? expr}}` 등은 **미평가** — 그대로 두고 `meta.unevaluated_macros` 에 보고.

현재 입력은 단일 시나리오라 매크로 0건 — 영향 없음. Marin 같은 다중 페르소나 캐릭터 지원하려면 별도 매크로 평가기 필요(v3).

## 관례

### 모델 기본값
`main.py --model` 기본은 `opus` (claude-opus-4-7). 비용 민감 작업은 `--model sonnet` (claude-sonnet-4-6, 1/10 비용).

### 파일 명명
- 입력: `input/<이름>.md` (한국어 캐릭터명 그대로)
- 출력: `output/md/<이름>.md`, `output/json/<이름>.json` — 모델 변형 prefix 없음. 다시 변환하면 같은 파일 덮어쓰기. A/B 테스트 필요시 외부에서 mv.

### 한국어 본문 + 영어 헤더
출력 .md 본문은 한국어, `### Basic Info` 같은 헤딩 키워드만 영어. RisuAI 네이티브 캐릭터들 (references/) 가 이 패턴.

### references/ 사용
`references/md/{neta,kitagawa-marin}.md` 두 캐릭터만 prompt.md 의 `{{NETA_EXAMPLE}}` / `{{MARIN_EXAMPLE}}` 슬롯에 박힘. 나머지 7종은 시각 참조용(LLM 슬롯 X).

few-shot 캐릭터 바꾸려면 `main.py:build_system_prompt()` 수정.

## 함정

### Windows 콘솔 한글 mojibake
PowerShell·cmd 의 코드페이지가 CP949 일 때 Python `print()` 한글이 깨짐. **파일은 정상**(UTF-8). 검수 시 stdout 말고 파일 직접 읽기.

### Anthropic API 일시 글리치
`getaddrinfo failed` 같은 일시 네트워크 오류 자주 발생. 재시도하면 보통 성공. main.py 는 재시도 로직 없음 — 호출자가 재실행.

### 백그라운드 잡 멈춤
`run_in_background=True` 로 main.py 돌리면 stdout 안 보이는 상태로 멈추는 경우 있음. 포그라운드 권장 (캐릭터당 30-60초).

### prompt.md 토큰 폭주
few-shot 으로 들어가는 references/md/kitagawa-marin.md 가 32KB. system prompt 가 ~35KB 됨. Marin 본체에 측정치 60+ 항목 같은 long content 때문. 입력 작은 캐릭터 변환 시에도 ~25K input tokens 소요 — 정상.

### chaId UUID 매번 다름
`merger.assemble_risu_json` 이 매 호출마다 새 UUID 생성. 같은 입력 재변환 시 JSON 이 비결정적 (chaId 다름). 회귀 테스트는 chaId 무시하고 비교.

## 테스트

```bash
python -m pytest tests/ -q       # 33 tests, ~0.05s
```

- `test_merger.py` — 14 tests, md → JSON 파싱·조립
- `test_assembler.py` — 19 tests, JSON → messages[] 직렬화

API 호출 안 함 (`anthropic` 임포트 안 함). 빠르고 결정적.

### 실 챗 검증 (옵션)

```bash
python scripts/qa_chat_test.py
```

세 캐릭터 어셈블 결과를 실제 Opus 호출에 던져 in-character 응답 받는지 확인. API 키 + 비용 발생. 결과는 `~/.gstack/qa-reports/chat-test-results.json` (워크스페이스 상위로 저장).

## 새 캐릭터 추가 workflow

1. `input/<새이름>.md` 작성 — README.md "새 캐릭터 추가" 참조
2. `python main.py <새이름> --assemble`
3. `output/md/<새이름>.md` 사람 검수 (LOCKED 위반 없는지, FREE 영역 합성 톤 맞는지)
4. 잠금 위반 발견 시 prompt.md `# LOCKED` 영역에 케이스 추가, `python main.py <새이름>` 재실행

## v3 후보 (미구현, 알아두기)

- `{{#if_pure}}` / `{{getvar::}}` 매크로 평가기 (Marin 다중 페르소나)
- 세계관 공유 (`world.md` include 식)
- 키워드 매칭 lorebook 활성화
- TavernAI `.png` character card 패키징
- 자동 품질 평가 LLM-judge
- 잠금 룰 lint 자동화 (입력 고유명 토큰 셋 ↔ 출력 텍스트 스캔)

## 의존성

`requirements.txt` — `anthropic`, `python-dotenv`, `pytest`. 그 외 표준 라이브러리만.

런타임 의존 파일:
- `prompt.md` — main.py 가 system prompt 로 사용
- `references/md/{neta,kitagawa-marin}.md` — few-shot 슬롯
- `references/default-preset.json` — assembler.py 의 글로벌 mainPrompt/jailbreak/formatingOrder 출처
- `.env` — `ANTHROPIC_API_KEY`
