#!/usr/bin/env python3
"""Build one test paper per class for a subject and append it to tests.json.

Why this exists
---------------
The daily update grows the question bank. This script turns that bank into a
test series: on each run it picks a fresh paper (25 questions by default) for
every class of the day's subject and appends the papers to tests.json. Papers
are self-contained - the questions are copied in - so the app never has to
resolve an index into the bank, and papers stay stable when the bank grows.

Usage
-----
    python3 tool/build_tests.py --subject science --date 2026-11-15

    --subject   science | maths | sst | gk | computer | english | hindi | values
    --date      YYYY-MM-DD (default: today, IST)
    --per-class questions per paper (default 25)
    --out       data file to append to (default tests.json)

Selection
---------
Only the most recently appended questions of a group are used, so the paper
follows the newest material, and the correct-answer index is balanced across
the paper. Nothing random: the same date + subject + class always gives the
same paper, so a re-run is idempotent (a paper whose id already exists is
skipped).
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSES = [str(c) for c in range(5, 13)]
# How far back into a group we may look for candidates.
RECENT = 500
# Split for the language subjects, mirroring the 50/30/20 the bank is built on.
LANG_SPLIT = {"grammar": 0.48, "vocabulary": 0.32, "literature": 0.20}


def load_merged():
    """Merge the files listed in manifest.json the same way the app does."""
    manifest = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
    merged = {}
    for name in manifest["files"]:
        if name == "meta.json":
            continue
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        data = json.load(open(path, encoding="utf-8"))
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
    return merged


def group_qs(section, name):
    """Return the question list of one group, plain list or {name, qs}."""
    group = (section or {}).get(name)
    if isinstance(group, list):
        return group
    if isinstance(group, dict) and isinstance(group.get("qs"), list):
        return group["qs"]
    return []


def usable(q):
    if not isinstance(q, dict):
        return False
    o = q.get("o") or {}
    return (isinstance(o.get("en"), list) and len(o["en"]) == 4
            and isinstance(o.get("hi"), list) and len(o["hi"]) == 4
            and isinstance(q.get("a"), int) and 0 <= q["a"] <= 3
            and isinstance((q.get("q") or {}).get("en"), str))


def norm(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def pool(section, names, limit=RECENT):
    """Recent usable questions from one or more groups, newest last."""
    out = []
    for name in names:
        qs = [q for q in group_qs(section, name) if usable(q)]
        out.extend(qs[-limit:])
    return out


def build_paper(questions, per_class, seed):
    """Pick per_class questions with a balanced correct-answer index."""
    rng = random.Random(seed)
    buckets = {i: [] for i in range(4)}
    seen = set()
    for q in questions:
        key = norm(q["q"]["en"])
        if key in seen:
            continue
        seen.add(key)
        buckets[q["a"]].append(q)
    for b in buckets.values():
        rng.shuffle(b)
    quota = [per_class // 4] * 4
    for i in range(per_class % 4):
        quota[i] += 1
    picked = []
    for idx in range(4):
        picked.extend(buckets[idx][:quota[idx]])
    if len(picked) < per_class:
        # Not enough questions for a balanced paper: top up from the leftovers.
        taken = {id(q) for q in picked}
        rest = [q for q in questions if id(q) not in taken]
        rng.shuffle(rest)
        picked.extend(rest[:per_class - len(picked)])
    rng.shuffle(picked)
    return picked[:per_class]


def subject_pools(merged, subject):
    """{class_key: (questions, title_en, title_hi)} for one subject."""
    out = {}
    if subject == "values":
        section = merged.get("traditions") or {}
        questions = pool(section, list(section.keys()))
        out["all"] = (questions, "Values & Religion Test", "मूल्य एवं धर्म टेस्ट")
        return out

    if subject in ("english", "hindi"):
        section = merged.get(subject) or {}
        for cls in CLASSES:
            questions = []
            for part, share in LANG_SPLIT.items():
                part_pool = pool(section, ["%s_%s" % (part, cls)], limit=300)
                want = max(1, int(round(25 * share)))
                questions.extend(part_pool[-want * 8:] if part_pool else [])
            label = "English Test" if subject == "english" else "हिंदी टेस्ट"
            label_hi = "अंग्रेज़ी टेस्ट" if subject == "english" else "हिंदी टेस्ट"
            out[cls] = (questions, "%s — Class %s" % (label, cls),
                        "%s — कक्षा %s" % (label_hi, cls))
        return out

    section = merged.get(subject) or {}
    titles = {
        "science": ("Science Test", "विज्ञान टेस्ट"),
        "maths": ("Maths Test", "गणित टेस्ट"),
        "sst": ("SST Test", "सामाजिक विज्ञान टेस्ट"),
        "gk": ("GK Test", "सामान्य ज्ञान टेस्ट"),
        "computer": ("Computer & AI Test", "कंप्यूटर और AI टेस्ट"),
    }
    en, hi = titles.get(subject, ("Test", "टेस्ट"))
    for cls in CLASSES:
        names = [cls]
        if subject == "science" and cls in ("11", "12"):
            # Senior science is split into three groups; the paper mixes them.
            names = ["physics_%s" % cls, "chemistry_%s" % cls, "biology_%s" % cls]
        out[cls] = (pool(section, names), "%s — Class %s" % (en, cls),
                    "%s — कक्षा %s" % (hi, cls))
    return out


# ---------------------------------------------------------------------------
# Competitive exam papers (SSC / HSSC / Railway)
# ---------------------------------------------------------------------------
# Each exam lists the subject mix of its paper. Subject names are data keys.
COMPETITIVE = {
    "ssc-cgl": {
        "name": "SSC CGL", "hi": "एसएससी सीजीएल", "duration": 60,
        "mix": {"reasoning": 25, "gk": 25, "maths": 25, "english": 25},
    },
    "ssc-chsl": {
        "name": "SSC CHSL", "hi": "एसएससी सीएचएसएल", "duration": 60,
        "mix": {"reasoning": 25, "gk": 25, "maths": 25, "english": 25},
    },
    "ssc-mts": {
        "name": "SSC MTS", "hi": "एसएससी एमटीएस", "duration": 45,
        "mix": {"reasoning": 20, "gk": 20, "maths": 20, "english": 20},
    },
    "hssc-cet": {
        "name": "HSSC CET", "hi": "एचएसएससी सीईटी", "duration": 95,
        "mix": {"gk": 20, "reasoning": 20, "maths": 20, "english": 20, "hindi": 20},
    },
    "hssc-group-d": {
        "name": "HSSC Group D", "hi": "एचएसएससी ग्रुप डी", "duration": 95,
        "mix": {"gk": 25, "reasoning": 20, "maths": 20, "hindi": 15, "computer": 10, "science": 10},
    },
    "railway-ntpc": {
        "name": "Railway NTPC", "hi": "रेलवे एनटीपीसी", "duration": 90,
        "mix": {"maths": 30, "reasoning": 30, "gk": 40},
    },
}
# Subjects whose paper is drawn from the senior (9-12) pool.
SENIOR_CLASSES = ("9", "10", "11", "12")


def senior_pool(merged, subject, limit=400):
    """Usable questions of one subject from classes 9-12 (all classes if unclassed)."""
    section = merged.get(subject) or {}
    if not isinstance(section, dict) or not section:
        return []
    keys = list(section.keys())
    names = [k for k in keys if str(k).split("_")[-1] in SENIOR_CLASSES] or keys
    return pool(section, names, limit=limit)


def build_mixed(mix, merged, seed):
    """Pick questions subject by subject for a full mock paper."""
    picked = []
    used = set()
    for subject, count in mix.items():
        questions = [q for q in senior_pool(merged, subject) if norm(q["q"]["en"]) not in used]
        take = build_paper(questions, count, "%s|%s" % (seed, subject))
        for q in take:
            used.add(norm(q["q"]["en"]))
        picked.extend(take)
        if len(take) < count:
            print("  %s: only %d of %d questions available" % (subject, len(take), count))
    rng = random.Random(seed)
    rng.shuffle(picked)
    return picked


def exam_papers(merged, exam, date):
    """Papers for one competitive exam: one per subject plus a full mock."""
    spec = COMPETITIVE[exam]
    out = []
    for subject in spec["mix"]:
        questions = senior_pool(merged, subject)
        title_en = "%s \u2014 %s" % (spec["name"], subject.title())
        title_hi = "%s \u2014 %s" % (spec["hi"], subject)
        picked = build_paper(questions, 25, "%s|%s|%s" % (date, exam, subject))
        if len(picked) < 25:
            print("skip %s/%s: only %d questions" % (exam, subject, len(picked)))
            continue
        out.append({
            "id": "%s-%s-%s" % (exam, subject, date), "exam": exam, "kind": "subject",
            "subject": subject, "class": None, "date": date,
            "title": {"en": title_en, "hi": title_hi},
            "duration_min": 30, "marks": 25, "questions": picked,
        })
    mock = build_mixed(spec["mix"], merged, "%s|%s|mock" % (date, exam))
    total = sum(spec["mix"].values())
    if len(mock) >= total:
        out.append({
            "id": "%s-mock-%s" % (exam, date), "exam": exam, "kind": "mock",
            "subject": "mixed", "class": None, "date": date,
            "title": {"en": "%s \u2014 Full Mock Test" % spec["name"],
                      "hi": "%s \u2014 पूरा मॉक टेस्ट" % spec["hi"]},
            "duration_min": spec["duration"], "marks": total, "questions": mock[:total],
        })
    return out


def main():
    args = sys.argv[1:]
    subject, date, per_class, exam = "", "", 25, ""
    out_name = "tests.json"
    for i, a in enumerate(args):
        if a == "--subject":
            subject = args[i + 1]
        elif a == "--date":
            date = args[i + 1]
        elif a == "--per-class":
            per_class = int(args[i + 1])
        elif a == "--out":
            out_name = args[i + 1]
        elif a == "--exam":
            exam = args[i + 1]
    if not subject and not exam:
        print("usage: build_tests.py --subject <subject> [--date YYYY-MM-DD]")
        print("       build_tests.py --exam <exam> [--date YYYY-MM-DD]")
        print("       exams: %s" % ", ".join(sorted(COMPETITIVE)))
        return 2
    if exam and exam not in COMPETITIVE:
        print("unknown exam %r; known: %s" % (exam, ", ".join(sorted(COMPETITIVE))))
        return 2
    if not date:
        date = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")

    merged = load_merged()

    out_path = os.path.join(ROOT, out_name)
    if os.path.exists(out_path):
        doc = json.load(open(out_path, encoding="utf-8"))
    else:
        doc = {}
    tests = doc.setdefault("tests", {})
    papers = tests.setdefault("papers", [])
    have = {p.get("id") for p in papers}

    if exam:
        added = 0
        for paper in exam_papers(merged, exam, date):
            if paper["id"] in have:
                continue
            papers.append(paper)
            added += 1
        if not added:
            print("no new papers to add for %s" % exam)
            return 0
        papers.sort(key=lambda p: (p["date"], p.get("exam") or p["subject"], p["id"]))
        json.dump(doc, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("added %d papers for %s on %s -> %s (total papers: %d)"
              % (added, exam, date, out_name, len(papers)))
        return 0

    pools = subject_pools(merged, subject)
    added = 0
    for cls, (questions, title_en, title_hi) in pools.items():
        paper_id = "%s-%s-%s" % (subject, cls, date)
        if paper_id in have:
            continue
        picked = build_paper(questions, per_class, "%s|%s|%s" % (date, subject, cls))
        if len(picked) < per_class:
            print("skip %s: only %d usable questions" % (paper_id, len(picked)))
            continue
        papers.append({
            "id": paper_id,
            "subject": subject,
            "class": None if cls == "all" else cls,
            "date": date,
            "title": {"en": title_en, "hi": title_hi},
            "duration_min": 30,
            "marks": per_class,
            "questions": picked,
        })
        added += 1

    if not added:
        print("no new papers to add")
        return 0
    papers.sort(key=lambda p: (p["date"], p.get("exam") or p["subject"], p["id"]))
    json.dump(doc, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("added %d papers for %s on %s -> %s (total papers: %d)"
          % (added, subject, date, out_name, len(papers)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
