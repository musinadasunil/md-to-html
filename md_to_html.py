#!/usr/bin/env python3
"""
Render a markdown file (with ```mermaid fenced diagrams) into a single,
self-contained HTML file that renders offline -- no CDN, no network access
needed to view it.

Usage:
    poetry run md-to-html render path/to/architecture.md
    poetry run md-to-html render path/to/architecture.md -o out.html --title "Payments Service"

Requires vendor/mermaid.min.js to sit next to this script (already vendored).
Dependencies are managed by Poetry (see pyproject.toml) -- run `poetry install` first.
"""
from __future__ import annotations

import argparse
import functools
import html
import json
import os
import re
import signal
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import markdown

SCRIPT_DIR = Path(__file__).resolve().parent
MERMAID_JS_PATH = SCRIPT_DIR / "vendor" / "mermaid.min.js"

DEFAULT_PORT = 4711
STATE_PATH = Path.home() / ".cache" / "md-to-html" / "server.json"

MERMAID_BLOCK_RE = re.compile(
    r'<pre><code class="(?:language-)?mermaid">(.*?)</code></pre>', re.DOTALL
)
CHECKBOX_RE = re.compile(r"<li>\[([ xX])\]\s*")

CSS = """
:root {
  --bg: #f3f4f0;
  --bg-raised: #ffffff;
  --ink: #1a1e1b;
  --ink-soft: #4c534d;
  --ink-faint: #7c847d;
  --border: #d7dbd2;
  --accent: #256b56;
  --accent-soft: #e2eee7;
  --code-bg: #eaeae3;
  --shadow: 0 1px 2px rgba(20, 30, 24, 0.06);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #10141a;
    --bg-raised: #171d24;
    --ink: #e8ece7;
    --ink-soft: #a3ada4;
    --ink-faint: #6d766f;
    --border: #2a323b;
    --accent: #5bc79c;
    --accent-soft: rgba(91, 199, 156, 0.13);
    --code-bg: #1c232b;
    --shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  }
}
:root[data-theme="dark"] {
  --bg: #10141a;
  --bg-raised: #171d24;
  --ink: #e8ece7;
  --ink-soft: #a3ada4;
  --ink-faint: #6d766f;
  --border: #2a323b;
  --accent: #5bc79c;
  --accent-soft: rgba(91, 199, 156, 0.13);
  --code-bg: #1c232b;
  --shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}
:root[data-theme="light"] {
  --bg: #f3f4f0;
  --bg-raised: #ffffff;
  --ink: #1a1e1b;
  --ink-soft: #4c534d;
  --ink-faint: #7c847d;
  --border: #d7dbd2;
  --accent: #256b56;
  --accent-soft: #e2eee7;
  --code-bg: #eaeae3;
  --shadow: 0 1px 2px rgba(20, 30, 24, 0.06);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  line-height: 1.65;
}
.wrap { max-width: 880px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }
h1, h2, h3, h4 { text-wrap: balance; line-height: 1.2; margin: 1.8rem 0 0.6rem; }
h1 { font-size: 2rem; margin-top: 0; letter-spacing: -0.01em; }
h2 { font-size: 1.4rem; padding-top: 0.4rem; border-top: 1px solid var(--border); margin-top: 2.4rem; }
h3 { font-size: 1.12rem; color: var(--ink); }

.doc-section {
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.7rem 1.9rem 1.9rem;
  margin: 1.6rem 0;
  box-shadow: var(--shadow);
}
.doc-section h2 {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
  color: var(--accent);
}
.doc-section > h2:first-child { margin-top: 0; }
h4 { font-size: 1rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.82rem; }
p, li { max-width: 72ch; }
p { margin: 0.7rem 0; }
a { color: var(--accent); }
strong { color: var(--ink); }
ul, ol { padding-left: 1.3rem; }
li { margin: 0.3rem 0; }
hr { border: none; border-top: 1px solid var(--border); margin: 2.2rem 0; }

code {
  font-family: ui-monospace, "SF Mono", "Roboto Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  background: var(--code-bg);
  padding: 0.12rem 0.38rem;
  border-radius: 3px;
  font-size: 0.88em;
}
pre:not(.mermaid) {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.9rem 1rem;
  overflow-x: auto;
}
pre:not(.mermaid) code { background: none; padding: 0; }

table {
  border-collapse: collapse;
  width: 100%;
  margin: 1rem 0;
  font-size: 0.92rem;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
th, td { text-align: left; padding: 0.55rem 0.8rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th { background: var(--code-bg); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-faint); }
tr:last-child td { border-bottom: none; }
.table-wrap { overflow-x: auto; }

blockquote {
  margin: 1rem 0;
  padding: 0.6rem 1rem;
  border-left: 3px solid var(--accent);
  background: var(--accent-soft);
  color: var(--ink-soft);
}

li.task { list-style: none; margin-left: -1.3rem; }
li.task input[type="checkbox"] { margin-right: 0.5rem; }
li.task-done { color: var(--ink-faint); }

.theme-toggle {
  position: fixed;
  top: 1rem;
  right: 1rem;
  font-family: ui-monospace, "SF Mono", "Roboto Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  background: var(--bg-raised);
  color: var(--ink-soft);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.4rem 0.9rem;
  cursor: pointer;
  box-shadow: var(--shadow);
}
.theme-toggle:hover { color: var(--accent); border-color: var(--accent); }
.theme-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* mermaid diagram cards */
pre.mermaid, div.mermaid {
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem 1.1rem;
  box-shadow: var(--shadow);
  overflow-x: auto;
  margin: 1.2rem 0;
}
pre.mermaid svg, div.mermaid svg { max-width: 100%; }

/* table of contents */
nav.toc {
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.1rem 1.4rem 1.3rem;
  margin: 1.6rem 0 2.4rem;
  box-shadow: var(--shadow);
  font-size: 0.92rem;
}
nav.toc .toc-title {
  font-size: 1.05rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--accent);
  margin-bottom: 0.6rem;
}
nav.toc ul { list-style: none; padding-left: 0; margin: 0; }
nav.toc ul ul { padding-left: 1.2rem; margin-top: 0.2rem; }
nav.toc li { margin: 0.35rem 0; }
nav.toc a { text-decoration: none; }
nav.toc a:hover { color: var(--accent); text-decoration: underline; }
/* depth 1 li = the page's h1 title */
nav.toc > ul > li > a { color: var(--ink); font-weight: 700; }
/* depth 2 li = h2 section headings -- match .doc-section h2's accent color */
nav.toc > ul > li > ul > li > a { color: var(--accent); font-weight: 600; font-size: 0.98rem; }
/* depth 3+ li = h3 subheadings and deeper -- match h3's ink color */
nav.toc > ul > li > ul > li > ul li > a { color: var(--ink); font-weight: 400; font-size: 0.88rem; }

header.doc-meta {
  font-family: ui-monospace, "SF Mono", "Roboto Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  font-size: 0.75rem;
  color: var(--ink-faint);
  margin-bottom: 0.3rem;
}
"""

