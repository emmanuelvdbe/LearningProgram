# Objectives inbox

Drop CompTIA exam objectives here. PDF, DOCX, Markdown, plain text, and JSON
are accepted. PDF text extraction uses `pdftotext`; install `poppler-utils` if
it is missing. Text extraction also works on `.docx` without extra packages.

Suggested file names make the next step obvious:

```
security-plus-sy0-701.pdf
network-plus-n10-009.pdf
cysa-plus-cs0-003.pdf
linux-plus-xk0-005.pdf
```

## Turn a document into a selectable exam

```bash
# 1. Create the exam folder and metadata
python3 main.py exam add security-plus-sy0-701 \
    --name "CompTIA Security+ (SY0-701)" --code SY0-701

# 2. Attach the objectives document (from this inbox or anywhere)
python3 main.py exam attach security-plus-sy0-701 \
    exams/_inbox/security-plus-sy0-701.pdf

# 3. Extract readable text
python3 main.py exam scan security-plus-sy0-701

# 4. Read the extracted objectives
python3 main.py exam objectives security-plus-sy0-701

# 5. Make it your active exam
python3 main.py exam use security-plus-sy0-701
```

An exam created this way is an **objectives-only** exam: it is selectable and
its save slot tracks that selection, but it has no missions until a curriculum
pack is built for it. Linux+ ships with a complete pack.
