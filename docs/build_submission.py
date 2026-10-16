"""Build docs/Submission.pdf from docs/SUBMISSION.md plus the sample outputs it includes.

    pip install markdown
    python docs/build_submission.py

Needs Google Chrome installed (used headless to print the PDF).
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
REPO = "https://github.com/EducatedBernie/agentic-ai-coworkers"
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

CSS = """
@page { size: Letter; margin: 0.7in 0.75in; }
body { font: 10.5pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1a1a1a; }
h1 { font-size: 22pt; margin: 0 0 4pt; }
h2 { font-size: 15pt; margin-top: 18pt; border-bottom: 1px solid #ccc; padding-bottom: 3pt; }
h3 { font-size: 12pt; margin-top: 12pt; }
h4, h5, h6 { font-size: 10.5pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; }
th, td { border: 1px solid #ccc; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #f2f2f2; }
code { font: 9pt Menlo, monospace; background: #f4f4f4; padding: 0 2pt; }
pre { background: #f4f4f4; padding: 8pt; overflow-wrap: anywhere; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
a { color: #0b57d0; overflow-wrap: anywhere; }
hr { border: 0; border-top: 1px solid #ddd; margin: 14pt 0; }
.diagram { text-align: center; }
.diagram svg { width: 100% !important; height: auto; }
.agent2-architecture svg { width: 62% !important; }
h2, h3 { break-after: avoid; }
.appendix { break-before: page; }
tr, img, svg { break-inside: avoid; }
"""


def demote(md: str, levels: int) -> str:
    return re.sub(r"(?m)^(#{1,6}) ", lambda m: "#" * min(6, len(m.group(1)) + levels) + " ", md)


def blank_line_before_lists(md: str) -> str:
    # Python-Markdown needs a blank line before a list; GitHub and model output often omit it.
    return re.sub(r"(?m)^((?![ \t]*(?:[-*+]|\d+\.)[ \t]).+)\n([ \t]*(?:[-*+]|\d+\.)[ \t])", r"\1\n\n\2", md)


def build() -> Path:
    src = (DOCS / "SUBMISSION.md").read_text()
    src = re.sub(r"<!-- include: (.+?) -->",
                 lambda m: demote((DOCS / m.group(1)).read_text(), 2), src)
    # Mermaid blocks render on GitHub; in the PDF they're swapped for pre-rendered SVGs, in order.
    svgs = iter(["agent1-architecture.svg", "agent2-architecture.svg"])
    src = re.sub(r"```mermaid\n.*?\n```", lambda m: f"DIAGRAM:{next(svgs)}", src, flags=re.S)
    src = src.replace("](../", f"]({REPO}/blob/main/")  # relative repo links don't work inside a PDF
    src = blank_line_before_lists(src)

    body = markdown.markdown(src, extensions=["tables", "fenced_code", "sane_lists"])
    body = re.sub(r"<p>DIAGRAM:(.+?)</p>",
                  lambda m: f'<div class="diagram {Path(m.group(1)).stem}">{(DOCS / m.group(1)).read_text()}</div>', body)
    body = re.sub(r"<h2>(Appendix )", r'<h2 class="appendix">\1', body)

    html = DOCS / "submission.html"
    html.write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>Agentic AI Coworkers</title>'
                    f"<style>{CSS}</style></head><body>{body}</body></html>")

    chrome = next((c for c in CHROME_CANDIDATES if c and Path(c).exists()), None)
    if not chrome:
        sys.exit(f"Chrome not found; open {html} in a browser and print to PDF instead.")
    pdf = DOCS / "Submission.pdf"
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", html.as_uri()], check=True, capture_output=True, timeout=120)
    html.unlink()
    return pdf


if __name__ == "__main__":
    print(f"Wrote {build()}")
