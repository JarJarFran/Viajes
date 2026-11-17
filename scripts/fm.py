"""Frontmatter IO: parse a node file and write its frontmatter back in one canonical form.

A node file is `---\n<yaml>\n---\n<markdown body>`. Files without a leading `---` are not nodes
(index READMEs). `dump()` is the single writer used by sync/log so that every node has the same
key order and formatting, which keeps diffs small and makes `sync.py --check` meaningful.
"""
import json
import re
from datetime import date, datetime

import yaml

FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
FLOW_ITEM_MAX = 110  # list-of-dict items shorter than this are written on one line


def parse(text):
    """Return (fm, body, error). fm is None (and error None) for files without frontmatter."""
    if not text.startswith("---"):
        return None, text, None
    m = FM_RE.match(text)
    if not m:
        return None, text, "frontmatter is not closed with a '---' line"
    body = text[m.end():]
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 2})" if mark else ""
        return None, body, f"invalid YAML frontmatter{where}: {getattr(e, 'problem', None) or e}"
    if not isinstance(fm, dict):
        return None, body, "frontmatter is not a mapping"
    return fm, body, None


def _scalar(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str) and ("\n" in v or v != v.strip()):
        return json.dumps(v, ensure_ascii=False)
    out = yaml.safe_dump(v, allow_unicode=True, default_flow_style=True, width=10**9, sort_keys=False).strip()
    if out.endswith("..."):
        out = out[:-3].strip()
    return out


def _key(k):
    """Keys like on/off/yes/no would be read back as booleans by YAML 1.1: quote them."""
    return _scalar(str(k))


def _flow(v):
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_key(k)}: {_flow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    return _scalar(v)


def _emit(key, v, indent=""):
    key = _key(key)
    if isinstance(v, list) and v and any(isinstance(x, dict) for x in v):
        lines = [f"{indent}{key}:"]
        for item in v:
            flow = _flow(item)
            if not isinstance(item, dict) or len(flow) <= FLOW_ITEM_MAX:
                lines.append(f"{indent}  - {flow}")
                continue
            for i, (k, x) in enumerate(item.items()):
                sub = _emit(k, x, indent + "    ")
                if i == 0:
                    sub = indent + "  - " + sub[len(indent) + 4:]
                lines.append(sub)
        return "\n".join(lines)
    if isinstance(v, dict) and v:
        return "\n".join([f"{indent}{key}:"] + [_emit(k, x, indent + "  ") for k, x in v.items()])
    return f"{indent}{key}: {_flow(v)}"


def dump(fm):
    """Serialize an (ordered) frontmatter dict. Keys starting with '_' are skipped."""
    return "\n".join(_emit(k, v) for k, v in fm.items() if not str(k).startswith("_"))


def render(fm, body):
    return "---\n" + dump(fm) + "\n---\n" + body
