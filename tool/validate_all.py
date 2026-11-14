#!/usr/bin/env python3
"""Merge the split data files and validate the result with validate_questions.py.

The bank is stored in several JSON files (see manifest.json). This script builds
one merged file in a temp directory and runs the repo validator on it, so CI
still catches mojibake, broken question shapes and duplicates.
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    manifest = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
    merged = {}
    for name in manifest["files"]:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            print("missing data file: %s" % name)
            return 1
        data = json.load(open(path, encoding="utf-8"))
        if name == "meta.json":
            merged["meta"] = data
        else:
            # A section can be split across several files (science.json +
            # science_2.json), so merge per section key instead of replacing it.
            for key, value in data.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    dst = merged[key]
                    for g, item in value.items():
                        cur = dst.get(g)
                        if isinstance(cur, list) and isinstance(item, list):
                            dst[g] = cur + item
                        elif (isinstance(cur, dict) and isinstance(item, dict)
                              and isinstance(cur.get("qs"), list) and isinstance(item.get("qs"), list)):
                            cur["qs"] = cur["qs"] + item["qs"]
                        else:
                            dst[g] = item
                else:
                    merged[key] = value
    for key in ("science", "maths", "sst", "traditions"):
        if key not in merged:
            print("merged data has no '%s' section" % key)
            return 1
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "questions.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    return subprocess.call([sys.executable, os.path.join(ROOT, "tool", "validate_questions.py"), out])

if __name__ == "__main__":
    sys.exit(main())
