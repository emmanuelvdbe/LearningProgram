#!/usr/bin/env python3
"""Graphical study lab with sandboxed terminals.

This is the optional desktop front end for the CompTIA Study Lab.  It shows
the same lessons, missions, hints, checks, and save slots as ``main.py``, and
adds:

* a module tree with live completion marks,
* a rendered lesson viewer,
* a mission brief with hints, verification, and reference solutions,
* a small workspace file editor, and
* one or more **sandboxed terminal sessions** for the mission workspace.

Every terminal is wrapped in bubblewrap.  The sandbox sees read-only system
directories, a private home, private ``/tmp``, and the mission workspace
mounted at ``/workspace``.  The project folder (including save slots), the
real home directory, and removable media are not visible.  Network access is
isolated by default and can be enabled per new session.

The terminal is line-oriented, not a full-screen terminal emulator: type a
command in the entry box and press Enter.  Shell state (``cd``, variables,
history) persists between commands, and Ctrl-C / Ctrl-D work.  Use the Files
tab for ``nano``/``vim``-style editing.

Only the Python standard library is used.  Tkinter is imported lazily so the
CLI keeps working on machines without a display.
"""
from __future__ import annotations

import argparse
import codecs
import os
import queue
import re
import sys
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Callable

import main
from study import saves as savefiles
from study.sandbox import (
    SandboxConfig,
    SandboxUnavailable,
    bwrap_path,
    sandbox_available,
    terminal_environment,
)
from study.terminal import PtySession

WINDOW_TITLE = "CompTIA Study Lab"
DEFAULT_GEOMETRY = "1280x820"

# Strips CSI, OSC, charset selection, and two-character escapes.  A partial
# escape at the end of a chunk is kept by AnsiStripper.feed() and completed on
# the next chunk.
ANSI_RE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[()][0-9A-B]|[=>]|[A-Za-z])"
)

INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")

LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")

MAX_EDIT_BYTES = 1_000_000
MAX_OUTPUT_LINES = 6000


def clean_output(data: bytes, decoder: codecs.IncrementalDecoder) -> str:
    """Decode and normalise one chunk of PTY output."""
    text = decoder.decode(data)
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\x07", "").replace("\x08", "")
    return text


class AnsiStripper:
    """Incremental ANSI stripper that survives chunk boundaries."""

    def __init__(self) -> None:
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.pending = ""

    def feed(self, data: bytes) -> str:
        text = self.pending + clean_output(data, self.decoder)
        text = ANSI_RE.sub("", text)
        index = text.rfind("\x1b")
        if index != -1:
            # Keep a possibly incomplete escape for the next chunk.
            self.pending = text[index:]
            text = text[:index]
        else:
            self.pending = ""
        return text

    def flush(self) -> str:
        text, self.pending = self.pending, ""
        return ANSI_RE.sub("", text)


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / (1024 * 1024):.1f} MiB"


def make_widget_text_read_only(widget) -> None:
    widget.configure(state="disabled")


def append_text(widget, text: str, tag: str | None = None) -> None:
    """Append to a read-only Text widget and keep it scrolled to the end."""
    if not text:
        return
    at_bottom = widget.yview()[1] > 0.995
    widget.configure(state="normal")
    widget.insert("end", text, tag or ())
    line = int(widget.index("end-1c").split(".")[0])
    if line > MAX_OUTPUT_LINES:
        widget.delete("1.0", f"{line - MAX_OUTPUT_LINES + 500}.0")
    widget.configure(state="disabled")
    if at_bottom:
        widget.see("end")


def replace_text(widget, text: str, tag: str | None = None) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("end", text, tag or ())
    widget.configure(state="disabled")
    widget.see("1.0")


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
class MarkdownRenderer:
    """Minimal Markdown-to-Text renderer with a few pleasant tags."""

    def __init__(self, app: "StudyApp") -> None:
        self.app = app
        self.family = app.ui_family
        self.mono = app.mono_family
        self.size = app.base_size

    def configure(self, widget) -> None:
        family, mono, size = self.family, self.mono, self.size
        widget.tag_configure("h1", font=(family, size + 8, "bold"), spacing1=4, spacing3=10)
        widget.tag_configure("h2", font=(family, size + 4, "bold"), spacing1=14, spacing3=6)
        widget.tag_configure("h3", font=(family, size + 2, "bold"), spacing1=10, spacing3=4)
        widget.tag_configure("body", font=(family, size), spacing3=2)
        widget.tag_configure(
            "code",
            font=(mono, max(7, size - 1)),
            background="#f4f6f8",
            lmargin1=18,
            lmargin2=18,
            spacing1=1,
            spacing3=1,
        )
        widget.tag_configure(
            "inline_code",
            font=(mono, max(7, size - 1)),
            background="#eef1f4",
        )
        widget.tag_configure("bold", font=(family, size, "bold"))
        widget.tag_configure("quote", font=(family, size, "italic"), foreground="#4a5560", lmargin1=18, lmargin2=18)
        widget.tag_configure("bullet", font=(family, size), lmargin1=18, lmargin2=32)
        widget.tag_configure(
            "table",
            font=(mono, max(7, size - 1)),
            background="#f8f9fa",
            lmargin1=12,
            lmargin2=12,
        )
        widget.tag_configure("link", foreground="#0b5cad", underline=True)
        widget.tag_configure("hr", foreground="#b8c0c8")
        widget.tag_configure("muted", foreground="#6b737b")
        widget.tag_configure("pass", foreground="#1a7f37", font=(family, size, "bold"))
        widget.tag_configure("fail", foreground="#b42318", font=(family, size, "bold"))
        widget.tag_configure("detail", font=(mono, max(7, size - 1)), foreground="#555c63", lmargin1=24, lmargin2=24)
        widget.tag_configure("term_cmd", foreground="#0b5394", font=(mono, size, "bold"))
        widget.tag_configure("term_meta", foreground="#6b737b", font=(mono, max(7, size - 1)))
        widget.tag_configure("term_end", foreground="#b42318", font=(mono, size, "bold"))

    def inline(self, widget, text: str, base: str) -> None:
        for token in INLINE_RE.split(text):
            if not token:
                continue
            if token.startswith("**") and token.endswith("**") and len(token) > 4:
                widget.insert("end", token[2:-2], (base, "bold"))
            elif token.startswith("`") and token.endswith("`") and len(token) > 2:
                widget.insert("end", token[1:-1], (base, "inline_code"))
            elif token.startswith("[") and "](" in token and token.endswith(")"):
                label = token[1 : token.index("]")]
                widget.insert("end", label, (base, "link"))
            else:
                widget.insert("end", token, base)

    def render(self, widget, markdown: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        in_code = False
        table: list[str] = []

        def flush_table() -> None:
            nonlocal table
            if not table:
                return
            for raw in table:
                if re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", raw):
                    continue
                cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
                widget.insert("end", "  ".join(cells) + "\n", "table")
            widget.insert("end", "\n", "body")
            table = []

        for raw in markdown.splitlines():
            line = raw.rstrip()
            if line.startswith("```"):
                flush_table()
                in_code = not in_code
                if not in_code:
                    widget.insert("end", "\n", "body")
                continue
            if in_code:
                widget.insert("end", line + "\n", "code")
                continue
            if line.strip().startswith("|"):
                table.append(line)
                continue
            flush_table()

            if not line.strip():
                widget.insert("end", "\n", "body")
            elif line.startswith("# "):
                widget.insert("end", line[2:].strip() + "\n", "h1")
            elif line.startswith("## "):
                widget.insert("end", line[3:].strip() + "\n", "h2")
            elif line.startswith("### "):
                widget.insert("end", line[4:].strip() + "\n", "h3")
            elif line.strip() in ("---", "***"):
                widget.insert("end", "─" * 72 + "\n", "hr")
            elif line.startswith(">"):
                self.inline(widget, line[1:].lstrip(), "quote")
                widget.insert("end", "\n", "quote")
            else:
                match = LIST_RE.match(line)
                if match:
                    indent, marker, rest = match.groups()
                    bullet = "•" if marker in ("-", "*", "+") else marker
                    prefix = " " * min(len(indent), 8) + bullet + " "
                    widget.insert("end", prefix, "bullet")
                    self.inline(widget, rest, "bullet")
                    widget.insert("end", "\n", "bullet")
                else:
                    self.inline(widget, line, "body")
                    widget.insert("end", "\n", "body")

        flush_table()
        if in_code:
            widget.insert("end", "\n", "body")
        widget.configure(state="disabled")
        widget.see("1.0")


# ---------------------------------------------------------------------------
# Lesson tab
# ---------------------------------------------------------------------------
class LessonPanel:
    def __init__(self, app: "StudyApp", parent) -> None:
        from tkinter import ttk

        self.app = app
        self.frame = ttk.Frame(parent, padding=(10, 8))
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)

        self.title = ttk.Label(self.frame, text="", style="ModuleTitle.TLabel")
        self.title.grid(row=0, column=0, sticky="w")
        self.meta = ttk.Label(self.frame, text="", style="Muted.TLabel")
        self.meta.grid(row=1, column=0, sticky="w", pady=(0, 6))

        from tkinter import Text

        self.text = Text(
            self.frame,
            wrap="word",
            padx=16,
            pady=12,
            borderwidth=0,
            highlightthickness=0,
            font=(app.ui_family, app.base_size),
        )
        scroll = ttk.Scrollbar(self.frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=2, column=0, sticky="nsew")
        scroll.grid(row=2, column=1, sticky="ns")
        app.renderer.configure(self.text)
        make_widget_text_read_only(self.text)

    def set_module(self, module: dict) -> None:
        exam = self.app.exam
        self.title.configure(text=f"{module['num']:02d}  {module['title']}")
        self.meta.configure(
            text=f"{module.get('part', '')} · {module.get('domain', '')} · about {module.get('minutes', 0)} min"
        )
        path = exam.lesson_path(module)
        if not path.is_file():
            replace_text(self.text, f"Lesson file is missing:\n\n{path}\n", "fail")
            return
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError as exc:
            replace_text(self.text, f"Could not read {path}: {exc}\n", "fail")
            return
        self.app.renderer.render(self.text, markdown)

    def show_message(self, title: str, message: str) -> None:
        self.title.configure(text=title)
        self.meta.configure(text="")
        replace_text(self.text, message, "body")


