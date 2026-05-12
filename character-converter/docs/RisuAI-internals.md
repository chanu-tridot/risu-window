# RisuAI 내부 자료 — DB 추출·포맷·슬롯 매핑

`references/` 에 새 RisuAI 캐릭터를 추가하거나, 변환기 출력이 RisuAI 앱과 어떻게 맞물리는지 이해하려는 사람을 위한 자료.

## RisuAI 설치 정보 (Windows)

- **설치 경로**: `%LOCALAPPDATA%\RisuAI\RisuAI.exe`
- **데이터 경로**: `%APPDATA%\co.aiclient.risu\`
  - `database/database.bin` — 전체 DB (캐릭터 + 글로벌 설정)
  - `assets/` — 캐릭터 이미지

## database.bin 포맷 (RISUSAVE)

커스텀 바이너리 포맷. 내부는 키-값 쌍으로 구성됨.

```
[RISUSAVE 헤더 8byte] [버전 2byte] [엔트리수 2byte]
→ "root" 키:   글로벌 설정 JSON (apiType, mainPrompt 등은 botPresets 배열 안에 있음)
→ "{chaId}" 키: 캐릭터별 JSON (name, desc, globalLore, firstMessage, ...)
```

**주의**: `mainPrompt` / `jailbreak` 는 root 최상위가 아니라 `botPresets[0]` 안에 있다.
파일 내 오프셋 `17541` 부근에서 실제 값이 시작 (오프셋 `71` 위치 것은 빈 값).

## 프롬프트 조립 순서 (formatingOrder 기본값)

RisuAI 가 챗 시 LLM 에 보내는 9-슬롯 직렬화 순서:

```
main → description → personaPrompt → chats → lastChat
     → jailbreak → lorebook → globalNote → authorNote
```

(맨 끝에 `postEverything` 슬롯이 자동 append 됨 — CoT·group instruction 용)

### 각 슬롯이 어디서 채워지는가

| 슬롯 | 소스 | 우리 변환기 |
|------|------|------------|
| `main` | `char.systemPrompt` (없으면 `botPresets[0].mainPrompt`) | character JSON `.systemPrompt` 는 빈 채 → 글로벌 폴백 |
| `description` | `db.descriptionPrefix` + `char.desc` + `char.personality` + `char.scenario` | Marin 패턴 — 모두 빈 채 |
| `personaPrompt` | 유저 페르소나 설정 | `assembler.py --persona-prompt` 로 주입 가능 |
| `chats` | 채팅 히스토리 + (chats[] 비면) `firstMessage` prepend | `firstMessage` 만 (fresh session 가정) |
| `lastChat` | 최근 user 메시지 (cull 보호용) | 비어 있음 (fresh session) |
| `jailbreak` | `botPresets[0].jailbreak` (토글 시) | `references/default-preset.json` 에서 박힘 |
| `lorebook` | `char.globalLore` 활성 엔트리 | 우리는 `alwaysActive=true` 만 통과 |
| `globalNote` | `char.replaceGlobalNote` 또는 `db.globalNote` | preset 의 globalNote (현재 빈 채) |
| `authorNote` | `char.postHistoryInstructions` 또는 `currentChat.note` | character JSON `.postHistoryInstructions` |

자세한 슬롯 빌더 로직은 RisuAI 소스 `src/ts/process/index.svelte.ts:317-1387` 참조.

## 캐릭터별 구조 패턴

같은 `character` 인터페이스를 다르게 채우는 두 가지 방식. references/ 에 둘 다 예시 있음.

### Pattern A — desc 집중형 (`references/md/neta.md`)
- 모든 캐릭터 정보가 `desc` 하나에 집약
- `globalLore` 가벼움 또는 없음
- 단순·직접적, 단일 시나리오용

### Pattern B — lorebook 분리형 (`references/md/kitagawa-marin.md`)
- `desc` 비어 있음
- 모든 정보가 `globalLore[0]` (alwaysActive=true, insertorder=400) 에
- `firstMessage` 가 `{{#if_pure}}` 매크로로 다중 시나리오·페르소나·언어 분기

**본 변환기는 Pattern B 를 선택** (이유는 `CLAUDE.md` "불변 사항" 1 참조).

## 새 캐릭터를 references/ 에 추가하기 (DB 추출 워크플로우)

자기 RisuAI 앱에 있는 캐릭터 카드를 references/ 에 가져오는 방법:

### 1. RisuAI 앱에서 캐릭터 임포트 후 PowerShell 추출

아래 스크립트를 **한 세션에서** 실행 (PowerShell 변수가 세션 간 유지 안 되므로 추출~저장을 하나의 블록으로):

```powershell
$path = "$env:APPDATA\co.aiclient.risu\database\database.bin"
$bytes = [System.IO.File]::ReadAllBytes($path)
$text = [System.Text.Encoding]::UTF8.GetString($bytes)

function Get-Str($chunk, $field) {
    $fIdx = $chunk.IndexOf("""$field"":""")
    if ($fIdx -lt 0) { return '' }
    $pos = $fIdx + $field.Length + 4
    $val = [System.Text.StringBuilder]::new()
    while ($pos -lt $chunk.Length) {
        $c = $chunk[$pos]
        if ($c -eq '\') {
            $n = $chunk[$pos+1]
            if ($n -eq 'n') { [void]$val.Append("`n") }
            elseif ($n -eq 't') { [void]$val.Append("`t") }
            elseif ($n -eq '"') { [void]$val.Append('"') }
            elseif ($n -eq '\') { [void]$val.Append('\') }
            else { [void]$val.Append($n) }
            $pos += 2; continue
        }
        if ($c -eq '"') { break }
        [void]$val.Append($c); $pos++
    }
    return $val.ToString().Trim()
}

