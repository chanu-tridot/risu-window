#!/usr/bin/env python
"""Convert a writer's character sheet (.md) into a RisuAI-style character JSON.

Pipeline:
    input/<character>.md
        │
        ▼  Anthropic API (system=prompt.md + few-shot, user=<character sheet>)
        │
    output/<character>.md            Pass-1 LLM markdown (human-readable, team review)
        │
        ▼  merger.py (deterministic, reference-based, no LLM)
        │
    output/<character>.json          Canonical RisuAI `character` interface JSON
        │
        ▼  assembler.py (optional, --assemble flag)
        │
    output/<character>.assembled.json  LLM-ready messages[] (ready for chat API)

Usage:
    python main.py 백서희
    python main.py 백서희 --model sonnet
    python main.py 백서희 --assemble
    python main.py --all --assemble

The `<character>` argument is the filename in input/ (with or without `.md`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from merger import assemble_risu_json, parse_pass1_md
from assembler import _load_default_preset, assemble_messages

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PROMPT_PATH = ROOT / "prompt.md"
REFERENCES_DIR = ROOT / "references"
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"

# Anthropic model IDs. Opus is default — higher RisuAI-pattern fidelity.
# See CLAUDE.md global instructions for latest model IDs.
MODELS: dict[str, str] = {
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}
DEFAULT_MODEL_KEY = "opus"
MAX_TOKENS = 8000


def build_system_prompt() -> str:
    """Compose the system prompt: template + 2 few-shot references."""
    template = PROMPT_PATH.read_text(encoding="utf-8")
    neta = (REFERENCES_DIR / "md" / "neta.md").read_text(encoding="utf-8")
    marin = (REFERENCES_DIR / "md" / "kitagawa-marin.md").read_text(encoding="utf-8")
    return template.replace("{{NETA_EXAMPLE}}", neta).replace("{{MARIN_EXAMPLE}}", marin)


def resolve_input_path(name: str) -> Path:
    """Accept `백서희`, `백서희.md`, or a relative/absolute path."""
    p = Path(name)
    if p.is_file():
        return p
    if not name.endswith(".md"):
        name = f"{name}.md"
    candidate = INPUT_DIR / name
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"Input not found: {name}. Looked in cwd and {INPUT_DIR}/"
    )


def convert_one(input_path: Path, model_key: str, do_assemble: bool) -> None:
    if model_key not in MODELS:
        raise ValueError(f"Unknown model key {model_key!r}; choose from {list(MODELS)}")
    model_id = MODELS[model_key]

    sheet = input_path.read_text(encoding="utf-8")
    system_prompt = build_system_prompt()

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model_id,
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

    md_dir = OUTPUT_DIR / "md"
    json_dir = OUTPUT_DIR / "json"
    md_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    md_path = md_dir / f"{stem}.md"
    json_path = json_dir / f"{stem}.json"

    md_path.write_text(md_text, encoding="utf-8")

    # Canonical RisuAI character JSON via deterministic merger.
    parsed = parse_pass1_md(md_text)
    risu_data = assemble_risu_json(parsed)
    json_path.write_text(
        json.dumps(risu_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = (
        f"[{stem} / {model_key}] "
        f"in={response.usage.input_tokens}t "
        f"out={response.usage.output_tokens}t "
        f"-> md/{md_path.name}, json/{json_path.name} "
        f"(globalLore={len(risu_data['globalLore'])})"
    )

    if do_assemble:
        preset = _load_default_preset()
        assembled = assemble_messages(risu_data, preset, user_name="사용자")
        asm_path = json_dir / f"{stem}.assembled.json"
        asm_path.write_text(
            json.dumps(assembled, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary += f", json/{asm_path.name} (msgs={assembled['meta']['message_count']})"

    print(summary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "character",
        nargs="?",
        help="Character filename in input/ (with or without .md), or a path. Omit with --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every file matching input/*.md",
    )
    parser.add_argument(
        "--model",
        choices=sorted(MODELS),
        default=DEFAULT_MODEL_KEY,
        help=f"Anthropic model to use (default: {DEFAULT_MODEL_KEY}).",
    )
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="Also produce <character>.assembled.json (LLM-ready messages[] array).",
    )
    args = parser.parse_args()

    if args.all:
        files = sorted(INPUT_DIR.glob("*.md"))
        if not files:
            print(f"No inputs found in {INPUT_DIR}/", file=sys.stderr)
            return 1
        for path in files:
            convert_one(path, args.model, args.assemble)
        return 0

    if args.character is None:
        parser.error("provide a character name or use --all")
    input_path = resolve_input_path(args.character)
    convert_one(input_path, args.model, args.assemble)
    return 0


if __name__ == "__main__":
    sys.exit(main())
