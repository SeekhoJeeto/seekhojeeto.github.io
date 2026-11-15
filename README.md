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
(like `science`, `maths`, `sst`, `gk`, `gs`, `computer`); both the site and the
app pick it up.

## Adding a subject to the website

The home screen is built from the `SUBJECTS` list in `index.html`, not from
hard-coded buttons, so a new subject needs no layout work:

1. Make a data file whose top-level key is the subject id, e.g.
   `computer.json` -> `{"computer": {"5": [...], "6": [...]}}`. Class keys are
   `"5"`..`"12"`; a subject can also be split like science
   (`physics_11`, `chemistry_11`, ...) and the site groups those per class.
2. Add the file name to `manifest.json` `files`. The site merges every file it
   finds there, so no code change is needed for a subject already listed in
   `SUBJECTS` (`science`, `maths`, `sst`, `gk`, `gs`, `computer`, `english`,
   `hindi`).
3. Only for a completely new id, add one line to `SUBJECTS` in `index.html`
   (id, data key, emoji, name in 13 languages, optional `parts`, and a
   `track` prefix used to remember seen questions).
4. Run `python3 tool/validate_all.py`. A subject with no questions yet is
   hidden automatically, and classes without questions show as disabled
   chips, so partial data is safe to ship.

## Competitive test series (SSC / HSSC / Railway)

`tool/build_tests.py --exam <exam>` builds the competitive side of the test
series: one 25-question paper per subject plus a full mock paper, all drawn
from the senior (class 9-12) pool, and appends them to `tests.json`.

    python3 tool/build_tests.py --exam ssc-cgl --date 2026-11-15

Known exams and their mix live in `COMPETITIVE` in the script: `ssc-cgl`,
`ssc-chsl`, `ssc-mts`, `hssc-cet`, `hssc-group-d`, `railway-ntpc`. A subject
whose bank is still thin is skipped with a message instead of shipping a short
paper, so the app never shows a half paper.

Two subject banks feed it: `reasoning.json` (classes 5-12) and
`currentaffairs.json`, which is grouped by month (`2026-11`) instead of by
class - the app shows the month chips for that subject instead of class chips.

In the app: Home -> Competitive Test Series -> exam chips -> two-column subject
grid (Science/Maths, English/GK, Reasoning/Current Affairs, Computer & AI) plus
the Full Mock card. A paper runs in "test" mode: one overall countdown for the
whole paper, no lives, score and explanation as you go.

## Test series (tests.json)

`tool/build_tests.py` turns the bank into a test series: for the day's
subject it builds one 25-question paper per class and appends them to
`tests.json` (listed in `manifest.json`). Papers are self-contained - the
questions are copied in - so the app never resolves an index into the bank
and old papers stay valid as the bank grows.

    python3 tool/build_tests.py --subject science --date 2026-11-15

Selection is deterministic (same date + subject + class gives the same
paper) and idempotent (an existing paper id is skipped), uses only the most
recently appended questions of each group, and balances the correct-answer
index across the paper. Subjects: science, maths, sst, gk, computer,
english, hindi, values. `values` gives a single paper, because values.json
has no classes.

The app still needs a small screen to list and play these papers - until
then the file is data only.

## File layout (why some files carry a whole subject)

The Flutter app (`seekhojeeto-app`) merges the manifest files by **replacing**
a section, not appending to it: the last file that contains `science` wins. So
a subject split across two files showed only the second half in the app -
`science.json` (classes 5-10) disappeared behind `science_2.json`.

To keep the installed app correct without a rebuild, the complete subject now
lives in one file:

| section | file |
|---|---|
| science | `science_2.json` (all 12 groups) |
| english | `english_2.json` (all 24 groups) |
| hindi   | `languages_2.json` (all 24 groups) |

`science.json`, `english.json` and `languages.json` are superseded: they are
no longer in `manifest.json` and must not be written to. The web app and
`tool/validate_all.py` only read what the manifest lists.

Do not split these three files again until the next app build is out: the
merge fix in the app repo makes splits safe, but an installed build that
predates it would lose half of the subject again.

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