THEME_JS = """
(function () {
  var root = document.documentElement;
  var toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "theme-toggle";
  toggle.setAttribute("aria-label", "Toggle light and dark theme");
  document.body.appendChild(toggle);

  function systemPrefersDark() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function currentTheme() {
    var explicit = root.getAttribute("data-theme");
    if (explicit === "light" || explicit === "dark") return explicit;
    return systemPrefersDark() ? "dark" : "light";
  }

  function renderDiagrams(theme) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: theme === "dark" ? "dark" : "default",
    });
    var nodes = Array.prototype.slice.call(document.querySelectorAll("pre.mermaid"));
    nodes.forEach(function (el) {
      el.removeAttribute("data-processed");
      el.innerHTML = el.getAttribute("data-source");
    });
    if (nodes.length) {
      mermaid.run({ nodes: nodes });
    }
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    toggle.textContent = theme === "dark" ? "Light theme" : "Dark theme";
    renderDiagrams(theme);
  }

  document.querySelectorAll("pre.mermaid").forEach(function (el) {
    el.setAttribute("data-source", el.textContent);
  });

  toggle.addEventListener("click", function () {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  });

  applyTheme(currentTheme());
})();
"""

HTML_TEMPLATE = """<!doctype html>
<html lang="en"{theme_attr}>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<header class="doc-meta">{source_name}</header>
{toc_html}
{body_html}
</div>
<script>{mermaid_js}</script>
<script>{theme_js}</script>
</body>
</html>
"""


