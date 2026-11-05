# seekhojeeto.github.io
Seekho Jeeto - gamified Science quiz for Class 5-12 with points and rewards

## questions.json

This file is the single source of truth for every question. It is used by the
website and by the Android app (`SeekhoJeeto/seekhojeeto-app`), which fetches
it live on every launch.

Rules for every update:

- Save it as **UTF-8 without a BOM**, and never pass the text through a
  Latin-1 / Windows-1252 step. That turns Hindi into mojibake such as
  `à¤…à¤°à¤¾à¤µà¤²à¥€` instead of `अरावली`.
- Every question needs at least `en` and `hi` text, 4 options in the **same
  order** in every language, `a` pointing at the same index for all
  languages, and a short explanation.
- Do not repeat an English question text that is already in the bank.
- Update `meta.last_updated` (`YYYY-MM-DD`) and `meta.last_added`.

Check the file before committing - CI runs the same check on every push:

    python3 tool/validate_questions.py questions.json

A new subject only needs a new top-level key with class keys `"5"`..`"12"`
(like `science`, `maths`, `sst`); both the site and the app pick it up.

## Daily target

Each class (5-12) should carry **20 questions per subject** - that is 160
questions per subject (Science, Maths, SST), 40 per class across the three.
Values & Religion keeps 2 per category per batch.

New questions are written in **English and Hindi only**. The older questions
that already have 13 languages are left untouched; translation of the new ones
is a later task, after the bank is big enough.

## Daily updates: drop files, do not rewrite the bank

The data files are 1-3 MB each. Appending a daily batch used to mean sending
the whole file inline through an API call, which is the step that kept
failing: the questions were generated but the commit never landed.

New questions are now delivered as small JSON drops under `inbox/` - only the
new items, a few dozen KB per file. The `Apply inbox drops` workflow
(`.github/workflows/apply-inbox.yml` + `tool/apply_inbox.py`) appends them to
the right lists, updates `meta.last_updated` / `meta.last_added`, runs
`tool/validate_all.py` and commits `Daily: add questions`. Nothing is
committed if a drop is malformed or the merged bank fails validation.

See `inbox/README.md` for the drop format and the checks that run on it.
