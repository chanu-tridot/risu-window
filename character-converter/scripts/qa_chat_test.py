"""Live LLM chat test against assembled messages — does the character actually work?

For each character's assembled.json:
1. Load messages[]
2. Append a context-appropriate user reply
3. Call Anthropic API (no system prompt — first message IS the system instructions)
4. Save the reply + print summary

This is the end-to-end validation: writer input → Risu shape → LLM chat → in-character reply.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

MODEL = "claude-opus-4-7"
MAX_TOKENS = 800

# Context-appropriate first user replies to each firstMessage scene.
USER_REPLIES = {
    # 백서희: "…너, 이름이 뭐야" 라고 물어본 직후
    "백서희": "(서희를 가만히 본다.) … 김호진. 그쪽은요?",
    # 차아진: 흥미로운 시선만 남기고 매니저와 함께 떠나는 직후
    "차아진": "(돌아서 가는 그녀의 뒷모습을 끝까지 본다. 손에 든 쇼핑백을 다시 고쳐 들고, 천천히 반대 방향으로 걷기 시작한다.)",
    # 이연: 윙크하며 '쉿, 비밀인데' 한 직후
    "이연":   "(시선을 마주친 채 잠시 침묵.) … 비밀, 지킬게요. 근데, 진짜 괜찮으신 거 맞아요?",
}


def run_chat_test(char_name: str) -> dict:
    path = ROOT / "outputs" / f"{char_name}.opus.assembled.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    messages = data["messages"]

    # Anthropic API expects a top-level system prompt + alternating user/assistant.
    # Our slot 0 is a system message (mainPrompt). Split it out.
    system_blocks = []
    chat_messages = []
    for m in messages:
        if m["role"] == "system":
            system_blocks.append(m["content"])
        else:
            chat_messages.append(m)

    # Append user reply
    user_reply = USER_REPLIES[char_name]
    chat_messages.append({"role": "user", "content": user_reply})

    # Combine all system messages into one (mainPrompt + jailbreak + lorebook).
    # In real RisuAI, these are kept as separate `system` role messages, but
    # Anthropic API takes a single `system` param + a list of chat messages.
    system_text = "\n\n---\n\n".join(system_blocks)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_text,
        messages=chat_messages,
    )
    reply = response.content[0].text

    return {
        "char": char_name,
        "user_reply": user_reply,
        "char_reply": reply,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "system_chars": len(system_text),
        "chat_msg_count": len(chat_messages),
    }


def main() -> int:
    results = {}
    for c in ["백서희", "차아진", "이연"]:
        print(f"=== {c} chat test ===", flush=True)
        r = run_chat_test(c)
        results[c] = r
        print(f"  in={r['input_tokens']}t out={r['output_tokens']}t system={r['system_chars']}chars")
        print(f"  user: {r['user_reply']}")
        print(f"  reply ({len(r['char_reply'])} chars):")
        for line in r['char_reply'].split('\n'):
            print(f"    {line}")
        print()

    # Save the full results for the QA report
    out_path = ROOT / ".." / ".gstack" / "qa-reports" / "chat-test-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