# 캐릭터 이름으로 블록 찾기
$idx = $text.IndexOf('"name":"캐릭터이름"')
$chunk = $text.Substring($idx, [Math]::Min(100000, $text.Length - $idx))

# 17개 프롬프트 필드 추출
$desc  = Get-Str $chunk 'desc'
$first = Get-Str $chunk 'firstMessage'
$sys   = Get-Str $chunk 'systemPrompt'
$post  = Get-Str $chunk 'postHistoryInstructions'
# ... 기타

# globalLore 배열은 depth tracking 으로 끝 찾기
$lIdx = $chunk.IndexOf('"globalLore":[')
# (구현 생략 — _extract_prompts.py 같은 별도 스크립트 권장)

# 결과를 references/json/<이름>.json + references/md/<이름>.md 로 저장
```

### 2. 자신의 RisuAI 앱에 있는 전체 캐릭터 목록 확인

```powershell
$path = "$env:APPDATA\co.aiclient.risu\database\database.bin"
$text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($path))
[regex]::Matches($text, '"name":"([^"]+)","firstMessage"') | ForEach-Object { $_.Groups[1].Value }
```

### 3. 추출 결과 정리

- `.json` 은 RisuAI character 인터페이스 그대로 (17 프롬프트 필드 추출 후 저장)
- `.md` 는 사람이 읽기 좋게 섹션별 덤프 (Basic Info / Appearance / globalLore 엔트리 / firstMessage / 등)

기존 references/ 9 캐릭터가 이 형태로 정리되어 있으므로 그 구조 참조.

## 알려진 이슈

- **CORS 오류**: Claude(Anthropic) API 를 RisuAI 데스크탑 앱에서 **직접 호출** 시 발생.
  - 해결 1: Settings → Reverse Proxy URL 설정
  - 해결 2: Gemini API 사용 (사용자의 `references/default-preset.json` 보면 `aiModel=gemini-3-flash-preview` 인 이유)
  - 본 변환기(`character-converter/main.py`)는 데스크탑 앱이 아니라 Python CLI 이므로 직접 호출 OK.
- **PowerShell 문자열**: `[system]` 등 대괄호 포함 문자열은 단일 따옴표(`'`) 사용 필수.
  `AppendLine("...")` 안에서 `[...]` 는 타입 캐스트로 오해받음.
- **변수 세션 유지 불가**: `$global:` 변수는 PowerShell 도구 호출 간 유지 안 됨.
  추출과 저장을 반드시 같은 호출 블록 안에서 처리.

## 더 깊게 파볼 곳 (RisuAI 소스)

`workspace/risu-ai/risuai-source/` 가 로컬에 클론되어 있다면:

- `src/ts/storage/database.svelte.ts:1304-1458` — `character` 인터페이스 정의 (캐논 32+ 필드)
- `src/ts/storage/database.svelte.ts:1281-1302` — `loreBook` 인터페이스 (10 필수 필드)
- `src/ts/storage/database.svelte.ts:764-1239` — root `Database` 인터페이스 (글로벌 root)
- `src/ts/storage/defaultPrompts.ts` — `prebuiltPresets.OAI` 기본 mainPrompt/jailbreak 텍스트
- `src/ts/process/index.svelte.ts:317-1387` — `unformated` 슬롯 빌더 + formatingOrder 직렬화 본체
- `src/ts/process/scripts.ts` — `risuChatParser` 매크로 평가기 (`{{#if_pure}}`/`{{getvar::}}` 등)
- `src/ts/process/lorebook.svelte.ts` — lorebook v3 활성화 알고리즘 (키워드 매칭, depth, recursive scan)
