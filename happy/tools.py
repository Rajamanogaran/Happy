"""Deterministic offline utilities. No eval, subprocess, model, or network access."""

import ast
import base64
import collections
import csv
import difflib
import hashlib
import io
import json
import math
import operator
import re
from urllib.parse import parse_qs, urlsplit

TOOLS = [
    (
        "calculator",
        "Safe calculator",
        "Arithmetic with +, −, *, /, //, %, powers and parentheses.",
        "(125 * 4) / 10",
    ),
    (
        "json",
        "JSON formatter",
        "Validate and pretty-print JSON.",
        '{"hello":"Happy","local":true}',
    ),
    (
        "csv",
        "CSV to JSON",
        "Convert a CSV table with unique column headers into JSON.",
        "name,role\nHappy,Assistant",
    ),
    (
        "stats",
        "Text statistics",
        "Count words, characters, sentences and reading time.",
        "Paste your text here.",
    ),
    (
        "keywords",
        "Keyword extractor",
        "Find frequently used words; no semantic or AI analysis.",
        "Paste your notes here.",
    ),
    (
        "summary",
        "Extractive summary",
        "Select representative sentences from your text, without generating claims.",
        "Paste a longer article or notes here.",
    ),
    ("diff", "Text comparison", "Compare two texts line by line.", "Original text"),
    (
        "base64-encode",
        "Base64 encoder",
        "Encode UTF-8 text as Base64.",
        "Hello, Happy!",
    ),
    (
        "base64-decode",
        "Base64 decoder",
        "Decode Base64 into UTF-8 text.",
        "SGVsbG8sIEhhcHB5IQ==",
    ),
    (
        "hash",
        "SHA-256 checksum",
        "Compute a text checksum. This is not encryption.",
        "Text to fingerprint",
    ),
    (
        "url",
        "URL inspector",
        "Inspect URL components without making a network request.",
        "https://example.com/search?q=happy",
    ),
    (
        "deduplicate",
        "Deduplicate lines",
        "Remove repeated lines while preserving the first occurrence.",
        "one\ntwo\none",
    ),
]
CATALOG = [dict(id=i, name=n, description=d, example=e) for i, n, d, e in TOOLS]
STOP = set(
    "the and that this with from have were your about into are for not but you our can will".split()
)


def words(text):
    return [
        w
        for w in re.findall(r"\b\w{3,}\b", text.casefold())
        if w not in STOP and not w.isdigit()
    ]


def calculate(text):
    if len(text) > 500:
        raise ValueError("Expression must be under 500 characters.")
    tree = ast.parse(text, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("Expression is too complex.")
    operations = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            value = visit(node.operand) * (1 if isinstance(node.op, ast.UAdd) else -1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(b) > 100:
                raise ValueError("Exponent must be between -100 and 100.")
            value = operations[type(node.op)](a, b)
        else:
            raise ValueError(
                "Only numbers, parentheses, and arithmetic operators are allowed."
            )
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or abs(value) > 1e100
        ):
            raise ValueError("Result exceeds the supported numeric range.")
        return value

    return str(visit(tree.body))


def execute(tool, text, other=""):
    try:
        if tool == "calculator":
            return calculate(text)
        if tool == "json":
            return json.dumps(
                json.loads(
                    text,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError("Non-finite JSON numbers are not supported.")
                    ),
                ),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        if tool == "csv":
            rows = list(csv.reader(io.StringIO(text), strict=True))
            if (
                not rows
                or not rows[0]
                or any(not h.strip() for h in rows[0])
                or len(set(rows[0])) != len(rows[0])
            ):
                raise ValueError("CSV needs non-empty, unique column headers.")
            if any(len(r) != len(rows[0]) for r in rows[1:]):
                raise ValueError("Every CSV row must have the same number of columns.")
            return json.dumps(
                [dict(zip(rows[0], r)) for r in rows[1:]], ensure_ascii=False, indent=2
            )
        if tool == "stats":
            count = len(re.findall(r"\b\w+\b", text))
            return json.dumps(
                {
                    "words": count,
                    "characters": len(text),
                    "lines": len(text.splitlines()),
                    "sentences": len(re.findall(r"[^.!?]+[.!?]?", text.strip())),
                    "reading_minutes_at_200_wpm": round(count / 200, 2),
                },
                indent=2,
            )
        if tool == "keywords":
            return (
                "\n".join(
                    f"{word}: {count}"
                    for word, count in collections.Counter(words(text)).most_common(15)
                )
                or "No keywords found."
            )
        if tool == "summary":
            sentences = [
                s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()
            ]
            counts = collections.Counter(words(text))
            ranked = sorted(
                enumerate(sentences),
                key=lambda pair: (
                    sum(counts[w] for w in set(words(pair[1])))
                    / max(1, len(words(pair[1])))
                ),
                reverse=True,
            )[:3]
            return (
                "Extractive summary · sentences selected from your text (not AI-generated):\n\n"
                + "\n\n".join(s for _, s in sorted(ranked))
            )
        if tool == "diff":
            return (
                "\n".join(
                    difflib.unified_diff(
                        text.splitlines(),
                        other.splitlines(),
                        fromfile="Original",
                        tofile="Revised",
                        lineterm="",
                    )
                )
                or "The texts are identical."
            )
        if tool == "base64-encode":
            return base64.b64encode(text.encode()).decode()
        if tool == "base64-decode":
            return base64.b64decode(text, validate=True).decode("utf-8")
        if tool == "hash":
            return hashlib.sha256(text.encode()).hexdigest()
        if tool == "url":
            p = urlsplit(text)
            if not p.scheme or not p.netloc:
                raise ValueError("Enter an absolute URL, including its scheme.")
            return json.dumps(
                {
                    "scheme": p.scheme,
                    "hostname": p.hostname,
                    "port": p.port,
                    "path": p.path,
                    "query": parse_qs(p.query),
                    "fragment": p.fragment,
                },
                ensure_ascii=False,
                indent=2,
            )
        if tool == "deduplicate":
            return "\n".join(dict.fromkeys(text.splitlines()))
        raise ValueError("Unknown tool.")
    except (
        ArithmeticError,
        SyntaxError,
        UnicodeError,
        csv.Error,
        RecursionError,
    ) as exc:
        raise ValueError(f"Cannot process this input: {exc}") from exc
