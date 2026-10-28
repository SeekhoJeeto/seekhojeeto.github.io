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