def convert_markdown(md_text: str) -> tuple[str, str]:
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists", "toc"],
        extension_configs={"toc": {"anchorlink": False, "permalink": False}},
    )
    body_html = md.convert(md_text)
    toc_html = getattr(md, "toc", "")
    return body_html, toc_html


def fix_mermaid_blocks(body_html: str) -> str:
    def repl(m: re.Match[str]) -> str:
        code = html.unescape(m.group(1))
        return f'<pre class="mermaid">\n{code}\n</pre>'

    return MERMAID_BLOCK_RE.sub(repl, body_html)


def style_checklists(body_html: str) -> str:
    def repl(m: re.Match[str]) -> str:
        checked = m.group(1).lower() == "x"
        cls = "task task-done" if checked else "task"
        checked_attr = " checked" if checked else ""
        return f'<li class="{cls}"><input type="checkbox" disabled{checked_attr}> '

    return CHECKBOX_RE.sub(repl, body_html)


def wrap_tables(body_html: str) -> str:
    return re.sub(
        r"(<table>.*?</table>)",
        r'<div class="table-wrap">\1</div>',
        body_html,
        flags=re.DOTALL,
    )


TRAILING_HR_RE = re.compile(r"\s*<hr\s*/?>\s*\Z")


def wrap_sections(body_html: str) -> str:
    """Wrap each top-level <h2> and everything up to the next <h2> in a card.

    Content before the first <h2> (the h1 title / lede paragraphs) is left
    alone so it reads as a page header rather than a card.
    """
    chunks = re.split(r"(?=<h2[ >])", body_html)
    if len(chunks) <= 1:
        return body_html

    header, sections = chunks[0], chunks[1:]
    wrapped = [
        f'<section class="doc-section">{TRAILING_HR_RE.sub("", s)}</section>'
        for s in sections
    ]
    return TRAILING_HR_RE.sub("", header) + "".join(wrapped)


def build_toc(toc_html: str) -> str:
    if not toc_html or "<li>" not in toc_html:
        return ""
    return f'<nav class="toc"><div class="toc-title">Contents</div>{toc_html}</nav>'


def render(md_path: Path, title: str | None, theme: str) -> str:
    md_text = md_path.read_text(encoding="utf-8")
    body_html, toc_html = convert_markdown(md_text)
    body_html = fix_mermaid_blocks(body_html)
    body_html = style_checklists(body_html)
    body_html = wrap_tables(body_html)
    body_html = wrap_sections(body_html)

    if not MERMAID_JS_PATH.exists():
        sys.exit(
            f"error: {MERMAID_JS_PATH} not found -- vendor mermaid.min.js next to this script first"
        )
    mermaid_js = MERMAID_JS_PATH.read_text(encoding="utf-8")
    theme_attr = f' data-theme="{theme}"' if theme in ("light", "dark") else ""

    return HTML_TEMPLATE.format(
        title=html.escape(title or md_path.stem),
        css=CSS,
        source_name=html.escape(md_path.name),
        toc_html=build_toc(toc_html),
        body_html=body_html,
        mermaid_js=mermaid_js,
        theme_js=THEME_JS,
        theme_attr=theme_attr,
    )


def read_state() -> dict | None:
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running_state() -> dict | None:
    """Return the state file's contents if the server it describes is alive."""
    state = read_state()
    if state and pid_alive(state["pid"]):
        return state
    return None


def url_for(output: Path) -> str | None:
    """URL for output on the persistent server, if it's running and covers output."""
    state = running_state()
    if not state:
        return None
    root = Path(state["root"])
    try:
        rel = output.resolve().relative_to(root)
    except ValueError:
        return None
    return f"http://127.0.0.1:{state['port']}/{rel.as_posix()}"


