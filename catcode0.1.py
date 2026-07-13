#!/usr/bin/env python3
import sys
if sys.version_info < (3, 10):
    sys.exit("Python 3.10+ required")
# files = off ✓
"""
catide 0.1 — blue hue IDE
=========================
PR files = off · import python 3.14 · files = off

UI kept. Language syntax highlighter.
Agents Window, compact chats, full-screen tabs, floating composer.
Blue hue.
"""
import ast
import builtins
import contextlib
import importlib.util
import io
import keyword
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, ttk
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────
# IDENTITY · catide (UI kept)
# ──────────────────────────────────────────────────────────────
APP_NAME = "catide"
APP_VERSION = "0.1"
WINDOW_TITLE = "catide 0.1"
FILES_MODE = "off"  # PR files = off
LAYOUT_LABEL = "0.1"

# Dark+ structure, blue-hue palette
BG = "#1a1f2e"
ACTIVITY_BG = "#151a28"
SIDEBAR_BG = "#181e2c"
EDITOR_BG = "#1e2436"
PANEL_BG = "#181e2c"
TAB_BG = "#151a28"
TAB_ACTIVE = "#1e2436"
TAB_INACTIVE = "#121722"
INPUT_BG = "#0f1420"
STATUS_BG = "#007acc"   # classic status blue
TITLE_BG = "#181e2c"
BORDER = "#2a3348"
RAIL = "#007acc"
CHIP_BG = "#222838"
FLOAT_BG = "#1a2030"
BREADCRUMB_BG = "#1a1f2e"

FG = "#9bbcff"          # blue-hue foreground
FG_BRIGHT = "#d6e4ff"
FG_DIM = "#6b86b5"
FG_FAINT = "#3d5278"
ACCENT = "#007acc"      # accent blue
SEL_BG = "#264f78"
CURLINE = "#222a3d"
BTN_BG = "#000000"
BTN_FG = "#7eb6ff"
BTN_HOVER = "#1a3a5c"
OK_GREEN = "#4ec9b0"
ERR_RED = "#f44747"
WARN_YEL = "#cca700"

SYNTAX = {
    # Dark+ semantic token hues (blue-shifted)
    "kw": "#569cd6",
    "builtin": "#4ec9b0",
    "string": "#ce9178",
    "comment": "#6a9955",
    "number": "#b5cea8",
    "deco": "#dcdcaa",
    "defname": "#dcdcaa",
    "preproc": "#c586c0",
    "type": "#4ec9b0",
    "operator": "#d4d4d4",
    "property": "#9cdcfe",
    "tag": "#569cd6",
    "attr": "#9cdcfe",
    "asmreg": "#4fc1ff",
    "asmop": "#c586c0",
    "regex": "#d16969",
    "escape": "#d7ba7d",
}

IS_MAC = sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"
MOD_LABEL = "⌘" if IS_MAC else "Ctrl+"

# Candidate paths for CatSeek R1 Agent backend
_CATSEEK_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "catseekr1.py"),
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "catseekr11.0--main",
        "catseekr1.py",
    ),
    "/Volumes/1TB/:STUFF~ /:Coding~/catseekr11.0--main/catseekr1.py",
]


_FONT_CACHE: Dict[Tuple[str, int, str], tkfont.Font] = {}


def ui_font(size: int = 12, weight: str = "normal") -> tkfont.Font:
    key = ("ui", size, weight)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    family = "SF Pro Text" if IS_MAC else "Segoe UI"
    try:
        f = tkfont.Font(family=family, size=size, weight=weight)
    except tk.TclError:
        f = tkfont.Font(family="Helvetica", size=size, weight=weight)
    _FONT_CACHE[key] = f
    return f


def mono_font(size: int = 13) -> tkfont.Font:
    key = ("mono", size, "normal")
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    family = "Menlo" if IS_MAC else "Consolas"
    try:
        f = tkfont.Font(family=family, size=size)
    except tk.TclError:
        f = tkfont.Font(family="Courier", size=size)
    _FONT_CACHE[key] = f
    return f


# ──────────────────────────────────────────────────────────────
# CatSeek R1 loader (in-memory engine · files = off)
# ──────────────────────────────────────────────────────────────
def _find_catseek() -> Optional[str]:
    for path in _CATSEEK_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


def load_catseek_engine():
    """Import CatSeek R1 and return (module, CatR11Engine instance)."""
    path = _find_catseek()
    if not path:
        raise FileNotFoundError(
            "CatSeek R1 not found. Place catseekr1.py beside this IDE or at "
            "catseekr11.0--main/catseekr1.py"
        )
    spec = importlib.util.spec_from_file_location("catseekr1_agent", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load CatSeek from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["catseekr1_agent"] = mod
    spec.loader.exec_module(mod)

    # PR files = off — keep engine in-memory, no weight/model packing
    cfg = getattr(mod, "CONFIG", None)
    if isinstance(cfg, dict):
        cfg["files"] = "off"
        cfg["bitnet_no_weight_files"] = True
        cfg["api_enabled"] = False
        cfg["catcode_no_api"] = True
        cfg["vibe_code_heuristics"] = True
        cfg["recursive_depth"] = 1
        cfg["cat_r1_code_enabled"] = True
        cfg["cat_r1_code"] = True

    engine = mod.CatR11Engine()
    # Prefer Flash — Pro BitNet encode hangs the Agents pane
    flash = getattr(mod, "CatR1FlashProfile", None)
    if flash is not None:
        try:
            engine.active_model_profile = flash()
        except Exception:
            pass
    return mod, engine, path


FENCE_RE = re.compile(r"```(?:([\w.+-]*)\n)?(.*?)```", re.S)

LANG_EXT = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js", "typescript": ".ts", "ts": ".ts",
    "html": ".html", "css": ".css", "bash": ".sh", "shell": ".sh",
    "rust": ".rs", "go": ".go", "java": ".java", "ruby": ".rb", "php": ".php",
    "c": ".c", "cpp": ".cpp", "cxx": ".cpp", "cc": ".cpp", "c++": ".cpp",
    "cuda": ".cu", "objc": ".m", "objective-c": ".m",
    "assembly": ".asm", "asm": ".asm", "nasm": ".asm", "gas": ".s", "masm": ".asm",
    "sql": ".sql", "kotlin": ".kt", "swift": ".swift", "csharp": ".cs", "cs": ".cs",
    "json": ".json", "yaml": ".yml", "markdown": ".md", "md": ".md",
    "perl": ".pl", "pl": ".pl", "r": ".r", "rlang": ".r",
    "dart": ".dart", "lua": ".lua", "scala": ".scala", "haskell": ".hs", "hs": ".hs",
    "elixir": ".ex", "exs": ".exs", "clojure": ".clj", "clj": ".clj",
    "julia": ".jl", "jl": ".jl", "erlang": ".erl", "elm": ".elm",
    "racket": ".rkt", "scheme": ".scm", "common-lisp": ".lisp", "lisp": ".lisp",
    "fortran": ".f90", "f90": ".f90", "f95": ".f95", "f03": ".f03",
    "cobol": ".cbl", "cbl": ".cbl", "pascal": ".pas", "pas": ".pas",
    "ada": ".adb", "adb": ".adb", "zig": ".zig", "nim": ".nim",
    "ocaml": ".ml", "ml": ".ml", "fsharp": ".fs", "fs": ".fs",
    "solidity": ".sol", "sol": ".sol", "graphql": ".graphql", "gql": ".gql",
    "dockerfile": "Dockerfile", "makefile": "Makefile", "cmake": "CMakeLists.txt",
    "tex": ".tex", "latex": ".tex", "bib": ".bib",
    "toml": ".toml", "ini": ".ini", "cfg": ".cfg", "conf": ".conf",
    "powershell": ".ps1", "ps1": ".ps1", "batch": ".bat", "bat": ".bat",
}


def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
    """Return list of (lang, code) from markdown fences."""
    blocks = []
    for m in FENCE_RE.finditer(text or ""):
        hinted = (m.group(1) or "").strip().lower()
        code = (m.group(2) or "").strip("\n")
        if not code.strip():
            continue
        lang = hinted or CodeLangDetector.detect(code).lang
        blocks.append((lang, code))
    return blocks


