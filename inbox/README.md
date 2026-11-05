# inbox/ — daily question drops

Drop files here instead of rewriting the big data files. The
`Apply inbox drops` workflow (`tool/apply_inbox.py`) appends each drop to the
right list, updates `meta.json`, validates the merged bank and commits with
the message `Daily: add questions`.

This exists because a data file is 1–3 MB, and appending to it used to mean
sending the whole file inline through an API call — the step that repeatedly
failed, leaving the new questions generated but never committed. A drop here
is only the new questions, a few dozen KB, so it always goes through.

## One file per drop

```json
{
  "target": "english.json",
  "date": "2026-11-05",
  "appends": [
    {"path": ["english", "grammar_5", "qs"], "items": [ {question}, ... ]}
  ]
}
```

- `target` must be a file listed in `manifest.json` (`questions.json` is the
  frozen snapshot and is not accepted).
- `path` is the list of keys from the top of the target file down to the list
  the items are appended to:
  - `["maths", "5"]` — plain class list
  - `["science", "physics_11", "qs"]` — grouped section
  - `["traditions", "values", "qs"]` — values & religion
  - `["english", "grammar_5", "qs"]` — english / languages groups
- `date` is optional; the newest one becomes `meta.last_updated`. If no drop
  gives a date, today's IST date is used.
- `items` are full question objects:
  `{"q": {"en", "hi"}, "o": {"en": [4], "hi": [4]}, "a": 0, "e": {"en", "hi"}}`

Keep each drop small (roughly one class, or one class-part, per file) so it
stays well under any single-request size limit.

## What is checked before anything is written

A drop is rejected as a whole — and no data file is touched — if the target is
not in the manifest, the path does not end at an existing list, an item is
missing `q`/`o`/`a`/`e`, an option list is not exactly 4 in both languages,
the answer index is not 0–3, the Hindi text has no Devanagari, mojibake is
detected, or an English question repeats one already in that file.

After applying, the workflow runs `python3 tool/validate_all.py`; if that
fails, nothing is committed and the run goes red with the reason.

## Run it locally

```bash
python3 tool/apply_inbox.py --check   # report only
python3 tool/apply_inbox.py           # apply and delete the drop files
python3 tool/validate_all.py
```