# ---------------------------------------------------------------------------
# Mission tab
# ---------------------------------------------------------------------------
class MissionPanel:
    def __init__(self, app: "StudyApp", parent) -> None:
        from tkinter import Text
        from tkinter import ttk

        self.app = app
        self.frame = ttk.Frame(parent, padding=(10, 8))
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(4, weight=1)

        header = ttk.Frame(self.frame)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.title = ttk.Label(header, text="", style="ModuleTitle.TLabel")
        self.title.grid(row=0, column=0, sticky="w")
        self.meta = ttk.Label(header, text="", style="Muted.TLabel")
        self.meta.grid(row=1, column=0, sticky="w")

        toolbar = ttk.Frame(self.frame)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        self.verify_button = ttk.Button(toolbar, text="Verify mission", command=self.verify)
        self.verify_button.pack(side="left")
        self.hint_button = ttk.Button(toolbar, text="Reveal hint", command=self.reveal_hint)
        self.hint_button.pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Reference solution…", command=self.show_reference).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(toolbar, text="Open files", command=self.app.show_files_tab).pack(
            side="left", padx=(6, 0)
        )
        self.workspace_button = ttk.Button(
            toolbar, text="Workspace…", command=self.show_workspace
        )
        self.workspace_button.pack(side="right")

        self.hints = ttk.LabelFrame(self.frame, text="Hints", padding=(8, 6))
        self.hints_text = Text(
            self.hints,
            height=5,
            wrap="word",
            font=(app.ui_family, app.base_size),
            borderwidth=0,
            highlightthickness=0,
        )
        self.hints_text.pack(fill="both", expand=True)
        app.renderer.configure(self.hints_text)
        make_widget_text_read_only(self.hints_text)
        self.hints_visible = False

        paned = ttk.Panedwindow(self.frame, orient="vertical")
        paned.grid(row=4, column=0, sticky="nsew", pady=(8, 0))

        brief_frame = ttk.Frame(paned)
        brief_frame.columnconfigure(0, weight=1)
        brief_frame.rowconfigure(0, weight=1)
        self.brief = Text(
            brief_frame,
            wrap="word",
            padx=14,
            pady=10,
            borderwidth=0,
            highlightthickness=0,
            font=(app.ui_family, app.base_size),
        )
        brief_scroll = ttk.Scrollbar(brief_frame, orient="vertical", command=self.brief.yview)
        self.brief.configure(yscrollcommand=brief_scroll.set)
        self.brief.grid(row=0, column=0, sticky="nsew")
        brief_scroll.grid(row=0, column=1, sticky="ns")
        app.renderer.configure(self.brief)
        make_widget_text_read_only(self.brief)
        paned.add(brief_frame, weight=3)

        verify_frame = ttk.LabelFrame(paned, text="Verification", padding=(8, 6))
        verify_frame.columnconfigure(0, weight=1)
        verify_frame.rowconfigure(0, weight=1)
        self.verify_text = Text(
            verify_frame,
            height=10,
            wrap="word",
            font=(app.mono_family, max(7, app.base_size - 1)),
            borderwidth=0,
            highlightthickness=0,
        )
        verify_scroll = ttk.Scrollbar(
            verify_frame, orient="vertical", command=self.verify_text.yview
        )
        self.verify_text.configure(yscrollcommand=verify_scroll.set)
        self.verify_text.grid(row=0, column=0, sticky="nsew")
        verify_scroll.grid(row=0, column=1, sticky="ns")
        app.renderer.configure(self.verify_text)
        make_widget_text_read_only(self.verify_text)
        paned.add(verify_frame, weight=2)

        self.module: dict | None = None
        self.mission = None
        self.workspace: Path | None = None
        self.hint_index = 0
        self._verify_token = 0

    # -- lifecycle ---------------------------------------------------------
    def set_module(self, module: dict, mission, workspace: Path) -> None:
        self.module = module
        self.mission = mission
        self.workspace = workspace
        self.hint_index = 0
        self.hide_hints()
        replace_text(self.hints_text, "")
        self._verify_token += 1
        self.verify_button.state(["!disabled"])
        replace_text(self.verify_text, "")
        self.title.configure(text=f"Mission {module['num']:02d} — {mission.title if mission else 'No mission'}")
        self.meta.configure(
            text=f"{module.get('domain', '')} · workspace: {workspace}"
        )
        if mission is None:
            replace_text(self.brief, "This module has no registered mission.\n", "muted")
            self.verify_button.state(["disabled"])
            self.hint_button.configure(text="No hints")
            self.hint_button.state(["disabled"])
            return
        self.hint_button.state(["!disabled"])
        self.hint_button.configure(
            text=f"Reveal hint (0/{len(mission.hints)})"
            if mission.hints
            else "No hints"
        )
        self.hint_button.state(["!disabled"] if mission.hints else ["disabled"])
        self.app.renderer.render(self.brief, mission.brief)

    # -- hints -------------------------------------------------------------
    def hide_hints(self) -> None:
        if self.hints_visible:
            self.hints.grid_forget()
            self.hints_visible = False

    def reveal_hint(self) -> None:
        if not self.mission or not self.mission.hints:
            return
        if self.hint_index >= len(self.mission.hints):
            return
        if not self.hints_visible:
            self.hints.grid(row=2, column=0, sticky="ew", pady=(2, 4))
            self.hints_visible = True
        hint = self.mission.hints[self.hint_index]
        self.hint_index += 1
        self.hints_text.configure(state="normal")
        self.hints_text.insert("end", f"{self.hint_index}. ", "bold")
        self.app.renderer.inline(self.hints_text, hint, "body")
        self.hints_text.insert("end", "\n\n", "body")
        self.hints_text.configure(state="disabled")
        self.hints_text.see("end")
        remaining = len(self.mission.hints) - self.hint_index
        self.hint_button.configure(
            text=(
                f"Reveal hint ({self.hint_index}/{len(self.mission.hints)})"
                if remaining
                else "All hints shown"
            )
        )
        if not remaining:
            self.hint_button.state(["disabled"])

    # -- verification ------------------------------------------------------
    def verify(self) -> None:
        if not self.mission or not self.module:
            return
        mission = self.mission
        module_id = self.module["id"]
        token = self._verify_token
        self.verify_button.state(["disabled"])
        replace_text(
            self.verify_text,
            f"Running checks for mission {mission.num:02d}…\n",
            "muted",
        )
        lab = main.exam_lab()

        def work():
            return mission.run_checks(lab)

        def done(checks):
            if token != self._verify_token or not self.module or self.module["id"] != module_id:
                return
            self.verify_button.state(["!disabled"])
            self.render_checks(checks, mission)

        def failed(exc: BaseException) -> None:
            if token != self._verify_token:
                return
            self.verify_button.state(["!disabled"])
            replace_text(self.verify_text, f"Verification crashed:\n{exc}\n", "fail")

        self.app.run_background(work, done, failed)

    def render_checks(self, checks, mission) -> None:
        passed = bool(checks) and all(check.ok for check in checks)
        replace_text(self.verify_text, "")
        self.verify_text.configure(state="normal")
        if passed:
            self.verify_text.insert("end", f"PASS — mission {mission.num:02d} complete\n", "pass")
        else:
            self.verify_text.insert("end", "NOT YET — fix the failures and verify again\n", "fail")
        for check in checks:
            marker = "✓" if check.ok else "✗"
            tag = "pass" if check.ok else "fail"
            self.verify_text.insert("end", f"{marker} {check.name}\n", tag)
            if check.detail:
                for line in str(check.detail).splitlines():
                    self.verify_text.insert("end", f"    {line}\n", "detail")
        self.verify_text.configure(state="disabled")
        self.verify_text.see("1.0")
        if passed:
            main.mark_complete(mission.id)
            self.app.set_status(f"Mission {mission.num:02d} complete")
        else:
            main.record_attempt(mission.id)
            self.app.set_status(f"Mission {mission.num:02d}: attempt recorded")
        self.app.refresh_progress()

    # -- reference and workspace ------------------------------------------
    def show_workspace(self) -> None:
        if self.workspace is None:
            return
        from tkinter import messagebox

        messagebox.showinfo(
            "Mission workspace",
            f"{self.workspace}\n\nIt is mounted read-write at /workspace in every "
            "terminal for this mission. The Files tab edits the same directory.",
            parent=self.frame,
        )

    def show_reference(self) -> None:
        from tkinter import Text, Toplevel
        from tkinter import ttk

        if not self.mission or not self.app.exam:
            return
        mission = self.mission
        exam = self.app.exam
        win = Toplevel(self.frame)
        win.title(f"Reference solution — mission {mission.num:02d}")
        win.geometry("900x650")
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)

        header = ttk.Frame(win, padding=(10, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=mission.title, style="ModuleTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="Read it after your own attempt, then reproduce it from memory.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w")

        if not mission.solution:
            ttk.Label(win, text="No reference files for this mission.", padding=20).grid(
                row=1, column=0
            )
            return

        notebook = ttk.Notebook(win)
        notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        for name, content in mission.solution.items():
            frame = ttk.Frame(notebook)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            text = Text(
                frame,
                wrap="none",
                font=(self.app.mono_family, max(7, self.app.base_size - 1)),
                borderwidth=0,
            )
            scroll_y = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
            text.grid(row=0, column=0, sticky="nsew")
            scroll_y.grid(row=0, column=1, sticky="ns")
            scroll_x.grid(row=1, column=0, sticky="ew")
            text.insert("1.0", content)
            text.configure(state="disabled")
            notebook.add(frame, text=name)

        footer = ttk.Frame(win, padding=(10, 0, 10, 10))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(
            footer,
            text=f"An installed copy goes to {main.exam_lab() / '_reference' / mission.dir_name}",
            style="Muted.TLabel",
        ).pack(side="left")

        def install() -> None:
            from tkinter import messagebox

            destination = main.exam_lab() / "_reference" / mission.dir_name

            def work():
                return exam.install_solution(mission, destination)

            def done(written) -> None:
                messagebox.showinfo(
                    "Reference installed",
                    "Wrote:\n\n" + "\n".join(str(path) for path in written)
                    + "\n\nYour mission workspace was not changed.",
                    parent=win,
                )

            def failed(exc: BaseException) -> None:
                messagebox.showerror("Could not install", str(exc), parent=win)

            self.app.run_background(work, done, failed)

        install_button = ttk.Button(footer, text="Install a reference copy", command=install)
        install_button.pack(side="right")
        if hasattr(mission, "post_install") and mission.post_install is not None:
            ttk.Label(
                footer,
                text="This solution also runs its build script.",
                style="Muted.TLabel",
            ).pack(side="right", padx=(0, 10))


# ---------------------------------------------------------------------------
# Sandboxed terminal tab
# ---------------------------------------------------------------------------
class TerminalSession:
    """One persistent shell inside one bubblewrap sandbox."""

    def __init__(
        self,
        app: "StudyApp",
        parent,
        module: dict,
        workspace: Path,
        home: Path,
        allow_network: bool,
    ) -> None:
        from tkinter import Text
        from tkinter import ttk

        self.app = app
        self.module = module
        self.workspace = Path(workspace)
        self.home = Path(home)
        self.allow_network = allow_network
        self.session: PtySession | None = None
        self.finished = False
        self.history: list[str] = []
        self.history_index = 0
        self.stripper = AnsiStripper()

        self.frame = ttk.Frame(parent, padding=(8, 6))
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        header = ttk.Frame(self.frame)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        header.columnconfigure(0, weight=1)
        self.title = ttk.Label(header, text="", style="Muted.TLabel")
        self.title.grid(row=0, column=0, sticky="w")
        self.status = ttk.Label(header, text="starting…", style="Muted.TLabel")
        self.status.grid(row=0, column=1, sticky="e")

        self.output = Text(
            self.frame,
            wrap="word",
            font=(app.mono_family, max(7, app.base_size - 1)),
            background="#101418",
            foreground="#d7dde3",
            insertbackground="#d7dde3",
            borderwidth=0,
            padx=10,
            pady=8,
        )
        scroll = ttk.Scrollbar(self.frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        self.output.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.output.tag_configure("term_meta", foreground="#8d98a3", font=(app.mono_family, max(7, app.base_size - 1)))
        self.output.tag_configure("term_cmd", foreground="#6cb6ff", font=(app.mono_family, app.base_size, "bold"))
        self.output.tag_configure("term_end", foreground="#ff8a80", font=(app.mono_family, app.base_size, "bold"))
        self.output.configure(state="disabled")

        controls = ttk.Frame(self.frame)
        controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="$", style="Prompt.TLabel").grid(row=0, column=0, padx=(2, 6))
        self.entry = ttk.Entry(controls, font=(app.mono_family, app.base_size))
        self.entry.grid(row=0, column=1, sticky="ew")
        self.entry.bind("<Return>", self.send)
        self.entry.bind("<Up>", self.history_previous)
        self.entry.bind("<Down>", self.history_next)
        self.entry.bind("<Control-l>", lambda event: self.clear())
        ttk.Button(controls, text="Ctrl-C", width=8, command=self.interrupt).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Button(controls, text="Ctrl-D", width=8, command=self.end_of_file).grid(
            row=0, column=3, padx=(4, 0)
        )
        ttk.Button(controls, text="Clear", width=7, command=self.clear).grid(
            row=0, column=4, padx=(4, 0)
        )
        ttk.Button(controls, text="Restart", width=8, command=self.restart).grid(
            row=0, column=5, padx=(4, 0)
        )

        network = "network shared" if allow_network else "network isolated"
        tag = f"M{module['num']:02d}" if module.get("num") else "Sandbox"
        self.title.configure(
            text=f"{tag} · {workspace} → /workspace · {network}"
        )
        self.start()

    # -- process -----------------------------------------------------------
    def start(self) -> None:
        config = SandboxConfig(
            workspace=self.workspace,
            home=self.home,
            allow_network=self.allow_network,
            new_session=False,
            hidden_paths=self.app.sandbox_hidden_paths(),
        )
        try:
            argv = config.command([config.shell, "--noprofile", "--norc", "-i"])
            self.session = PtySession(
                argv,
                env=terminal_environment(),
                echo=False,
                rows=32,
                cols=110,
            ).start()
        except (SandboxUnavailable, OSError) as exc:
            self.finished = True
            self.append(f"Could not start the sandbox: {exc}\n", "term_end")
            self.status.configure(text="sandbox unavailable")
            self.entry.state(["disabled"])
            return
        self.status.configure(text="running")
        self.append(f"$ sandboxed shell — {config.describe()}\n", "term_meta")
        self.append(
            "  The project folder, real home, and removable media are not mounted.\n"
            "  Type a command and press Enter. Ctrl-C interrupts; Ctrl-D exits.\n\n",
            "term_meta",
        )

    def append(self, text: str, tag: str | None = None) -> None:
        append_text(self.output, text, tag)

    def send(self, _event=None) -> str:
        if self.session is None or self.finished:
            return "break"
        line = self.entry.get()
        self.entry.delete(0, "end")
        self.append(f"$ {line}\n", "term_cmd")
        if line.strip():
            self.history.append(line)
        self.history_index = len(self.history)
        self.session.send_line(line)
        return "break"

    def history_previous(self, _event=None) -> str:
        if not self.history:
            return "break"
        self.history_index = max(0, self.history_index - 1)
        self.entry.delete(0, "end")
        self.entry.insert(0, self.history[self.history_index])
        return "break"

    def history_next(self, _event=None) -> str:
        if not self.history:
            return "break"
        self.history_index = min(len(self.history), self.history_index + 1)
        self.entry.delete(0, "end")
        if self.history_index < len(self.history):
            self.entry.insert(0, self.history[self.history_index])
        return "break"

    def interrupt(self) -> None:
        if self.session is not None and not self.finished:
            self.session.interrupt()
            self.append("^C\n", "term_meta")
            self.entry.focus_set()

    def end_of_file(self) -> None:
        if self.session is not None and not self.finished:
            self.session.end_of_file()

    def clear(self) -> None:
        replace_text(self.output, "")
        self.entry.focus_set()

    def restart(self) -> None:
        if self.session is not None:
            self.session.close()
        self.finished = False
        self.stripper = AnsiStripper()
        self.entry.state(["!disabled"])
        self.clear()
        self.start()

    def poll(self) -> None:
        if self.session is None:
            return
        data = self.session.read()
        if data:
            text = self.stripper.feed(data)
            if text:
                self.append(text)
        if self.session.eof and not self.finished:
            self.finished = True
            tail = self.stripper.flush()
            if tail:
                self.append(tail)
            code = self.session.poll()
            if code is None:
                code = self.session.poll()
            self.append(f"\n[shell exited with status {code}]\n", "term_end")
            self.status.configure(text=f"exited ({code})")
            self.entry.state(["disabled"])
            self.app.refresh_terminal_selector()

    def focus(self) -> None:
        self.entry.focus_set()

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None

    @property
    def label(self) -> str:
        suffix = "" if not self.finished else " (ended)"
        tag = f"M{self.module['num']:02d}" if self.module.get("num") else "Sandbox"
        return f"{tag} · {self.module['title'][:24]}{suffix}"


class TerminalPanel:
    def __init__(self, app: "StudyApp", parent) -> None:
        from tkinter import StringVar
        from tkinter import ttk

        self.app = app
        self.frame = ttk.Frame(parent, padding=(8, 6))
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)
        self.sessions: list[TerminalSession] = []
        self.current: TerminalSession | None = None
        self.module: dict | None = None
        self.workspace: Path | None = None
        self.counter = 0
        self.selector_var = StringVar()
        self.network_var = app.network_var

        toolbar = ttk.Frame(self.frame)
        toolbar.grid(row=0, column=0, sticky="ew")
        self.new_button = ttk.Button(
            toolbar, text="New terminal", command=self.new_terminal
        )
        self.new_button.pack(side="left")
        ttk.Label(toolbar, text="Session", style="Muted.TLabel").pack(
            side="left", padx=(10, 4)
        )
        self.selector = ttk.Combobox(
            toolbar, textvariable=self.selector_var, state="readonly", width=38
        )
        self.selector.pack(side="left")
        self.selector.bind("<<ComboboxSelected>>", self._select_from_combo)
        self.close_button = ttk.Button(
            toolbar, text="Close session", command=self.close_current
        )
        self.close_button.pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            toolbar,
            text="Allow network (new sessions)",
            variable=self.network_var,
            command=self._sync_network_note,
        ).pack(side="right")

        self.note = ttk.Label(self.frame, text="", style="Muted.TLabel")
        self.note.grid(row=1, column=0, sticky="w", pady=(4, 4))

        self.stack = ttk.Frame(self.frame)
        self.stack.grid(row=2, column=0, sticky="nsew")
        self.stack.columnconfigure(0, weight=1)
        self.stack.rowconfigure(0, weight=1)

        self.empty = ttk.Frame(self.stack, padding=30)
        self.empty.grid(row=0, column=0, sticky="nsew")
        self.empty.columnconfigure(0, weight=1)
        ttk.Label(
            self.empty,
            text="No sandboxed terminal for this module yet",
            style="ModuleTitle.TLabel",
        ).grid(row=0, column=0, pady=(30, 6))
        self.empty_text = ttk.Label(
            self.empty,
            text="",
            style="Muted.TLabel",
            justify="center",
        )
        self.empty_text.grid(row=1, column=0, pady=(0, 16))
        self.start_button = ttk.Button(
            self.empty, text="Start sandboxed terminal", command=self.new_terminal
        )
        self.start_button.grid(row=2, column=0)
        ttk.Label(
            self.empty,
            text=(
                "bubblewrap: read-only /usr and /etc · private home and /tmp\n"
                "workspace mounted at /workspace · network isolated by default"
            ),
            style="Muted.TLabel",
            justify="center",
        ).grid(row=3, column=0, pady=(18, 0))

        self.set_available(sandbox_available())
        self.show_empty()

    def set_available(self, available: bool) -> None:
        self.available = available
        if available:
            self.note.configure(
                text="Sessions run in bubblewrap: host home, project folder, and media are masked."
            )
            self.start_button.state(["!disabled"])
            self.new_button.state(["!disabled"])
        else:
            self.note.configure(
                text=(
                    "bubblewrap (bwrap) is not installed, so terminals are disabled. "
                    "Install it with your package manager and reopen the GUI."
                )
            )
            self.start_button.state(["disabled"])
            self.new_button.state(["disabled"])

    def _sync_network_note(self) -> None:
        if self.network_var.get():
            self.note.configure(
                text="New sessions will share the host network. Existing sessions keep their setting."
            )
        else:
            self.note.configure(
                text="Sessions run in bubblewrap: host home, project folder, and media are masked."
            )

    # -- module binding ----------------------------------------------------
    def set_module(self, module: dict, workspace: Path) -> None:
        self.module = module
        self.workspace = Path(workspace)
        tag = f"M{module['num']:02d}" if module.get("num") else "Sandbox"
        self.new_button.configure(text=f"New terminal for {tag}")
        self.start_button.configure(text=f"Start terminal for {tag}")
        self.empty_text.configure(
            text=f"{module['title']}\nWorkspace: {workspace}"
        )
        for session in self.sessions:
            if session.module["id"] == module["id"]:
                self.select(session, focus=False)
                return
        self.show_empty()

    def show_empty(self) -> None:
        self.current = None
        self.empty.tkraise()
        self.refresh_selector()
        self.selector_var.set("")
        self.close_button.state(["disabled"])

    def new_terminal(self) -> None:
        if self.module is None or self.workspace is None:
            return
        if not self.available:
            from tkinter import messagebox

            messagebox.showerror(
                "Sandbox unavailable",
                "bubblewrap (bwrap) is required for sandboxed terminals.\n"
                f"Looked for: {bwrap_path() or 'bwrap'}",
                parent=self.frame,
            )
            return
        self.counter += 1
        home = self.app.session_home(self.module["id"], self.counter)
        session = TerminalSession(
            self.app,
            self.stack,
            self.module,
            self.workspace,
            home,
            allow_network=bool(self.network_var.get()),
        )
        session.frame.grid(row=0, column=0, sticky="nsew")
        self.sessions.append(session)
        self.select(session)
        session.focus()
        self.app.set_status(
            f"Started sandboxed terminal for module {self.module['num']:02d}"
            + (" (network shared)" if session.allow_network else "")
        )

    def select(self, session: TerminalSession, focus: bool = True) -> None:
        self.current = session
        session.frame.tkraise()
        self.refresh_selector()
        self.selector_var.set(session.label)
        self.close_button.state(["!disabled"])
        if focus:
            session.focus()

    def refresh_selector(self) -> None:
        self.selector.configure(values=[session.label for session in self.sessions])
        if self.current is not None:
            self.selector_var.set(self.current.label)

    def refresh_terminal_selector(self) -> None:
        self.refresh_selector()

    def _session_for_label(self, label: str) -> TerminalSession | None:
        for session in self.sessions:
            if session.label == label:
                return session
        return None

    def _select_from_combo(self, _event=None) -> None:
        session = self._session_for_label(self.selector_var.get())
        if session is not None:
            self.select(session)

    def close_current(self) -> None:
        session = self.current
        if session is None:
            return
        self.close_session(session)

    def close_session(self, session: TerminalSession) -> None:
        session.close()
        if session in self.sessions:
            self.sessions.remove(session)
        session.frame.destroy()
        self.current = None
        module_id = self.module["id"] if self.module else None
        for candidate in reversed(self.sessions):
            if module_id and candidate.module["id"] == module_id:
                self.select(candidate)
                return
        self.show_empty()

    def close_all(self) -> None:
        for session in list(self.sessions):
            session.close()
            session.frame.destroy()
        self.sessions.clear()
        self.current = None

    def poll_all(self) -> None:
        for session in list(self.sessions):
            session.poll()