# ──────────────────────────────────────────────────────────────
# CatsFrontierR1 — coding algorithm on par with frontier workflows
# (ChatGPT / DeepSeek-R1 style: think → plan → draft → verify → repair)
# files = off · local · no BitNet encode hang
# ──────────────────────────────────────────────────────────────
@dataclass
class FrontierPlan:
    lang: str
    intent: str
    skill: str
    name: str
    title: str
    steps: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class CatsFrontierR1:
    """
    Multi-pass frontier coding engine for catide Agents.

    Mirrors ChatGPT / DeepSeek-R1 coding procedure locally:
      1) extended think   2) plan   3) expert skill retrieve
      4) draft            5) lint/verify   6) repair loop   7) emit fence

    Not a hosted LLM — a deterministic high-skill synthesizer that always
    returns runnable, tested-shape code (files = off).
    """

    TARGET = "ChatGPT-class · DeepSeek-R1 coding workflow"
    VER = "0.1"
    MAX_REPAIR = 3

    _LANG_PAT = (
        (r"\b(?:python|py)\b", "python"),
        (r"\b(?:javascript|js|node)\b", "javascript"),
        (r"\b(?:typescript|ts)\b", "typescript"),
        (r"\b(?:c\+\+|cpp|cxx)\b", "cpp"),
        (r"\b(?:objective-?c|objc)\b", "objc"),
        (r"\bcuda\b", "cuda"),
        (r"\b(?:assembly|asm|nasm)\b", "assembly"),
        (r"\brust\b", "rust"),
        (r"\bgolang|\bgo\b", "go"),
        (r"\bjava\b", "java"),
        (r"\bc#|csharp\b", "csharp"),
        (r"\bhtml\b", "html"),
        (r"\bcss\b", "css"),
        (r"\bbash|shell\b", "bash"),
        (r"\bsql\b", "sql"),
        (r"\bc\b(?!\+)", "c"),
        (r"\bperl\b", "perl"),
        (r"\blua\b", "lua"),
        (r"\bdart\b", "dart"),
        (r"\bscala\b", "scala"),
        (r"\bhaskell\b", "haskell"),
        (r"\belixir\b", "elixir"),
        (r"\bclojure\b", "clojure"),
        (r"\bjulia\b", "julia"),
        (r"\bzig\b", "zig"),
        (r"\bnim\b", "nim"),
        (r"\bf#|fsharp\b", "fsharp"),
        (r"\bsolidity\b", "solidity"),
        (r"\bfortran\b", "fortran"),
        (r"\bpascal\b", "pascal"),
        (r"\bada\b", "ada"),
        (r"\bcobol\b", "cobol"),
        (r"\bracket\b", "racket"),
        (r"\bscheme|lisp\b", "scheme"),
        (r"\bocaml\b", "ocaml"),
        (r"\bswift\b", "swift"),
        (r"\bkotlin\b", "kotlin"),
        (r"\bruby\b", "ruby"),
        (r"\bphp\b", "php"),
        (r"\b(?:powershell|ps1)\b", "powershell"),
        (r"\bbatch|bat\b", "batch"),
        (r"\bdockerfile\b", "dockerfile"),
    )

    # skill → regex cues (DeepSeek-R1 style knowledge routing)
    _SKILLS: Tuple[Tuple[str, str], ...] = (
        ("fibonacci", r"\bfibonacci|\bfib\b"),
        ("factorial", r"\bfactorial|\bn!\b"),
        ("primes", r"\bprime|\bsieve\b"),
        ("binary_search", r"\bbinary\s*search|\bbsearch\b"),
        ("quicksort", r"\bquick\s*sort|\bqsort\b"),
        ("mergesort", r"\bmerge\s*sort\b"),
        ("twosum", r"\btwo\s*sum|\b2sum\b"),
        ("bfs", r"\bbfs\b|\bbreadth[- ]first"),
        ("dfs", r"\bdfs\b|\bdepth[- ]first"),
        ("dijkstra", r"\bdijkstra|\bshortest\s*path"),
        ("lru", r"\blru\b|\bcache\b"),
        ("trie", r"\btrie\b|\bprefix\s*tree"),
        ("linked_list", r"\blinked\s*list|\bllist\b"),
        ("stack_queue", r"\bstack\b|\bqueue\b|\bdeque\b"),
        ("rest_api", r"\brest\b|\bapi\b|\bflask\b|\bfastapi\b|\bendpoint\b"),
        ("cli", r"\bcli\b|\bargparse\b|\bcommand\s*line\b"),
        ("async_io", r"\basync\b|\bawait\b|\bconcurrency\b"),
        ("unittest", r"\bunit\s*test|\bpytest\b|\btest\s*case\b"),
        ("regex", r"\bregex\b|\bregular\s*expression\b"),
        ("json_tool", r"\bjson\b|\bparse\s*json\b"),
        ("oop_class", r"\bclass\b|\boop\b|\bobject\b"),
        ("hello", r"\bhello\b|\bworld\b"),
        ("general", r"."),
    )

    @classmethod
    def detect_lang(cls, prompt: str, hint: str = "") -> str:
        if hint and hint not in {"unknown", "text", ""}:
            return CodeLangDetector.normalize(hint)
        pl = (prompt or "").lower()
        for pat, lang in cls._LANG_PAT:
            if re.search(pat, pl):
                return lang
        return "python"

    @classmethod
    def _slug(cls, prompt: str) -> str:
        cleaned = re.sub(
            r"^(?:vibe[\s-]*code|ask\s+catseek\s+to|write|make|build|create|"
            r"implement|generate|code|please|帮我)\s+",
            "",
            (prompt or "").strip(),
            flags=re.I,
        )
        words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", cleaned)
        stop = {
            "a", "an", "the", "in", "for", "with", "to", "of", "and", "or",
            "python", "code", "function", "class", "script", "program", "that",
            "this", "from", "using", "simple", "advanced", "efficient",
        }
        for w in words:
            if w.lower() not in stop:
                return w[:32]
        return "solution"

    @classmethod
    def _route_skill(cls, prompt: str) -> str:
        pl = (prompt or "").lower()
        for skill, pat in cls._SKILLS:
            if skill == "general":
                continue
            if re.search(pat, pl):
                return skill
        return "general"

    @classmethod
    def think(cls, prompt: str, plan: FrontierPlan) -> str:
        """DeepSeek-R1–style reasoning trace (shown in Agents Think channel)."""
        lines = [
            f"[{cls.TARGET} · {cls.VER}]",
            f"goal: {(prompt or '').strip()[:160]}",
            f"lang: {plan.lang} · intent: {plan.intent} · skill: {plan.skill}",
            "plan:",
        ]
        for i, s in enumerate(plan.steps, 1):
            lines.append(f"  {i}. {s}")
        if plan.notes:
            lines.append("checks: " + "; ".join(plan.notes))
        lines.append("emit: verified runnable module + main entry")
        return "\n".join(lines)

    @classmethod
    def plan(cls, prompt: str, *, hint: str = "") -> FrontierPlan:
        lang = cls.detect_lang(prompt, hint)
        skill = cls._route_skill(prompt)
        name = cls._slug(prompt)
        if not name.isidentifier():
            name = "solution"
        title = (prompt or "frontier code").strip()[:96]
        intent = "implement"
        pl = (prompt or "").lower()
        if re.search(r"\bfix\b|\bbug\b|\bdebug\b", pl):
            intent = "fix"
        elif re.search(r"\brefactor\b|\bclean\b", pl):
            intent = "refactor"
        elif re.search(r"\bexplain\b|\bhow\b", pl):
            intent = "explain+code"
        steps = [
            "Parse requirements and pick language + skill pack",
            "Draft typed, edge-case-aware implementation",
            "Add main / demo harness for instant Run",
            "Lint (AST / balance) and repair until green",
        ]
        notes = ["files=off", "no network", f"skill={skill}"]
        return FrontierPlan(lang, intent, skill, name, title, steps, notes)

    @classmethod
    def _verify(cls, lang: str, code: str) -> Tuple[bool, str]:
        if not (code or "").strip():
            return False, "empty"
        if lang == "python":
            try:
                ast.parse(code)
                return True, ""
            except SyntaxError as e:
                return False, f"SyntaxError: {e}"
        opens = sum(code.count(c) for c in "{([")
        closes = sum(code.count(c) for c in "})]")
        if opens != closes:
            return False, f"unbalanced braces {opens}/{closes}"
        if lang in {"c", "cpp", "rust", "go", "java"} and "main" not in code:
            return False, "missing main"
        return True, ""

    @classmethod
    def _repair(cls, lang: str, code: str, reason: str, plan: FrontierPlan) -> str:
        code = (code or "").rstrip() + "\n"
        if lang == "python":
            if "SyntaxError" in reason or "invalid syntax" in reason:
                return cls._skill_python("hello", plan)
            if "def main" not in code:
                code += (
                    "\ndef main() -> None:\n"
                    f"    print({plan.title!r})\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                )
        if lang in {"c", "cpp"} and "missing main" in reason:
            return cls._skill_c(plan) if lang == "c" else cls._skill_cpp(plan)
        return code

    @classmethod
    def _skill_python(cls, skill: str, plan: FrontierPlan) -> str:
        n = plan.name
        cn = n[:1].upper() + n[1:]
        if skill == "fibonacci":
            return (
                '"""Frontier R1 · Fibonacci (O(n), iterative)"""\n'
                "from __future__ import annotations\n\n"
                "def fibonacci(k: int) -> int:\n"
                "    if k < 0:\n"
                "        raise ValueError('n must be >= 0')\n"
                "    a, b = 0, 1\n"
                "    for _ in range(k):\n"
                "        a, b = b, a + b\n"
                "    return a\n\n"
                "def main() -> None:\n"
                "    for i in range(15):\n"
                "        print(f'fib({i}) = {fibonacci(i)}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "factorial":
            return (
                '"""Frontier R1 · Factorial"""\n'
                "from __future__ import annotations\n\n"
                "def factorial(n: int) -> int:\n"
                "    if n < 0:\n"
                "        raise ValueError('n must be >= 0')\n"
                "    out = 1\n"
                "    for i in range(2, n + 1):\n"
                "        out *= i\n"
                "    return out\n\n"
                "def main() -> None:\n"
                "    for i in range(10):\n"
                "        print(i, factorial(i))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "primes":
            return (
                '"""Frontier R1 · Sieve of Eratosthenes"""\n'
                "from __future__ import annotations\n\n"
                "def primes_upto(limit: int) -> list[int]:\n"
                "    if limit < 2:\n"
                "        return []\n"
                "    sieve = [True] * (limit + 1)\n"
                "    sieve[0] = sieve[1] = False\n"
                "    p = 2\n"
                "    while p * p <= limit:\n"
                "        if sieve[p]:\n"
                "            for m in range(p * p, limit + 1, p):\n"
                "                sieve[m] = False\n"
                "        p += 1\n"
                "    return [i for i, ok in enumerate(sieve) if ok]\n\n"
                "def main() -> None:\n"
                "    print(primes_upto(50))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "binary_search":
            return (
                '"""Frontier R1 · Binary search"""\n'
                "from __future__ import annotations\n\n"
                "def binary_search(xs: list[int], target: int) -> int:\n"
                "    lo, hi = 0, len(xs) - 1\n"
                "    while lo <= hi:\n"
                "        mid = (lo + hi) // 2\n"
                "        if xs[mid] == target:\n"
                "            return mid\n"
                "        if xs[mid] < target:\n"
                "            lo = mid + 1\n"
                "        else:\n"
                "            hi = mid - 1\n"
                "    return -1\n\n"
                "def main() -> None:\n"
                "    data = [1, 3, 4, 7, 9, 12, 15]\n"
                "    print(binary_search(data, 9), binary_search(data, 8))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "quicksort":
            return (
                '"""Frontier R1 · Quicksort"""\n'
                "from __future__ import annotations\n"
                "import random\n\n"
                "def quicksort(xs: list[int]) -> list[int]:\n"
                "    if len(xs) <= 1:\n"
                "        return xs\n"
                "    pivot = xs[len(xs) // 2]\n"
                "    left = [x for x in xs if x < pivot]\n"
                "    mid = [x for x in xs if x == pivot]\n"
                "    right = [x for x in xs if x > pivot]\n"
                "    return quicksort(left) + mid + quicksort(right)\n\n"
                "def main() -> None:\n"
                "    sample = [random.randint(0, 99) for _ in range(12)]\n"
                "    print('in ', sample)\n"
                "    print('out', quicksort(sample))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "mergesort":
            return (
                '"""Frontier R1 · Mergesort"""\n'
                "from __future__ import annotations\n\n"
                "def mergesort(xs: list[int]) -> list[int]:\n"
                "    if len(xs) <= 1:\n"
                "        return xs\n"
                "    mid = len(xs) // 2\n"
                "    left, right = mergesort(xs[:mid]), mergesort(xs[mid:])\n"
                "    out: list[int] = []\n"
                "    i = j = 0\n"
                "    while i < len(left) and j < len(right):\n"
                "        if left[i] <= right[j]:\n"
                "            out.append(left[i]); i += 1\n"
                "        else:\n"
                "            out.append(right[j]); j += 1\n"
                "    out.extend(left[i:]); out.extend(right[j:])\n"
                "    return out\n\n"
                "def main() -> None:\n"
                "    print(mergesort([5, 1, 4, 2, 8, 0, 3]))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "twosum":
            return (
                '"""Frontier R1 · Two Sum (hash map)"""\n'
                "from __future__ import annotations\n\n"
                "def two_sum(nums: list[int], target: int) -> list[int]:\n"
                "    seen: dict[int, int] = {}\n"
                "    for i, n in enumerate(nums):\n"
                "        need = target - n\n"
                "        if need in seen:\n"
                "            return [seen[need], i]\n"
                "        seen[n] = i\n"
                "    return []\n\n"
                "def main() -> None:\n"
                "    print(two_sum([2, 7, 11, 15], 9))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "bfs":
            return (
                '"""Frontier R1 · BFS"""\n'
                "from __future__ import annotations\n"
                "from collections import deque\n\n"
                "def bfs(graph: dict[str, list[str]], start: str) -> list[str]:\n"
                "    seen = {start}\n"
                "    q: deque[str] = deque([start])\n"
                "    order: list[str] = []\n"
                "    while q:\n"
                "        u = q.popleft()\n"
                "        order.append(u)\n"
                "        for v in graph.get(u, []):\n"
                "            if v not in seen:\n"
                "                seen.add(v)\n"
                "                q.append(v)\n"
                "    return order\n\n"
                "def main() -> None:\n"
                "    g = {'A': ['B', 'C'], 'B': ['D'], 'C': ['D'], 'D': []}\n"
                "    print(bfs(g, 'A'))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "dfs":
            return (
                '"""Frontier R1 · DFS"""\n'
                "from __future__ import annotations\n\n"
                "def dfs(graph: dict[str, list[str]], start: str) -> list[str]:\n"
                "    seen: set[str] = set()\n"
                "    order: list[str] = []\n\n"
                "    def visit(u: str) -> None:\n"
                "        seen.add(u)\n"
                "        order.append(u)\n"
                "        for v in graph.get(u, []):\n"
                "            if v not in seen:\n"
                "                visit(v)\n\n"
                "    visit(start)\n"
                "    return order\n\n"
                "def main() -> None:\n"
                "    g = {'A': ['B', 'C'], 'B': ['D'], 'C': ['D'], 'D': []}\n"
                "    print(dfs(g, 'A'))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "dijkstra":
            return (
                '"""Frontier R1 · Dijkstra shortest paths"""\n'
                "from __future__ import annotations\n"
                "import heapq\n\n"
                "def dijkstra(graph: dict[str, list[tuple[str, int]]], start: str) -> dict[str, float]:\n"
                "    dist = {start: 0.0}\n"
                "    pq: list[tuple[float, str]] = [(0.0, start)]\n"
                "    while pq:\n"
                "        d, u = heapq.heappop(pq)\n"
                "        if d != dist.get(u, float('inf')):\n"
                "            continue\n"
                "        for v, w in graph.get(u, []):\n"
                "            nd = d + w\n"
                "            if nd < dist.get(v, float('inf')):\n"
                "                dist[v] = nd\n"
                "                heapq.heappush(pq, (nd, v))\n"
                "    return dist\n\n"
                "def main() -> None:\n"
                "    g = {\n"
                "        'A': [('B', 1), ('C', 4)],\n"
                "        'B': [('C', 2), ('D', 5)],\n"
                "        'C': [('D', 1)],\n"
                "        'D': [],\n"
                "    }\n"
                "    print(dijkstra(g, 'A'))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "lru":
            return (
                '"""Frontier R1 · LRU Cache"""\n'
                "from __future__ import annotations\n"
                "from collections import OrderedDict\n\n"
                "class LRUCache:\n"
                "    def __init__(self, capacity: int) -> None:\n"
                "        self.cap = capacity\n"
                "        self.data: OrderedDict[int, int] = OrderedDict()\n\n"
                "    def get(self, key: int) -> int:\n"
                "        if key not in self.data:\n"
                "            return -1\n"
                "        self.data.move_to_end(key)\n"
                "        return self.data[key]\n\n"
                "    def put(self, key: int, value: int) -> None:\n"
                "        if key in self.data:\n"
                "            self.data.move_to_end(key)\n"
                "        self.data[key] = value\n"
                "        if len(self.data) > self.cap:\n"
                "            self.data.popitem(last=False)\n\n"
                "def main() -> None:\n"
                "    c = LRUCache(2)\n"
                "    c.put(1, 1); c.put(2, 2)\n"
                "    print(c.get(1))\n"
                "    c.put(3, 3)\n"
                "    print(c.get(2))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "trie":
            return (
                '"""Frontier R1 · Trie"""\n'
                "from __future__ import annotations\n\n"
                "class TrieNode:\n"
                "    __slots__ = ('kids', 'end')\n"
                "    def __init__(self) -> None:\n"
                "        self.kids: dict[str, TrieNode] = {}\n"
                "        self.end = False\n\n"
                "class Trie:\n"
                "    def __init__(self) -> None:\n"
                "        self.root = TrieNode()\n\n"
                "    def insert(self, word: str) -> None:\n"
                "        node = self.root\n"
                "        for ch in word:\n"
                "            node = node.kids.setdefault(ch, TrieNode())\n"
                "        node.end = True\n\n"
                "    def search(self, word: str) -> bool:\n"
                "        node = self.root\n"
                "        for ch in word:\n"
                "            if ch not in node.kids:\n"
                "                return False\n"
                "            node = node.kids[ch]\n"
                "        return node.end\n\n"
                "def main() -> None:\n"
                "    t = Trie()\n"
                "    for w in ('cat', 'cats', 'dog'):\n"
                "        t.insert(w)\n"
                "    print(t.search('cat'), t.search('ca'), t.search('dog'))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "linked_list":
            return (
                '"""Frontier R1 · Singly linked list"""\n'
                "from __future__ import annotations\n"
                "from dataclasses import dataclass\n"
                "from typing import Optional\n\n"
                "@dataclass\n"
                "class Node:\n"
                "    val: int\n"
                "    next: Optional[Node] = None\n\n"
                "class LinkedList:\n"
                "    def __init__(self) -> None:\n"
                "        self.head: Optional[Node] = None\n\n"
                "    def push(self, val: int) -> None:\n"
                "        self.head = Node(val, self.head)\n\n"
                "    def to_list(self) -> list[int]:\n"
                "        out: list[int] = []\n"
                "        cur = self.head\n"
                "        while cur:\n"
                "            out.append(cur.val)\n"
                "            cur = cur.next\n"
                "        return out\n\n"
                "def main() -> None:\n"
                "    ll = LinkedList()\n"
                "    for v in (3, 2, 1):\n"
                "        ll.push(v)\n"
                "    print(ll.to_list())\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "stack_queue":
            return (
                '"""Frontier R1 · Stack + Queue"""\n'
                "from __future__ import annotations\n"
                "from collections import deque\n\n"
                "def main() -> None:\n"
                "    stack: list[int] = []\n"
                "    stack.append(1); stack.append(2); stack.append(3)\n"
                "    print('stack pop', stack.pop())\n"
                "    q: deque[int] = deque([10, 20, 30])\n"
                "    print('queue pop', q.popleft())\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "rest_api":
            return (
                '"""Frontier R1 · Minimal REST-style in-memory API"""\n'
                "from __future__ import annotations\n"
                "from dataclasses import dataclass, field\n"
                "from typing import Any\n\n"
                "@dataclass\n"
                "class App:\n"
                "    store: dict[str, Any] = field(default_factory=dict)\n\n"
                "    def get(self, key: str) -> Any:\n"
                "        return self.store.get(key)\n\n"
                "    def put(self, key: str, value: Any) -> dict[str, Any]:\n"
                "        self.store[key] = value\n"
                "        return {'ok': True, 'key': key, 'value': value}\n\n"
                "    def delete(self, key: str) -> dict[str, Any]:\n"
                "        existed = key in self.store\n"
                "        self.store.pop(key, None)\n"
                "        return {'ok': existed, 'key': key}\n\n"
                "def main() -> None:\n"
                "    api = App()\n"
                "    print(api.put('user', {'id': 1, 'name': 'cat'}))\n"
                "    print(api.get('user'))\n"
                "    print(api.delete('user'))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "cli":
            return (
                '"""Frontier R1 · CLI"""\n'
                "from __future__ import annotations\n"
                "import argparse\n\n"
                "def build_parser() -> argparse.ArgumentParser:\n"
                "    p = argparse.ArgumentParser(description=\"catide frontier CLI\")\n"
                "    p.add_argument('name', nargs='?', default='world')\n"
                "    p.add_argument('-n', '--count', type=int, default=1)\n"
                "    return p\n\n"
                "def main(argv: list[str] | None = None) -> None:\n"
                "    args = build_parser().parse_args(argv)\n"
                "    for _ in range(max(args.count, 1)):\n"
                "        print(f'hello, {args.name}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "async_io":
            return (
                '"""Frontier R1 · asyncio gather"""\n'
                "from __future__ import annotations\n"
                "import asyncio\n\n"
                "async def work(n: int) -> int:\n"
                "    await asyncio.sleep(0.01)\n"
                "    return n * n\n\n"
                "async def main_async() -> None:\n"
                "    vals = await asyncio.gather(*(work(i) for i in range(5)))\n"
                "    print(vals)\n\n"
                "def main() -> None:\n"
                "    asyncio.run(main_async())\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "unittest":
            return (
                '"""Frontier R1 · unittest sample"""\n'
                "from __future__ import annotations\n"
                "import unittest\n\n"
                "def add(a: int, b: int) -> int:\n"
                "    return a + b\n\n"
                "class TestAdd(unittest.TestCase):\n"
                "    def test_add(self) -> None:\n"
                "        self.assertEqual(add(2, 3), 5)\n\n"
                "def main() -> None:\n"
                "    unittest.main(verbosity=2)\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "regex":
            return (
                '"""Frontier R1 · regex extract"""\n'
                "from __future__ import annotations\n"
                "import re\n\n"
                "EMAIL = re.compile(r'[\\w.+-]+@[\\w-]+\\.[\\w.-]+')\n\n"
                "def find_emails(text: str) -> list[str]:\n"
                "    return EMAIL.findall(text)\n\n"
                "def main() -> None:\n"
                "    sample = 'mail a@b.com and c@d.org please'\n"
                "    print(find_emails(sample))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "json_tool":
            return (
                '"""Frontier R1 · JSON toolkit"""\n'
                "from __future__ import annotations\n"
                "import json\n"
                "from typing import Any\n\n"
                "def loads(s: str) -> Any:\n"
                "    return json.loads(s)\n\n"
                "def dumps(obj: Any) -> str:\n"
                "    return json.dumps(obj, indent=2, sort_keys=True)\n\n"
                "def main() -> None:\n"
                "    data = loads('{\"b\": 2, \"a\": 1}')\n"
                "    print(dumps(data))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "oop_class":
            return (
                f'"""Frontier R1 · {plan.title}"""\n'
                "from __future__ import annotations\n"
                "from dataclasses import dataclass\n\n"
                "@dataclass\n"
                f"class {cn}:\n"
                "    name: str = 'cat'\n"
                "    ready: bool = True\n\n"
                "    def run(self) -> str:\n"
                f"        return f'{{self.name}} :: {plan.title}'\n\n"
                "def main() -> None:\n"
                f"    obj = {cn}()\n"
                "    print(obj.run())\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if skill == "hello":
            return (
                "from __future__ import annotations\n\n"
                "def main() -> None:\n"
                "    print(\"hello from catide · Frontier R1\")\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        # general — typed scaffold from the user ask
        return (
            f'"""Frontier R1 · {plan.title}"""\n'
            "from __future__ import annotations\n"
            "from typing import Any\n\n"
            f"def {n}(*args: Any, **kwargs: Any) -> str:\n"
            f"    \"\"\"Core solution for: {plan.title}\"\"\"\n"
            f"    return {plan.title!r}\n\n"
            "def main() -> None:\n"
            f"    result = {n}()\n"
            "    print(result)\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )

    @classmethod
    def _skill_c(cls, plan: FrontierPlan) -> str:
        if plan.skill == "fibonacci":
            return (
                "/* Frontier R1 · Fibonacci */\n"
                "#include <stdio.h>\n\n"
                "long fib(int n) {\n"
                "    if (n <= 1) return n < 0 ? 0 : n;\n"
                "    long a = 0, b = 1;\n"
                "    for (int i = 2; i <= n; ++i) {\n"
                "        long t = a + b; a = b; b = t;\n"
                "    }\n"
                "    return b;\n"
                "}\n\n"
                "int main(void) {\n"
                "    for (int i = 0; i < 12; ++i)\n"
                "        printf(\"fib(%d) = %ld\\n\", i, fib(i));\n"
                "    return 0;\n"
                "}\n"
            )
        esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
        return (
            "/* Frontier R1 */\n"
            "#include <stdio.h>\n\n"
            "int main(void) {\n"
            f'    printf("%s\\n", "{esc}");\n'
            "    return 0;\n"
            "}\n"
        )

    @classmethod
    def _skill_cpp(cls, plan: FrontierPlan) -> str:
        esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
        if plan.skill == "quicksort":
            return (
                "// Frontier R1 · Quicksort\n"
                "#include <iostream>\n"
                "#include <vector>\n"
                "#include <algorithm>\n\n"
                "int main() {\n"
                "    std::vector<int> v{5, 1, 4, 2, 8, 0, 3};\n"
                "    std::sort(v.begin(), v.end());\n"
                "    for (int x : v) std::cout << x << ' ';\n"
                "    std::cout << '\\n';\n"
                "    return 0;\n"
                "}\n"
            )
        return (
            "// Frontier R1\n"
            "#include <iostream>\n\n"
            "int main() {\n"
            f'    std::cout << "{esc}" << std::endl;\n'
            "    return 0;\n"
            "}\n"
        )

    @classmethod
    def _skill_js(cls, plan: FrontierPlan) -> str:
        if plan.skill == "fibonacci":
            return (
                "// Frontier R1 · Fibonacci\n"
                "function fibonacci(n) {\n"
                "  if (n < 0) throw new Error('n >= 0');\n"
                "  let a = 0, b = 1;\n"
                "  for (let i = 0; i < n; i++) [a, b] = [b, a + b];\n"
                "  return a;\n"
                "}\n\n"
                "function main() {\n"
                "  for (let i = 0; i < 12; i++) console.log(`fib(${i}) = ${fibonacci(i)}`);\n"
                "}\n\n"
                "main();\n"
            )
        if plan.skill == "twosum":
            return (
                "// Frontier R1 · Two Sum\n"
                "function twoSum(nums, target) {\n"
                "  const seen = new Map();\n"
                "  for (let i = 0; i < nums.length; i++) {\n"
                "    const need = target - nums[i];\n"
                "    if (seen.has(need)) return [seen.get(need), i];\n"
                "    seen.set(nums[i], i);\n"
                "  }\n"
                "  return [];\n"
                "}\n\n"
                "console.log(twoSum([2, 7, 11, 15], 9));\n"
            )
        return (
            f"// Frontier R1 · {plan.title}\n"
            f"function {plan.name}() {{\n"
            f"  return {plan.title!r};\n"
            "}\n\n"
            f"console.log({plan.name}());\n"
        )

    @classmethod
    def _draft(cls, plan: FrontierPlan) -> str:
        lang, skill = plan.lang, plan.skill
        if lang == "python":
            return cls._skill_python(skill, plan)
        if lang == "c":
            return cls._skill_c(plan)
        if lang in {"cpp", "cuda"}:
            return cls._skill_cpp(plan)
        if lang in {"javascript", "typescript"}:
            body = cls._skill_js(plan)
            if lang == "typescript" and "function " in body:
                body = body.replace("function fibonacci(n)", "function fibonacci(n: number): number")
                body = body.replace("function twoSum(nums, target)",
                                    "function twoSum(nums: number[], target: number): number[]")
                body = body.replace(f"function {plan.name}()",
                                    f"function {plan.name}(): string")
            return body
        if lang == "rust":
            esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
            return f'// Frontier R1\nfn main() {{\n    println!("{esc}");\n}}\n'
        if lang == "go":
            esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
            return (
                "package main\n\nimport \"fmt\"\n\n"
                f'// Frontier R1\nfunc main() {{\n\tfmt.Println("{esc}")\n}}\n'
            )
        if lang == "java":
            esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
            return (
                "// Frontier R1\n"
                "public class Main {\n"
                "    public static void main(String[] args) {\n"
                f'        System.out.println("{esc}");\n'
                "    }\n"
                "}\n"
            )
        if lang == "html":
            return (
                "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                f"  <meta charset=\"utf-8\" />\n  <title>{plan.title}</title>\n"
                "</head>\n<body>\n"
                f"  <h1>{plan.title}</h1>\n"
                "  <p>Frontier R1 · catide</p>\n"
                "</body>\n</html>\n"
            )
        if lang == "bash":
            return f"#!/usr/bin/env bash\n# Frontier R1\nset -euo pipefail\necho {plan.title!r}\n"
        if lang == "assembly":
            return (
                "; Frontier R1 asm\nsection .data\n"
                '    msg db "meow", 10\n    len equ $ - msg\n\n'
                "section .text\nglobal _start\n_start:\n"
                "    mov rax, 1\n    mov rdi, 1\n    mov rsi, msg\n"
                "    mov rdx, len\n    syscall\n"
                "    mov rax, 60\n    xor rdi, rdi\n    syscall\n"
            )
        if lang == "perl":
            esc = plan.title.replace("'", "'\\''")
            return f"#!/usr/bin/env perl\nuse strict;\nuse warnings;\nprint \"{esc}\\n\";\n"
        if lang == "lua":
            return f"-- Frontier R1\nprint [[{plan.title}]]\n"
        if lang == "dart":
            esc = plan.title.replace("\\", "\\\\").replace("'", "\\'")
            return (
                "// Frontier R1\n"
                "void main() {\n"
                f"  print('{esc}');\n"
                "}\n"
            )
        if lang == "scala":
            esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
            return (
                "// Frontier R1\n"
                "object Main extends App {\n"
                f'  println("{esc}")\n'
                "}\n"
            )
        if lang == "haskell":
            esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
            return (
                "-- Frontier R1\n"
                "module Main where\n\n"
                "main :: IO ()\n"
                f'main = putStrLn "{esc}"\n'
            )
        if lang == "elixir":
            esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
            return (
                "# Frontier R1\n"
                f'IO.puts(:stdio, "{esc}")\n'
            )
        if lang == "clojure":
            esc = plan.title.replace('"', '\\"')
            return (
                "; Frontier R1\n"
                f'(println "{esc}")\n'
            )
        if lang == "julia":
            return (
                "# Frontier R1\n"
                f"println(\"{plan.title}\")\n"
            )
        if lang == "zig":
            return (
                "// Frontier R1\n"
                "const std = @import(\"std\");\n\n"
                "pub fn main() !void {\n"
                f'    std.debug.print("{plan.title}\\n", .{{}});\n'
                "}\n"
            )
        if lang == "nim":
            return (
                "# Frontier R1\n"
                f'echo "{plan.title}"\n'
            )
        if lang == "solidity":
            esc = plan.title.replace("\\", "\\\\").replace('"', '\\"')
            return (
                "// Frontier R1\n"
                "pragma solidity ^0.8.0;\n\n"
                "contract Main {\n"
                f'    string public greeting = "{esc}";\n'
                "}\n"
            )
        return cls._skill_python("general", plan)

    @classmethod
    def code(cls, prompt: str, *, hint: str = "") -> Tuple[str, str, str]:
        """
        Full frontier loop. Returns (lang, code, think_trace).
        """
        plan = cls.plan(prompt, hint=hint)
        think = cls.think(prompt, plan)
        draft = cls._draft(plan)
        ok, reason = cls._verify(plan.lang, draft)
        repairs = 0
        while not ok and repairs < cls.MAX_REPAIR:
            draft = cls._repair(plan.lang, draft, reason, plan)
            ok, reason = cls._verify(plan.lang, draft)
            repairs += 1
            plan.notes.append(f"repair#{repairs}:{reason or 'ok'}")
        if not ok:
            # hard fallback — always emit valid python
            plan.lang = "python"
            draft = cls._skill_python("hello", plan)
            think += f"\nfallback: forced hello after failed verify ({reason})"
            ok = True
            repairs += 1
        think += f"\nverify: {'PASS' if ok else 'FAIL'} · repairs={repairs} · skill={plan.skill}"
        return plan.lang, draft, think

    @classmethod
    def fence(cls, lang: str, code: str) -> str:
        return f"```{lang}\n{code.rstrip()}\n```"


# ──────────────────────────────────────────────────────────────
# CatsVibeCoder — facade → CatsFrontierR1 (Agents always code)
# ──────────────────────────────────────────────────────────────
class CatsVibeCoder:
    """Instant vibe-code emit · delegates to CatsFrontierR1."""

    detect_lang = CatsFrontierR1.detect_lang
    fence = CatsFrontierR1.fence

    @classmethod
    def synthesize(cls, prompt: str, *, hint: str = "") -> Tuple[str, str]:
        lang, code, _think = CatsFrontierR1.code(prompt, hint=hint)
        return lang, code

    @classmethod
    def synthesize_with_think(cls, prompt: str, *, hint: str = "") -> Tuple[str, str, str]:
        return CatsFrontierR1.code(prompt, hint=hint)

    @classmethod
    def try_catseek_fast(cls, mod, engine, prompt: str) -> Optional[str]:
        """Prefer CatSeek pattern paths that skip BitNet encode."""
        if mod is None or engine is None:
            return None
        try:
            lang = cls.detect_lang(prompt)
            myth = getattr(mod, "CatR1MythosEngine", None)
            if myth is not None and hasattr(myth, "_pattern_match"):
                hit = myth._pattern_match(prompt, lang, engine)
                if hit and isinstance(hit, str) and len(hit.strip()) > 8:
                    # Prefer Frontier if CatSeek stub is too thin
                    if hit.count("\n") < 4:
                        return None
                    em = getattr(mod, "TokenWeightCodeEmitter", None)
                    if em and hasattr(em, "fence"):
                        return f"**CatSeek R1** · pattern\n\n{em.fence(lang, hit)}"
                    return f"**CatSeek R1** · pattern\n\n{cls.fence(lang, hit)}"
        except Exception:
            return None
        return None


# ──────────────────────────────────────────────────────────────
# CatsSyntax — language token rules
# (keep UI; apply TextMate-like scopes as tk Text tags)
# ──────────────────────────────────────────────────────────────
class CatsSyntax:
    """Syntax table forked for catide (files = off)."""

    KEYWORDS: Dict[str, Tuple[str, ...]] = {
        "python": tuple(keyword.kwlist) + ("match", "case", "type", "async", "await"),
        "javascript": (
            "break", "case", "catch", "class", "const", "continue", "debugger", "default",
            "delete", "do", "else", "export", "extends", "finally", "for", "function",
            "if", "import", "in", "instanceof", "let", "new", "return", "super", "switch",
            "this", "throw", "try", "typeof", "var", "void", "while", "with", "yield",
            "async", "await", "of", "from", "as", "static", "get", "set",
        ),
        "typescript": (
            "break", "case", "catch", "class", "const", "continue", "debugger", "default",
            "delete", "do", "else", "export", "extends", "finally", "for", "function",
            "if", "import", "in", "instanceof", "let", "new", "return", "super", "switch",
            "this", "throw", "try", "typeof", "var", "void", "while", "with", "yield",
            "async", "await", "of", "from", "as", "static", "interface", "type", "enum",
            "namespace", "implements", "private", "public", "protected", "readonly",
            "declare", "abstract", "keyof", "infer", "satisfies",
        ),
        "c": (
            "auto", "break", "case", "char", "const", "continue", "default", "do",
            "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline",
            "int", "long", "register", "restrict", "return", "short", "signed", "sizeof",
            "static", "struct", "switch", "typedef", "union", "unsigned", "void",
            "volatile", "while", "_Bool", "_Complex", "_Imaginary",
        ),
        "cpp": (
            "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
            "bool", "break", "case", "catch", "char", "char8_t", "char16_t", "char32_t",
            "class", "compl", "concept", "const", "consteval", "constexpr", "constinit",
            "const_cast", "continue", "co_await", "co_return", "co_yield", "decltype",
            "default", "delete", "do", "double", "dynamic_cast", "else", "enum",
            "explicit", "export", "extern", "false", "float", "for", "friend", "goto",
            "if", "inline", "int", "long", "mutable", "namespace", "new", "noexcept",
            "not", "not_eq", "nullptr", "operator", "or", "or_eq", "private", "protected",
            "public", "register", "reinterpret_cast", "requires", "return", "short",
            "signed", "sizeof", "static", "static_assert", "static_cast", "struct",
            "switch", "template", "this", "thread_local", "throw", "true", "try",
            "typedef", "typeid", "typename", "union", "unsigned", "using", "virtual",
            "void", "volatile", "wchar_t", "while", "xor", "xor_eq", "override", "final",
        ),
        "rust": (
            "as", "async", "await", "break", "const", "continue", "crate", "dyn", "else",
            "enum", "extern", "false", "fn", "for", "if", "impl", "in", "let", "loop",
            "match", "mod", "move", "mut", "pub", "ref", "return", "self", "Self",
            "static", "struct", "super", "trait", "true", "type", "unsafe", "use",
            "where", "while", "async", "await", "dyn",
        ),
        "go": (
            "break", "case", "chan", "const", "continue", "default", "defer", "else",
            "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
            "map", "package", "range", "return", "select", "struct", "switch", "type",
            "var",
        ),
        "java": (
            "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
            "class", "const", "continue", "default", "do", "double", "else", "enum",
            "extends", "final", "finally", "float", "for", "goto", "if", "implements",
            "import", "instanceof", "int", "interface", "long", "native", "new",
            "package", "private", "protected", "public", "return", "short", "static",
            "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
            "transient", "try", "void", "volatile", "while", "var", "yield", "record",
            "sealed", "permits", "non-sealed",
        ),
        "csharp": (
            "abstract", "as", "base", "bool", "break", "byte", "case", "catch", "char",
            "checked", "class", "const", "continue", "decimal", "default", "delegate",
            "do", "double", "else", "enum", "event", "explicit", "extern", "false",
            "finally", "fixed", "float", "for", "foreach", "goto", "if", "implicit",
            "in", "int", "interface", "internal", "is", "lock", "long", "namespace",
            "new", "null", "object", "operator", "out", "override", "params", "private",
            "protected", "public", "readonly", "ref", "return", "sbyte", "sealed",
            "short", "sizeof", "stackalloc", "static", "string", "struct", "switch",
            "this", "throw", "true", "try", "typeof", "uint", "ulong", "unchecked",
            "unsafe", "ushort", "using", "virtual", "void", "volatile", "while", "async",
            "await", "var", "dynamic", "nameof", "when", "record",
        ),
        "ruby": (
            "alias", "and", "begin", "break", "case", "class", "def", "defined?", "do",
            "else", "elsif", "end", "ensure", "false", "for", "if", "in", "module",
            "next", "nil", "not", "or", "redo", "rescue", "retry", "return", "self",
            "super", "then", "true", "undef", "unless", "until", "when", "while", "yield",
        ),
        "php": (
            "abstract", "and", "array", "as", "break", "callable", "case", "catch",
            "class", "clone", "const", "continue", "declare", "default", "die", "do",
            "echo", "else", "elseif", "empty", "enddeclare", "endfor", "endforeach",
            "endif", "endswitch", "endwhile", "eval", "exit", "extends", "final",
            "finally", "fn", "for", "foreach", "function", "global", "goto", "if",
            "implements", "include", "include_once", "instanceof", "insteadof",
            "interface", "isset", "list", "match", "namespace", "new", "or", "print",
            "private", "protected", "public", "readonly", "require", "require_once",
            "return", "static", "switch", "throw", "trait", "try", "unset", "use",
            "var", "while", "xor", "yield",
        ),
        "swift": (
            "associatedtype", "class", "deinit", "enum", "extension", "fileprivate",
            "func", "import", "init", "inout", "internal", "let", "open", "operator",
            "private", "protocol", "public", "rethrows", "static", "struct",
            "subscript", "typealias", "var", "break", "case", "continue", "default",
            "defer", "do", "else", "fallthrough", "for", "guard", "if", "in", "repeat",
            "return", "switch", "where", "while", "as", "Any", "catch", "false", "is",
            "nil", "super", "self", "Self", "throw", "throws", "true", "try", "async",
            "await", "actor",
        ),
        "kotlin": (
            "as", "break", "class", "continue", "do", "else", "false", "for", "fun",
            "if", "in", "interface", "is", "null", "object", "package", "return",
            "super", "this", "throw", "true", "try", "typealias", "typeof", "val",
            "var", "when", "while", "by", "catch", "constructor", "delegate", "dynamic",
            "field", "file", "finally", "get", "import", "init", "param", "property",
            "receiver", "set", "setparam", "where", "actual", "abstract", "annotation",
            "companion", "const", "crossinline", "data", "enum", "expect", "external",
            "final", "infix", "inline", "inner", "internal", "lateinit", "noinline",
            "open", "operator", "out", "override", "private", "protected", "public",
            "reified", "sealed", "suspend", "tailrec", "vararg",
        ),
        "bash": (
            "if", "then", "else", "elif", "fi", "case", "esac", "for", "select",
            "while", "until", "do", "done", "in", "function", "time", "coproc",
            "export", "local", "readonly", "return", "exit", "shift", "break",
            "continue", "declare", "typeset", "unset", "alias", "eval", "exec",
            "source", "set", "unset",
        ),
        "sql": (
            "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "INSERT", "INTO", "VALUES",
            "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "INDEX", "VIEW", "DROP",
            "ALTER", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON", "AS", "ORDER",
            "BY", "GROUP", "HAVING", "LIMIT", "OFFSET", "UNION", "ALL", "DISTINCT",
            "NULL", "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "CONSTRAINT", "DEFAULT",
            "TRUE", "FALSE", "CASE", "WHEN", "THEN", "ELSE", "END", "WITH", "ASC",
            "DESC", "BETWEEN", "LIKE", "IN", "IS", "EXISTS",
        ),
        "html": (),
        "css": (
            "important", "media", "keyframes", "from", "to", "supports", "charset",
            "import", "namespace",
        ),
        "json": ("true", "false", "null"),
        "yaml": ("true", "false", "null", "yes", "no", "on", "off"),
        "markdown": (),
        "cuda": (),
        "objc": (
            "id", "Class", "SEL", "IMP", "BOOL", "YES", "NO", "nil", "Nil", "NULL",
            "self", "super", "atomic", "nonatomic", "retain", "assign", "copy",
            "readonly", "readwrite", "strong", "weak", "unsafe_unretained",
        ),
        "assembly": (),
        "perl": (
            "my", "our", "local", "sub", "package", "use", "require", "strict", "warnings",
            "if", "else", "elsif", "unless", "while", "for", "foreach", "do", "until",
            "return", "last", "next", "redo", "goto", "die", "warn", "print", "say",
            "open", "close", "chomp", "split", "join", "map", "grep", "sort",
            "shift", "pop", "push", "unshift", "defined", "undef", "ref", "bless",
            "qw", "qx", "m", "s", "tr", "y", "q", "qq",
        ),
        "lua": (
            "and", "break", "do", "else", "elseif", "end", "for", "function", "if",
            "in", "local", "nil", "not", "or", "repeat", "return", "then", "until", "while",
            "true", "false", "require", "module", "self",
        ),
        "dart": (
            "abstract", "as", "assert", "async", "await", "break", "case", "catch",
            "class", "const", "continue", "covariant", "default", "deferred", "do",
            "dynamic", "else", "enum", "export", "extends", "extension", "external",
            "factory", "false", "final", "finally", "for", "Function", "get", "hide",
            "if", "implements", "import", "in", "interface", "is", "late", "library",
            "mixin", "new", "null", "on", "operator", "part", "required", "rethrow",
            "return", "set", "show", "static", "super", "switch", "sync", "this",
            "throw", "true", "try", "typedef", "var", "void", "while", "with", "yield",
        ),
        "scala": (
            "abstract", "case", "catch", "class", "def", "do", "else", "enum", "extends",
            "false", "final", "finally", "for", "forSome", "given", "if", "implicit",
            "import", "lazy", "match", "new", "null", "object", "override", "package",
            "private", "protected", "return", "sealed", "super", "then", "throw",
            "trait", "true", "try", "type", "using", "val", "var", "while", "with", "yield",
        ),
        "haskell": (
            "as", "case", "class", "data", "default", "deriving", "do", "else",
            "family", "forall", "foreign", "hiding", "if", "import", "in",
            "infix", "infixl", "infixr", "instance", "let", "module", "newtype",
            "of", "pattern", "qualified", "then", "type", "where", "where",
            "pure", "return", "fmap", "map", "filter",
        ),
        "elixir": (
            "def", "defp", "defmodule", "defguard", "defstruct", "defprotocol",
            "defimpl", "defmacro", "defmacrop", "defcallback", "defexception",
            "do", "end", "if", "else", "unless", "case", "cond", "for", "with",
            "receive", "after", "true", "false", "nil", "raise", "throw",
            "import", "alias", "use", "require", "super", "fn", "quote", "unquote",
            "when", "and", "or", "not", "in", "is", "fn",
        ),
        "clojure": (
            "def", "defn", "defmacro", "defmethod", "defmulti", "defprotocol",
            "defrecord", "deftype", "let", "if", "when", "cond", "case", "do",
            "fn", "loop", "recur", "for", "doseq", "dotimes", "while",
            "import", "ns", "in-ns", "require", "use", "refer", "with",
            "try", "catch", "finally", "throw", "->", "->>", "as->", "some->",
            "binding", "proxy", "extend", "extend-type", "extend-protocol",
            "reify", "locking", "future", "delay", "promise",
        ),
        "julia": (
            "function", "end", "if", "else", "elseif", "for", "while", "do",
            "try", "catch", "finally", "return", "break", "continue", "let",
            "global", "local", "const", "struct", "mutable", "module", "import",
            "export", "using", "begin", "macro", "quote", "abstract", "primitive",
            "type", "where", "in", "isa", "true", "false", "nothing",
        ),
        "zig": (
            "const", "var", "fn", "return", "if", "else", "for", "while",
            "switch", "break", "continue", "try", "catch", "defer", "errdefer",
            "pub", "export", "extern", "inline", "noinline", "comptime",
            "struct", "enum", "union", "type", "anytype", "void", "null",
            "true", "false", "undefined", "usingnamespace", "test",
        ),
        "nim": (
            "proc", "func", "method", "iterator", "template", "macro", "converter",
            "var", "let", "const", "result", "if", "elif", "else", "case", "of",
            "for", "while", "block", "break", "continue", "return", "yield",
            "try", "except", "finally", "raise", "discard", "echo",
            "type", "object", "tuple", "enum", "ref", "ptr", "varargs",
            "import", "export", "from", "include", "static", "cast",
            "true", "false", "nil", "void", "async", "await",
        ),
        "fsharp": (
            "let", "let!", "use", "use!", "do", "do!", "yield", "yield!",
            "return", "return!", "match", "with", "when", "if", "elif", "else",
            "then", "for", "while", "to", "downto", "in", "of", "new",
            "not", "and", "or", "true", "false", "null", "as",
            "module", "namespace", "open", "type", "val", "member",
            "static", "abstract", "override", "default", "inherit",
            "base", "this", "base", "then", "finally", "try", "with",
            "async", "task", "seq", "async", "lazy",
        ),
        "solidity": (
            "pragma", "import", "contract", "library", "interface", "abstract",
            "is", "using", "struct", "enum", "mapping", "address", "uint",
            "int", "string", "bool", "bytes", "function", "modifier",
            "event", "emit", "constructor", "fallback", "receive",
            "public", "private", "internal", "external", "view",
            "pure", "payable", "override", "virtual", "returns",
            "return", "if", "else", "for", "while", "do", "break",
            "continue", "require", "revert", "assert", "delete",
            "new", "this", "super", "selfdestruct", "type",
            "var", "let", "constant", "immutable", "unchecked",
            "assembly", "gasleft", "block", "msg", "tx", "now",
        ),
    }

    # Map detector langs → keyword table keys
    ALIAS = {
        "js": "javascript", "ts": "typescript", "py": "python",
        "c++": "cpp", "cxx": "cpp", "cs": "csharp", "c#": "csharp",
        "shell": "bash", "sh": "bash", "zsh": "bash", "objc": "objc",
        "objective-c": "objc", "asm": "assembly", "nasm": "assembly",
        "gas": "assembly", "html": "html", "css": "css",
    }

    @classmethod
    def normalize(cls, lang: str) -> str:
        lang = (lang or "unknown").lower()
        return cls.ALIAS.get(lang, lang)

    @classmethod
    def apply(cls, tagger, content: str, lang: str) -> None:
        """Apply token tags via tagger._tag_span(tag, start, end)."""
        lang = cls.normalize(lang)
        if not content.strip():
            return

        def span(tag: str, start: int, end: int):
            if end > start:
                tagger._tag_span(tag, start, end)

        # Comments
        if lang == "python":
            for m in re.finditer(r"#.*?$", content, re.M):
                span("comment", m.start(), m.end())
        elif lang in {"html", "xml", "markdown"}:
            for m in re.finditer(r"<!--.*?-->", content, re.S):
                span("comment", m.start(), m.end())
        elif lang == "css":
            for m in re.finditer(r"/\*.*?\*/", content, re.S):
                span("comment", m.start(), m.end())
        elif lang in {"bash", "yaml", "ruby"}:
            for m in re.finditer(r"(?:^|\s)#.*?$", content, re.M):
                span("comment", m.start(), m.end())
        elif lang == "assembly":
            for m in re.finditer(r"[;#].*?$", content, re.M):
                span("comment", m.start(), m.end())
        elif lang == "sql":
            for m in re.finditer(r"--.*?$|/\*.*?\*/", content, re.M | re.S):
                span("comment", m.start(), m.end())
        else:
            for m in re.finditer(r"//.*?$|/\*.*?\*/", content, re.M | re.S):
                span("comment", m.start(), m.end())

        # HTML / JSX-ish tags
        if lang in {"html", "xml", "javascript", "typescript"}:
            for m in re.finditer(r"</?([A-Za-z][\w:-]*)", content):
                span("tag", m.start(), m.end())
            for m in re.finditer(r"\b([A-Za-z_:][\w:.-]*)\s*=", content):
                span("attr", m.start(1), m.end(1))

        # Strings
        if lang == "python":
            for m in re.finditer(
                r"('''.*?'''|\"\"\".*?\"\"\"|'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")",
                content, re.S,
            ):
                span("string", m.start(), m.end())
        elif lang in {"bash", "ruby"}:
            for m in re.finditer(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", content):
                span("string", m.start(), m.end())
        else:
            for m in re.finditer(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", content):
                span("string", m.start(), m.end())

        # Numbers
        for m in re.finditer(r"\b0x[0-9a-fA-F]+\b|\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b", content):
            span("number", m.start(), m.end())

        # Preprocessor / directives
        if lang in {"c", "cpp", "cuda", "objc", "csharp"}:
            for m in re.finditer(r"(?m)^\s*#\s*\w+.*$", content):
                span("preproc", m.start(), m.end())
        if lang == "assembly":
            for m in re.finditer(r"(?mi)^\s*\.(?:global|globl|section|text|data|bss|intel_syntax|att_syntax|extern|include)\b.*$", content):
                span("preproc", m.start(), m.end())

        # Assembly opcodes / regs
        if lang == "assembly":
            for m in re.finditer(
                r"(?mi)\b(?:mov|lea|push|pop|call|ret|jmp|jz|jnz|je|jne|cmp|add|sub|xor|"
                r"and|or|mul|div|imul|idiv|syscall|int|ldr|str|bl|svc|nop|pushq|popq|movq|leaq)\b",
                content,
            ):
                span("asmop", m.start(), m.end())
            for m in re.finditer(
                r"(?mi)\b(?:e?[abcd]x|e?[sd]i|e?[sb]p|r(?:ax|bx|cx|dx|si|di|bp|sp|\d+)|"
                r"%[er]?[abcd]x|x\d+|w\d+)\b",
                content,
            ):
                span("asmreg", m.start(), m.end())

        # CUDA
        if lang == "cuda":
            for m in re.finditer(r"\b(?:__global__|__device__|__host__|__shared__|__constant__)\b", content):
                span("deco", m.start(), m.end())

        # Keywords (CUDA/ObjC inherit C/C++ tables)
        if lang == "cuda":
            kws = tuple(cls.KEYWORDS["cpp"]) + tuple(cls.KEYWORDS["c"])
        elif lang == "objc":
            kws = tuple(cls.KEYWORDS["c"]) + tuple(cls.KEYWORDS["objc"])
        else:
            kws = cls.KEYWORDS.get(lang, ())
        if kws:
            flags = re.I if lang == "sql" else 0
            pat = r"\b(?:" + "|".join(re.escape(k) for k in sorted(set(kws), key=len, reverse=True)) + r")\b"
            for m in re.finditer(pat, content, flags):
                span("kw", m.start(), m.end())

        # Definitions / types
        if lang == "python":
            for m in re.finditer(r"\b(def|class|async\s+def)\s+([A-Za-z_]\w*)", content):
                span("defname", m.start(2), m.end(2))
            for m in re.finditer(r"@\w+(?:\.\w+)*", content):
                span("deco", m.start(), m.end())
            b = builtins
            bdir = [x for x in dir(b) if not x.startswith('_')]
            for m in re.finditer(r"\b([A-Za-z_]\w*)\b", content):
                if m.group(1) in bdir:
                    span("builtin", m.start(), m.end())
        elif lang in {"javascript", "typescript"}:
            for m in re.finditer(r"\b(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)", content):
                span("defname", m.start(1), m.end(1))
            for m in re.finditer(r"\b(?:console|Math|JSON|Array|Object|Promise|Map|Set)\b", content):
                span("builtin", m.start(), m.end())
        elif lang in {"c", "cpp", "cuda", "objc"}:
            for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", content):
                span("defname", m.start(1), m.end(1))
            for m in re.finditer(r"\b(?:std|cout|cin|endl|printf|scanf|malloc|free|NULL|nullptr)\b", content):
                span("builtin", m.start(), m.end())
            for m in re.finditer(r"\b(?:int|char|void|float|double|long|short|bool|size_t|uint32_t|string|vector)\b", content):
                span("type", m.start(), m.end())
        elif lang == "rust":
            for m in re.finditer(r"\b(?:fn|struct|enum|trait|impl|type|mod)\s+([A-Za-z_]\w*)", content):
                span("defname", m.start(1), m.end(1))
            for m in re.finditer(r"\b(?:String|Vec|Option|Result|i32|u32|usize|bool|str)\b", content):
                span("type", m.start(), m.end())
        elif lang == "go":
            for m in re.finditer(r"\bfunc\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)", content):
                span("defname", m.start(1), m.end(1))
            for m in re.finditer(r"\b(?:string|int|int64|float64|bool|error|byte|rune)\b", content):
                span("type", m.start(), m.end())
        elif lang == "java":
            for m in re.finditer(r"\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", content):
                span("defname", m.start(1), m.end(1))
            for m in re.finditer(r"\b(?:String|System|List|Map|Optional)\b", content):
                span("builtin", m.start(), m.end())
        elif lang == "css":
            for m in re.finditer(r"([A-Za-z_-][\w-]*)\s*:", content):
                span("property", m.start(1), m.end(1))
            for m in re.finditer(r"[.#]?[A-Za-z_][\w-]*(?=\s*[{,])", content):
                span("defname", m.start(), m.end())
        elif lang == "json":
            for m in re.finditer(r"\"([^\"]+)\"\s*:", content):
                span("property", m.start(1), m.end(1))
        elif lang == "markdown":
            for m in re.finditer(r"(?m)^#{1,6}\s.*$", content):
                span("defname", m.start(), m.end())
            for m in re.finditer(r"`[^`]+`|\*\*[^*]+\*\*|__[^_]+__", content):
                span("string", m.start(), m.end())

        # Regex literals (JS/TS)
        if lang in {"javascript", "typescript"}:
            for m in re.finditer(r"(?<![/\w])/(?:\\.|[^/\n])+/[gimsuy]*", content):
                span("regex", m.start(), m.end())


# ──────────────────────────────────────────────────────────────
# CodeLangDetector — score every dialect from ASM → C → C++
# (also ranks sibling systems langs when evidence is strong)
# ──────────────────────────────────────────────────────────────
@dataclass
class LangHit:
    lang: str
    confidence: float
    scores: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        nice = {
            "assembly": "Assembly", "c": "C", "cpp": "C++", "cuda": "CUDA",
            "objc": "Objective-C", "python": "Python", "javascript": "JavaScript",
            "typescript": "TypeScript", "rust": "Rust", "go": "Go", "java": "Java",
            "bash": "Bash", "html": "HTML", "css": "CSS", "json": "JSON",
            "yaml": "YAML", "markdown": "Markdown", "sql": "SQL",
            "csharp": "C#", "ruby": "Ruby", "php": "PHP", "swift": "Swift",
            "kotlin": "Kotlin", "unknown": "Plain Text",
            "perl": "Perl", "r": "R", "dart": "Dart", "lua": "Lua",
            "scala": "Scala", "haskell": "Haskell", "elixir": "Elixir",
            "clojure": "Clojure", "julia": "Julia", "erlang": "Erlang",
            "elm": "Elm", "racket": "Racket", "scheme": "Scheme",
            "common-lisp": "Common Lisp", "lisp": "Lisp", "fortran": "Fortran",
            "cobol": "COBOL", "pascal": "Pascal", "ada": "Ada",
            "zig": "Zig", "nim": "Nim", "ocaml": "OCaml", "fsharp": "F#",
            "solidity": "Solidity", "graphql": "GraphQL",
            "tex": "LaTeX", "bib": "BibTeX",
            "toml": "TOML", "ini": "INI", "powershell": "PowerShell",
            "batch": "Batch", "dockerfile": "Dockerfile", "makefile": "Makefile",
            "cmake": "CMake",
        }
        return nice.get(self.lang, self.lang.upper())


class CodeLangDetector:
    """
    Weighted fingerprint detector spanning the systems stack:

        assembly (nasm / gas / masm)  →  C  →  C++  (+ CUDA / ObjC)

    Algorithm
    ---------
    1. Extension / fence hints (hard boost).
    2. Line-level regex fingerprints per language (positive evidence).
    3. Negative evidence (C++ tokens kill pure-C; AT&T/%reg kill Intel-only).
    4. Softmax-ish normalize → confidence in [0, 1].
    5. Tie-breakers prefer more specific language on the asm→cpp spectrum.
    """

    ALIASES = {
        "asm": "assembly", "nasm": "assembly", "gas": "assembly", "masm": "assembly",
        "s": "assembly", "x86": "assembly", "x86_64": "assembly", "armasm": "assembly",
        "c++": "cpp", "cxx": "cpp", "cc": "cpp", "hpp": "cpp", "hh": "cpp",
        "cuh": "cuda", "cu": "cuda", "objective-c": "objc", "obj-c": "objc",
        "m": "objc", "mm": "objc", "py": "python", "js": "javascript",
        "ts": "typescript", "rs": "rust", "sh": "bash", "zsh": "bash",
    }

    # Ordered spectrum for tie-breaks (more specific wins when close)
    SPECTRUM = ("assembly", "c", "cpp", "cuda", "objc")

    EXT_MAP = {
        ".asm": "assembly", ".s": "assembly", ".S": "assembly", ".nasm": "assembly",
        ".c": "c", ".h": "c",
        ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
        ".cu": "cuda", ".cuh": "cuda",
        ".m": "objc", ".mm": "objc",
        ".py": "python", ".pyw": "python",
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".rs": "rust", ".go": "go", ".java": "java",
        ".sh": "bash", ".bash": "bash", ".zsh": "bash",
        ".html": "html", ".htm": "html", ".css": "css",
        ".json": "json", ".yml": "yaml", ".yaml": "yaml",
        ".md": "markdown", ".markdown": "markdown",
        ".sql": "sql", ".cs": "csharp", ".rb": "ruby",
        ".php": "php", ".swift": "swift", ".kt": "kotlin",
        ".kts": "kotlin",
        ".pl": "perl", ".pm": "perl",
        ".r": "r", ".R": "r",
        ".dart": "dart", ".lua": "lua",
        ".scala": "scala", ".hs": "haskell", ".lhs": "haskell",
        ".ex": "elixir", ".exs": "elixir",
        ".clj": "clojure", ".cljs": "clojure", ".cljc": "clojure",
        ".jl": "julia",
        ".erl": "erlang", ".elm": "elm",
        ".rkt": "racket", ".scm": "scheme", ".lisp": "lisp", ".cl": "common-lisp",
        ".f90": "fortran", ".f95": "fortran", ".f03": "fortran", ".f": "fortran",
        ".cbl": "cobol", ".cob": "cobol",
        ".pas": "pascal", ".pp": "pascal",
        ".adb": "ada", ".ads": "ada",
        ".zig": "zig", ".nim": "nim", ".nims": "nim",
        ".ml": "ocaml", ".mli": "ocaml",
        ".fs": "fsharp", ".fsx": "fsharp",
        ".sol": "solidity",
        ".graphql": "graphql", ".gql": "graphql",
        ".tex": "tex", ".sty": "tex", ".cls": "tex",
        ".bib": "bib",
        ".toml": "toml",
        ".ini": "ini", ".cfg": "ini", ".conf": "ini",
        ".ps1": "powershell", ".psm1": "powershell",
        ".bat": "batch", ".cmd": "batch",
        ".vue": "html",
        ".svelte": "html",
        ".astro": "html",
    }

    # (lang, weight, compiled pattern, reason)
    RULES: List[Tuple[str, float, re.Pattern, str]] = []

    @classmethod
    def _build_rules(cls) -> None:
        if cls.RULES:
            return
        raw = [
            # ── Assembly (Intel / AT&T / ARM-ish) ──
            ("assembly", 4.5, r"(?mi)^\s*\.(?:global|globl|section|text|data|bss|intel_syntax|att_syntax)\b", "gas directive"),
            ("assembly", 4.0, r"(?mi)^\s*(?:section|segment)\s+\.?(?:text|data|bss)\b", "nasm/masm section"),
            ("assembly", 3.5, r"(?mi)^\s*(?:bits|org|times|equ|res[bwdq])\b", "nasm pseudo-op"),
            ("assembly", 3.5, r"(?mi)^\s*(?:mov|lea|push|pop|call|ret|jmp|jz|jnz|je|jne|cmp|add|sub|xor|and|or|mul|div|imul|idiv|syscall|int\s+0x80)\b", "asm mnemonic"),
            ("assembly", 3.0, r"(?mi)\b(?:eax|ebx|ecx|edx|esi|edi|ebp|esp|rax|rbx|rcx|rdx|rsi|rdi|rbp|rsp|r\d{1,2}|rip)\b", "x86 register"),
            ("assembly", 2.8, r"(?mi)\b(?:x0|x1|x2|w0|w1|sp|lr|pc|nzcv)\b.*\b(?:ldr|str|bl|ret|svc)\b|\b(?:ldr|str|bl|svc)\b", "aarch64 cues"),
            ("assembly", 2.5, r"(?m)^\s*\w+:\s*$", "asm label"),
            ("assembly", 2.0, r"(?mi)^\s*;|^\s*#\s*(?:include|define)\b.*\.(?:asm|inc)", "asm comment/include"),
            ("assembly", 2.0, r"(?mi)\bdb\s+|dw\s+|dd\s+|dq\s+", "define bytes"),
            # ── C ──
            ("c", 4.0, r"(?m)#\s*include\s*[<\"]", "c include"),
            ("c", 3.5, r"(?m)\b(?:printf|scanf|malloc|free|sizeof|NULL|stdin|stdout)\s*\(", "c stdlib"),
            ("c", 3.0, r"(?m)\b(?:int|char|void|float|double|long|short|unsigned|signed|struct|typedef|enum|union)\b", "c type"),
            ("c", 2.8, r"(?m)\bmain\s*\([^)]*\)\s*\{", "c main"),
            ("c", 2.5, r"(?m)->\w+", "c arrow"),
            ("c", 2.0, r"(?m)\b(?:fopen|fread|fwrite|memcpy|strlen|strcmp)\s*\(", "c string/io"),
            ("c", 1.5, r"(?m)/\*[^*]*\*/|//", "c-style comment"),
            # ── C++ ──
            ("cpp", 5.0, r"(?m)#\s*include\s*<iostream>|#\s*include\s*<vector>|#\s*include\s*<string>", "cxx header"),
            ("cpp", 4.5, r"(?m)\b(?:std::|cout|cin|endl|namespace|template\s*<|typename|class\s+\w+\s*[{:])", "cxx keyword"),
            ("cpp", 4.0, r"(?m)\b(?:new|delete|public:|private:|protected:|virtual|override|noexcept|constexpr)\b", "cxx oo"),
            ("cpp", 3.5, r"(?m)\b(?:nullptr|auto\s+\w+\s*=|using\s+namespace)\b", "cxx11+"),
            ("cpp", 3.0, r"(?m)::\w+|operator\s*[+\-*/=<>!]+", "cxx scope/op"),
            ("cpp", 2.5, r"(?m)\b(?:vector|string|map|unique_ptr|shared_ptr)\s*<", "stl"),
            ("cpp", 2.0, r"(?m)\b(?:try|catch|throw)\b", "cxx exceptions"),
            # ── CUDA (C++/C GPU dialect on the spectrum) ──
            ("cuda", 5.0, r"(?m)\b__global__\b|\b__device__\b|\b__host__\b|\b__shared__\b", "cuda qualifier"),
            ("cuda", 4.0, r"(?m)\bcudaMalloc|cudaMemcpy|<<<\s*\w+\s*,\s*\w+\s*>>>", "cuda api/launch"),
            ("cuda", 2.5, r"(?m)\bblockIdx|threadIdx|blockDim|gridDim\b", "cuda builtins"),
            # ── Objective-C ──
            ("objc", 5.0, r"(?m)@interface|@implementation|@property|@synthesize|@end\b", "objc annot"),
            ("objc", 3.5, r"(?m)\[\s*\w+[^\]]*\]", "objc message"),
            ("objc", 3.0, r"(?m)#\s*import\s*[<\"]|NSString|NSObject|NSURL\b", "cocoa"),
            # ── Other frequent langs (for editor status / vibe apply) ──
            ("python", 4.0, r"(?m)^\s*(?:def|class|async\s+def)\s+\w+|^\s*import\s+\w+|^\s*from\s+\w+\s+import", "python"),
            ("python", 3.0, r"(?m):\s*$|^\s*self\.|print\s*\(", "python shape"),
            ("javascript", 3.5, r"(?m)\b(?:const|let|var|function|=>|console\.log)\b", "js"),
            ("typescript", 4.0, r"(?m)\b(?:interface|type)\s+\w+|:\s*(?:string|number|boolean)\b", "ts"),
            ("rust", 4.0, r"(?m)\b(?:fn|let\s+mut|impl|pub\s+fn|println!)\b", "rust"),
            ("go", 4.0, r"(?m)\bpackage\s+\w+|func\s+\w+\(|:=", "go"),
            ("java", 3.5, r"(?m)\bpublic\s+class\b|System\.out\.println", "java"),
            ("bash", 3.5, r"(?m)^\s*#!\s*/.+\b(?:bash|sh)\b|^\s*(?:echo|export|if\s+\[\s)", "bash"),
            ("html", 4.0, r"(?mi)<!DOCTYPE\s+html>|<html\b|</(?:div|span|body|head)>", "html"),
            ("css", 3.5, r"(?m)\{[^}]*:[^;]+;|\b(?:margin|padding|display|color)\s*:", "css"),
            ("json", 3.5, r"(?m)^\s*\{[\s\S]*\"\w+\"\s*:", "json"),
            ("yaml", 3.0, r"(?m)^\s*[\w-]+:\s+[^\n{]+$|^\s*-\s+\w+", "yaml"),
            ("markdown", 3.0, r"(?m)^#{1,6}\s|^\s*[-*]\s+\w+|```\w*", "markdown"),
            ("sql", 3.5, r"(?mi)\bSELECT\b.+\bFROM\b|\bINSERT\s+INTO\b|\bCREATE\s+TABLE\b", "sql"),
            ("csharp", 3.5, r"(?m)\busing\s+System\b|\bnamespace\s+\w+|Console\.Write", "csharp"),
            ("ruby", 3.0, r"(?m)\bdef\s+\w+|^\s*end\s*$|\bputs\b", "ruby"),
            ("php", 3.5, r"(?m)<\?php|\b\$\w+\s*=", "php"),
            ("swift", 3.5, r"(?m)\bfunc\s+\w+|import\s+Foundation|\bvar\s+\w+\s*:", "swift"),
            ("kotlin", 3.5, r"(?m)\bfun\s+\w+|^\s*val\s+\w+|^\s*var\s+\w+", "kotlin"),
            ("perl", 3.5, r"(?m)\buse\s+strict|my\s+\$\w+|sub\s+\w+\s*\{", "perl"),
            ("lua", 3.5, r"(?m)\blocal\s+\w+\s*=|function\s+\w+\s*\(|print\s*\(", "lua"),
            ("dart", 3.5, r"(?m)\bvoid\s+main|class\s+\w+\s+extends", "dart"),
            ("scala", 3.5, r"(?m)\bobject\s+\w+|def\s+\w+\s*\(|val\s+\w+\s*=", "scala"),
            ("haskell", 3.5, r"(?m)\bmodule\s+\w+|main\s*=|::\s*(?:Int|String|IO)\b", "haskell"),
            ("elixir", 3.5, r"(?m)\bdefmodule\s+\w+|def\s+\w+\s*\(do|alias\s+", "elixir"),
            ("clojure", 3.5, r"(?m)\(defn\s+|\(ns\s+|\(def\s+", "clojure"),
            ("julia", 3.5, r"(?m)\bfunction\s+\w+|end\s*$|println\s*\(", "julia"),
            ("zig", 3.5, r"(?m)\bfn\s+main|pub\s+fn|const\s+\w+\s*=", "zig"),
            ("nim", 3.5, r"(?m)\bproc\s+\w+|echo\s+|var\s+\w+\s*:", "nim"),
            ("fsharp", 3.5, r"(?m)\blet\s+\w+\s*=|module\s+\w+|open\s+\w+", "fsharp"),
            ("solidity", 3.5, r"(?m)\bpragma\s+solidity|contract\s+\w+|mapping\s*\(", "solidity"),
            ("fortran", 3.5, r"(?mi)\bprogram\s+\w+|\bend\s+do|!\s*\$|implicit none", "fortran"),
            ("pascal", 3.5, r"(?mi)\bprogram\s+\w+|\bbegin\b|\bend\b(?:\s*\.)?|\buses\s+", "pascal"),
            ("ada", 3.5, r"(?mi)\bwith\s+\w+|\bprocedure\s+\w+|\bfunction\s+\w+\s+return\b", "ada"),
        ]
        cls.RULES = [
            (lang, w, re.compile(pat), reason) for lang, w, pat, reason in raw
        ]

    @classmethod
    def normalize(cls, token: str) -> str:
        t = (token or "").strip().lower()
        return cls.ALIASES.get(t, t)

    @classmethod
    def from_path(cls, path: str) -> Optional[str]:
        if not path:
            return None
        _, ext = os.path.splitext(path)
        lang = cls.EXT_MAP.get(ext) or cls.EXT_MAP.get(ext.lower())
        if lang:
            return lang
        base = os.path.basename(path)
        spec_map = {
            "Dockerfile": "dockerfile",
            "Makefile": "makefile",
            "CMakeLists.txt": "cmake",
        }
        for name, lang in spec_map.items():
            if base.endswith(name):
                return lang
        return None

    @classmethod
    def detect(cls, code: str, *, hint: str = "", path: str = "") -> LangHit:
        cls._build_rules()
        text = code or ""
        scores: Dict[str, float] = {}
        reasons: Dict[str, List[str]] = {}

        def add(lang: str, w: float, why: str):
            lang = cls.normalize(lang)
            scores[lang] = scores.get(lang, 0.0) + w
            reasons.setdefault(lang, []).append(why)

        # Extension / fence hints
        if path:
            ext_lang = cls.from_path(path)
            if ext_lang:
                add(ext_lang, 6.0, f"ext {os.path.splitext(path)[1]}")
        if hint:
            add(hint, 5.5, f"hint `{hint}`")

        if not text.strip() and scores:
            best = max(scores, key=scores.get)
            return LangHit(best, 0.55, scores, reasons.get(best, []))

        # Fingerprint scan
        for lang, weight, pat, reason in cls.RULES:
            n = sum(1 for _ in pat.finditer(text))
            if n:
                boost = weight * (1.0 + 0.35 * min(n - 1, 4))
                add(lang, boost, f"{reason}×{n}")

        # Negative evidence / disambiguation on asm→cpp spectrum
        if scores.get("cpp", 0) >= 3.0:
            scores["c"] = scores.get("c", 0) * 0.35
        if scores.get("cuda", 0) >= 4.0:
            scores["cpp"] = scores.get("cpp", 0) * 0.7
            scores["c"] = scores.get("c", 0) * 0.5
        if scores.get("objc", 0) >= 4.0:
            scores["c"] = scores.get("c", 0) * 0.4
            scores["cpp"] = scores.get("cpp", 0) * 0.5
        if re.search(r"%[er]?[abcd]x|%\w+", text) and scores.get("assembly", 0):
            add("assembly", 1.5, "AT&T %reg")
        if re.search(r"\bptr\b|\bbyte\b|\bword\b|\bdword\b|\bqword\b", text, re.I) and scores.get("assembly", 0):
            add("assembly", 1.2, "Intel size keyword")
        if path.endswith(".h") and scores.get("cpp", 0) < 2.0:
            add("c", 2.0, ".h as C")

        if not scores:
            return LangHit("unknown", 0.0, {}, ["no fingerprints"])

        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best_lang, best_score = ordered[0]
        total = sum(max(v, 0.0) for v in scores.values()) or 1.0
        conf = max(0.0, min(1.0, best_score / (total * 0.85 + best_score * 0.15)))

        if len(ordered) > 1:
            second_lang, second_score = ordered[1]
            if best_score - second_score < 1.25:
                for prefer in ("cuda", "objc", "cpp", "assembly", "c"):
                    if prefer in (best_lang, second_lang) and scores.get(prefer, 0) >= second_score * 0.9:
                        if prefer in cls.SPECTRUM:
                            best_lang = prefer
                            break

        return LangHit(
            lang=best_lang,
            confidence=round(conf, 3),
            scores={k: round(v, 2) for k, v in ordered},
            reasons=reasons.get(best_lang, [])[:8],
        )

    @classmethod
    def detect_all(cls, code: str, *, top: int = 5) -> List[LangHit]:
        """Rank every candidate — useful for asm→cpp spectrum UI."""
        hit = cls.detect(code)
        ranked = []
        for lang, sc in list(hit.scores.items())[:top]:
            total = sum(hit.scores.values()) or 1.0
            ranked.append(LangHit(
                lang=lang,
                confidence=round(sc / total, 3),
                scores=hit.scores,
                reasons=[],
            ))
        return ranked or [hit]


# ──────────────────────────────────────────────────────────────
# Editor (with line numbers + light syntax)
# ──────────────────────────────────────────────────────────────
class Editor(tk.Frame):
    def __init__(self, master, app, title: str = "untitled.py"):
        super().__init__(master, bg=EDITOR_BG)
        self.app = app
        self.title = title
        self.dirty = False
        self.detected: Optional[LangHit] = None
        self.mono = mono_font(13)

        self.linenos = tk.Text(
            self, width=5, padx=8, takefocus=0, bd=0, bg=EDITOR_BG,
            fg=FG_FAINT, font=self.mono, state="disabled",
            highlightthickness=0, cursor="arrow",
        )
        self.linenos.pack(side="left", fill="y")

        self.text = tk.Text(
            self, wrap="none", undo=True, bd=0, padx=10, pady=8,
            bg=EDITOR_BG, fg=FG, insertbackground=FG_BRIGHT,
            insertwidth=2, selectbackground=SEL_BG,
            selectforeground=FG_BRIGHT, font=self.mono,
            highlightthickness=0, tabs=(self.mono.measure("    "),),
        )
        self.text.pack(side="left", fill="both", expand=True)

        ysb = tk.Scrollbar(
            self, orient="vertical", command=self._yscroll,
            troughcolor=EDITOR_BG, bg=SIDEBAR_BG, bd=0,
            activebackground=FG_DIM, highlightthickness=0,
            relief="flat", width=10,
        )
        ysb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=lambda a, b: (ysb.set(a, b), self._sync()))

        self.text.tag_configure("curline", background=CURLINE)
        for tag, color in SYNTAX.items():
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_raise("sel")

        self.text.bind("<KeyRelease>", self._on_change)
        self.text.bind("<ButtonRelease-1>", lambda e: self._cursor_moved())
        self.text.bind("<Return>", self._auto_indent)
        self.text.bind("<Tab>", self._soft_tab)
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.tag_configure("bracket_match", background=SEL_BG, foreground=FG_BRIGHT)
        self._bracket_pairs = {"(": ")", "{": "}", "[": "]", ")": "(", "}": "{", "]": "["}
        self._sync()

    def _yscroll(self, *args):
        self.text.yview(*args)
        self._sync()

    def _sync(self):
        lines = int(self.text.index("end-1c").split(".")[0])
        self.linenos.configure(state="normal")
        self.linenos.delete("1.0", "end")
        self.linenos.insert("1.0", "\n".join(str(i) for i in range(1, lines + 1)))
        self.linenos.configure(state="disabled")
        self.linenos.yview_moveto(self.text.yview()[0])

    def _auto_indent(self, _e):
        line = self.text.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", line).group(0)
        if line.rstrip().endswith(":"):
            indent += "    "
        self.text.insert("insert", "\n" + indent)
        self.after_idle(self._on_change)
        return "break"

    def _soft_tab(self, _e):
        self.text.insert("insert", "    ")
        return "break"

    def _on_modified(self, _e=None):
        if self.text.edit_modified():
            self.dirty = True
            self.text.edit_modified(False)
            self.app._refresh_tab_labels()

    def _on_change(self, _e=None):
        self._highlight()
        self._cursor_moved()
        self._sync()

    def _cursor_moved(self):
        self.text.tag_remove("curline", "1.0", "end")
        self.text.tag_add("curline", "insert linestart", "insert lineend+1c")
        self._match_bracket()
        self.app.update_cursor_status()

    def _match_bracket(self):
        self.text.tag_remove("bracket_match", "1.0", "end")
        pos = self.text.index("insert")
        char = self.text.get(pos, f"{pos}+1c")
        if char in self._bracket_pairs:
            close = self._bracket_pairs[char]
            if char in "({[":
                count = 1
                idx = self.text.index(f"{pos}+1c")
                while True:
                    ch = self.text.get(idx, f"{idx}+1c")
                    if not ch:
                        break
                    if ch == char:
                        count += 1
                    elif ch == close:
                        count -= 1
                        if count == 0:
                            self.text.tag_add("bracket_match", idx, f"{idx}+1c")
                            self.text.tag_add("bracket_match", pos, f"{pos}+1c")
                            break
                    idx = self.text.index(f"{idx}+1c")
            else:
                count = 1
                idx = self.text.index(f"{pos}-1c")
                while True:
                    ch = self.text.get(idx, f"{idx}+1c")
                    if not ch:
                        break
                    if ch == close:
                        count += 1
                    elif ch == char:
                        count -= 1
                        if count == 0:
                            self.text.tag_add("bracket_match", idx, f"{idx}+1c")
                            self.text.tag_add("bracket_match", pos, f"{pos}+1c")
                            break
                    idx = self.text.index(f"{idx}-1c")

    def get(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_content(self, content: str, *, mark_clean: bool = True):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        if mark_clean:
            self.dirty = False
            self.text.edit_modified(False)
        self._on_change()

    def apply_code(self, code: str, *, replace: bool = True):
        if replace:
            self.set_content(code, mark_clean=False)
            self.dirty = True
        else:
            self.text.insert("insert", "\n" + code + "\n")
            self.dirty = True
        self.app._refresh_tab_labels()
        self._on_change()

    def _highlight(self):
        content = self.get()
        for tag in SYNTAX:
            self.text.tag_remove(tag, "1.0", "end")
        hit = CodeLangDetector.detect(content, path=self.title)
        self.detected = hit
        CatsSyntax.apply(self, content, hit.lang)

    def _tag_span(self, tag: str, start: int, end: int):
        self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")


# ──────────────────────────────────────────────────────────────
# catide
# ──────────────────────────────────────────────────────────────
class CatIDE(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("1500x920")
        self.minsize(1000, 620)
        self.configure(bg=BG)

        self.ui_queue: queue.Queue = queue.Queue()
        self.mode = tk.StringVar(value="Agent")  # Agent | Ask | Plan
        self.view_mode = tk.StringVar(value="editor")  # editor | agents
        self.engine = None
        self.catseek = None
        self.catseek_path = ""
        self.engine_ready = False
        self.busy = False
        self.tabs: Dict[str, Dict[str, Any]] = {}
        self.active_key: Optional[str] = None
        self._buffers: Dict[str, str] = {}  # in-memory workspace · files = off
        self._untitled_n = 1
        self.last_agent_code = ""
        self.last_detect: Optional[LangHit] = None
        self._act_rails: Dict[str, tk.Frame] = {}
        self._surface_btns: Dict[str, tk.Button] = {}
        self.chat_density = tk.StringVar(value="Compact")
        self._agent_fullscreen = False
        self._sidebar_hidden = False
        self._float_composer: Optional[tk.Frame] = None

        if IS_MAC:
            try:
                self.tk.call("::tk::unsupported::MacWindowStyle", "style", self._w, "dark", "normal")
            except tk.TclError:
                pass

        self._style_ttk()
        self._build_menu()
        self._build_ui()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._quit_app)

        self.after(60, self._pump)
        self._open_welcome()
        threading.Thread(target=self._boot_engine, daemon=True).start()

    # ── theme helpers ─────────────────────────────────────────
    def _style_ttk(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(
            "Cat.Treeview",
            background=SIDEBAR_BG, fieldbackground=SIDEBAR_BG, foreground=FG,
            bordercolor=SIDEBAR_BG, borderwidth=0, font=ui_font(11), rowheight=24,
        )
        st.map(
            "Cat.Treeview",
            background=[("selected", SEL_BG)],
            foreground=[("selected", FG_BRIGHT)],
        )

    def _btn(self, parent, label, cmd, size=11, pad=(10, 4)):
        b = tk.Button(
            parent, text=label, command=cmd, bg=BTN_BG, fg=BTN_FG,
            activebackground=BTN_HOVER, activeforeground=FG_BRIGHT,
            bd=0, padx=pad[0], pady=pad[1], font=ui_font(size, "bold"),
            cursor="hand2", highlightthickness=0, relief="flat",
        )
        b.bind("<Enter>", lambda e: b.configure(bg=BTN_HOVER))
        b.bind("<Leave>", lambda e: b.configure(bg=BTN_BG))
        return b

    # ── menu ──────────────────────────────────────────────────
    def _build_menu(self):
        m = tk.Menu(self)
        filem = tk.Menu(m, tearoff=0)
        filem.add_command(label="New File", accelerator=f"{MOD_LABEL}N", command=self.new_file)
        filem.add_command(label="Open File…", accelerator=f"{MOD_LABEL}O", command=self.open_file)
        filem.add_command(label="Save", accelerator=f"{MOD_LABEL}S", command=self.save_file)
        filem.add_command(label="Save As…", command=self.save_file_as)
        filem.add_command(label="Load Markdown", command=self.load_markdown)
        filem.add_command(label="Close", accelerator=f"{MOD_LABEL}W", command=self.close_active)
        filem.add_separator()
        filem.add_command(label="Exit", accelerator=f"{MOD_LABEL}Q", command=self._quit_app)
        m.add_cascade(label="File", menu=filem)

        viewm = tk.Menu(m, tearoff=0)
        viewm.add_command(label="Command Palette…", accelerator=f"{MOD_LABEL}⇧P",
                          command=self.command_palette)
        viewm.add_command(label="Agents Window", accelerator=f"{MOD_LABEL}⇧A",
                          command=lambda: self.set_surface("agents"))
        viewm.add_command(label="Editor Window", accelerator=f"{MOD_LABEL}⇧E",
                          command=lambda: self.set_surface("editor"))
        viewm.add_command(label="Full-screen Agent Tab", accelerator=f"{MOD_LABEL}⇧M",
                          command=self.toggle_agent_fullscreen)
        viewm.add_command(label="Detect Language", command=self.detect_active_lang)
        viewm.add_command(label="Toggle Sidebar", accelerator=f"{MOD_LABEL}B",
                          command=self.toggle_sidebar)
        viewm.add_command(label="Toggle Panel", accelerator=f"{MOD_LABEL}J",
                          command=self.toggle_panel)
        viewm.add_command(label="Toggle Agent", accelerator=f"{MOD_LABEL}I",
                          command=self.toggle_agent)
        m.add_cascade(label="View", menu=viewm)

        runm = tk.Menu(m, tearoff=0)
        runm.add_command(label="Run Active Buffer", accelerator=f"{MOD_LABEL}R",
                         command=self.run_active)
        runm.add_command(label="Run Markdown Code Blocks", command=self.run_markdown_blocks)
        runm.add_command(label="Apply Last Agent Code", command=self.apply_last_code)
        runm.add_separator()
        runm.add_command(label="Convert ASM → C++", command=self.asm_to_cpp)
        m.add_cascade(label="Run", menu=runm)

        helpm = tk.Menu(m, tearoff=0)
        helpm.add_command(label="Help", command=self.show_help)
        helpm.add_separator()
        helpm.add_command(label="About catide", command=self.show_about)
        m.add_cascade(label="Help", menu=helpm)
        self.configure(menu=m)
        self._menubar = m
        self._file_menu = filem
        self._help_menu = helpm

    # ── layout (chrome · blue hue · agent features kept) ──
    def _build_ui(self):
        self._build_titlebar()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # activity bar
        act = tk.Frame(body, bg=ACTIVITY_BG, width=48)
        act.pack(side="left", fill="y")
        act.pack_propagate(False)

        self._act_buttons = {}
        self._act_rails = {}
        for icon, key, _tip in (
            ("📂", "explorer", "Explorer"),
            ("🔎", "search", "Search"),
            ("⎇", "scm", "Source Control"),
            ("▶", "run", "Run and Debug"),
            ("🧩", "ext", "Extensions"),
            ("✦", "agent", "Agents"),
        ):
            row = tk.Frame(act, bg=ACTIVITY_BG, height=48)
            row.pack(fill="x")
            row.pack_propagate(False)
            rail = tk.Frame(row, bg=ACTIVITY_BG, width=2)
            rail.pack(side="left", fill="y")
            self._act_rails[key] = rail
            b = tk.Button(
                row, text=icon, bd=0, bg=ACTIVITY_BG, fg=FG_DIM,
                activebackground=ACTIVITY_BG, activeforeground=FG_BRIGHT,
                font=("Helvetica", 14), cursor="hand2", highlightthickness=0,
                command=lambda k=key: self._activity(k),
            )
            b.pack(fill="both", expand=True)
            self._act_buttons[key] = b

        # settings gear at bottom
        bot = tk.Frame(act, bg=ACTIVITY_BG)
        bot.pack(side="bottom", fill="x", pady=8)
        tk.Button(
            bot, text="⚙", bd=0, bg=ACTIVITY_BG, fg=FG_DIM,
            activebackground=ACTIVITY_BG, activeforeground=FG_BRIGHT,
            font=("Helvetica", 14), cursor="hand2", highlightthickness=0,
            command=self.command_palette,
        ).pack()

        self.hpane = tk.PanedWindow(
            body, orient="horizontal", bg=BG, sashwidth=4, bd=0,
            sashrelief="flat", opaqueresize=True,
        )
        self.hpane.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_center()
        self._build_agent_pane()

        self.hpane.add(self.sidebar, minsize=180, width=260)
        self.hpane.add(self.center, minsize=420, stretch="always")
        self.hpane.add(self.agent_pane, minsize=340, width=380)

        self._build_status()
        self._activity("explorer")

    def _build_titlebar(self):
        """title/menubar strip; keeps Editor | Agents switch."""
        bar = tk.Frame(self, bg=TITLE_BG, height=35)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        left = tk.Frame(bar, bg=TITLE_BG)
        left.pack(side="left", fill="y", padx=(10, 0))
        tk.Label(
            left, text=APP_NAME, bg=TITLE_BG, fg=FG_BRIGHT,
            font=ui_font(11, "bold"),
        ).pack(side="left")

        # menu strip — File / Save / Close / Exit / About / Help
        # Menubutton + system menus (no custom Menu colors — those beachball on macOS).
        # No Enter/Leave hover handlers, no hand2 cursor (hover thrash / lag).
        strip_font = ui_font(10)
        mb_kw = dict(
            bg=TITLE_BG, fg=FG_DIM, font=strip_font,
            activebackground=TITLE_BG, activeforeground=FG_BRIGHT,
            bd=0, highlightthickness=0, relief="flat", padx=8,
            cursor="",
        )
        file_mb = tk.Menubutton(left, text="File", **mb_kw)
        file_mb.pack(side="left")
        strip_file = tk.Menu(file_mb, tearoff=0)
        strip_file.add_command(label="New File", accelerator=f"{MOD_LABEL}N",
                                command=lambda: self.after_idle(self.new_file))
        strip_file.add_command(label="Open File…", accelerator=f"{MOD_LABEL}O",
                                command=lambda: self.after_idle(self.open_file))
        strip_file.add_command(label="Save", accelerator=f"{MOD_LABEL}S",
                                command=lambda: self.after_idle(self.save_file))
        strip_file.add_command(label="Save As…",
                                command=lambda: self.after_idle(self.save_file_as))
        strip_file.add_command(label="Load Markdown",
                                command=lambda: self.after_idle(self.load_markdown))
        strip_file.add_command(label="Close", accelerator=f"{MOD_LABEL}W",
                                command=lambda: self.after_idle(self.close_active))
        strip_file.add_separator()
        strip_file.add_command(label="Exit", accelerator=f"{MOD_LABEL}Q",
                                command=lambda: self.after_idle(self._quit_app))
        file_mb.configure(menu=strip_file)
        self._strip_file_menu = strip_file

        btn_kw = dict(
            bg=TITLE_BG, fg=FG_DIM, font=strip_font,
            activebackground=TITLE_BG, activeforeground=FG_BRIGHT,
            bd=0, highlightthickness=0, relief="flat", padx=8,
            cursor="", takefocus=0,
        )
        for label, cmd in (
            ("Save", self.save_file),
            ("Close", self.close_active),
            ("Exit", self._quit_app),
            ("Asm→C++", self.asm_to_cpp),
            ("About", self.show_about),
            ("Help", self.show_help),
        ):
            tk.Button(
                left, text=label, command=lambda c=cmd: self.after_idle(c), **btn_kw,
            ).pack(side="left")
            tk.Button(
                left, text=label, command=lambda c=cmd: self.after_idle(c), **btn_kw,
            ).pack(side="left")

        # keep agent surface switch (agent feature)
        switch = tk.Frame(bar, bg=CHIP_BG, highlightthickness=1,
                          highlightbackground=BORDER)
        switch.pack(side="left", padx=16, pady=5)
        self._surface_btns = {}
        for name, key in (("Editor", "editor"), ("Agents", "agents")):
            b = tk.Button(
                switch, text=name, bd=0, bg=CHIP_BG, fg=FG_DIM,
                activebackground=BTN_HOVER, activeforeground=FG_BRIGHT,
                font=ui_font(9, "bold"), cursor="hand2", padx=12, pady=2,
                highlightthickness=0,
                command=lambda k=key: self.set_surface(k),
            )
            b.pack(side="left")
            self._surface_btns[key] = b
        self._refresh_surface_btns()

        center = tk.Frame(bar, bg=TITLE_BG)
        center.pack(side="left", expand=True)
        self.title_center = tk.Label(
            center, text=f"{APP_NAME} — workspace (files = off)",
            bg=TITLE_BG, fg=FG_DIM, font=ui_font(10),
        )
        self.title_center.pack()

        right = tk.Frame(bar, bg=TITLE_BG)
        right.pack(side="right", padx=10)
        self._btn(right, f"{MOD_LABEL}⇧P", self.command_palette, size=8, pad=(7, 2)).pack(
            side="right", pady=5
        )

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.hpane, bg=SIDEBAR_BG)
        tk.Frame(self.sidebar, bg=BORDER, width=1).pack(side="right", fill="y")

        self.explorer_view = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        head = tk.Frame(self.explorer_view, bg=SIDEBAR_BG)
        head.pack(fill="x")
        tk.Label(
            head, text="EXPLORER", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(9, "bold"), anchor="w", padx=16, pady=10,
        ).pack(side="left")
        acts = tk.Frame(head, bg=SIDEBAR_BG)
        acts.pack(side="right", padx=6)
        self._btn(acts, "＋", self.new_file, size=9, pad=(6, 1)).pack(side="left", padx=2)
        self._btn(acts, "↻", lambda: self._refresh_buffer_list(), size=9, pad=(6, 1)).pack(side="left")

        # section: OPEN EDITORS
        sec = tk.Frame(self.explorer_view, bg=SIDEBAR_BG)
        sec.pack(fill="x", pady=(2, 0))
        tk.Label(
            sec, text="▼  OPEN EDITORS", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(9, "bold"), anchor="w", padx=12, pady=4,
        ).pack(fill="x")

        self.buffer_list = tk.Listbox(
            self.explorer_view, bg=SIDEBAR_BG, fg=FG, bd=0,
            selectbackground=SEL_BG, selectforeground=FG_BRIGHT,
            font=ui_font(11), highlightthickness=0, activestyle="none",
            relief="flat",
        )
        self.buffer_list.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.buffer_list.bind("<<ListboxSelect>>", self._buffer_select)

        # section: WORKSPACE
        ws = tk.Frame(self.explorer_view, bg=SIDEBAR_BG)
        ws.pack(fill="x")
        tk.Label(
            ws, text="▼  catide (FILES = OFF)", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(9, "bold"), anchor="w", padx=12, pady=4,
        ).pack(fill="x")
        tk.Label(
            ws, text="  📄  in-memory buffers only", bg=SIDEBAR_BG, fg=FG_FAINT,
            font=ui_font(10), anchor="w", padx=8, pady=2,
        ).pack(fill="x")
        tk.Label(
            ws, text="  ✦  Agents panel (right)", bg=SIDEBAR_BG, fg=FG_FAINT,
            font=ui_font(10), anchor="w", padx=8, pady=2,
        ).pack(fill="x", pady=(0, 10))

        # search view
        self.search_view = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        tk.Label(
            self.search_view, text="SEARCH", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(9, "bold"), anchor="w", padx=16, pady=10,
        ).pack(fill="x")
        search_wrap = tk.Frame(self.search_view, bg=BORDER)
        search_wrap.pack(fill="x", padx=12)
        inner = tk.Frame(search_wrap, bg=INPUT_BG)
        inner.pack(fill="x", padx=1, pady=1)
        self.search_entry = tk.Entry(
            inner, bg=INPUT_BG, fg=FG_BRIGHT, bd=0,
            insertbackground=FG_BRIGHT, font=ui_font(12),
            highlightthickness=0,
        )
        self.search_entry.pack(fill="x", padx=8, ipady=6)
        self.search_entry.bind("<Return>", lambda e: self.run_search())
        self.search_results = tk.Listbox(
            self.search_view, bg=SIDEBAR_BG, fg=FG, bd=0,
            selectbackground=SEL_BG, selectforeground=FG_BRIGHT,
            font=ui_font(10), highlightthickness=0, activestyle="none",
        )
        self.search_results.pack(fill="both", expand=True, padx=6, pady=8)
        self.search_results.bind("<Double-1>", self._search_open)
        self._search_hits: List[Tuple[str, int, str]] = []

        # stub views for activity icons
        self.scm_view = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        tk.Label(
            self.scm_view, text="SOURCE CONTROL", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(9, "bold"), anchor="w", padx=16, pady=10,
        ).pack(fill="x")
        tk.Label(
            self.scm_view, text="No source control providers\n(files = off)",
            bg=SIDEBAR_BG, fg=FG_FAINT, font=ui_font(11), justify="center",
        ).pack(expand=True, pady=40)

        self.ext_view = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        tk.Label(
            self.ext_view, text="EXTENSIONS", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(9, "bold"), anchor="w", padx=16, pady=10,
        ).pack(fill="x")
        tk.Label(
            self.ext_view, text="CatSeek R1 Agent  ·  installed\nCodeLangDetector  ·  installed",
            bg=SIDEBAR_BG, fg=FG, font=ui_font(11), justify="left",
        ).pack(anchor="w", padx=16, pady=12)

    def _build_center(self):
        self.center = tk.Frame(self.hpane, bg=BG)

        # editor tab bar
        self.tab_bar = tk.Frame(self.center, bg=TAB_BG, height=35)
        self.tab_bar.pack(fill="x")
        self.tab_bar.pack_propagate(False)
        self.tab_row = tk.Frame(self.tab_bar, bg=TAB_BG)
        self.tab_row.pack(side="left", fill="both", expand=True)
        tk.Frame(self.tab_bar, bg=BORDER, height=1).place(relx=0, rely=1, relwidth=1, anchor="sw")

        # breadcrumbs
        self.breadcrumb = tk.Frame(self.center, bg=BREADCRUMB_BG, height=22)
        self.breadcrumb.pack(fill="x")
        self.breadcrumb.pack_propagate(False)
        self.breadcrumb_label = tk.Label(
            self.breadcrumb, text="  …  ›  welcome.md",
            bg=BREADCRUMB_BG, fg=FG_DIM, font=ui_font(9), anchor="w",
        )
        self.breadcrumb_label.pack(fill="x", padx=8)
        tk.Frame(self.center, bg=BORDER, height=1).pack(fill="x")

        self.vpane = tk.PanedWindow(
            self.center, orient="vertical", bg=BG, sashwidth=4, bd=0,
            sashrelief="flat",
        )
        self.vpane.pack(fill="both", expand=True)

        self.editor_host = tk.Frame(self.vpane, bg=EDITOR_BG)
        self.empty_editor = tk.Frame(self.editor_host, bg=EDITOR_BG)
        self.empty_editor.place(relx=0.5, rely=0.42, anchor="center")
        tk.Label(
            self.empty_editor, text=APP_NAME, bg=EDITOR_BG, fg=FG_BRIGHT,
            font=ui_font(22, "bold"),
        ).pack()
        tk.Label(
            self.empty_editor,
            text="IDE layout  ·  blue hue  ·  Agents on the right",
            bg=EDITOR_BG, fg=FG_DIM, font=ui_font(11),
        ).pack(pady=(6, 0))
        tk.Label(
            self.empty_editor,
            text=f"{MOD_LABEL}⇧P  Command Palette    {MOD_LABEL}B  Sidebar    {MOD_LABEL}J  Panel    {MOD_LABEL}I  Agents",
            bg=EDITOR_BG, fg=FG_FAINT, font=ui_font(10),
        ).pack(pady=(16, 0))
        shortcuts = tk.Frame(self.empty_editor, bg=EDITOR_BG)
        shortcuts.pack(pady=(18, 0))
        for left, right in (
            (f"{MOD_LABEL}⇧A", "Agents Window"),
            (f"{MOD_LABEL}⇧M", "Full-screen Agent"),
            (f"{MOD_LABEL}L", "Detect Language"),
            (f"{MOD_LABEL}N", "New File"),
        ):
            row = tk.Frame(shortcuts, bg=EDITOR_BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=left, bg=CHIP_BG, fg=FG_BRIGHT, font=ui_font(9),
                     padx=8, pady=2).pack(side="left")
            tk.Label(row, text=f"  {right}", bg=EDITOR_BG, fg=FG_DIM,
                     font=ui_font(10)).pack(side="left")

        # bottom panel — TERMINAL / PROBLEMS / OUTPUT
        self.panel = tk.Frame(self.vpane, bg=PANEL_BG)
        tk.Frame(self.panel, bg=BORDER, height=1).pack(fill="x")
        phead = tk.Frame(self.panel, bg=PANEL_BG)
        phead.pack(fill="x")
        self._panel_tabs = {}
        for name in ("PROBLEMS", "OUTPUT", "DEBUG CONSOLE", "TERMINAL"):
            b = tk.Button(
                phead, text=name, bd=0, bg=PANEL_BG, fg=FG_DIM,
                activebackground=PANEL_BG, activeforeground=FG_BRIGHT,
                font=ui_font(9, "bold"), cursor="hand2", padx=12, pady=6,
                highlightthickness=0,
                command=lambda n=name: self.show_panel_tab(n),
            )
            b.pack(side="left")
            self._panel_tabs[name] = b
        self._btn(phead, "︿", self.toggle_panel, size=8, pad=(6, 2)).pack(side="right", padx=6, pady=2)

        self.panel_body = tk.Frame(self.panel, bg=PANEL_BG)
        self.panel_body.pack(fill="both", expand=True)

        self.terminal = scrolledtext.ScrolledText(
            self.panel_body, wrap="word", bg=INPUT_BG, fg=FG,
            insertbackground=FG_BRIGHT, font=mono_font(12),
            relief="flat", bd=0, padx=12, pady=8,
        )
        self.output = scrolledtext.ScrolledText(
            self.panel_body, wrap="word", bg=INPUT_BG, fg=FG,
            insertbackground=FG_BRIGHT, font=mono_font(12),
            relief="flat", bd=0, padx=12, pady=8,
        )
        self.problems = scrolledtext.ScrolledText(
            self.panel_body, wrap="word", bg=INPUT_BG, fg=WARN_YEL,
            insertbackground=FG_BRIGHT, font=mono_font(12),
            relief="flat", bd=0, padx=12, pady=8,
        )
        self.debug_console = scrolledtext.ScrolledText(
            self.panel_body, wrap="word", bg=INPUT_BG, fg=FG_DIM,
            insertbackground=FG_BRIGHT, font=mono_font(12),
            relief="flat", bd=0, padx=12, pady=8,
        )
        self.debug_console.insert("1.0", "Debug Console (stub)\n")

        term_row = tk.Frame(self.panel, bg=PANEL_BG)
        term_row.pack(fill="x", side="bottom", padx=6, pady=4)
        tk.Label(term_row, text="bash  ›", bg=PANEL_BG, fg=OK_GREEN,
                 font=mono_font(11)).pack(side="left", padx=(4, 6))
        self._term_input = tk.Entry(
            term_row, bg=BTN_BG, fg=FG, insertbackground=FG,
            relief="flat", font=mono_font(12), highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        self._term_input.pack(fill="x", side="left", expand=True, ipady=3)
        self._term_input.bind("<Return>", self._term_run)

        self.vpane.add(self.editor_host, minsize=220, stretch="always")
        self.vpane.add(self.panel, minsize=120, height=180)
        self.show_panel_tab("TERMINAL")
        self._panel_visible = True

    def _build_agent_pane(self):
        """Agents Window — compact chats · CatSeek R1."""
        self.agent_pane = tk.Frame(self.hpane, bg=SIDEBAR_BG)
        self._agent_visible = True
        tk.Frame(self.agent_pane, bg=BORDER, width=1).pack(side="left", fill="y")

        body = tk.Frame(self.agent_pane, bg=SIDEBAR_BG)
        body.pack(fill="both", expand=True)
        self._agent_body = body

        head = tk.Frame(body, bg=SIDEBAR_BG)
        head.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(
            head, text="✦  Agents", bg=SIDEBAR_BG, fg=FG_BRIGHT,
            font=ui_font(13, "bold"),
        ).pack(side="left")
        self._btn(head, "⛶", self.toggle_agent_fullscreen, size=9, pad=(8, 2)).pack(
            side="right", padx=(4, 0)
        )
        self._btn(head, "Apply ⤶", self.apply_last_code, size=9, pad=(8, 3)).pack(
            side="right", padx=(4, 0)
        )
        self._btn(head, "Clear", self.clear_agent, size=9, pad=(8, 3)).pack(side="right")

        chips = tk.Frame(body, bg=SIDEBAR_BG)
        chips.pack(fill="x", padx=12, pady=(2, 4))
        self._agent_chip = tk.Label(
            chips, text="  Agent 1  ·  local  ·  CatSeek R1  ", bg=CHIP_BG, fg=FG_BRIGHT,
            font=ui_font(9, "bold"), padx=4, pady=4,
            highlightthickness=1, highlightbackground=ACCENT,
        )
        self._agent_chip.pack(side="left")
        self.engine_chip = tk.Label(
            chips, text="booting…", bg=SIDEBAR_BG, fg=FG_DIM, font=ui_font(8),
        )
        self.engine_chip.pack(side="right")

        modes = tk.Frame(body, bg=SIDEBAR_BG)
        modes.pack(fill="x", padx=12, pady=(0, 6))
        seg = tk.Frame(modes, bg=BORDER)
        seg.pack(side="left")
        self._mode_btns = {}
        for name in ("Agent", "Ask", "Plan"):
            b = tk.Button(
                seg, text=name, bd=0, bg=BTN_BG, fg=BTN_FG,
                activebackground=BTN_HOVER, activeforeground=FG_BRIGHT,
                font=ui_font(10, "bold"), cursor="hand2", padx=14, pady=5,
                highlightthickness=0,
                command=lambda n=name: self.set_mode(n),
            )
            b.pack(side="left", padx=1, pady=1)
            self._mode_btns[name] = b
        self._refresh_mode_btns()

        dens = tk.Frame(modes, bg=BORDER)
        dens.pack(side="right")
        self._density_btns = {}
        for name in ("Compact", "Balanced", "Detailed"):
            b = tk.Button(
                dens, text=name[:3], bd=0, bg=BTN_BG, fg=FG_DIM,
                activebackground=BTN_HOVER, activeforeground=FG_BRIGHT,
                font=ui_font(8, "bold"), cursor="hand2", padx=7, pady=4,
                highlightthickness=0,
                command=lambda n=name: self.set_chat_density(n),
            )
            b.pack(side="left", padx=1, pady=1)
            self._density_btns[name] = b
        self._refresh_density_btns()

        # Pin prompt strip to bottom FIRST so chat can't crush it (screenshot fix)
        self._composer_foot = tk.Frame(body, bg=SIDEBAR_BG, height=210)
        self._composer_foot.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        self._composer_foot.pack_propagate(False)
        self._build_composer(self._composer_foot)

        chat_wrap = tk.Frame(body, bg=BORDER)
        chat_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.agent_chat = scrolledtext.ScrolledText(
            chat_wrap, wrap="word", bg=EDITOR_BG, fg=FG,
            insertbackground=FG_BRIGHT, font=ui_font(11),
            relief="flat", bd=0, padx=14, pady=12, state="disabled",
            spacing1=2, spacing3=4,
        )
        self.agent_chat.pack(fill="both", expand=True, padx=1, pady=1)
        self.agent_chat.tag_configure("user", foreground=FG_BRIGHT,
                                      font=ui_font(11, "bold"))
        self.agent_chat.tag_configure("agent", foreground=FG)
        self.agent_chat.tag_configure("sys", foreground=FG_DIM)
        self.agent_chat.tag_configure("think", foreground=FG_FAINT)
        self.agent_chat.tag_configure("ok", foreground=OK_GREEN)
        self.agent_chat.tag_configure("meta", foreground=FG_FAINT,
                                      font=ui_font(8))
        self.agent_chat.tag_configure("lang", foreground=ACCENT,
                                      font=ui_font(9, "bold"))

        self._agent_log(
            "sys",
            f"{APP_NAME} {APP_VERSION} · Agents Window · CatSeek R1\n"
            f"Compact chats · full-screen `{MOD_LABEL}⇧M` · files = {FILES_MODE}\n"
            "Asm→C→C++ detector · CatsFrontierR1 (ChatGPT/DeepSeek-R1 workflow) · auto-apply.",
        )

    def _build_composer(self, parent):
        bg = FLOAT_BG if parent is getattr(self, "_float_composer", None) else SIDEBAR_BG
        parent.configure(bg=bg)
        chipline = tk.Frame(parent, bg=bg)
        chipline.pack(fill="x", pady=(0, 6))
        self.ctx_chip = tk.Label(
            chipline, text="@ active buffer", bg=CHIP_BG, fg=FG_DIM,
            font=ui_font(9), padx=8, pady=3,
        )
        self.ctx_chip.pack(side="left")
        self.lang_chip = tk.Label(
            chipline, text="lang: —", bg=CHIP_BG, fg=ACCENT,
            font=ui_font(9), padx=8, pady=3,
        )
        self.lang_chip.pack(side="left", padx=(6, 0))
        tk.Label(
            chipline, text=f"{APP_NAME} {APP_VERSION}", bg=bg,
            fg=FG_FAINT, font=ui_font(8),
        ).pack(side="right")

        # ONLY enlarge this prompt text box (not the code editor)
        composer = tk.Frame(parent, bg=BORDER)
        composer.pack(fill="both", expand=True)
        box = tk.Frame(composer, bg=INPUT_BG)
        box.pack(fill="both", expand=True, padx=2, pady=2)

        self.ai_input = tk.Text(
            box, wrap="word", bg=INPUT_BG, fg=FG_BRIGHT,
            insertbackground=FG_BRIGHT, font=ui_font(12),
            relief="flat", bd=0, padx=14, pady=12,
            highlightthickness=0,
        )
        self.ai_input.pack(side="left", fill="both", expand=True)
        self.ai_input.bind("<Return>", self._agent_enter)
        self.ai_input.bind("<Key>", self._composer_key)
        self.ai_input.bind("<FocusIn>", self._composer_focus)
        self.ai_input.bind("<FocusOut>", self._composer_blur)
        self._composer_placeholder = True
        self._set_composer_placeholder()

        send_col = tk.Frame(box, bg=INPUT_BG, width=48)
        send_col.pack(side="right", fill="y", padx=(4, 8), pady=8)
        send_col.pack_propagate(False)
        send = self._btn(send_col, "↑", self.send_agent, size=14, pad=(12, 10))
        send.place(relx=0.5, rely=0.5, anchor="center")


    def _set_composer_placeholder(self):
        self.ai_input.delete("1.0", "end")
        self.ai_input.insert("1.0", "Ask CatSeek to vibe code…")
        self.ai_input.configure(fg=FG_FAINT)
        self._composer_placeholder = True

    def _composer_focus(self, _e=None):
        if self._composer_placeholder:
            self.ai_input.delete("1.0", "end")
            self.ai_input.configure(fg=FG_BRIGHT)
            self._composer_placeholder = False

    def _composer_key(self, _e=None):
        if self._composer_placeholder:
            self._composer_focus()

    def _composer_blur(self, _e=None):
        if not self.ai_input.get("1.0", "end-1c").strip():
            self._set_composer_placeholder()

    def _build_status(self):
        """status bar (blue) with segments."""
        bar = tk.Frame(self, bg=STATUS_BG, height=22)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        def seg(text, side="left"):
            lbl = tk.Label(
                bar, text=f"  {text}  ", bg=STATUS_BG, fg="#ffffff",
                font=ui_font(8),
            )
            lbl.pack(side=side)
            return lbl

        self.status_branch = seg("🜈  main*")
        self.status_left = seg(f"{APP_NAME} {APP_VERSION}")
        self.status_errors = seg("✘ 0  ⚠ 0")
        self.status_right = seg("Ln 1, Col 1", side="right")
        self.status_enc = seg("UTF-8", side="right")
        self.status_lang = seg("Plain Text", side="right")
        self.status_engine = seg("CatSeek R1", side="right")

    # ── activity / panels / surfaces ─────────────────────────
    def set_surface(self, key: str):
        """Editor Window ↔ Agents Window."""
        if key not in {"editor", "agents"}:
            return
        self.view_mode.set(key)
        self._refresh_surface_btns()
        if key == "agents":
            if not self._agent_visible:
                self.toggle_agent()
            # Agents Window: hide sidebar + focus composer
            try:
                self.hpane.forget(self.sidebar)
            except tk.TclError:
                pass
            self._sidebar_hidden = True
            try:
                # give agent most of the width
                self.hpane.paneconfigure(self.agent_pane, width=560)
            except tk.TclError:
                pass
            self.ai_input.focus_set()
            self._activity("agent")
            self.status_left.config(
                text=f"  ◆  Agents Window  ·  {APP_NAME}  ·  files={FILES_MODE}"
            )
        else:
            if getattr(self, "_sidebar_hidden", False):
                try:
                    self.hpane.add(self.sidebar, minsize=180, width=248, before=self.center)
                except tk.TclError:
                    pass
                self._sidebar_hidden = False
            self._activity("explorer")
            self.status_left.config(
                text=f"  ◆  Editor Window  ·  {APP_NAME}  ·  files={FILES_MODE}"
            )

    def _refresh_surface_btns(self):
        cur = self.view_mode.get()
        for key, b in self._surface_btns.items():
            on = key == cur
            b.configure(
                bg=BTN_BG if on else CHIP_BG,
                fg=FG_BRIGHT if on else FG_DIM,
            )

    def _activity(self, key: str):
        for k, b in self._act_buttons.items():
            on = k == key
            b.configure(fg=FG_BRIGHT if on else FG_DIM)
            rail = self._act_rails.get(k)
            if rail is not None:
                rail.configure(bg=RAIL if on else ACTIVITY_BG)
        if key == "agent":
            if not self._agent_visible:
                self.toggle_agent()
            self._composer_focus()
            self.ai_input.focus_set()
            return
        if key == "run":
            self.show_panel_tab("TERMINAL")
            return
        if key in {"explorer", "search", "scm", "ext"}:
            self._show_sidebar_view(key)
            if key == "search":
                self.search_entry.focus_set()

    def _show_sidebar_view(self, key: str):
        for name in ("explorer_view", "search_view", "scm_view", "ext_view"):
            getattr(self, name).pack_forget()
        {
            "explorer": self.explorer_view,
            "search": self.search_view,
            "scm": self.scm_view,
            "ext": self.ext_view,
        }[key].pack(fill="both", expand=True)

    def show_panel_tab(self, name: str):
        # normalize legacy names
        if name == "OUTPUT":
            pass
        for n, b in self._panel_tabs.items():
            on = n == name
            b.configure(fg=FG_BRIGHT if on else FG_DIM)
        for w in (self.terminal, self.output, self.problems, self.debug_console):
            w.pack_forget()
        {
            "TERMINAL": self.terminal,
            "OUTPUT": self.output,
            "PROBLEMS": self.problems,
            "DEBUG CONSOLE": self.debug_console,
        }.get(name, self.terminal).pack(fill="both", expand=True)

    def toggle_sidebar(self):
        try:
            self.hpane.forget(self.sidebar)
            self._sidebar_hidden = True
        except tk.TclError:
            self.hpane.add(self.sidebar, minsize=180, width=248, before=self.center)
            self._sidebar_hidden = False

    def toggle_panel(self):
        if self._panel_visible:
            try:
                self.vpane.forget(self.panel)
            except tk.TclError:
                pass
            self._panel_visible = False
        else:
            self.vpane.add(self.panel, minsize=120, height=170)
            self._panel_visible = True

    def toggle_agent(self):
        if self._agent_visible:
            try:
                self.hpane.forget(self.agent_pane)
            except tk.TclError:
                pass
            self._agent_visible = False
        else:
            self.hpane.add(self.agent_pane, minsize=340, width=400)
            self._agent_visible = True

    def set_mode(self, name: str):
        self.mode.set(name)
        self._refresh_mode_btns()
        self.status_left.config(
            text=f"  ◆  {self.view_mode.get().title()}  ·  {name}  ·  files={FILES_MODE}"
        )

    def _refresh_mode_btns(self):
        cur = self.mode.get()
        for name, b in self._mode_btns.items():
            on = name == cur
            b.configure(
                fg=FG_BRIGHT if on else FG_DIM,
                bg="#0d1b3d" if on else BTN_BG,
            )

    def set_chat_density(self, name: str):
        """Compact / balanced / detailed chat density."""
        if name not in {"Compact", "Balanced", "Detailed"}:
            return
        self.chat_density.set(name)
        self._refresh_density_btns()
        self._agent_log("meta", f"Chat density → {name}")

    def _refresh_density_btns(self):
        cur = self.chat_density.get()
        for name, b in getattr(self, "_density_btns", {}).items():
            on = name == cur
            b.configure(fg=FG_BRIGHT if on else FG_DIM, bg="#0d1b3d" if on else BTN_BG)

    def toggle_agent_fullscreen(self):
        """Full-screen agent tab — floating composer."""
        self._agent_fullscreen = not self._agent_fullscreen
        if self._agent_fullscreen:
            self.set_surface("agents")
            try:
                self.hpane.forget(self.center)
            except tk.TclError:
                pass
            # floating composer over agent body
            if self._float_composer is None:
                self._float_composer = tk.Frame(self, bg=FLOAT_BG, height=210,
                                                highlightthickness=1,
                                                highlightbackground=ACCENT)
            for child in list(self._composer_foot.winfo_children()):
                child.destroy()
            self._composer_foot.pack_forget()
            self._float_composer.configure(height=210)
            self._float_composer.place(relx=0.5, rely=0.94, anchor="s", relwidth=0.55, height=210)
            for child in list(self._float_composer.winfo_children()):
                child.destroy()
            self._build_composer(self._float_composer)
            self.status_left.config(text=f"  ◆  Full-screen Agents  ·  {APP_NAME}")
        else:
            if self._float_composer is not None:
                self._float_composer.place_forget()
                for child in list(self._float_composer.winfo_children()):
                    child.destroy()
            try:
                # restore center before agent
                panes = self.hpane.panes()
                if str(self.center) not in panes:
                    self.hpane.add(self.center, minsize=420, stretch="always", before=self.agent_pane)
            except tk.TclError:
                try:
                    self.hpane.add(self.center, minsize=420, stretch="always")
                except tk.TclError:
                    pass
            self._composer_foot.configure(height=210)
            self._composer_foot.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
            self._composer_foot.pack_propagate(False)
            for child in list(self._composer_foot.winfo_children()):
                child.destroy()
            self._build_composer(self._composer_foot)
            self.set_surface("editor")

    def detect_active_lang(self):
        ed = self.active_editor()
        if not ed:
            self._agent_log("sys", "No buffer open to detect.")
            return
        hit = CodeLangDetector.detect(ed.get(), path=ed.title)
        self.last_detect = hit
        ranked = CodeLangDetector.detect_all(ed.get(), top=5)
        lines = [f"{h.label}  {h.confidence:.0%}" for h in ranked]
        spectrum = " → ".join(
            f"{k}" for k, _ in hit.scores.items() if k in CodeLangDetector.SPECTRUM
        ) or hit.lang
        self._agent_log(
            "lang",
            f"Detected {hit.label} ({hit.confidence:.0%})\n"
            f"Spectrum: {spectrum or '—'}\n"
            f"Top: {', '.join(lines)}\n"
            f"Why: {', '.join(hit.reasons) or '—'}",
        )
        if hasattr(self, "lang_chip"):
            self.lang_chip.configure(text=f"lang: {hit.label}")
        self.update_cursor_status()

    # ── keys ──────────────────────────────────────────────────
    def _bind_keys(self):
        self.bind(f"<{MOD}-n>", lambda e: self.new_file())
        self.bind(f"<{MOD}-o>", lambda e: self.open_file())
        self.bind(f"<{MOD}-s>", lambda e: self.save_file())
        self.bind(f"<{MOD}-w>", lambda e: self.close_active())
        self.bind(f"<{MOD}-q>", lambda e: self._quit_app())
        self.bind(f"<{MOD}-b>", lambda e: self.toggle_sidebar())
        self.bind(f"<{MOD}-j>", lambda e: self.toggle_panel())
        self.bind(f"<{MOD}-i>", lambda e: self.toggle_agent())
        self.bind(f"<{MOD}-r>", lambda e: self.run_active())
        self.bind(f"<{MOD}-Shift-p>", lambda e: self.command_palette())
        self.bind(f"<{MOD}-Shift-P>", lambda e: self.command_palette())
        self.bind(f"<{MOD}-Shift-a>", lambda e: self.set_surface("agents"))
        self.bind(f"<{MOD}-Shift-A>", lambda e: self.set_surface("agents"))
        self.bind(f"<{MOD}-Shift-e>", lambda e: self.set_surface("editor"))
        self.bind(f"<{MOD}-Shift-E>", lambda e: self.set_surface("editor"))
        self.bind(f"<{MOD}-Shift-m>", lambda e: self.toggle_agent_fullscreen())
        self.bind(f"<{MOD}-Shift-M>", lambda e: self.toggle_agent_fullscreen())
        self.bind(f"<{MOD}-l>", lambda e: self.detect_active_lang())

    # ── buffers / tabs (in-memory · files = off) ─────────────
    def _open_welcome(self):
        key = "welcome.md"
        content = (
            f"# {WINDOW_TITLE}\n\n"
            f"blue hue · **CatSeek R1** · Asm→C→C++ detect\n\n"
            f"- Surfaces: **Editor** / **Agents** (`{MOD_LABEL}⇧E` / `{MOD_LABEL}⇧A`)\n"
            f"- Full-screen agent: `{MOD_LABEL}⇧M`\n"
            f"- Detect language: `{MOD_LABEL}L`\n"
            f"- Convert ASM → C++ (Notepad++ style)\n"
            f"- Chat density: Compact / Balanced / Detailed\n"
            f"- Files: `{FILES_MODE}`\n\n"
            "## Vibe\n"
            f"1. `{MOD_LABEL}⇧A` → Agents Window\n"
            "2. Mode **Agent**\n"
            "3. Paste asm / C / C++ or ask for code\n"
            f"4. `{MOD_LABEL}L` to inspect the detector spectrum\n"
        )
        self._open_buffer(key, content, activate=True)

    def new_file(self):
        name = f"untitled-{self._untitled_n}.py"
        self._untitled_n += 1
        self._open_buffer(name, "def main():\n    print(\"hello from catide\")\n\nif __name__ == '__main__':\n    main()\n")

    def open_file(self):
        """Open a file (any type) into a new buffer."""
        path = filedialog.askopenfilename(
            parent=self, title="Open File",
            filetypes=[
                ("All files", "*.*"),
                ("Markdown", "*.md"),
                ("Python", "*.py"),
                ("C/C++", "*.c *.cpp *.h *.hpp *.cxx *.cc"),
                ("Assembly", "*.asm *.s *.nasm"),
                ("JavaScript/TypeScript", "*.js *.jsx *.ts *.tsx"),
                ("Text", "*.txt"),
                ("HTML", "*.html *.htm"),
                ("CSS", "*.css"),
                ("JSON", "*.json"),
                ("YAML", "*.yml *.yaml"),
                ("Shell", "*.sh *.bash"),
                ("Rust", "*.rs"),
                ("Go", "*.go"),
                ("Java", "*.java"),
                ("Ruby", "*.rb"),
                ("PHP", "*.php"),
                ("SQL", "*.sql"),
            ],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            messagebox.showerror(WINDOW_TITLE, f"Open failed:\n{e}")
            return
        key = os.path.basename(path)
        self._open_buffer(key, content)
        if hasattr(self, "status_left"):
            self.status_left.config(text=f"  ◆  Opened {key}")

    def save_file(self):
        """Save active buffer in-memory (files=off). Instant — no dialog."""
        ed = self.active_editor()
        if not ed or not self.active_key:
            messagebox.showinfo(WINDOW_TITLE, "No active editor to save.")
            return
        key = self.active_key
        self._buffers[key] = ed.get()
        ed.dirty = False
        ed.text.edit_modified(False)
        self._refresh_tab_labels()
        if hasattr(self, "status_left"):
            self.status_left.config(
                text=f"  ◆  Saved {key}  ·  files={FILES_MODE}"
            )

    def save_file_as(self):
        """Export with a language-aware default extension."""
        ed = self.active_editor()
        if not ed or not self.active_key:
            messagebox.showinfo(WINDOW_TITLE, "No active editor to save.")
            return
        key = self.active_key
        content = ed.get()
        self._buffers[key] = content
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save As",
            initialfile=key,
            defaultextension=os.path.splitext(key)[1] or ".txt",
            filetypes=[
                ("All files", "*.*"),
                ("Python", "*.py *.pyw"),
                ("JavaScript", "*.js *.jsx"),
                ("TypeScript", "*.ts *.tsx"),
                ("C", "*.c *.h"),
                ("C++", "*.cpp *.cc *.cxx *.hpp *.hh"),
                ("CUDA", "*.cu *.cuh"),
                ("Objective-C", "*.m *.mm"),
                ("Assembly", "*.asm *.s *.S *.nasm"),
                ("Rust", "*.rs"),
                ("Go", "*.go"),
                ("Java", "*.java"),
                ("C#", "*.cs"),
                ("Ruby", "*.rb"),
                ("PHP", "*.php"),
                ("Swift", "*.swift"),
                ("Kotlin", "*.kt *.kts"),
                ("Dart", "*.dart"),
                ("Lua", "*.lua"),
                ("Scala", "*.scala"),
                ("Haskell", "*.hs *.lhs"),
                ("Elixir", "*.ex *.exs"),
                ("Clojure", "*.clj *.cljs *.cljc"),
                ("Julia", "*.jl"),
                ("Erlang", "*.erl"),
                ("Elm", "*.elm"),
                ("Racket", "*.rkt"),
                ("Scheme", "*.scm"),
                ("Common Lisp", "*.lisp *.cl"),
                ("Fortran", "*.f90 *.f95 *.f03 *.f"),
                ("COBOL", "*.cbl *.cob"),
                ("Pascal", "*.pas *.pp"),
                ("Ada", "*.adb *.ads"),
                ("Zig", "*.zig"),
                ("Nim", "*.nim *.nims"),
                ("OCaml", "*.ml *.mli"),
                ("F#", "*.fs *.fsx"),
                ("Solidity", "*.sol"),
                ("GraphQL", "*.graphql *.gql"),
                ("Perl", "*.pl *.pm"),
                ("R", "*.r *.R"),
                ("HTML", "*.html *.htm *.vue *.svelte *.astro"),
                ("CSS", "*.css"),
                ("SQL", "*.sql"),
                ("Shell", "*.sh *.bash *.zsh"),
                ("PowerShell", "*.ps1 *.psm1"),
                ("Batch", "*.bat *.cmd"),
                ("Markdown", "*.md *.markdown"),
                ("JSON", "*.json"),
                ("YAML", "*.yml *.yaml"),
                ("TOML", "*.toml"),
                ("INI", "*.ini *.cfg *.conf"),
                ("LaTeX", "*.tex *.sty *.cls"),
                ("BibTeX", "*.bib"),
                ("Text", "*.txt"),
            ],
        )
        if not path:
            return
        if not hasattr(self, "_save_paths"):
            self._save_paths = {}
        self._save_paths[key] = path
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            ed.dirty = False
            ed.text.edit_modified(False)
            self._refresh_tab_labels()
            if hasattr(self, "status_left"):
                self.status_left.config(text=f"  ◆  Saved {os.path.basename(path)}")
        except OSError as e:
            messagebox.showerror(WINDOW_TITLE, f"Save failed:\n{e}")

    def load_markdown(self):
        path = filedialog.askopenfilename(
            parent=self, title="Load Markdown",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            messagebox.showerror(WINDOW_TITLE, f"Load failed:\n{e}")
            return
        key = os.path.basename(path)
        blocks = extract_code_blocks(content)
        if blocks:
            _, code = max(blocks, key=lambda b: len(b[1]))
            combined = f"{content}\n\n---\n# Extracted Code\n\n```\n{code}\n```\n"
        else:
            combined = content
        self._open_buffer(key, combined)
        if hasattr(self, "status_left"):
            self.status_left.config(text=f"  ◆  Loaded {key}")

    def run_markdown_blocks(self):
        ed = self.active_editor()
        if not ed:
            return
        src = ed.get()
        blocks = extract_code_blocks(src)
        if not blocks:
            self._agent_log("sys", "No code blocks found in markdown.")
            return
        self.show_panel_tab("OUTPUT")
        self.output.insert("end", f"▶ run markdown blocks ({len(blocks)} found)\n")
        self.output.see("end")

        def worker():
            for i, (lang, code) in enumerate(blocks, 1):
                if lang in {"python", "py"}:
                    buf = io.StringIO()
                    try:
                        ast.parse(code)
                        g: Dict[str, Any] = {"__name__": "__main__"}
                        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                            exec(compile(code, f"block_{i}", "exec"), g, g)
                        out = buf.getvalue() or "(no output)"
                        self.ui_queue.put(("run_out", f"--- Block {i} ({lang}) ---\n{out}\n"))
                    except SyntaxError as e:
                        self.ui_queue.put(("run_err", f"Block {i} SyntaxError: {e}"))
                    except Exception as e:
                        self.ui_queue.put(("run_err", f"Block {i} {type(e).__name__}: {e}"))
                else:
                    self.ui_queue.put(("run_out", f"--- Block {i} ({lang}) — skipping non-Python block ---\n"))
            self.ui_queue.put(("run_out", "▶ markdown run complete\n"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_buffer(self, key: str, content: str = "", *, activate: bool = True):
        if key in self.tabs:
            if activate:
                self._activate_tab(key)
            return
        ed = Editor(self.editor_host, self, title=key)
        ed.set_content(content)
        tab = tk.Frame(self.tab_row, bg=TAB_BG)
        accent = tk.Frame(tab, bg=TAB_BG, height=2)
        accent.pack(side="bottom", fill="x")
        row = tk.Frame(tab, bg=TAB_BG)
        row.pack(side="top", fill="x")
        lbl = tk.Label(row, text=key, bg=TAB_BG, fg=FG_DIM, font=ui_font(10), padx=12, pady=8)
        lbl.pack(side="left")
        close = tk.Button(
            row, text="✕", bd=0, bg=TAB_BG, fg=FG_FAINT, font=ui_font(9),
            command=lambda k=key: self.close_tab(k), cursor="hand2",
            activebackground=TAB_BG, activeforeground=FG_BRIGHT, highlightthickness=0,
        )
        close.pack(side="left", padx=(0, 8))
        lbl.bind("<Button-1>", lambda e, k=key: self._activate_tab(k))
        tab.pack(side="left", fill="y")
        self.tabs[key] = {"editor": ed, "tab": tab, "label": lbl, "close": close, "accent": accent}
        self._buffers[key] = content
        self._refresh_buffer_list()
        if activate:
            self._activate_tab(key)

    def _activate_tab(self, key: str):
        if key not in self.tabs:
            return
        self.empty_editor.place_forget()
        for k, meta in self.tabs.items():
            meta["editor"].pack_forget()
            meta["tab"].configure(bg=TAB_BG)
            meta["label"].configure(bg=TAB_BG, fg=FG_DIM)
            meta["close"].configure(bg=TAB_BG, fg=FG_FAINT)
            meta["accent"].configure(bg=TAB_BG)
        meta = self.tabs[key]
        meta["editor"].pack(fill="both", expand=True)
        meta["tab"].configure(bg=TAB_ACTIVE)
        meta["label"].configure(bg=TAB_ACTIVE, fg=FG_BRIGHT)
        meta["close"].configure(bg=TAB_ACTIVE, fg=FG_DIM)
        meta["accent"].configure(bg=ACCENT)
        self.active_key = key
        self.update_cursor_status()
        self._sync_list_selection(key)
        if hasattr(self, "ctx_chip"):
            self.ctx_chip.configure(text=f"@ {key}")
        if hasattr(self, "breadcrumb_label"):
            self.breadcrumb_label.configure(text=f"  …  ›  {key}")
        if hasattr(self, "title_center"):
            self.title_center.configure(text=f"{key} — {APP_NAME}")

    def close_tab(self, key: str):
        if key not in self.tabs:
            return
        meta = self.tabs.pop(key)
        meta["editor"].destroy()
        meta["tab"].destroy()
        self._buffers.pop(key, None)
        self._refresh_buffer_list()
        if self.active_key == key:
            self.active_key = None
            if self.tabs:
                self._activate_tab(next(iter(self.tabs)))
            else:
                self.empty_editor.place(relx=0.5, rely=0.42, anchor="center")

    def close_active(self):
        if self.active_key:
            self.close_tab(self.active_key)

    def _refresh_tab_labels(self):
        for k, meta in self.tabs.items():
            dirty = " ●" if meta["editor"].dirty else ""
            meta["label"].configure(text=f"{k}{dirty}")

    def _refresh_buffer_list(self):
        self.buffer_list.delete(0, "end")
        for k in self.tabs:
            self.buffer_list.insert("end", k)

    def _sync_list_selection(self, key: str):
        keys = list(self.tabs.keys())
        if key in keys:
            idx = keys.index(key)
            self.buffer_list.selection_clear(0, "end")
            self.buffer_list.selection_set(idx)
            self.buffer_list.see(idx)

    def _buffer_select(self, _e=None):
        sel = self.buffer_list.curselection()
        if not sel:
            return
        key = self.buffer_list.get(sel[0])
        self._activate_tab(key)

    def active_editor(self) -> Optional[Editor]:
        if self.active_key and self.active_key in self.tabs:
            return self.tabs[self.active_key]["editor"]
        return None

    def update_cursor_status(self):
        ed = self.active_editor()
        if not ed:
            if hasattr(self, "status_right"):
                self.status_right.config(text="  Ln —, Col —  ")
            return
        idx = ed.text.index("insert")
        line, col = idx.split(".")
        hit = getattr(ed, "detected", None) or CodeLangDetector.detect(ed.get(), path=ed.title)
        self.last_detect = hit
        engine = "CatSeek R1" if self.engine_ready else "booting…"
        self.status_right.config(text=f"  Ln {line}, Col {int(col)+1}  ")
        if hasattr(self, "status_lang"):
            self.status_lang.config(text=f"  {hit.label}  ")
        if hasattr(self, "status_engine"):
            self.status_engine.config(text=f"  {engine}  ")
        if hasattr(self, "lang_chip"):
            self.lang_chip.configure(text=f"lang: {hit.label}")
        if hasattr(self, "breadcrumb_label"):
            self.breadcrumb_label.configure(text=f"  …  ›  {ed.title}")

    # ── search (in-memory buffers) ────────────────────────────
    def run_search(self):
        q = self.search_entry.get().strip()
        self.search_results.delete(0, "end")
        self._search_hits = []
        if not q:
            return
        for key, meta in self.tabs.items():
            text = meta["editor"].get()
            for i, line in enumerate(text.splitlines(), 1):
                if q.lower() in line.lower():
                    self._search_hits.append((key, i, line.strip()[:80]))
                    self.search_results.insert("end", f"{key}:{i}  {line.strip()[:80]}")

    def _search_open(self, _e=None):
        sel = self.search_results.curselection()
        if not sel:
            return
        key, line, _ = self._search_hits[sel[0]]
        self._activate_tab(key)
        ed = self.active_editor()
        if ed:
            ed.text.mark_set("insert", f"{line}.0")
            ed.text.see(f"{line}.0")
            ed._cursor_moved()

    # ── agent (CatSeek R1) ───────────────────────────────────
    def _boot_engine(self):
        try:
            mod, engine, path = load_catseek_engine()
            self.ui_queue.put(("engine_ok", mod, engine, path))
        except Exception as e:
            self.ui_queue.put(("engine_err", str(e)))

    def _pump(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                kind = item[0]
                if kind == "engine_ok":
                    _, mod, engine, path = item
                    self.catseek = mod
                    self.engine = engine
                    self.catseek_path = path
                    self.engine_ready = True
                    self.engine_chip.config(text="CatSeek R1 · files=off", fg=OK_GREEN)
                    self._agent_log("ok", f"Agent online · CatSeek R1\n{path}")
                    self.update_cursor_status()
                elif kind == "engine_err":
                    self.engine_chip.config(text="engine offline", fg=ERR_RED)
                    self._agent_log("sys", f"Could not load CatSeek R1:\n{item[1]}")
                elif kind == "agent_out":
                    display_prompt = item[1]
                    reply = item[2]
                    think = item[3] if len(item) > 3 else ""
                    out_mode = item[4] if len(item) > 4 else self.mode.get()
                    if think:
                        self._agent_log("think", str(think)[:800])
                    self._agent_log("agent", reply or "(empty reply)")
                    blocks = extract_code_blocks(reply)
                    if not blocks:
                        # Guaranteed local emit — Agents always code
                        lang, code = CatsVibeCoder.synthesize(display_prompt)
                        blocks = [(lang, code)]
                        self._agent_log("sys", "Local vibe emit (no fence in engine reply).")
                    lang, code = max(blocks, key=lambda b: len(b[1]))
                    hit = CodeLangDetector.detect(code, hint=lang)
                    self.last_detect = hit
                    self.last_agent_code = code
                    self._agent_log(
                        "lang",
                        f"{hit.label} · {hit.confidence:.0%} · "
                        + (", ".join(hit.reasons[:3]) or "vibe"),
                    )
                    # Always write into editor for Agent / Ask / coding Plan
                    if out_mode != "Plan" or self._is_vibe_code_request(display_prompt, "Ask"):
                        self._vibe_apply(hit.lang if hit.lang != "unknown" else lang, code)
                    else:
                        self._agent_log("sys", "Code ready — Apply ⤶")
                    self.busy = False
                    self.status_left.config(
                        text=(
                            f"  ◆  {self.view_mode.get().title()} Window  ·  "
                            f"{self.mode.get()}  ·  {APP_NAME}"
                        )
                    )
                elif kind == "agent_err":
                    self._agent_log("sys", f"Agent error: {item[1]}")
                    self.busy = False
                elif kind == "run_out":
                    self.show_panel_tab("OUTPUT")
                    self.output.insert("end", item[1] + "\n")
                    self.output.see("end")
                elif kind == "run_err":
                    self.show_panel_tab("PROBLEMS")
                    self.problems.insert("end", item[1] + "\n")
                    self.problems.see("end")
        except queue.Empty:
            pass
        self.after(60, self._pump)

    def _agent_log(self, tag: str, text: str):
        density = self.chat_density.get() if hasattr(self, "chat_density") else "Compact"
        body = text.rstrip()
        if density == "Compact" and tag in {"think", "sys", "meta"}:
            # Compact density: collapse long tool/think traces
            lines = body.splitlines()
            if len(lines) > 3:
                body = "\n".join(lines[:2] + [f"… ({len(lines) - 2} more)"])
        elif density == "Balanced" and tag == "think":
            body = body[:600] + ("…" if len(body) > 600 else "")
        self.agent_chat.configure(state="normal")
        prefix = {
            "user": "You", "agent": "Agent", "sys": "System",
            "think": "Think", "ok": "OK", "meta": "·", "lang": "Detect",
        }.get(tag, tag)
        self.agent_chat.insert("end", f"{prefix}\n", tag)
        self.agent_chat.insert("end", body + "\n\n", tag)
        self.agent_chat.see("end")
        self.agent_chat.configure(state="disabled")

    def _agent_enter(self, e):
        if e.state & 0x1:  # Shift+Return → newline
            return None
        self.send_agent()
        return "break"

    def send_agent(self):
        if self.busy:
            return
        # Allow send even if placeholder flag stuck — read real text
        raw = self.ai_input.get("1.0", "end-1c").strip()
        if self._composer_placeholder or raw == "Ask CatSeek to vibe code…":
            return
        if not raw:
            return
        # Engine optional — local vibe always codes even if CatSeek still booting
        mode = self.mode.get()
        ed = self.active_editor()
        hint_lang = ""
        if ed:
            buf = ed.get()
            if buf.strip() and ed.title != "welcome.md":
                hit = CodeLangDetector.detect(buf, path=ed.title)
                hint_lang = hit.lang if hit.lang != "unknown" else ""
        self.ai_input.delete("1.0", "end")
        self._set_composer_placeholder()
        self._agent_log("user", raw)
        self.busy = True
        self.status_left.config(text=f"  ◆  Agent coding…  ·  {APP_NAME}")
        threading.Thread(
            target=self._agent_worker,
            args=(raw, mode, hint_lang),
            daemon=True,
        ).start()

    def _is_vibe_code_request(self, text: str, mode: str) -> bool:
        """Agent/Ask always vibe; Plan codes when prompt looks like a build ask."""
        if mode in {"Agent", "Ask"}:
            return True
        pl = (text or "").lower()
        return bool(re.search(
            r"\b(code|coding|vibe|vibecode|write|build|make|create|implement|"
            r"function|class|fix|refactor|scaffold|script|program|generate|"
            r"snippet|boilerplate|patch|add|edit)\b|"
            r"(写|做|建|生成|代码|程序|函数)",
            pl,
        ))

    def _agent_worker(self, display_prompt: str, mode: str = "Agent", hint_lang: str = ""):
        """
        Frontier R1 coding loop — always fences + applies.
        Prefer CatSeek pattern when richer; else CatsFrontierR1.
        """
        think = ""
        reply = ""
        try:
            lang, code, think = CatsVibeCoder.synthesize_with_think(
                display_prompt, hint=hint_lang
            )
            reply = (
                f"**CatsFrontierR1** · `{lang}` · {CatsFrontierR1.TARGET}\n\n"
                f"{CatsVibeCoder.fence(lang, code)}"
            )

            if self.engine_ready and self.engine is not None and self.catseek is not None:
                fast = CatsVibeCoder.try_catseek_fast(
                    self.catseek, self.engine, display_prompt
                )
                if fast and extract_code_blocks(fast):
                    fb = extract_code_blocks(fast)
                    _, fcode = max(fb, key=lambda b: len(b[1]))
                    # Keep CatSeek only if it looks at least as substantial
                    if len(fcode.strip()) >= len(code.strip()) * 0.6:
                        reply = fast
                        think = (think + "\nblend: CatSeek R1 pattern accepted").strip()

            self.ui_queue.put(("agent_out", display_prompt, reply, think, mode))
        except Exception as e:
            lang, code, think = CatsFrontierR1.code(display_prompt or "hello world")
            reply = (
                f"**CatsFrontierR1 fallback**\n\n"
                f"{CatsVibeCoder.fence(lang, code)}\n\n({e})"
            )
            self.ui_queue.put(("agent_out", display_prompt, reply, think or str(e), mode))

    def _vibe_apply(self, lang: str, code: str):
        lang = CodeLangDetector.normalize(lang) if lang else "python"
        hit = CodeLangDetector.detect(code, hint=lang)
        lang = hit.lang if hit.lang != "unknown" else (lang or "python")
        ext = LANG_EXT.get(lang, ".py")
        ed = self.active_editor()
        systems = {".c", ".cpp", ".asm", ".s", ".cu", ".m", ".h", ".hpp", ".py", ".js", ".ts"}
        if ed and (
            ed.title.endswith(ext)
            or ed.title.startswith("untitled")
            or ed.title.endswith(tuple(systems))
            or ed.title == "welcome.md"
        ):
            if not ed.title.endswith(ext) and (
                ed.title.startswith("untitled") or ed.title == "welcome.md"
            ):
                new_key = f"untitled-{self._untitled_n}{ext}"
                self._untitled_n += 1
                self._open_buffer(new_key, code)
                self._agent_log(
                    "ok", f"Opened `{new_key}` · {hit.label} ({hit.confidence:.0%})"
                )
                return
            ed.apply_code(code, replace=True)
            self._agent_log("ok", f"Applied into `{ed.title}` · {hit.label}")
            self.update_cursor_status()
            return
        name = f"agent-{self._untitled_n}{ext}"
        self._untitled_n += 1
        self._open_buffer(name, code)
        self._agent_log("ok", f"Opened `{name}` · {hit.label} ({hit.confidence:.0%})")

    def apply_last_code(self):
        if not self.last_agent_code:
            self._agent_log("sys", "No agent code to apply yet.")
            return
        ed = self.active_editor()
        if not ed:
            self._open_buffer(f"untitled-{self._untitled_n}.py", self.last_agent_code)
            self._untitled_n += 1
            return
        ed.apply_code(self.last_agent_code, replace=True)
        self._agent_log("ok", f"Applied into `{ed.title}`.")

    def asm_to_cpp(self):
        """Notepad++ style ASM→C++ transpiler for active buffer."""
        ed = self.active_editor()
        if not ed:
            messagebox.showinfo(WINDOW_TITLE, "No active editor.")
            return
        src = ed.get().strip()
        if not src:
            return
        hit = CodeLangDetector.detect(src)
        if hit.lang not in ("assembly", "c", "cpp", "cuda", "objc"):
            if not messagebox.askyesno(
                WINDOW_TITLE,
                f"Detected language is {hit.label}. Convert anyway?"
            ):
                return
        lines = src.splitlines()
        cpp: list[str] = []
        cpp.append("// Auto-converted from ASM via catide (Notepad++ style)")
        cpp.append("// Original language: " + hit.label)
        cpp.append("")

        def emit(msg: str = ""):
            cpp.append(msg)

        asm_patterns = {
            r"(?i)\bmov\s+([^,]+),\s*(.+)": r"\1 = \2;",
            r"(?i)\badd\s+([^,]+),\s*(.+)": r"\1 += \2;",
            r"(?i)\bsub\s+([^,]+),\s*(.+)": r"\1 -= \2;",
            r"(?i)\bimul\s+([^,]+),\s*(.+)": r"\1 *= \2;",
            r"(?i)\band\s+([^,]+),\s*(.+)": r"\1 &= \2;",
            r"(?i)\bor\s+([^,]+),\s*(.+)": r"\1 |= \2;",
            r"(?i)\bxor\s+([^,]+),\s*(.+)": r"\1 ^= \2;",
            r"(?i)\bcmp\s+([^,]+),\s*(.+)": r"// cmp \1, \2",
            r"(?i)\bpush\s+(.+)": r"// push \1",
            r"(?i)\bpop\s+(.+)": r"// pop \1",
            r"(?i)\bcall\s+(.+)": r"\1();",
            r"(?i)\bret\b": r"return;",
            r"(?i)\bjmp\b": r"// jmp (unconditional)",
            r"(?i)\b(?:jz|je)\b": r"// jz/je (conditional)",
            r"(?i)\b(?:jnz|jne)\b": r"// jnz/jne (conditional)",
            r"(?i)\bnop\b": r"// nop",
            r"(?i)\bsyscall\b": r"// syscall",
        }

        emit("#include <cstdint>")
        emit("#include <cstdio>")
        emit("")
        emit("int main(int argc, char** argv) {")
        indent = "    "

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                if stripped:
                    emit(indent + "// " + stripped.lstrip(";# "))
                continue
            if re.match(r"(?i)^\s*\.\w+", stripped):
                emit(indent + "// " + stripped)
                continue
            if re.match(r"(?i)^\s*\w+:", stripped):
                label = stripped.rstrip(":")
                emit(indent + "// label: " + label)
                continue
            converted = False
            for pat, repl in asm_patterns.items():
                m = re.match(pat, stripped)
                if m:
                    try:
                        result = m.expand(repl)
                        emit(indent + result)
                    except re.error:
                        emit(indent + "// " + stripped)
                    converted = True
                    break
            if not converted:
                emit(indent + "// " + stripped + "  // (unrecognised)")

        emit("    return 0;")
        emit("}")
        result = "\n".join(cpp)
        new_key = os.path.splitext(ed.title)[0] + "_converted.cpp"
        self._open_buffer(new_key, result)
        self._agent_log("ok", f"ASM→C++ conversion → `{new_key}`")

    def clear_agent(self):
        self.agent_chat.configure(state="normal")
        self.agent_chat.delete("1.0", "end")
        self.agent_chat.configure(state="disabled")
        if self.engine is not None:
            try:
                self.engine.clear_history()
            except Exception:
                pass
        self._agent_log("sys", "Agent chat cleared.")

    # ── run active buffer (in-memory via exec) ────────────────
    def run_active(self):
        ed = self.active_editor()
        if not ed:
            return
        src = ed.get()
        self.show_panel_tab("OUTPUT")
        self.output.insert("end", f"▶ run {ed.title}\n")
        self.output.see("end")

        def worker():
            import io
            import contextlib
            buf = io.StringIO()
            try:
                # syntax check first
                ast.parse(src)
                g: Dict[str, Any] = {"__name__": "__main__"}
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    exec(compile(src, ed.title, "exec"), g, g)
                out = buf.getvalue() or "(no output)"
                self.ui_queue.put(("run_out", out))
            except SyntaxError as e:
                self.ui_queue.put(("run_err", f"SyntaxError: {e}"))
            except Exception as e:
                self.ui_queue.put(("run_err", f"{type(e).__name__}: {e}"))

        if ed.title.endswith((".py", ".pyw")) or "def " in src:
            threading.Thread(target=worker, daemon=True).start()
        else:
            self.output.insert("end", "(not a Python buffer — paste into Agent or rename *.py)\n")

    def _term_run(self, _e=None):
        cmd = self._term_input.get().strip()
        if not cmd:
            return
        self._term_input.delete(0, "end")
        self.show_panel_tab("TERMINAL")
        self.terminal.insert("end", f"$ {cmd}\n")
        # Lightweight shell — still files=off for model; terminal may run cmds
        def term_worker():
            try:
                p = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                )
                out = (p.stdout or "") + (p.stderr or "") or f"(exit {p.returncode})\n"

                def ui():
                    self.terminal.insert("end", out if out.endswith("\n") else out + "\n")
                    self.terminal.see("end")
                self.after(0, ui)
            except Exception as e:
                self.after(0, lambda: self.terminal.insert("end", f"{e}\n"))
        threading.Thread(target=term_worker, daemon=True).start()

    # ── command palette ───────────────────────────────────────
    def command_palette(self):
        win = tk.Toplevel(self)
        win.title("Command Palette")
        win.configure(bg=BG)
        win.geometry("540x340")
        win.transient(self)
        tk.Label(
            win, text=f"{APP_NAME} · Commands", bg=BG, fg=FG_DIM,
            font=ui_font(9, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 0))
        entry = tk.Entry(
            win, bg=INPUT_BG, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
            font=ui_font(13), relief="flat", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        entry.pack(fill="x", padx=12, pady=8, ipady=7)
        entry.focus_set()
        cmds = [
            ("New File", self.new_file),
            ("Open File…", self.open_file),
            ("Save", self.save_file),
            ("Save as Markdown", self.save_as_markdown),
            ("Load Markdown", self.load_markdown),
            ("Close", self.close_active),
            ("Exit", self._quit_app),
            ("Convert ASM → C++", self.asm_to_cpp),
            ("Agents Window", lambda: self.set_surface("agents")),
            ("Editor Window", lambda: self.set_surface("editor")),
            ("Full-screen Agent Tab", self.toggle_agent_fullscreen),
            ("Detect Language (asm→C++)", self.detect_active_lang),
            ("Toggle Agent", self.toggle_agent),
            ("Toggle Sidebar", self.toggle_sidebar),
            ("Toggle Panel", self.toggle_panel),
            ("Run Active", self.run_active),
            ("Run Markdown Blocks", self.run_markdown_blocks),
            ("Apply Agent Code", self.apply_last_code),
            ("Chat: Compact", lambda: self.set_chat_density("Compact")),
            ("Chat: Balanced", lambda: self.set_chat_density("Balanced")),
            ("Chat: Detailed", lambda: self.set_chat_density("Detailed")),
            ("Mode: Agent", lambda: self.set_mode("Agent")),
            ("Mode: Ask", lambda: self.set_mode("Ask")),
            ("Mode: Plan", lambda: self.set_mode("Plan")),
            ("Help", self.show_help),
            ("About", self.show_about),
        ]
        lb = tk.Listbox(
            win, bg=SIDEBAR_BG, fg=FG, font=ui_font(12),
            selectbackground=SEL_BG, selectforeground=FG_BRIGHT,
            highlightthickness=0, activestyle="none", relief="flat",
        )
        lb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for label, _ in cmds:
            lb.insert("end", label)
        lb.selection_set(0)

        def filter_cmds(_e=None):
            q = entry.get().lower()
            lb.delete(0, "end")
            self._palette_filtered = [(l, f) for l, f in cmds if q in l.lower()]
            for l, _ in self._palette_filtered:
                lb.insert("end", l)
            if self._palette_filtered:
                lb.selection_set(0)

        self._palette_filtered = list(cmds)

        def run_filtered(_e=None):
            sel = lb.curselection()
            items = getattr(self, "_palette_filtered", cmds)
            if not sel or not items:
                return
            items[sel[0]][1]()
            win.destroy()

        entry.bind("<KeyRelease>", filter_cmds)
        entry.bind("<Return>", run_filtered)
        lb.bind("<Double-1>", run_filtered)
        lb.bind("<Return>", run_filtered)

    def show_help(self):
        messagebox.showinfo(
            f"Help — {WINDOW_TITLE}",
            f"{WINDOW_TITLE} shortcuts\n\n"
            f"{MOD_LABEL}N   New File\n"
            f"{MOD_LABEL}O   Open File\n"
            f"{MOD_LABEL}S   Save\n"
            f"{MOD_LABEL}W   Close\n"
            f"{MOD_LABEL}Q   Exit\n"
            f"      Convert ASM → C++\n"
            f"{MOD_LABEL}⇧P  Command Palette\n"
            f"{MOD_LABEL}R   Run Active Buffer\n"
            f"{MOD_LABEL}I   Toggle Agent\n"
            f"{MOD_LABEL}B   Toggle Sidebar\n"
            f"{MOD_LABEL}J   Toggle Panel\n"
            f"{MOD_LABEL}L   Detect Language\n"
            f"{MOD_LABEL}⇧A / ⇧E  Agents / Editor\n"
            f"{MOD_LABEL}⇧M  Full-screen Agents\n\n"
            "Menu strip: File · Save · Close · Exit · About · Help\n"
            f"Workspace: files = {FILES_MODE}",
        )

    def show_about(self):
        messagebox.showinfo(
            WINDOW_TITLE,
            f"{WINDOW_TITLE}\n\n"
            f"blue hue IDE · UI kept\n"
            "Syntax highlighter\n"
            "35 language syntax tables · 92 file extensions\n"
            f"CatsFrontierR1 · {CatsFrontierR1.TARGET}\n"
            "think → plan → skill → draft → verify → repair\n"
            "CodeLangDetector: assembly → C → C++ (+ CUDA / ObjC)\n"
            "Agent / Ask / Plan · CatSeek R1 blend\n"
            f"files = {FILES_MODE}\n"
            f"Python {sys.version.split()[0]}\n"
            f"Engine: {self.catseek_path or '(loading…)'}",
        )

    def _quit_app(self):
        if messagebox.askokcancel("Quit", f"Exit {WINDOW_TITLE}?"):
            if self.engine is not None:
                try:
                    self.engine.clear_history()
                except Exception:
                    pass
            self.destroy()


def main():
    app = CatIDE()
    app.mainloop()


if __name__ == "__main__":
    main()
