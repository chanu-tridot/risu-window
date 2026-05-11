# risu-window

RisuAI 캐릭터 프롬프트 분석 워크스페이스.
RisuAI 로컬 설치본의 DB에서 캐릭터별 프롬프트 데이터를 추출하고 마크다운으로 정리한다.

---

## 디렉토리 구조

```
risu-window/
├── CLAUDE.md              # 이 파일
├── RisuAI_setup.exe       # 설치파일 (v2026.4.181)
├── risuai.msi             # 깨진 파일 — 사용 불가
├── global-settings.md     # 글로벌 프롬프트 설정 (mainPrompt, jailbreak)
├── neta.md                # 네타 캐릭터 프롬프트 분석
└── kitagawa-marin.md      # 키타가와 마린 캐릭터 프롬프트 분석
```

---

## RisuAI 설치 정보

- **설치 경로**: `%LOCALAPPDATA%\RisuAI\RisuAI.exe`
- **데이터 경로**: `%APPDATA%\co.aiclient.risu\`
  - `database/database.bin` — 전체 DB (캐릭터 + 설정)
  - `assets/` — 캐릭터 이미지

---

## database.bin 포맷

`RISUSAVE` 커스텀 바이너리 포맷. 내부는 키-값 쌍으로 구성된다.

```
[RISUSAVE 헤더 8byte] [버전 2byte] [엔트리수 2byte]
→ "root" 키: 글로벌 설정 JSON (apiType, mainPrompt 등은 botPresets 배열 안에 있음)
→ "{chaId}" 키: 캐릭터별 JSON
```

**주의**: `mainPrompt`/`jailbreak`는 최상위가 아니라 `botPresets[0]` 안에 있다.
파일 내 오프셋 `17541` 부근에서 실제 값이 시작된다 (오프셋 `71`의 것은 빈 값).

---

## 프롬프트 조립 순서 (formatingOrder 기본값)

```
main → description → personaPrompt → chats → lastChat → jailbreak → lorebook → globalNote → authorNote
```

### 각 슬롯 매핑

| 슬롯 | 소스 |
|------|------|
| main | `char.systemPrompt` (없으면 `botPresets[0].mainPrompt`) |
| description | `db.descriptionPrefix` + `char.desc` + `char.personality` + `char.scenario` |
| personaPrompt | 유저 페르소나 설정 |
| chats | 채팅 히스토리 |
| jailbreak | `botPresets[0].jailbreak` (토글 시) |
| lorebook | `char.globalLore` 활성 엔트리 |
| authorNote | `char.postHistoryInstructions` |

---

## 캐릭터 추출 워크플로우

### 새 캐릭터 추가 시

1. RisuAI에서 캐릭터 임포트
2. 아래 PowerShell 스크립트를 **한 세션에서** 실행 (변수가 세션 간 유지되지 않으므로 추출~저장을 하나의 블록으로 처리)
3. `캐릭터이름.md` 파일로 저장

### 추출 스크립트 패턴

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

# 필드 추출
$desc  = Get-Str $chunk 'desc'
$first = Get-Str $chunk 'firstMessage'
$sys   = Get-Str $chunk 'systemPrompt'
$post  = Get-Str $chunk 'postHistoryInstructions'

# globalLore 추출 (로어북 있는 캐릭터)
$lIdx = $chunk.IndexOf('"globalLore":[')
# ... depth tracking으로 배열 끝 찾기
```

### 전체 캐릭터 목록 확인

```powershell
$path = "$env:APPDATA\co.aiclient.risu\database\database.bin"
$text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($path))
[regex]::Matches($text, '"name":"([^"]+)","firstMessage"') | ForEach-Object { $_.Groups[1].Value }
```

---

## 캐릭터별 구조 패턴

### 패턴 A — desc 집중형 (네타)
모든 캐릭터 정보가 `desc` 하나에 집약. 단순하고 직접적.

### 패턴 B — lorebook 분리형 (Kitagawa Marin)
`desc`는 비어있고 `globalLore` 엔트리에 정보 분산.
`firstMessage`가 조건부 템플릿(`{{#if_pure}}`)으로 다중 시나리오를 하나의 필드에 구현.

---

## 알려진 이슈

- **CORS 오류**: Claude(Anthropic) API를 데스크탑 앱에서 직접 호출 시 발생.
  → 해결: Settings → Reverse Proxy URL 설정 또는 Gemini API 사용
- **PowerShell 문자열**: `[system]` 등 대괄호 포함 문자열은 단일 따옴표(`'`) 사용 필수.
  `AppendLine("...")` 안에서 `[...]`는 타입 캐스트로 오해받음.
- **변수 세션 유지 불가**: `$global:` 변수는 PowerShell 도구 호출 간 유지되지 않음.
  추출과 저장을 반드시 같은 호출 블록 안에서 처리.
