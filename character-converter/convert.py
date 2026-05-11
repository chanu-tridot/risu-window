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
from dotenv import load_dotenv

from md_to_json import parse_md_to_json

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
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
