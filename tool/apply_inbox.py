#!/usr/bin/env python3
"""Apply small "inbox" drops to the big data files.

Why this exists
---------------
The bank is split into files of 1-3 MB (english.json, languages.json,
science.json, sst.json ...). Appending to one of them means rewriting the
whole file, and doing that through an API call needs the entire multi-megabyte
body inline. That is the step that keeps failing: a 2.5 MB payload cannot be
carried by a single tool call, and when the programmatic route is unavailable
the daily update dies with the data already generated.

So the daily update no longer rewrites the big files. It drops only the NEW
questions - a few dozen KB each - as JSON files under `inbox/`, and this
script (run by .github/workflows/apply-inbox.yml inside the repo) appends them
to the right list, updates meta.json and removes the drop files. The big files
are rewritten on the CI runner, where file size costs nothing.

Drop format
-----------
One JSON file per drop, any filename, processed in sorted order:

    {
      "target": "english.json",
      "date": "2026-11-05",
      "appends": [
        {"path": ["english", "grammar_5", "qs"], "items": [ {...}, ... ]},
        {"path": ["english", "vocabulary_5", "qs"], "items": [ {...}, ... ]}
      ]
    }

`path` is the list of keys from the top of `target` down to the list the items
are appended to. That one form covers every shape in the bank:

    ["maths", "5"]                      plain class list
    ["sst", "7"]                        plain class list
    ["science", "physics_11", "qs"]     grouped section
    ["traditions", "values", "qs"]      values & religion
    ["english", "grammar_5", "qs"]      english / languages groups

Every item must already be in the bank's question shape:

    {"q": {"en": "...", "hi": "..."},
     "o": {"en": ["a","b","c","d"], "hi": ["a","b","c","d"]},
     "a": 0,
     "e": {"en": "...", "hi": "..."}}

Checks run here, so a bad drop can never reach the bank
-------------------------------------------------------
  * the target file must be listed in manifest.json
  * the path must end at an existing list
  * q/o/a/e present, en and hi non-empty, 4 options in both languages,
    a an integer 0..3, Hindi text in Devanagari, no mojibake
  * no item may repeat an English question already in that file (compared
    after normalisation) or another item in the same drop
  * meta.json is updated: last_updated (latest drop date) and last_added
    (number of questions appended by this run)

The workflow then runs tool/validate_all.py on the merged bank before it
commits, so a drop that would break the bank fails the run instead of
publishing.

Usage
-----
    python3 tool/apply_inbox.py             # apply every inbox/*.json
    python3 tool/apply_inbox.py --check     # dry run, report only
    python3 tool/apply_inbox.py --inbox DIR # use another drop directory

Exit codes: 0 = applied (or nothing to do), 1 = a drop was rejected and no
data file was changed.
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOJIBAKE_MARKERS = ("Ã", "Â", "à¤", "à¥", "â€", "\ufffd")
DEVANAGARI = re.compile("[\u0900-\u097F]")
SIZE_LIMIT = 3 * 1024 * 1024  # the bank splits a file past ~3 MB


def norm(text):
    """Same normalisation as tool/validate_questions.py."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def load(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("%s starts with a UTF-8 BOM" % path)
    return json.loads(raw.decode("utf-8"))


def dump(path, data, compact=True):
    """Write UTF-8, no BOM, no trailing newline.

    Compact separators match how the data files are already stored, so a diff
    shows only the questions that were added.
    """
    seps = (",", ":") if compact else (", ", ": ")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=seps)


