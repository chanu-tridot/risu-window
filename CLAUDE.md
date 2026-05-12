# risu-window — RisuAI Windows 추출 운영 가이드

이 워크스페이스는 두 가지를 한다:
1. **RisuAI 로컬 설치본에서 캐릭터·preset 추출** (이 파일에 운영 노하우)
2. **작가 캐릭터 시트 → RisuAI native JSON 변환** (`character-converter/`)

## RisuAI 설치 위치 (Windows)

```
설치본: %LOCALAPPDATA%\RisuAI\RisuAI.exe
데이터: %APPDATA%\co.aiclient.risu\
  └── database\database.bin   # 캐릭터 + 글로벌 설정 (RISUSAVE 바이너리)
  └── assets\                  # 캐릭터 이미지
```

`database.bin` 포맷 사양·내부 구조는 `character-converter/docs/RisuAI-internals.md` 참조.

## 캐릭터 빠른 추출 (단일 캐릭터, PowerShell 한 세션)

```powershell
$path = "$env:APPDATA\co.aiclient.risu\database\database.bin"
$bytes = [System.IO.File]::ReadAllBytes($path)
$text  = [System.Text.Encoding]::UTF8.GetString($bytes)

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

$idx   = $text.IndexOf('"name":"캐릭터이름"')
$chunk = $text.Substring($idx, [Math]::Min(100000, $text.Length - $idx))

$name  = Get-Str $chunk 'name'
$desc  = Get-Str $chunk 'desc'
$first = Get-Str $chunk 'firstMessage'
$sys   = Get-Str $chunk 'systemPrompt'
$post  = Get-Str $chunk 'postHistoryInstructions'
# globalLore 는 depth tracking 필요 — character-converter/docs/RisuAI-internals.md 참조
```

## 전체 캐릭터 목록 확인

```powershell
$path = "$env:APPDATA\co.aiclient.risu\database\database.bin"
$text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($path))
[regex]::Matches($text, '"name":"([^"]+)","firstMessage"') | ForEach-Object { $_.Groups[1].Value }
```

## 추출 결과 → references/ 배치

추출한 캐릭터를 `character-converter/references/md/<이름>.md` + `character-converter/references/json/<이름>.json` 으로 저장하면 few-shot 또는 비교 자료로 즉시 사용 가능. 현재 references/ 에 9 캐릭터 (`hayan`, `kang-sieun`, `kitagawa-marin`, `meruru`, `mio`, `neta`, `ovento`, `seo-yunha`, `yeongyeong-family`).

## 알려진 운영 이슈

- **RisuAI 데스크탑 앱 ↔ Anthropic API CORS 오류**: 앱에서 Claude 직접 호출 불가. Reverse Proxy URL 설정 또는 Gemini API 사용. `references/default-preset.json` 의 `aiModel=gemini-3-flash-preview` 가 이 우회 흔적.
- **PowerShell 대괄호 문자열**: `[system]` 등 대괄호 포함 문자열은 단일 따옴표(`'`) 사용 필수. `AppendLine("...")` 안에서 `[...]` 는 타입 캐스트로 오해받음.
- **PowerShell 변수 세션 유지 불가**: `$global:` 변수는 도구 호출 간 유지 안 됨. 추출~저장을 같은 호출 블록 안에서 처리.

## 변환기 사용

작가 시트 → RisuAI JSON 변환은 `character-converter/` 폴더 안에서 작업. 자세한 사용법은 `character-converter/README.md` 참조.