def server_start(port: int, root: Path) -> None:
    """Start the one persistent, shared server, detached from this terminal.

    Idempotent: if a server described by the state file is already alive,
    this just reports it instead of starting a second one. The server binds
    once here (in this process) and the child inherits the bound socket, so
    there's no bind-after-fork race.
    """
    state = running_state()
    if state:
        print(f"already running: pid {state['pid']}, http://127.0.0.1:{state['port']}/ (root {state['root']})")
        return

    root = root.resolve()
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as e:
        sys.exit(f"error: can't bind 127.0.0.1:{port} ({e}) -- something else may be using that port")

    pid = os.fork()
    if pid > 0:
        # Parent: the child inherited the bound socket, so it's safe to
        # close our handle and exit -- the child keeps listening.
        httpd.server_close()
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({"pid": pid, "port": port, "root": str(root)}))
        print(f"server started: pid {pid}, http://127.0.0.1:{port}/ (root {root})")
        print("stop with: md-to-html server stop")
        return

    # Child: detach from the controlling terminal so closing it (or the
    # parent shell) doesn't send us SIGHUP, then run forever.
    os.setsid()
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull_fd, 0)
    os.dup2(devnull_fd, 1)
    os.dup2(devnull_fd, 2)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        os._exit(0)


def server_stop() -> None:
    state = running_state()
    if not state:
        print("no server running")
        STATE_PATH.unlink(missing_ok=True)
        return
    os.kill(state["pid"], signal.SIGTERM)
    STATE_PATH.unlink(missing_ok=True)
    print(f"stopped pid {state['pid']}")


def server_status() -> None:
    state = running_state()
    if not state:
        print("not running")
        return
    print(f"running: pid {state['pid']}, http://127.0.0.1:{state['port']}/ (root {state['root']})")


def cmd_render(args: argparse.Namespace) -> None:
    if not args.input.exists():
        sys.exit(f"error: {args.input} not found")

    output = args.output or args.input.with_suffix(".html")
    output.write_text(render(args.input, args.title, args.theme), encoding="utf-8")
    print(f"wrote {output}")

    url = url_for(output)
    if url:
        print(f"open at {url}")
        if args.open:
            webbrowser.open(url)
    elif args.open:
        sys.exit("error: no md-to-html server running -- start one with `md-to-html server start`")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    render_p = sub.add_parser("render", help="render a markdown file to a self-contained HTML file")
    render_p.add_argument("input", type=Path, help="markdown file to render")
    render_p.add_argument("-o", "--output", type=Path, help="output .html path (default: alongside input)")
    render_p.add_argument("--title", help="page title (default: input filename)")
    render_p.add_argument(
        "--theme",
        choices=["auto", "light", "dark"],
        default="auto",
        help="starting theme (default: auto, follows OS preference). A toggle button in the "
        "page always lets you override this live.",
    )
    render_p.add_argument(
        "--open",
        action="store_true",
        help="open the result in the browser via the running `md-to-html server` (error if none is running)",
    )
    render_p.set_defaults(func=cmd_render)

    server_p = sub.add_parser("server", help="manage the one persistent local server shared by all renders")
    server_sub = server_p.add_subparsers(dest="server_command", required=True)

    start_p = server_sub.add_parser("start", help="start the shared server in the background (idempotent)")
    start_p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to listen on (default: {DEFAULT_PORT})")
    start_p.add_argument(
        "--root",
        type=Path,
        default=Path.home(),
        help="directory to serve (default: your home directory, so any rendered .html "
        "anywhere under it is reachable)",
    )
    start_p.set_defaults(func=lambda a: server_start(a.port, a.root))

    stop_p = server_sub.add_parser("stop", help="stop the shared server")
    stop_p.set_defaults(func=lambda a: server_stop())

    status_p = server_sub.add_parser("status", help="show whether the shared server is running")
    status_p.set_defaults(func=lambda a: server_status())

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