def walk_questions(node):
    """Yield every question object found anywhere in a data file."""
    if isinstance(node, dict):
        if "q" in node and "o" in node and "a" in node:
            yield node
        else:
            for value in node.values():
                yield from walk_questions(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_questions(value)


def check_item(item, where):
    """Return a list of problems with one question object."""
    problems = []
    if not isinstance(item, dict):
        return ["%s: item is not an object" % where]
    for key in ("q", "o", "a", "e"):
        if key not in item:
            return ["%s: missing '%s'" % (where, key)]

    for key in ("q", "e"):
        block = item[key]
        if not isinstance(block, dict):
            problems.append("%s: '%s' is not an object" % (where, key))
            continue
        for lang in ("en", "hi"):
            value = block.get(lang)
            if not isinstance(value, str) or not value.strip():
                problems.append("%s: '%s' has no %s text" % (where, key, lang))

    opts = item.get("o")
    if not isinstance(opts, dict):
        problems.append("%s: 'o' is not an object" % where)
    else:
        for lang in ("en", "hi"):
            arr = opts.get(lang)
            if not isinstance(arr, list):
                problems.append("%s: 'o' has no %s option list" % (where, lang))
            elif len(arr) != 4:
                problems.append("%s: %s has %d options, expected 4"
                                % (where, lang, len(arr)))
            elif any(not isinstance(o, str) or not o.strip() for o in arr):
                problems.append("%s: empty %s option" % (where, lang))

    answer = item.get("a")
    if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer <= 3:
        problems.append("%s: answer index %r is not an integer 0-3" % (where, answer))

    hi = (item.get("q") or {}).get("hi", "") if isinstance(item.get("q"), dict) else ""
    if isinstance(hi, str) and hi.strip() and not DEVANAGARI.search(hi):
        problems.append("%s: Hindi question text has no Devanagari" % where)

    text = json.dumps(item, ensure_ascii=False)
    for marker in MOJIBAKE_MARKERS:
        if marker in text:
            problems.append("%s: mojibake text (contains %r)" % (where, marker))
            break
    return problems


def resolve(data, path, where):
    """Walk `path` inside `data` and return the list it points at."""
    node = data
    for depth, key in enumerate(path):
        if isinstance(node, dict):
            if key not in node:
                raise ValueError("%s: path %r has no key %r" % (where, path, key))
            node = node[key]
        elif isinstance(node, list):
            raise ValueError("%s: path %r expected a key at %r, found a list"
                             % (where, path, key))
        else:
            raise ValueError("%s: path %r cannot descend into %r"
                             % (where, path, key))
    if not isinstance(node, list):
        raise ValueError("%s: path %r does not end at a list" % (where, path))
    return node


def today_ist():
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(tz).strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inbox", default=os.path.join(ROOT, "inbox"))
    parser.add_argument("--check", action="store_true",
                        help="report what would happen, change nothing")
    args = parser.parse_args()

    manifest = load(os.path.join(ROOT, "manifest.json"))
    allowed = set(manifest.get("files", []))

    drops = sorted(glob.glob(os.path.join(args.inbox, "*.json")))
    drops = [d for d in drops if os.path.basename(d) != "manifest.json"]
    if not drops:
        print("inbox is empty - nothing to do")
        return 0

    # One working copy of each target file, so several drops can hit the same
    # file in a single run.
    loaded = {}
    appended = {}
    dates = []
    problems = []

    def get_target(name):
        if name not in loaded:
            src = os.path.join(ROOT, name)
            if not os.path.exists(src):
                raise ValueError("target %s does not exist in the repo" % name)
            loaded[name] = load(src)
        return loaded[name]

    for drop_path in drops:
        where = os.path.basename(drop_path)
        try:
            drop = load(drop_path)
        except Exception as exc:
            problems.append("%s: not readable JSON (%s)" % (where, exc))
            continue

        target = drop.get("target")
        if target in ("meta.json", "manifest.json"):
            problems.append("%s: %r is maintained by this script, not by drops"
                            % (where, target))
            continue
        if target not in allowed:
            problems.append("%s: target %r is not in manifest.json" % (where, target))
            continue
        date = drop.get("date")
        if isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            dates.append(date)

        data = get_target(target)
        seen = {norm(q.get("q", {}).get("en", "")) for q in walk_questions(data)}

        appends = drop.get("appends")
        if not isinstance(appends, list) or not appends:
            problems.append("%s: no 'appends' list" % where)
            continue

        for index, block in enumerate(appends):
            tag = "%s.appends[%d]" % (where, index)
            path = block.get("path")
            if not isinstance(path, list) or not path or not all(isinstance(p, str) for p in path):
                problems.append("%s: 'path' must be a non-empty list of keys" % tag)
                continue
            try:
                bucket = resolve(data, path, tag)
            except ValueError as exc:
                problems.append(str(exc))
                continue
            items = block.get("items")
            if not isinstance(items, list) or not items:
                problems.append("%s: 'items' must be a non-empty list" % tag)
                continue
            for position, item in enumerate(items):
                item_where = "%s.items[%d]" % (tag, position)
                bad = check_item(item, item_where)
                if bad:
                    problems.extend(bad)
                    continue
                key = norm(item["q"]["en"])
                if key in seen:
                    problems.append("%s: repeats a question already in %s: %s"
                                    % (item_where, target, item["q"]["en"][:70]))
                    continue
                seen.add(key)
                bucket.append(item)
                appended[target] = appended.get(target, 0) + 1

    if problems:
        print("REJECTED - no data file was changed")
        for problem in problems:
            print("  " + problem)
        return 1

    total = sum(appended.values())
    print("appended %d question(s)" % total)
    for target in sorted(appended):
        print("  %s: +%d" % (target, appended[target]))

    # meta.json
    meta = loaded.get("meta.json")
    if meta is None:
        meta_path = os.path.join(ROOT, "meta.json")
        meta = load(meta_path)
        loaded["meta.json"] = meta
    meta["last_updated"] = max(dates) if dates else today_ist()
    meta["last_added"] = total
    print("meta.json: last_updated=%s last_added=%d"
          % (meta["last_updated"], meta["last_added"]))

    if args.check:
        print("--check: nothing written")
        return 0

    for target, data in loaded.items():
        path = os.path.join(ROOT, target)
        dump(path, data, compact=(target != "meta.json"))
        size = os.path.getsize(path)
        if target not in ("meta.json", "manifest.json") and size > SIZE_LIMIT:
            print("warning: %s is %.2f MB - the size rule says split it"
                  % (target, size / (1024.0 * 1024.0)))

    for drop_path in drops:
        os.remove(drop_path)
        print("consumed %s" % os.path.basename(drop_path))

    print("done - now run: python3 tool/validate_all.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