# ---------------------------------------------------------------------------
# Files tab
# ---------------------------------------------------------------------------
class FilesPanel:
    def __init__(self, app: "StudyApp", parent) -> None:
        from tkinter import Text
        from tkinter import ttk

        self.app = app
        self.frame = ttk.Frame(parent, padding=(8, 6))
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)
        self.workspace: Path | None = None
        self.current_path: Path | None = None
        self.iids: dict[str, str] = {}

        toolbar = ttk.Frame(self.frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(toolbar, text="New file…", command=self.new_file).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(toolbar, text="Save", command=self.save).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Reload", command=self.reload).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Delete", command=self.delete).pack(side="left", padx=(6, 0))
        self.workspace_label = ttk.Label(toolbar, text="", style="Muted.TLabel")
        self.workspace_label.pack(side="right")

        paned = ttk.Panedwindow(self.frame, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(paned)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Workspace files", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll.grid(row=1, column=1, sticky="ns")
        self.tree.column("#0", width=300)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(left, weight=0)

        right = ttk.Frame(paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.path_label = ttk.Label(right, text="No file selected", style="Muted.TLabel")
        self.path_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.editor = Text(
            right,
            wrap="none",
            undo=True,
            font=(app.mono_family, max(7, app.base_size - 1)),
            borderwidth=1,
            relief="solid",
        )
        editor_y = ttk.Scrollbar(right, orient="vertical", command=self.editor.yview)
        editor_x = ttk.Scrollbar(right, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=editor_y.set, xscrollcommand=editor_x.set)
        self.editor.grid(row=1, column=0, sticky="nsew")
        editor_y.grid(row=1, column=1, sticky="ns")
        editor_x.grid(row=2, column=0, sticky="ew")
        self.editor.bind("<<Modified>>", self._on_modified)
        self.editor.bind("<Control-s>", lambda event: (self.save(), "break")[1])
        self.editor.bind("<Control-S>", lambda event: (self.save(), "break")[1])
        paned.add(right, weight=1)

        self.dirty = False
        self._loading = False

    def set_workspace(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.workspace_label.configure(text=str(workspace))
        self.current_path = None
        self.dirty = False
        self._loading = True
        self.editor.delete("1.0", "end")
        self.editor.edit_modified(False)
        self._loading = False
        self.path_label.configure(text="No file selected")
        self.refresh()

    def relative_files(self) -> list[Path]:
        if self.workspace is None or not self.workspace.is_dir():
            return []
        files: list[Path] = []
        for root, dirs, names in os.walk(self.workspace):
            dirs[:] = sorted(
                name
                for name in dirs
                if name not in {".git", "__pycache__", ".mypy_cache", ".pytest_cache"}
            )
            for name in sorted(names):
                if name.endswith(".fixtures-ready"):
                    continue
                path = Path(root) / name
                try:
                    if path.is_file() and not path.is_symlink():
                        files.append(path)
                except OSError:
                    continue
        return files

    def refresh(self) -> None:
        if self.workspace is None:
            return
        selected = self.current_path
        self.tree.delete(*self.tree.get_children())
        self.iids.clear()
        for path in self.relative_files():
            rel = path.relative_to(self.workspace).as_posix()
            iid = f"file::{rel}"
            try:
                size = human_size(path.stat().st_size)
            except OSError:
                size = "?"
            self.tree.insert("", "end", iid=iid, text=f"{rel}    ({size})")
            self.iids[rel] = iid
        if selected is not None:
            rel = selected.relative_to(self.workspace).as_posix()
            iid = self.iids.get(rel)
            if iid:
                self.tree.selection_set(iid)
                self.tree.see(iid)

    def _on_select(self, _event=None) -> None:
        from tkinter import messagebox

        selection = self.tree.selection()
        if not selection or self.workspace is None:
            return
        rel = selection[0][len("file::") :]
        path = self.workspace / rel
        if self.current_path == path:
            return
        if self.dirty and self.current_path is not None:
            answer = messagebox.askyesnocancel(
                "Unsaved changes",
                f"Save changes to {self.current_path.name}?",
                parent=self.frame,
            )
            if answer is None:
                if self.current_path is not None:
                    rel_old = self.current_path.relative_to(self.workspace).as_posix()
                    iid = self.iids.get(rel_old)
                    if iid:
                        self.tree.selection_set(iid)
                return
            if answer and not self.save():
                return
        self.open_path(path)

    def open_path(self, path: Path) -> None:
        from tkinter import messagebox

        try:
            stat = path.stat()
        except OSError as exc:
            messagebox.showerror("Cannot open", str(exc), parent=self.frame)
            return
        if stat.st_size > MAX_EDIT_BYTES:
            messagebox.showinfo(
                "File too large",
                f"{path.name} is {human_size(stat.st_size)}; the editor limit is "
                f"{human_size(MAX_EDIT_BYTES)}.",
                parent=self.frame,
            )
            return
        try:
            raw = path.read_bytes()
        except OSError as exc:
            messagebox.showerror("Cannot read", str(exc), parent=self.frame)
            return
        if b"\x00" in raw[:8192]:
            messagebox.showinfo(
                "Binary file",
                f"{path.name} looks binary; use a terminal command such as `file` "
                "or `xxd` to inspect it.",
                parent=self.frame,
            )
            return
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            messagebox.showinfo(
                "Unsupported encoding",
                f"{path.name} is not UTF-8 text. The editor only saves UTF-8; "
                "inspect or convert it in a terminal with `file` and `iconv`.",
                parent=self.frame,
            )
            return
        self._loading = True
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_modified(False)
        self._loading = False
        self.dirty = False
        self.current_path = path
        self.path_label.configure(text=str(path.relative_to(self.workspace or path.parent)))
        self.editor.focus_set()

    def reload(self) -> None:
        if self.current_path is not None:
            self.open_path(self.current_path)

    def save(self) -> bool:
        from tkinter import messagebox

        if self.current_path is None:
            return self.new_file()
        try:
            self.current_path.parent.mkdir(parents=True, exist_ok=True)
            self.current_path.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self.frame)
            return False
        self.editor.edit_modified(False)
        self.dirty = False
        if self.workspace is not None:
            self.path_label.configure(
                text=self.current_path.relative_to(self.workspace).as_posix()
            )
        self.app.set_status(f"Saved {self.current_path.name}")
        self.refresh()
        return True

    def new_file(self) -> bool:
        from tkinter import messagebox, simpledialog

        if self.workspace is None:
            return False
        name = simpledialog.askstring(
            "New file",
            "Relative path inside the workspace (for example scripts/report.py):",
            parent=self.frame,
        )
        if not name:
            return False
        rel = Path(name.strip())
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            messagebox.showerror(
                "Invalid path",
                "Enter a relative path inside the workspace, without '..'.",
                parent=self.frame,
            )
            return False
        path = self.workspace / rel
        if path.exists():
            messagebox.showerror("Already exists", f"{rel} already exists.", parent=self.frame)
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Cannot create file", str(exc), parent=self.frame)
            return False
        self.refresh()
        iid = self.iids.get(rel.as_posix())
        if iid:
            self.tree.selection_set(iid)
            self.tree.see(iid)
        self.open_path(path)
        return True

    def delete(self) -> None:
        from tkinter import messagebox

        if self.current_path is None:
            return
        name = self.current_path.name
        if not messagebox.askyesno(
            "Delete file", f"Delete {name} from the mission workspace?", parent=self.frame
        ):
            return
        try:
            self.current_path.unlink()
        except OSError as exc:
            messagebox.showerror("Cannot delete", str(exc), parent=self.frame)
            return
        self.current_path = None
        self.dirty = False
        self._loading = True
        self.editor.delete("1.0", "end")
        self.editor.edit_modified(False)
        self._loading = False
        self.path_label.configure(text="No file selected")
        self.refresh()
        self.app.set_status(f"Deleted {name}")

    def _on_modified(self, _event=None) -> None:
        if self._loading:
            self.editor.edit_modified(False)
            return
        if self.editor.edit_modified():
            self.dirty = True
            if self.current_path is not None and not self.path_label.cget("text").endswith("*"):
                self.path_label.configure(
                    text=str(self.current_path.relative_to(self.workspace or self.current_path.parent))
                    + " *"
                )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class StudyApp:
    def __init__(self, lab: str | None = None, module_key: str | None = None) -> None:
        import tkinter as tk
        from tkinter import StringVar
        from tkinter import font as tkfont
        from tkinter import ttk

        main.init_lab(lab)
        main.init_state()

        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(DEFAULT_GEOMETRY)
        self.root.minsize(1000, 640)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.base_font = tkfont.nametofont("TkDefaultFont")
        self.ui_family = self.base_font.actual("family")
        self.base_size = max(9, int(self.base_font.actual("size")))
        families = set(tkfont.families(self.root))
        self.mono_family = next(
            (
                name
                for name in (
                    "DejaVu Sans Mono",
                    "Liberation Mono",
                    "Noto Sans Mono",
                    "Courier New",
                )
                if name in families
            ),
            "TkFixedFont",
        )

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("ModuleTitle.TLabel", font=(self.ui_family, self.base_size + 3, "bold"))
        style.configure("Muted.TLabel", foreground="#626a72")
        style.configure("Prompt.TLabel", font=(self.mono_family, self.base_size, "bold"), foreground="#0b5394")
        style.configure("Done.Treeview", foreground="#1a7f37")
        style.configure("Part.Treeview", font=(self.ui_family, self.base_size, "bold"))

        self.renderer = MarkdownRenderer(self)
        self.network_var = StringVar(value="0")
        self.status_var = StringVar(value="")
        self._status_token = 0
        self._current_module: dict | None = None
        self._exam_display: dict[str, str] = {}
        self._save_by_display: dict[str, str] = {}
        self._module_iids: dict[str, str] = {}
        self._modules_by_iid: dict[str, dict] = {}
        self._closed = False
        self._after_ids: set[str] = set()

        self._build_ui()

        self.refresh_exams()
        self.refresh_saves()
        self.rebuild_modules(module_key)
        self._poll_terminals()
        self.later(200, self._focus_current)

    def later(self, delay: int, callback: Callable[[], None]) -> str:
        """Schedule a callback and remember it so shutdown can cancel it."""
        holder: dict[str, str] = {}

        def run() -> None:
            self._after_ids.discard(holder.get("id", ""))
            if not self._closed:
                callback()

        identifier = self.root.after(delay, run)
        holder["id"] = identifier
        self._after_ids.add(identifier)
        return identifier

    @property
    def exam(self):
        """The active exam (kept in sync by main's activation helpers)."""
        return main.ACTIVE_EXAM

    # -- construction ------------------------------------------------------
    def _build_ui(self) -> None:
        from tkinter import StringVar
        from tkinter import ttk

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=(10, 8, 10, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(6, weight=1)

        ttk.Label(header, text="CompTIA Study Lab", style="ModuleTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, text="Exam", style="Muted.TLabel").grid(
            row=0, column=1, padx=(18, 4)
        )
        self.exam_var = StringVar()
        self.exam_combo = ttk.Combobox(
            header, textvariable=self.exam_var, state="readonly", width=34
        )
        self.exam_combo.grid(row=0, column=2)
        self.exam_combo.bind("<<ComboboxSelected>>", self._on_exam_selected)

        ttk.Label(header, text="Save", style="Muted.TLabel").grid(
            row=0, column=3, padx=(14, 4)
        )
        self.save_var = StringVar()
        self.save_combo = ttk.Combobox(
            header, textvariable=self.save_var, state="readonly", width=18
        )
        self.save_combo.grid(row=0, column=4)
        self.save_combo.bind("<<ComboboxSelected>>", self._on_save_selected)
        ttk.Button(header, text="New save…", command=self.new_save).grid(
            row=0, column=5, padx=(6, 0)
        )

        progress = ttk.Frame(header)
        progress.grid(row=0, column=6, sticky="e")
        self.progress_bar = ttk.Progressbar(progress, length=180, mode="determinate")
        self.progress_bar.pack(side="left")
        self.progress_label = ttk.Label(progress, text="", style="Muted.TLabel")
        self.progress_label.pack(side="left", padx=(8, 0))
        ttk.Button(progress, text="Refresh", command=self.refresh_everything).pack(
            side="left", padx=(10, 0)
        )

        self.paned = ttk.Panedwindow(self.root, orient="horizontal")
        self.paned.grid(row=1, column=0, sticky="nsew", padx=10)

        left = ttk.Frame(self.paned)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Modules", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll.grid(row=1, column=1, sticky="ns")
        self.tree.column("#0", width=330)
        self.tree.tag_configure("done", foreground="#1a7f37")
        self.tree.tag_configure("part", font=(self.ui_family, self.base_size, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self._on_module_selected)
        self.paned.add(left, weight=0)

        right = ttk.Frame(self.paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(right)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.paned.add(right, weight=1)

        self.lesson_tab = LessonPanel(self, self.notebook)
        self.mission_tab = MissionPanel(self, self.notebook)
        self.terminal_tab = TerminalPanel(self, self.notebook)
        self.files_tab = FilesPanel(self, self.notebook)
        self.notebook.add(self.lesson_tab.frame, text="Lesson")
        self.notebook.add(self.mission_tab.frame, text="Mission")
        self.notebook.add(self.terminal_tab.frame, text="Terminal")
        self.notebook.add(self.files_tab.frame, text="Files")

        status = ttk.Frame(self.root, padding=(10, 3, 10, 6))
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        sandbox_text = (
            "bubblewrap sandbox ready · network isolated by default"
            if sandbox_available()
            else "bubblewrap missing: terminals disabled"
        )
        ttk.Label(status, text=sandbox_text, style="Muted.TLabel").grid(
            row=0, column=1, sticky="e"
        )

        self._build_menu()
        self.root.bind_all("<Control-Key-1>", lambda event: self.notebook.select(0))
        self.root.bind_all("<Control-Key-2>", lambda event: self.notebook.select(1))
        self.root.bind_all("<Control-Key-3>", lambda event: self.notebook.select(2))
        self.root.bind_all("<Control-Key-4>", lambda event: self.notebook.select(3))
        self.root.bind_all("<F5>", lambda event: self.mission_tab.verify())

    def _build_menu(self) -> None:
        import tkinter as tk

        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New save slot…", command=self.new_save)
        file_menu.add_command(label="Refresh", command=self.refresh_everything)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.close)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Lesson", command=lambda: self.notebook.select(0))
        view_menu.add_command(label="Mission", command=lambda: self.notebook.select(1))
        view_menu.add_command(label="Terminal", command=lambda: self.notebook.select(2))
        view_menu.add_command(label="Files", command=lambda: self.notebook.select(3))
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="How it works", command=self.show_about)
        help_menu.add_command(label="Environment status", command=self.show_doctor)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menubar)

    # -- exam, save, progress ---------------------------------------------
    def refresh_exams(self) -> None:
        exams = main.refresh_exams()
        active = main.ACTIVE_EXAM
        if active is not None:
            # ``load_exams`` builds fresh Exam objects (and fresh pack caches).
            # Re-point the active exam so later calls use the new objects.
            refreshed = main.get_exam(active.id, exams)
            if refreshed is not None:
                main.ACTIVE_EXAM = refreshed
                active = refreshed
        self._exam_display = {}
        for exam in exams:
            display = f"{exam.code or exam.id} — {exam.name}"
            self._exam_display[display] = exam.id
        values = list(self._exam_display)
        self.exam_combo.configure(values=values)
        for display, exam_id in self._exam_display.items():
            if active is not None and exam_id == active.id:
                self.exam_var.set(display)
                break
        else:
            if values:
                self.exam_var.set(values[0])

    def refresh_saves(self) -> None:
        assert main.SAVE_DIR is not None
        names = savefiles.list_save_names(main.SAVE_DIR)
        self._save_by_display = {name: name for name in names}
        self.save_combo.configure(values=names)
        self.save_var.set(main.SAVE_NAME)
        self.save_combo.configure(state="readonly" if names else "disabled")

    def _on_exam_selected(self, _event=None) -> None:
        exam_id = self._exam_display.get(self.exam_var.get())
        if not exam_id:
            return
        exam = main.get_exam(exam_id, main.EXAMS)
        if exam is None or (main.ACTIVE_EXAM is not None and exam.id == main.ACTIVE_EXAM.id):
            return
        main._activate_exam(exam)
        self.set_status(f"Switched to {exam.name}")
        self.rebuild_modules(None)

    def _on_save_selected(self, _event=None) -> None:
        name = self._save_by_display.get(self.save_var.get())
        if not name or name == main.SAVE_NAME:
            return
        try:
            main._activate_save(name)
        except (OSError, ValueError) as exc:
            self.error("Could not switch save", str(exc))
            self.refresh_saves()
            return
        self.set_status(f"Switched to save {name}")
        self.refresh_exams()
        self.refresh_saves()
        self.rebuild_modules(None)

    def new_save(self) -> None:
        from tkinter import simpledialog

        if main.SAVE_DIR is None or main.ACTIVE_EXAM is None:
            return
        name = simpledialog.askstring(
            "New save slot",
            "Name for the new save slot (letters, digits, dot, dash, underscore):",
            parent=self.root,
        )
        if not name:
            return
        try:
            normalized = savefiles.normalize_name(name)
            data = savefiles.create_save(main.SAVE_DIR, normalized, main.ACTIVE_EXAM.id)
        except (OSError, ValueError, FileExistsError) as exc:
            self.error("Could not create save", str(exc))
            return
        main._activate_save(data["name"])
        self.refresh_saves()
        self.rebuild_modules(None)
        self.set_status(f"Created save {data['name']}")

    def rebuild_modules(self, preferred_key: str | None) -> None:
        modules = main.current_modules()
        self.tree.delete(*self.tree.get_children())
        self._module_iids.clear()
        self._modules_by_iid.clear()

        if not modules:
            self._show_empty_exam()
            self.refresh_progress()
            return

        progress = main.load_progress()
        completed = set(progress.get("completed", {}))
        parts: dict[str, str] = {}
        for module in modules:
            part = module.get("part") or "Modules"
            if part not in parts:
                parts[part] = self.tree.insert(
                    "", "end", text=part, open=True, tags=("part",)
                )
            done = module["id"] in completed
            label = self._module_label(module, done)
            iid = f"m::{module['id']}"
            self.tree.insert(
                parts[part],
                "end",
                iid=iid,
                text=label,
                tags=("done",) if done else (),
            )
            self._module_iids[module["id"]] = iid
            self._modules_by_iid[iid] = module

        target = None
        if preferred_key:
            target = main.ACTIVE_EXAM.get_module(preferred_key) if main.ACTIVE_EXAM else None
        if target is None and self._current_module is not None:
            for module in modules:
                if module["id"] == self._current_module["id"]:
                    target = module
                    break
        if target is None:
            target = main.next_module() or modules[0]

        iid = self._module_iids.get(target["id"])
        if iid:
            self.tree.selection_set(iid)
            self.tree.see(iid)
        self.load_module(target)
        self.refresh_progress()

    def _module_label(self, module: dict, done: bool) -> str:
        mark = "✓" if done else " "
        return f"{module['num']:02d}  {module['title']}   {mark}"

    def _on_module_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        module = self._modules_by_iid.get(selection[0])
        if module is None:
            return
        if self._current_module is not None and self._current_module["id"] == module["id"]:
            return
        self.load_module(module)

    def load_module(self, module: dict) -> None:
        exam = main.ACTIVE_EXAM
        if exam is None:
            return
        mission = exam.get_mission(module["id"])
        if mission is not None:
            try:
                workspace = mission.prepare(main.exam_lab())
            except OSError as exc:
                self.error("Could not prepare the mission workspace", str(exc))
                workspace = main.exam_lab() / f"m{module['num']:02d}"
        else:
            workspace = main.exam_lab() / f"m{module['num']:02d}"
            workspace.mkdir(parents=True, exist_ok=True)
        self._current_module = module
        self.lesson_tab.set_module(module)
        self.mission_tab.set_module(module, mission, workspace)
        self.terminal_tab.set_module(module, workspace)
        self.files_tab.set_workspace(workspace)
        self.root.title(
            f"{WINDOW_TITLE} — {exam.code or exam.id} · module {module['num']:02d}"
        )

    def _show_empty_exam(self) -> None:
        exam = main.ACTIVE_EXAM
        self._current_module = None
        if exam is not None:
            self.root.title(f"{WINDOW_TITLE} — {exam.code or exam.id} · objectives only")
        title = "No curriculum yet"
        message = (
            f"{exam.name if exam else 'This exam'} is selectable and readable, but it "
            "does not have a curriculum pack.\n\n"
            f"Objectives: {exam.objectives_dir if exam else 'n/a'}\n\n"
            "Add a pack under exams/<exam-id>/pack/ with MODULES, get_mission(), and "
            "lesson_path(), or switch to a complete Linux+ pack."
        )
        self.lesson_tab.show_message(title, message)
        self.mission_tab.set_module(
            {"num": 0, "title": title, "domain": "", "id": "none"},
            None,
            main.exam_lab(),
        )
        self.terminal_tab.set_module(
            {"num": 0, "title": title, "id": "none"}, main.exam_lab()
        )
        self.files_tab.set_workspace(main.exam_lab())

    def refresh_progress(self) -> None:
        modules = main.current_modules()
        if not modules:
            self.progress_bar.configure(maximum=1, value=0)
            self.progress_label.configure(text="no modules")
            return
        completed = main.load_progress().get("completed", {})
        done = sum(1 for module in modules if module["id"] in completed)
        self.progress_bar.configure(maximum=len(modules), value=done)
        exam = main.ACTIVE_EXAM
        self.progress_label.configure(
            text=f"{done}/{len(modules)} missions · save {main.SAVE_NAME}"
        )
        for module in modules:
            iid = self._module_iids.get(module["id"])
            if not iid:
                continue
            is_done = module["id"] in completed
            self.tree.item(
                iid,
                text=self._module_label(module, is_done),
                tags=("done",) if is_done else (),
            )
        if exam is not None:
            self.root.title(
                f"{WINDOW_TITLE} — {exam.code or exam.id} · {done}/{len(modules)}"
            )

    def refresh_everything(self) -> None:
        self.refresh_exams()
        self.refresh_saves()
        self.rebuild_modules(None)
        self.set_status("Refreshed")

    # -- terminal helpers --------------------------------------------------
    def sandbox_hidden_paths(self) -> tuple[Path, ...]:
        """Host paths a terminal must never see, even under read-only roots."""
        paths: list[Path] = [main.PROGRAM_DIR]
        try:
            paths.append(main.save_directory())
        except OSError:
            pass
        if main.LAB is not None:
            paths.append(main.LAB)
        return tuple(paths)

    def session_home(self, module_id: str, counter: int) -> Path:
        root = main.exam_lab() / "_sandbox" / f"{module_id}-{counter}"
        for name in ("home", "tmp"):
            (root / name).mkdir(parents=True, exist_ok=True)
        return root / "home"

    def refresh_terminal_selector(self) -> None:
        self.terminal_tab.refresh_terminal_selector()

    def _poll_terminals(self) -> None:
        if self._closed:
            return
        try:
            self.terminal_tab.poll_all()
        except Exception:
            traceback.print_exc()
        self.later(60, self._poll_terminals)
    def _focus_current(self) -> None:
        if self.terminal_tab.current is not None:
            self.terminal_tab.current.focus()

    # -- tabs and status ---------------------------------------------------
    def show_files_tab(self) -> None:
        self.notebook.select(self.files_tab.frame)
        self.files_tab.refresh()

    def _on_tab_changed(self, _event=None) -> None:
        try:
            current = self.notebook.index(self.notebook.select())
        except Exception:
            return
        if current == 2:
            self.terminal_tab.refresh_selector()
        elif current == 3:
            self.files_tab.refresh()

    def set_status(self, message: str) -> None:
        self._status_token += 1
        token = self._status_token
        self.status_var.set(message)
        self.later(
            9000,
            lambda: self.status_var.set("")
            if token == self._status_token
            else None,
        )

    def error(self, title: str, message: str) -> None:
        from tkinter import messagebox

        messagebox.showerror(title, message, parent=self.root)

    def run_background(
        self,
        work: Callable[[], object],
        done: Callable[[object], None],
        failed: Callable[[BaseException], None],
    ) -> None:
        results: queue.Queue[tuple[str, object]] = queue.Queue()

        def runner() -> None:
            try:
                results.put(("ok", work()))
            except BaseException as exc:  # noqa: BLE001 - reported to the UI
                results.put(("error", exc))

        threading.Thread(target=runner, daemon=True).start()

        def poll() -> None:
            if self._closed:
                return
            try:
                kind, value = results.get_nowait()
            except queue.Empty:
                self.later(80, poll)
                return
            if kind == "ok":
                done(value)
            else:
                failed(value)  # type: ignore[arg-type]

        self.later(80, poll)

    def show_about(self) -> None:
        from tkinter import messagebox

        messagebox.showinfo(
            "How the GUI works",
            "• Lesson: the written module, rendered from Markdown.\n"
            "• Mission: the brief, hints, verification, and reference solution.\n"
            "• Terminal: persistent shells inside bubblewrap. The mission folder "
            "is mounted at /workspace; your real home, the project folder, and "
            "removable media are hidden. Network is isolated unless enabled.\n"
            "• Files: edit workspace files directly, because nano/vim need a "
            "full-screen terminal.\n\n"
            "Verification runs on the host against the same workspace files, so "
            "commands and edits made in the sandbox are checked for real.\n\n"
            "Keyboard: Ctrl-1…4 switch tabs, F5 verifies, Ctrl-S saves a file.",
            parent=self.root,
        )

    def show_doctor(self) -> None:
        from tkinter import Text, Toplevel

        lines = [
            f"Python: {sys.version.split()[0]}",
            f"Program: {main.PROGRAM_DIR}",
            f"Lab: {main.LAB}",
            f"Lab note: {main.LAB_NOTE or '(none)'}",
            f"Exam: {main.ACTIVE_EXAM.name if main.ACTIVE_EXAM else '(none)'}",
            f"Save: {main.SAVE_NAME} ({main.SAVE_DIR})",
            f"bubblewrap: {bwrap_path() or 'not installed'}",
            f"Lab supports permissions: {'yes' if main.permissions_supported(main.LAB)[0] else 'no'}",
        ]
        win = Toplevel(self.root)
        win.title("Environment status")
        win.geometry("760x420")
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        text = Text(win, wrap="word", font=(self.mono_family, self.base_size))
        text.grid(row=0, column=0, sticky="nsew")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    # -- shutdown ----------------------------------------------------------
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            for identifier in list(self._after_ids):
                try:
                    self.root.after_cancel(identifier)
                except Exception:
                    pass
            self._after_ids.clear()
            self.terminal_tab.close_all()
        finally:
            self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def check() -> int:
    """Print GUI prerequisites without opening a window."""
    print("GUI prerequisites")
    print("-" * 60)
    print(f"  Python:      {sys.version.split()[0]}")
    try:
        import tkinter  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"  [!!] Tkinter:  {exc}")
        return 1
    print("  [ok] Tkinter:   available")
    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    print(
        f"  [{'ok' if display else '!!'}] Display:   {display or 'not set (GUI needs X11 or Wayland)'}"
    )
    executable = bwrap_path()
    print(
        f"  [{'ok' if executable else '!!'}] bubblewrap: {executable or 'not installed (terminals disabled)'}"
    )
    if executable:
        try:
            with tempfile.TemporaryDirectory(prefix="linuxplus-gui-check-") as temporary:
                root = Path(temporary)
                config = SandboxConfig(root / "workspace", root / "home")
                ok, message = config.validate()
            print(f"  [{'ok' if ok else '!!'}] Sandbox:   {message}")
            if not ok:
                return 1
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"  [!!] Sandbox:   {exc}")
            return 1
    print("-" * 60)
    return 0 if executable and display else 1


def launch(lab: str | None = None, module_key: str | None = None) -> int:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print(
            "No graphical display found. Set DISPLAY (X11) or WAYLAND_DISPLAY, "
            "or use the CLI: python3 main.py list",
            file=sys.stderr,
        )
        return 1
    try:
        app = StudyApp(lab=lab, module_key=module_key)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        return 1
    return app.run()


def _direct_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gui.py",
        description="Graphical CompTIA Study Lab with sandboxed terminals.",
    )
    parser.add_argument("--lab", metavar="DIR", help="override the lab workspace")
    parser.add_argument("--module", help="module number or id to open")
    parser.add_argument(
        "--check", action="store_true", help="check GUI prerequisites and exit"
    )
    args = parser.parse_args(argv)
    if args.check:
        return check()
    return launch(lab=args.lab, module_key=args.module)


if __name__ == "__main__":
    sys.exit(_direct_main())
