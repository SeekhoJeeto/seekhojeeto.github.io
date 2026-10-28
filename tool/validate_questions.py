#!/usr/bin/env python3
"""Validate questions.json before it goes live.

This guards the two mistakes we have actually hit in this repo:

  1. Indic text stored in the wrong encoding. If a file is written or
     re-encoded wrongly, Hindi turns into mojibake such as
     "à¤…à¤°à¤¾à¤µà¤²à¥€" instead of "अरावली". The file must decode as
     strict UTF-8 and must not contain the tell-tale mojibake sequences.

  2. A daily batch that breaks the question shape: a missing en/hi, the
     wrong number of options, an answer index out of range, or a question
     that repeats one already in the bank.

Run it after every update:

    python3 tool/validate_questions.py questions.json

Exit code 0 = the bank is good, 1 = problems (printed one per line).
Standard library only, so it runs anywhere.
"""

import json
import re
import sys

MOJIBAKE_MARKERS = ("Ã", "Â", "à¤", "à¥", "â€", "\ufffd")
CLASSES = [str(c) for c in range(5, 13)]
REQUIRED_TOP = ("science", "maths", "traditions", "meta")
CLASSED_SECTIONS = ("science", "maths", "sst")
TEXT_SECTIONS = CLASSED_SECTIONS + ("traditions",)

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def norm(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def walk_strings(node, path):
    """Yield (path, string) for every string in the structure."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, "%s[%d]" % (path, i))


def check_question(q, where, seen):
    if not isinstance(q, dict):
        err("%s: question is not an object" % where)
        return
    for key in ("q", "o", "a", "e"):
        if key not in q:
            err("%s: missing '%s'" % (where, key))
            return

    for key in ("q", "e"):
        block = q[key]
        if not isinstance(block, dict):
            err("%s: '%s' is not an object" % (where, key))
            continue
        for lang in ("en", "hi"):
            val = block.get(lang)
            if not isinstance(val, str) or not val.strip():
                err("%s: '%s' has no %s text" % (where, key, lang))

    opts = q.get("o")
    if not isinstance(opts, dict):
        err("%s: 'o' is not an object" % where)
        return
    for lang in ("en", "hi"):
        if not isinstance(opts.get(lang), list):
            err("%s: 'o' has no %s option list" % (where, lang))
            return
    lengths = {lang: len(v) for lang, v in opts.items() if isinstance(v, list)}
    if len(set(lengths.values())) != 1:
        err("%s: option counts differ between languages: %s" % (where, lengths))
    count = lengths.get("en", 0)
    if count != 4:
        err("%s: expected 4 options, found %d" % (where, count))
    for lang, arr in opts.items():
        if isinstance(arr, list) and any(not isinstance(o, str) or not o.strip() for o in arr):
            err("%s: empty option text in %s" % (where, lang))

    a = q.get("a")
    if not isinstance(a, int) or isinstance(a, bool) or not 0 <= a < max(count, 1):
        err("%s: answer index %r is out of range" % (where, a))

    text = (q.get("q") or {}).get("en", "")
    if isinstance(text, str) and text.strip():
        key = norm(text)
        if key in seen:
            err("%s: duplicate question, same as %s: %s" % (where, seen[key], text))
        else:
            seen[key] = where


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "questions.json"

    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        print("%s is not valid UTF-8: %s" % (path, exc))
        print("Rewrite it with: json.dump(data, f, ensure_ascii=False, indent=1)")
        return 1

    if text.startswith("\ufeff"):
        err("file starts with a UTF-8 BOM; save it without one")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print("%s is not valid JSON: %s" % (path, exc))
        return 1

    if not isinstance(data, dict):
        print("%s: top level must be an object" % path)
        return 1

    for key in REQUIRED_TOP:
        if key not in data:
            err("top level is missing '%s'" % key)

    # 1) encoding / mojibake
    for section in TEXT_SECTIONS:
        if section not in data:
            continue
        for where, value in walk_strings(data[section], section):
            for marker in MOJIBAKE_MARKERS:
                if marker in value:
                    err("%s: mojibake text (contains %r): %s" % (where, marker, value[:60]))
                    break

    # 2) shape
    seen = {}
    totals = {}
    for section in CLASSED_SECTIONS:
        if section not in data:
            if section == "sst":
                continue
            continue
        block = data[section]
        if not isinstance(block, dict):
            err("%s: must be an object of classes" % section)
            continue
        count = 0
        for cls in CLASSES:
            arr = block.get(cls)
            if not isinstance(arr, list) or not arr:
                err("%s.%s: missing or empty class list" % (section, cls))
                continue
            for i, q in enumerate(arr):
                check_question(q, "%s.%s[%d]" % (section, cls, i), seen)
            count += len(arr)
        totals[section] = count

    traditions = data.get("traditions")
    if isinstance(traditions, dict):
        count = 0
        for cat, block in traditions.items():
            if not isinstance(block, dict) or not isinstance(block.get("qs"), list):
                err("traditions.%s: missing 'qs' list" % cat)
                continue
            name = block.get("name")
            if not isinstance(name, dict) or not name.get("en"):
                err("traditions.%s: missing name.en" % cat)
            for i, q in enumerate(block["qs"]):
                check_question(q, "traditions.%s[%d]" % (cat, i), seen)
            count += len(block["qs"])
        totals["traditions"] = count
    elif "traditions" in data:
        err("traditions: must be an object of categories")

    meta = data.get("meta")
    if isinstance(meta, dict):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(meta.get("last_updated", ""))):
            err("meta.last_updated must look like YYYY-MM-DD")
        if not isinstance(meta.get("last_added"), int):
            err("meta.last_added must be an integer")
    elif "meta" in data:
        err("meta: must be an object")

    for w in warnings:
        print("warning: %s" % w)

    if errors:
        for e in errors:
            print("error: %s" % e)
        print("\n%d problem(s) found in %s" % (len(errors), path))
        return 1

    summary = ", ".join("%s %d" % (k, v) for k, v in totals.items())
    print("OK: %s is valid UTF-8 JSON (%s), %d questions in total."
          % (path, summary, sum(totals.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
