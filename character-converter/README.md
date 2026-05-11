# character-converter (PoC)

작가 캐릭터 시트(한국어 `.md`)를 RisuAI 스타일 분석 문서(`.md`)와 RisuAI native JSON(`.json`)으로 변환하는 PoC.

## 무엇을 하는가

```
inputs/<이름>.md             ┐
prompt.md                    │
examples/neta.md             ├─► Claude Sonnet 4.6 ─► outputs/<이름>.md ─► outputs/<이름>.json
examples/kitagawa-marin.md   │                        (LLM이 생성)         (결정론적 파서)
└─ 작가 시트 입력 ────────────┘
```

- **`.md`**: 사람이 읽기 좋은 분석 문서. 팀 리뷰는 이 파일을 본다.
- **`.json`**: RisuAI native 스키마(`database.bin` 내부 캐릭터 JSON과 동일 구조). 후속 단계(import, 다른 파이프라인 연계)용.
- 변환 로직은 100% `prompt.md`에 있음. 품질 튜닝은 `prompt.md`만 수정.
- **모델 선택**: PoC는 Claude Sonnet 4.6 사용. 설계 spec은 초기에 Opus 4.7을 1차로 명시했으나, 실제 변환 결과의 품질·비용 트레이드오프를 보고 Sonnet 4.6으로 정착. 더 어려운 캐릭터에서 품질이 부족하면 `convert.py`의 `MODEL` 상수를 `claude-opus-4-7`로 바꿔 비교 가능.

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
2. **할루시네이션** — `inputs/<이름>.md`와 나란히 놓고 비교: 출력에 입력에 없는 사실(외모 측정치, 가족·학교·회사·친구 이름, 구체 수치)이 추가되지 않았는가?
3. **톤** — `firstMessage`가 사건 1번의 주요 비트(만남·갈등·반전·결말)를 모두 살렸는가? `globalLore` 각 엔트리가 원본 사건의 핵심 갈등·대사를 보존했는가?
4. **언어** — 본문이 한국어인가? 영어는 헤딩 키워드(`### Basic Info` 등)에만 있는가?
5. **중복 방지** — 사건 1번이 `globalLore`에 중복되지 않았는가?

## 파일

- `prompt.md` — 메타 프롬프트 (변환 규칙 + few-shot 슬롯)
- `examples/` — 출력 포맷 레퍼런스 (neta, kitagawa-marin)
- `inputs/` — 작가 캐릭터 시트 3종
- `outputs/` — 변환 결과 페어 (`.md` + `.json`)
- `convert.py` — CLI + Claude Sonnet 4.6 API 호출 + dotenv 로딩
- `md_to_json.py` — `.md` → RisuAI native JSON 파서 (정규식 기반)
- `tests/` — 파서 단위 테스트 (9개, 모두 통과)

## 알려진 한계

- `outputs/`는 실제 RisuAI에 1클릭 import되는 형식이 아니다. `database.bin` 내부 캐릭터 JSON과 같은 모양일 뿐이며, `.png` character card 패키징은 후속 단계.
- 사건 5개를 모두 별 엔트리로 풀어쓰는 식이라 lorebook이 좀 크다. 실제 RP에서 context 비용을 보고 조정 필요.
- LLM이 200~400자 globalLore 캡을 항상 지키지는 못한다. 정보 밀도가 높은 사건(예: 차아진 `<재회>`, 백서희 `<선택의 기준>`)에서 400자를 살짝 초과하는 경향이 관찰됨. 후속 단계에서 후처리 검증 로직 또는 더 엄격한 few-shot 예시로 보완 가능.
- 일부 firstMessage에서 분위기·소품 디테일(시간 길이, 의상 소품, 짧은 환경 묘사)을 LLM이 자체 추가할 수 있다. 사실 차원의 할루시네이션은 아니지만 PoC 검수 시 확인 권장.
- LLM 출력 포맷이 `prompt.md` 규칙을 벗어나면 `md_to_json.py` 파서가 깨질 수 있다. 출력이 이상하면 먼저 `outputs/<이름>.md`의 헤딩 구조를 눈으로 확인.

## 다음 단계

- TavernAI v2 호환 JSON 변환 → `.png` character card 패키징 → 실제 RisuAI import 테스트
- 첫 변환 결과를 추가 few-shot으로 넣어 품질 부스트
- 지영님 트랙(avadot.com JSON)과 공유 가능한 중간 표현 정의
- 400자 캡 강제용 후처리 검증 또는 자동 압축 단계
- Notion API 직접 연동으로 입력 파이프라인 자동화
