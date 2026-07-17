#!/usr/bin/env python3
"""Render a Claude Code session transcript (JSONL) to a verbatim Markdown file.

Usage:
    render_transcript.py OUTPUT.md [SESSION_JSONL]

If SESSION_JSONL is omitted, the current session is resolved from the
CLAUDE_CODE_SESSION_ID environment variable by globbing
~/.claude/projects/*/<id>.jsonl. This is the transcript Claude Code writes as
the conversation happens, so it is a true verbatim record — unlike a summary
reconstructed from context, it survives compaction.

Main-thread messages only: subagent sidechains (isSidechain=true) are skipped so
the file is the human<->assistant conversation, not every subagent's internal loop.
Nothing is truncated — this is meant to be complete.
"""
import glob
import json
import os
import sys


def resolve_jsonl(explicit):
    if explicit:
        return explicit
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        sys.exit("No SESSION_JSONL given and CLAUDE_CODE_SESSION_ID is unset.")
    matches = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    if not matches:
        sys.exit(f"Could not find transcript for session {sid}.")
    return matches[0]


def render_text(block):
    return block.get("text", "")


def render_tool_use(block):
    name = block.get("name", "tool")
    inp = block.get("input", {})
    try:
        pretty = json.dumps(inp, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        pretty = str(inp)
    return f"**⚙️ Tool call: `{name}`**\n\n```json\n{pretty}\n```"


def _result_to_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                parts.append(b.get("text", "") if b.get("type") == "text" else json.dumps(b, ensure_ascii=False))
            else:
                parts.append(str(b))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False)


def render_tool_result(block):
    text = _result_to_text(block.get("content", ""))
    return f"**↳ Tool result**\n\n```\n{text}\n```"


def render_thinking(block):
    text = block.get("thinking", "") or block.get("text", "")
    return f"<details>\n<summary>💭 thinking</summary>\n\n{text}\n\n</details>"


def render_message(record):
    """Return a markdown chunk for one user/assistant record, or '' to skip."""
    if record.get("type") not in ("user", "assistant"):
        return ""
    if record.get("isSidechain"):
        return ""
    msg = record.get("message")
    if not isinstance(msg, dict):
        return ""
    role = msg.get("role", record.get("type"))
    content = msg.get("content")
    ts = record.get("timestamp", "")

    # A user record carrying only tool_result blocks is a tool response, not a human turn.
    blocks = content if isinstance(content, list) else None
    only_tool_results = (
        blocks is not None
        and blocks
        and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks)
    )

    if role == "user":
        heading = "### ↳ Tool result" if only_tool_results else f"### 🧑 User · {ts}"
    else:
        heading = f"### 🤖 Assistant · {ts}"

    pieces = []
    if isinstance(content, str):
        pieces.append(content)
    elif isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                pieces.append(str(b))
                continue
            bt = b.get("type")
            if bt == "text":
                pieces.append(render_text(b))
            elif bt == "thinking":
                pieces.append(render_thinking(b))
            elif bt == "tool_use":
                pieces.append(render_tool_use(b))
            elif bt == "tool_result":
                pieces.append(render_tool_result(b))
            else:
                pieces.append(f"```json\n{json.dumps(b, ensure_ascii=False)}\n```")
    body = "\n\n".join(p for p in pieces if p and p.strip())
    if not body.strip():
        return ""
    # For pure tool-result carriers we already emitted the result block; drop the double heading.
    if only_tool_results:
        return body
    return f"{heading}\n\n{body}"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out_path = sys.argv[1]
    jsonl = resolve_jsonl(sys.argv[2] if len(sys.argv) > 2 else None)

    chunks = []
    with open(jsonl, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunk = render_message(record)
            if chunk:
                chunks.append(chunk)

    header = (
        f"# Session transcript\n\n"
        f"Verbatim record rendered from `{os.path.basename(jsonl)}`.\n\n"
        f"---\n"
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header + "\n" + "\n\n".join(chunks) + "\n")
    print(f"Wrote {out_path} ({len(chunks)} messages from {os.path.basename(jsonl)})")


if __name__ == "__main__":
    main()
