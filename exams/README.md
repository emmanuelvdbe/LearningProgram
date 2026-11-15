# Exams

This folder makes the study platform multi-exam.

```
exams/
    _inbox/                 drop CompTIA objectives here
    linux-plus-xk0-005/
        exam.json           exam metadata and curriculum pack selection
        objectives/         optional source objectives and extracted text
    linux-plus-xk0-006/
        exam.json           manifest with five official domains
        OBJECTIVES.md       objective-to-module map
        objectives/         official XK0-006 PDF and extracted text
        pack/               22 lessons and 22 missions
    <your-exam-id>/
        exam.json
        objectives/
```

## Built-in packs

| Exam | Code | Pack | Modules | Study time |
| --- | --- | --- | --- | --- |
| `linux-plus-xk0-005` | XK0-005 | `curriculum/` | 16 | ~26 hours |
| `linux-plus-xk0-006` | XK0-006 | `pack/` | 22 | ~39 hours |

The XK0-006 pack is a self-contained package under
`exams/linux-plus-xk0-006/pack/`; see
[`linux-plus-xk0-006/OBJECTIVES.md`](linux-plus-xk0-006/OBJECTIVES.md) for the
complete objective-to-module mapping.

## Add an exam

```bash
python3 main.py exam add security-plus-sy0-701 \
    --name "CompTIA Security+ (SY0-701)" --code SY0-701

python3 main.py exam attach security-plus-sy0-701 \
    exams/_inbox/security-plus-sy0-701.pdf

python3 main.py exam scan security-plus-sy0-701
python3 main.py exam use security-plus-sy0-701
```

## Manifest fields

| Field | Meaning |
| --- | --- |
| `id` | Stable folder-safe identifier |
| `name` | Full exam name shown in the UI |
| `short_name` | Short label used in prompts |
| `code` | Vendor exam code, e.g. `XK0-005` |
| `status` | `ready` or `objectives-only` |
| `curriculum` | `linux_plus` for the built-in pack, `pack` for an exam-local package, `null` for none |
| `description` | One-line summary |
| `domains` | Optional list of exam domains |

A new exam is **objectives-only** until a curriculum pack exists. It is still
selectable, readable, and tracked per save slot. Linux+ ships with two complete
packs: XK0-005 (`curriculum/`) and XK0-006 (`pack/`).
