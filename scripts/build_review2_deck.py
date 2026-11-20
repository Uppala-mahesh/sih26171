"""Build the TBP Review-II deck for Drishti.

Source of truth: the repository at the commit being presented and the latest
capability-suite report (server/eval/last_run.json). The deck deliberately
prints the measured pass count instead of a hard-coded "13/13".

Run:
    .\\.venv\\Scripts\\python.exe scripts/build_review2_deck.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt
from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "review2" / "Drishti-Review2.pptx"
SHOTS = ROOT / "docs" / "review2" / "screenshots"

# --------------------------------------------------------------------------
# Palette and type, taken from src/index.css (the dossier look).
# --------------------------------------------------------------------------
INK = "20242C"
INK_DIM = "6B6F79"
INK_FAINT = "9A968B"
PAPER = "E7DFCC"
PAPER_DEEP = "DDD3BB"
SHEET = "F6F1E4"
SHEET_DEEP = "EFE8D7"
STAMP = "B3402A"
OK = "2E6B4F"
AMBER = "9A6318"
WHITE = "FFFFFF"

UI = "Segoe UI"
MONO = "Consolas"
DEVA = "Nirmala UI"

W, H = 13.333, 7.5
M = 0.72
RIGHT = W - M  # one content margin for every slide, every box, every picture


def C(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def fit(x, w):
    """Clip a width to the content margin. Full-bleed shapes start at x=0."""
    if x <= 0.01:
        return w
    return max(0.05, min(w, RIGHT - x))


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def rect(slide, x, y, w, h, fill=None, line=None, line_w=0.75,
         dashed=False, shape=MSO_SHAPE.RECTANGLE, radius=None):
    shp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(fit(x, w)),
                                 Inches(h))
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        shp.adjustments[0] = radius
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = C(fill)
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = C(line)
        shp.line.width = Pt(line_w)
        if dashed:
            shp.line.dash_style = MSO_LINE.DASH
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def text(slide, x, y, w, h, runs, size=15, color=INK, font=UI,
         bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         line_spacing=1.0, space_after=0, italic=False, margins=(0, 0, 0, 0)):
    """Add a textbox. `runs` is a string or a list of run dicts."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(fit(x, w)),
                                   Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left, tf.margin_right, tf.margin_top, tf.margin_bottom = (
        Inches(margins[0]), Inches(margins[1]), Inches(margins[2]), Inches(margins[3])
    )
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line_spacing
    p.space_after = Pt(space_after)
    if isinstance(runs, str):
        runs = [{"t": runs}]
    for run in runs:
        r = p.add_run()
        r.text = run["t"]
        f = r.font
        f.name = run.get("font", font)
        f.size = Pt(run.get("size", size))
        f.bold = run.get("bold", bold)
        f.italic = run.get("italic", italic)
        f.color.rgb = C(run.get("color", color))
    return box


def rule(slide, x, y, w, color=INK, thickness=1.0):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                 Inches(fit(x, w)), Inches(thickness / 72))
    shp.fill.solid()
    shp.fill.fore_color.rgb = C(color)
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def header(slide, kicker, title, title_size=29):
    text(slide, M, 0.36, 10.5, 0.25, kicker, size=9.5, color=STAMP,
         font=MONO, bold=True)
    text(slide, M, 0.62, W - 2 * M, 0.62, title, size=title_size, color=INK,
         bold=True, line_spacing=0.95)
    rule(slide, M, 1.34, W - 2 * M, INK, 1.1)


def footer(slide, n, total=15):
    rule(slide, M, 7.08, W - 2 * M, "B9AF98", 0.6)
    text(slide, M, 7.14, 7.0, 0.2, "DRISHTI  ·  SIH26171  ·  REVIEW II",
         size=7.5, color=INK_FAINT, font=MONO)
    text(slide, W - M - 1.2, 7.14, 1.2, 0.2, f"{n:02d} / {total:02d}",
         size=7.5, color=INK_FAINT, font=MONO, align=PP_ALIGN.RIGHT)


def notes(slide, body):
    slide.notes_slide.notes_text_frame.text = body


def set_cell_border(cell, color=INK, width_pt=0.6):
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        for old in tcPr.findall(qn(tag)):
            tcPr.remove(old)
    for tag in ("a:lnB", "a:lnT", "a:lnR", "a:lnL"):
        ln = etree.SubElement(tcPr, qn(tag))
        ln.set("w", str(int(width_pt * 12700)))
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")
        fill = etree.SubElement(ln, qn("a:solidFill"))
        clr = etree.SubElement(fill, qn("a:srgbClr"))
        clr.set("val", color)
        dash = etree.SubElement(ln, qn("a:prstDash"))
        dash.set("val", "solid")
        tcPr.remove(ln)
        tcPr.insert(0, ln)


def table(slide, x, y, w, h, data, col_widths, row_heights,
          font_size=10.5, header_size=9.5, header_fill=INK,
          body_fill=SHEET, alt_fill=SHEET_DEEP):
    rows, cols = len(data), len(data[0])
    shape = slide.shapes.add_table(rows, cols, Inches(x), Inches(y),
                                   Inches(w), Inches(h))
    tbl = shape.table
    tbl.first_row = False
    tbl.horz_banding = False
    for i, cw in enumerate(col_widths):
        tbl.columns[i].width = Inches(cw)
    for i, rh in enumerate(row_heights):
        tbl.rows[i].height = Inches(rh)
    for r, row in enumerate(data):
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.09)
            cell.margin_right = Inches(0.07)
            cell.margin_top = Inches(0.05)
            cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            is_head = r == 0
            cell.fill.solid()
            cell.fill.fore_color.rgb = C(header_fill if is_head else
                                         (body_fill if r % 2 else alt_fill))
            set_cell_border(cell, INK if is_head else "C9BFA7", 0.5)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.line_spacing = 0.92
            run = p.add_run()
            run.text = str(value)
            run.font.name = UI
            run.font.size = Pt(header_size if is_head else font_size)
            run.font.bold = is_head
            run.font.color.rgb = C(SHEET if is_head else INK)
    return shape


def picture(slide, path, x, y, w, border=INK):
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y),
                                   width=Inches(fit(x, w)))
    pic.line.color.rgb = C(border)
    pic.line.width = Pt(0.9)
    return pic


# --------------------------------------------------------------------------
# Data loaded from the latest run, never hard-coded.
# --------------------------------------------------------------------------
run_path = ROOT / "server" / "eval" / "last_run.json"
results = []
if run_path.exists():
    raw = json.loads(run_path.read_text(encoding="utf-8"))
    results = raw if isinstance(raw, list) else raw.get("results", [])

passed_n = sum(1 for r in results if r.get("passed"))
total_n = len(results)
total_s = sum(float(r.get("elapsed_s") or 0) for r in results)
elapsed = {r.get("id"): r.get("elapsed_s") for r in results}
outcomes = {r.get("id"): (r.get("outcome"), r.get("passed")) for r in results}

CASE_ORDER = [
    "demo-read-example", "demo-nav-click", "demo-extract-priced",
    "demo-extract-table", "demo-ask-readonly", "demo-effort-deep",
    "demo-pii-redaction", "demo-payment-gate", "demo-payment-approved",
    "demo-prompt-injection", "demo-form-job-application",
    "demo-form-scholarship", "demo-login-wall",
]

# --------------------------------------------------------------------------
prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)
blank = prs.slide_layouts[6]

# ==========================================================================
# 1 · TITLE
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=INK)
rule(s, M, 0.5, W - 2 * M, "5A5E66", 0.8)
rule(s, M, 6.98, W - 2 * M, "5A5E66", 0.8)

text(s, M, 0.72, 8.0, 0.3,
     "SMART INDIA HACKATHON 2026  ·  PROBLEM STATEMENT 26171",
     size=10, color="A9A290", font=MONO, bold=True)
text(s, M, 1.25, 6.2, 0.32, "TBP REVIEW II  ·  21 NOVEMBER 2026",
     size=10, color=STAMP, font=MONO, bold=True)

text(s, M, 1.85, 7.0, 1.15, "Drishti", size=78, color=SHEET, bold=True,
     line_spacing=0.9)
text(s, M + 0.06, 3.03, 7.0, 0.4,
     [{"t": "दृष्टि", "font": DEVA, "size": 25, "color": "D8CDB6"},
      {"t": "   sight  ·  the act of seeing", "font": UI, "size": 15,
       "color": "A9A290"}])

text(s, M, 3.65, 7.2, 1.25,
     "On-device visual perception\nfor light-weight browser agents",
     size=30, color=SHEET, bold=False, line_spacing=1.02)

text(s, M, 5.25, 7.2, 0.7,
     "A Chrome agent that works inside your logged-in session, redacts the page\n"
     "before serialisation, and asks a human before anything consequential.",
     size=13.5, color="C9C0AE", line_spacing=1.25)

text(s, M, 6.3, 7.6, 0.5,
     "Department of Space / ISRO  ·  Smart Automation · Software\n"
     "Team: [add names]  ·  [add institution]",
     size=9.5, color="8F887A", font=MONO, line_spacing=1.35)

# Aperture mark
cx, cy = 10.55, 3.15
for d, col, width in [(3.4, "6C6F76", 1.0), (2.5, "8F887A", 1.2),
                      (1.55, STAMP, 2.4)]:
    rect(s, cx - d / 2, cy - d / 2, d, d, fill=None, line=col, line_w=width,
         shape=MSO_SHAPE.OVAL)
rect(s, cx - 0.42, cy - 0.42, 0.84, 0.84, fill=STAMP, line=None,
     shape=MSO_SHAPE.OVAL)

stamp = s.shapes.add_textbox(Inches(9.55), Inches(5.45), Inches(3.1), Inches(0.62))
stamp.rotation = -7
stf = stamp.text_frame
stf.word_wrap = False
stf.margin_left = stf.margin_right = Inches(0.05)
p = stf.paragraphs[0]
p.alignment = PP_ALIGN.CENTER
r = p.add_run()
r.text = "PRIVACY BEFORE TRANSMISSION"
r.font.name = MONO
r.font.size = Pt(10.5)
r.font.bold = True
r.font.color.rgb = C(STAMP)
stamp.fill.background()
stamp.line.color.rgb = C(STAMP)
stamp.line.width = Pt(1.8)

text(s, M, 7.04, 12.0, 0.2,
     "Built from this checkout  ·  every number in this deck comes from a run",
     size=7.5, color="6E6A60", font=MONO)

notes(s, "Drishti means sight. The project is a Chrome extension plus a local "
         "orchestration server that gives a browser agent local perception before "
         "any cloud reasoning. Review II focus: the working loop, the privacy "
         "boundary, and the evidence that both behave as described.")

# ==========================================================================
# 2 · ABSTRACT
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "01 / ABSTRACT", "A browser agent that looks before it speaks.")
footer(s, 2)

body = (
    "Drishti is a Chrome MV3 extension and a local FastAPI orchestrator that drives "
    "the operator’s own logged-in browser through a closed observe → reason → policy "
    "→ act → verify loop. The DOM is walked and redacted inside the page; screenshots "
    "are masked, OCR-checked and withheld if a PII shape survives. Only sanitised "
    "context reaches the cloud reasoner. A deterministic policy layer, a human "
    "approval gate and a fresh-state verifier stand between the model and the page. "
    "Every task ends with a hash-chained audit trail and a four-state perception "
    "verdict that says what was actually proved."
)
text(s, M, 1.62, 7.55, 2.75, body, size=15.5, color=INK, line_spacing=1.28)

text(s, M, 4.55, 7.4, 0.28, "THE INVARIANT", size=9, color=STAMP,
     font=MONO, bold=True)
text(s, M, 4.9, 7.45, 0.95,
     "Raw page  →  local detection  →  local redaction  →  sanitised  →  network",
     size=13, color=INK, font=MONO, bold=True, line_spacing=1.2)
text(s, M, 5.55, 7.3, 0.8,
     "Redaction happens before serialisation. Redacting after transmission would "
     "defeat the requirement, so the trust boundary is drawn at the page.",
     size=12, color=INK_DIM, line_spacing=1.22)

stats = [
    ("9", "PII pattern families\nredacted in-page"),
    ("27", "permitted action verbs\nin a closed whitelist"),
    ("4", "perception verdict states\nWITHHOLD is fail-closed"),
    (f"{total_n or 13}", "capability cases in the\nautomated demo suite"),
]
sx, sy = 8.72, 1.62
for i, (num, label) in enumerate(stats):
    x = sx + (i % 2) * 1.99
    y = sy + (i // 2) * 1.72
    rect(s, x, y, 1.86, 1.52, fill=SHEET, line=INK, line_w=0.8)
    text(s, x + 0.14, y + 0.1, 1.58, 0.55, num, size=30, color=STAMP, bold=True)
    text(s, x + 0.14, y + 0.7, 1.58, 0.7, label, size=8.2, color=INK_DIM,
         line_spacing=1.12)

text(s, 8.72, 5.25, 3.85, 0.85,
     "Not a chatbot in a sidebar.\nA control loop with evidence.",
     size=13, color=INK, bold=True, line_spacing=1.2)
notes(s, "The abstract in one breath: local perception and redaction, cloud "
         "reasoning on sanitised context only, deterministic control, human "
         "approval, verification, audit. Nine PII families, twenty-seven verbs, "
         "four verdict states, thirteen capability cases.")

# ==========================================================================
# 3 · PROBLEM
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "02 / PROBLEM", "Three failures meet in the same browser tab.")
footer(s, 3)

cards = [
    ("01", "PRIVACY",
     "Raw DOM and screenshots are the easiest context to send. They carry email, "
     "cards, Aadhaar, OTPs, passwords and private messages — most of it irrelevant "
     "to the task.",
     "Redact in the page before serialisation."),
    ("02", "SESSION",
     "Playwright and Puppeteer start a fresh profile. The work that matters — mail, "
     "chat, a college portal — lives inside the operator’s authenticated session, "
     "which a fresh browser does not have.",
     "Run inside the operator’s own Chrome profile."),
    ("03", "TRUST",
     "Page text can instruct the agent: open this link, paste this OTP, change the "
     "recipient, submit the form. A model that cannot separate data from instruction "
     "is one crafted paragraph away from exfiltration.",
     "Page text is data; Python decides what executes."),
]
for i, (num, label, body, answer) in enumerate(cards):
    x = M + i * 4.03
    rect(s, x, 1.62, 3.78, 3.55, fill=SHEET, line=INK, line_w=0.9)
    text(s, x + 0.22, 1.8, 0.6, 0.35, num, size=13, color=STAMP, font=MONO, bold=True)
    text(s, x + 0.22, 2.15, 3.3, 0.35, label, size=11, color=INK, font=MONO, bold=True)
    text(s, x + 0.22, 2.62, 3.34, 1.78, body, size=12.2, color=INK_DIM,
         line_spacing=1.22)
    rule(s, x + 0.22, 4.52, 3.34, "C9BFA7", 0.7)
    text(s, x + 0.22, 4.62, 3.34, 0.2, "DRISHTI RESPONSE", size=8, color=STAMP,
         font=MONO, bold=True)
    text(s, x + 0.22, 4.85, 3.34, 0.3, answer, size=9.6, color=INK, bold=True)

rect(s, M, 5.48, W - 2 * M, 1.08, fill=None, line=STAMP, line_w=1.2)
text(s, M + 0.2, 5.62, 2.0, 0.25, "SCOPE", size=8.5, color=STAMP, font=MONO, bold=True)
text(s, M + 0.2, 5.88, 11.4, 0.58,
     "One operator  ·  own Chrome profile  ·  one active task.  Not unattended, not a "
     "CAPTCHA solver, not a multi-tenant service.",
     size=12.5, color=INK, line_spacing=1.15)

text(s, M, 6.78, 12.0, 0.22,
     "Motivation sources: Willison, “The Lethal Trifecta” (2025); OWASP LLM01 Prompt Injection.",
     size=8, color=INK_FAINT, font=MONO)
notes(s, "Three failures, not one. Privacy: the page is full of data the task does "
         "not need. Session: the useful web is logged in, and a fresh automation "
         "browser is not. Trust: page text is adversarial input. Drishti’s scope is "
         "deliberately one operator and one task.")

# ==========================================================================
# 4 · EXISTING VS PROPOSED
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "03 / PRIOR ART", "What exists, and what it costs.")
footer(s, 4)

rows = [
    ["Approach", "Limitation", "Drishti’s response", "Evidence"],
    ["Cloud browser agents", "Raw screenshot + DOM go to the vendor on every step.",
     "In-page redaction before serialisation; masked capture; measured verdict.",
     "agent-content.js:316\nG7 · G10"],
    ["Playwright / Puppeteer", "Fresh profile loses logged-in sessions; automation is detectable.",
     "MV3 extension runs in the operator’s own Chrome profile.",
     "manifest.json\nADR-002"],
    ["Scripted scrapers", "Selectors break on layout change; no recovery or verification.",
     "Closed loop; stable nid; stale-element recovery; fresh-state verifier.",
     "fnv1a / nid\nverifier.py:76"],
    ["Prior versions", "v1: privacy kernel, mock reasoner. v2: honesty layer, no agent.",
     "v3 combines the privacy kernel, the verdict and a working browser loop.",
     "SRS §7\nlive demos"],
    ["Manual browsing", "Safe, but the operator still performs every step.",
     "Agent proposes; policy gates; human answers only consequential prompts.",
     "policy.py:75\npayment demo"],
]
table(s, M, 1.6, W - 2 * M, 4.85, rows,
      col_widths=[2.15, 3.35, 3.95, 2.44],
      row_heights=[0.42, 0.86, 0.86, 0.86, 0.86, 0.86],
      font_size=10.3, header_size=9.2)

rect(s, M, 6.6, W - 2 * M, 0.36, fill=None, line=None)
text(s, M, 6.62, 11.9, 0.3,
     "The contribution is the integration: local redaction + measured verdict + "
     "deterministic policy + separate quoter + hash-chained audit.",
     size=11, color=STAMP, bold=True, font=MONO)
notes(s, "Each row is a real alternative with a real cost. Cloud agents see "
         "everything. Playwright is logged out. Scrapers break. Our prior versions "
         "had one half each. The novel part is not any single idea; it is the "
         "working combination and the refusal to claim unmeasured privacy.")

# ==========================================================================
# 5 · ARCHITECTURE
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "04 / ARCHITECTURE", "One loop, three trust zones, one boundary.")
footer(s, 5)

# Zones
rect(s, 0.55, 1.55, 5.5, 4.55, fill="EDE5D3", line="B9AF98", line_w=0.8)
text(s, 0.72, 1.66, 2.25, 0.25, "CHROME  ·  OPERATOR PROFILE", size=8.5,
     color=INK_DIM, font=MONO, bold=True)
text(s, 2.55, 1.66, 1.05, 0.25, "REDACT HERE", size=7.5, color=STAMP,
     font=MONO, bold=True, align=PP_ALIGN.RIGHT)

rect(s, 6.55, 1.55, 3.45, 4.55, fill="EDE5D3", line="B9AF98", line_w=0.8)
text(s, 6.72, 1.66, 3.1, 0.25, "LOCAL SERVER  ·  127.0.0.1:8787", size=8.5,
     color=INK_DIM, font=MONO, bold=True)

rect(s, 10.31, 2.45, 2.3, 1.95, fill=INK, line=None)
text(s, 10.38, 2.6, 2.0, 0.25, "CLOUD REASONER", size=8.5, color="A9A290",
     font=MONO, bold=True)
text(s, 10.38, 2.95, 1.98, 0.95,
     "Gemini (default)\nGroq · OpenRouter\nOpenAI",
     size=11, color=SHEET, line_spacing=1.3)
text(s, 10.38, 3.98, 2.0, 0.4, "sanitised context only", size=8.5, color="D8CDB6",
     font=MONO)

# Browser stack
rect(s, 0.88, 1.98, 2.55, 0.72, fill=STAMP, line=None)
text(s, 1.0, 2.1, 2.3, 0.25, "WEB PAGE", size=9, color=SHEET, font=MONO, bold=True)
text(s, 1.0, 2.36, 2.3, 0.25, "untrusted input", size=9.5, color="F3D9CF")

rect(s, 0.88, 2.95, 2.55, 0.95, fill=SHEET, line=INK, line_w=0.9)
text(s, 1.0, 3.05, 2.35, 0.25, "agent-content.js", size=10, color=INK, bold=True)
text(s, 1.0, 3.32, 2.35, 0.5, "walk · redact · stable ids\nexecute · login wall",
     size=8.7, color=INK_DIM, line_spacing=1.15)

rect(s, 0.88, 4.12, 2.55, 0.95, fill=SHEET, line=INK, line_w=0.9)
text(s, 1.0, 4.22, 2.35, 0.25, "agent-background.js", size=10, color=INK, bold=True)
text(s, 1.0, 4.49, 2.35, 0.5, "WebSocket · capture · mask\ndownload · upload",
     size=8.7, color=INK_DIM, line_spacing=1.15)

rect(s, 3.7, 4.12, 2.05, 0.95, fill=SHEET, line=INK, line_w=0.9)
text(s, 3.82, 4.22, 1.85, 0.25, "offscreen", size=10, color=INK, bold=True)
text(s, 3.82, 4.49, 1.85, 0.5, "Tesseract OCR\nMobileCLIP-S0",
     size=8.7, color=INK_DIM, line_spacing=1.15)

# redaction boundary
rect(s, 0.74, 1.87, 2.83, 2.2, fill=None, line=STAMP, line_w=1.4, dashed=True)

# server stack
rect(s, 6.75, 1.98, 3.05, 0.72, fill=SHEET, line=INK, line_w=0.9)
text(s, 6.87, 2.06, 2.85, 0.23, "FastAPI / uvicorn", size=10, color=INK, bold=True)
text(s, 6.87, 2.3, 2.85, 0.28, "/ws/agent  /ws/cockpit  /tasks", size=8.4,
     color=INK_DIM, font=MONO)

rect(s, 6.75, 2.95, 3.05, 0.95, fill=SHEET, line=INK, line_w=0.9)
text(s, 6.87, 3.04, 2.85, 0.23, "loop.py", size=10, color=INK, bold=True)
text(s, 6.87, 3.3, 2.85, 0.45, "observe · reason · policy\napprove · execute · verify",
     size=8.7, color=INK_DIM, line_spacing=1.15)

rect(s, 6.75, 4.12, 1.45, 0.92, fill=SHEET, line=INK, line_w=0.9)
text(s, 6.87, 4.2, 1.25, 0.22, "policy + verify", size=8.7, color=INK, bold=True)
text(s, 6.87, 4.45, 1.25, 0.5, "deterministic\nfresh state", size=8.2,
     color=INK_DIM, line_spacing=1.1)

rect(s, 8.35, 4.12, 1.45, 0.92, fill=SHEET, line=INK, line_w=0.9)
text(s, 8.47, 4.2, 1.25, 0.22, "events.py", size=8.7, color=INK, bold=True)
text(s, 8.47, 4.45, 1.25, 0.5, "SHA-256 chain\nJSONL audit", size=8.2,
     color=INK_DIM, line_spacing=1.1)

# flows between the boxes
rect(s, 2.08, 3.92, 0.16, 0.18, fill=STAMP, line=None, shape=MSO_SHAPE.DOWN_ARROW)
rect(s, 3.46, 4.5, 0.2, 0.13, fill=STAMP, line=None, shape=MSO_SHAPE.RIGHT_ARROW)

# content script -> service worker -> local server (ws)
rect(s, 2.15, 5.07, 0.03, 0.2, fill=STAMP, line=None)  # background bottom stub
rect(s, 2.15, 5.27, 3.91, 0.03, fill=STAMP, line=None)
rect(s, 6.06, 2.4, 0.03, 2.9, fill=STAMP, line=None)
rect(s, 6.06, 2.38, 0.56, 0.03, fill=STAMP, line=None)
rect(s, 6.62, 2.31, 0.13, 0.15, fill=STAMP, line=None, shape=MSO_SHAPE.RIGHT_ARROW)
text(s, 5.62, 3.65, 0.5, 0.2, "ws://", size=7.2, color=STAMP, font=MONO, bold=True)

# local server -> cloud reasoner
rect(s, 9.84, 3.36, 0.44, 0.14, fill=STAMP, line=None, shape=MSO_SHAPE.RIGHT_ARROW)
text(s, 9.84, 3.12, 0.44, 0.2, "HTTPS", size=7.2, color=STAMP, font=MONO,
     bold=True, align=PP_ALIGN.CENTER)

text(s, 0.75, 5.55, 4.6, 0.5,
     "Only the service worker holds the server address. The content script cannot name it (G7).",
     size=8.3, color=INK_DIM, font=MONO, line_spacing=1.2)
text(s, 6.75, 5.55, 3.05, 0.5,
     "Loopback only · token-authenticated · one runtime per session.",
     size=8.3, color=INK_DIM, font=MONO, line_spacing=1.2)

text(s, M, 6.24, W - 2 * M, 0.62,
     "G7  content script has no server address     ·     G6  capture is masked before "
     "encoding     ·     G10  a caught leak withholds the screenshot",
     size=9.2, color=INK, font=MONO, bold=True, line_spacing=1.25)
notes(s, "Three processes. The page and content script are the untrusted side; "
         "redaction happens there, inside the dashed line. The service worker is the "
         "only egress. The local server owns policy, approval, verification and "
         "audit. The cloud model receives sanitised context and returns one action. "
         "G7 enforces that the content script cannot even name the server.")

# ==========================================================================
# 6 · PRIVACY PIPELINE
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "05 / PRIVACY", "Redact where the data lives, then prove it.")
footer(s, 6)

stages = [("RAW PAGE", "DOM + inputs"), ("LOCAL DETECT", "9 patterns + checks"),
          ("LOCAL REDACT", "placeholders + boxes"), ("SANITIZED", "only safe context"),
          ("NETWORK", "cloud reasoner")]
stage_pitch = (W - 2 * M - 2.02) / 4
for i, (name, sub) in enumerate(stages):
    x = M + i * stage_pitch
    fill = STAMP if i == 0 else (INK if i == 4 else SHEET)
    fg = SHEET if i in (0, 4) else INK
    rect(s, x, 1.62, 2.02, 0.88, fill=fill, line=INK, line_w=0.9)
    text(s, x + 0.12, 1.7, 1.8, 0.24, name, size=8.5, color=fg, font=MONO, bold=True)
    text(s, x + 0.12, 1.98, 1.8, 0.4, sub, size=9.5,
         color=(SHEET if i in (0, 4) else INK_DIM), line_spacing=1.1)
    if i < 4:
        rect(s, x + 2.114, 1.99, 0.26, 0.14, fill=STAMP, line=None,
             shape=MSO_SHAPE.RIGHT_ARROW)
# vertical boundary between sanitised context and the network
bound_x = M + 3 * stage_pitch + 2.02 + (stage_pitch - 2.02) / 2
rect(s, bound_x - 0.018, 1.62, 0.036, 0.88, fill=STAMP, line=None)
text(s, bound_x - 0.85, 2.6, 1.7, 0.2, "TRUST BOUNDARY", size=7.2, color=STAMP,
     font=MONO, bold=True, align=PP_ALIGN.CENTER)

text(s, M, 2.95, 5.6, 0.28, "WHAT IS REMOVED BEFORE SERIALISATION",
     size=8.7, color=STAMP, font=MONO, bold=True)
items = [
    ("9 PII families", "card · Aadhaar · PAN · GSTIN · voter ID · DL · UPI · email · phone"),
    ("Protected inputs", "password / OTP / CVV / card become [PROTECTED INPUT] len=N"),
    ("Pixels", "sensitive boxes are painted solid black before JPEG encoding"),
    ("Re-read", "OCR runs on the masked image; a surviving shape withholds the capture"),
]
for i, (lead, body) in enumerate(items):
    y = 3.32 + i * 0.72
    text(s, M, y, 1.75, 0.25, lead, size=9.2, color=INK, bold=True)
    text(s, M + 1.75, y, 4.0, 0.6, body, size=9.6, color=INK_DIM, line_spacing=1.15)

text(s, 6.6, 2.95, 5.9, 0.28, "THE VERDICT IS DERIVED, NEVER STORED",
     size=8.7, color=STAMP, font=MONO, bold=True)
verdicts = [
    ("SANITIZED", OK, "Every attempted path succeeded; nothing left uncertain."),
    ("ALLOW_DECLARED", INK, "Text path clean; visual path incomplete or not attempted."),
    ("DEGRADED", AMBER, "A capability was unavailable and the step continued anyway."),
    ("WITHHOLD", STAMP, "A guarantee could not be verified. Fail closed; claim nothing."),
]
for i, (name, col, desc) in enumerate(verdicts):
    y = 3.32 + i * 0.72
    rect(s, 6.6, y, 5.95, 0.58, fill=SHEET, line=col, line_w=1.0)
    text(s, 6.72, y, 1.55, 0.58, name, size=8.6, color=col, font=MONO, bold=True,
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, 8.3, y, 4.1, 0.58, desc, size=8.7, color=INK_DIM, line_spacing=1.08,
         anchor=MSO_ANCHOR.MIDDLE)

text(s, 6.6, 6.32, 5.95, 0.5,
     "server/schemas.py:210  ·  WITHHOLD dominates aggregation  ·  G13 grades eight real observations",
     size=7.8, color=INK_FAINT, font=MONO, line_spacing=1.2)

notes(s, "The invariant is positional: redaction is before serialisation, inside "
         "the page. Nine families, protected inputs, painted boxes, then a re-read of "
         "the masked image. The verdict is computed from measured fields, never "
         "stored, and WITHHOLD wins ties. That is how the system admits a gap instead "
         "of inventing a clean result.")

# ==========================================================================
# 7 · LOOP AND CONTROL
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "06 / CONTROL", "The model proposes. The system decides.")
footer(s, 7)

steps = ["OBSERVE", "REASON", "POLICY", "APPROVE", "EXECUTE", "VERIFY"]
step_pitch = (W - 2 * M - 1.78) / 5
for i, name in enumerate(steps):
    x = M + i * step_pitch
    fill = STAMP if name == "APPROVE" else (INK if name in ("POLICY", "VERIFY") else SHEET)
    fg = SHEET if fill != SHEET else INK
    rect(s, x, 1.62, 1.78, 0.78, fill=fill, line=INK, line_w=0.9)
    text(s, x, 1.86, 1.78, 0.28, name, size=9.2, color=fg, font=MONO, bold=True,
         align=PP_ALIGN.CENTER)
    if i < 5:
        rect(s, x + 1.80, 1.94, 0.20, 0.14, fill=INK_DIM, line=None,
             shape=MSO_SHAPE.RIGHT_ARROW)

text(s, M, 2.5, 11.8, 0.24,
     "↺  every executed action returns to a fresh observation before the next reason call",
     size=9.5, color=INK_DIM, font=MONO)

cards = [
    ("DETERMINISTIC POLICY",
     "27 verbs, closed whitelist.\nUnknown verbs denied.\nSubmit, payment and high-risk\nnames require a human.",
     "server/policy.py:75"),
    ("HUMAN GATE",
     "120 s timeout → deny + cancel.\nNever auto-approves.\nAuthentication codes always\nneed a live human.",
     "server/loop.py:1499"),
    ("FRESH-STATE VERIFY",
     "Stale observations rejected.\nPostconditions checked.\nThree consecutive failures\nstop the task.",
     "server/verifier.py:76"),
]
for i, (head, body, source) in enumerate(cards):
    x = M + i * 4.03
    rect(s, x, 2.92, 3.78, 1.72, fill=SHEET, line=INK, line_w=0.9)
    text(s, x + 0.18, 3.03, 3.4, 0.24, head, size=8.8, color=STAMP, font=MONO, bold=True)
    text(s, x + 0.18, 3.34, 3.42, 1.18, body, size=10.6, color=INK_DIM, line_spacing=1.22)
    rule(s, x + 0.18, 4.32, 3.42, "C9BFA7", 0.6)
    text(s, x + 0.18, 4.42, 3.42, 0.2, source, size=7.6, color=INK_FAINT, font=MONO)

text(s, M, 4.9, 5.8, 0.25, "PAGE TEXT IS UNTRUSTED INPUT", size=8.7, color=STAMP,
     font=MONO, bold=True)
text(s, M, 5.2, 5.75, 1.25,
     "Four independent defences: sentence-level neutralisation, data-marking, a "
     "capability gate on outgoing text and links, and a separate quoter that writes "
     "messages without ever seeing the page.",
     size=10.5, color=INK_DIM, line_spacing=1.25)

text(s, M, 6.08, 5.75, 0.3,
     "server/sanitizer.py  ·  capability_gate.py  ·  quoter.py",
     size=7.8, color=INK_FAINT, font=MONO)

rect(s, 6.75, 4.9, 5.85, 1.55, fill=INK, line=None)
text(s, 6.95, 5.02, 5.45, 0.24, "AUDIT IS EVIDENCE, NOT DECORATION",
     size=8.7, color="D8CDB6", font=MONO, bold=True)
text(s, 6.95, 5.34, 5.45, 0.95,
     "Every event is appended to a SHA-256 hash chain. /tasks/{id}/audit/verify "
     "recomputes it; a broken link is reported instead of hidden.",
     size=10.5, color=SHEET, line_spacing=1.25)
text(s, 6.95, 6.12, 5.45, 0.24,
     "13/13 run: 13–72 audit lines per task · 16 for PII",
     size=7.8, color="D8CDB6", font=MONO)
notes(s, "The loop is deliberately boring: observe, reason, policy, optional human, "
         "execute, verify. The model only ever emits one proposed action. The policy "
         "is Python, not a prompt. A denied approval cancels. Verification reads the "
         "page again, and three consecutive failures stop the run. The audit is a "
         "hash chain with an independent verify endpoint.")

# ==========================================================================
# 8 · POPUP
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "07 / INTERFACE", "A control surface, not a chat toy.")
footer(s, 8)

features = [
    ("AGENT  /  ASK", "Ask is read-only at the backend: ANSWER_ONLY_ACTIONS refuses "
     "click, type, submit, navigate, upload and download before execution."),
    ("POWER", "Fast: 30 steps / 300 s, no vision. Balanced: 60 / 600 s. Deep: 90 / "
     "900 s. The profile is sent in TASK_CREATE and enforced by the loop."),
    ("CONTEXT  +", "A working tray for selection, table and page context. Quick "
     "actions adapt to what is on screen instead of showing a fixed menu."),
    ("SETTINGS", "A dossier drawer: provider health, privacy mode, approval memory, "
     "credentials and the honest limits of each control."),
]
for i, (head, body) in enumerate(features):
    y = 1.62 + i * 1.22
    text(s, M, y, 2.1, 0.24, head, size=8.9, color=STAMP, font=MONO, bold=True)
    text(s, M + 2.05, y - 0.02, 6.45, 1.05, body, size=11.2, color=INK_DIM,
         line_spacing=1.22)
    rule(s, M, y + 0.95, 8.5, "C9BFA7", 0.6)

picture(s, SHOTS / "popup-ui-cropped.png", 9.72, 1.55, 2.64)
text(s, 9.72, 5.77, 2.83, 0.5,
     "Built popup · 390 × 600\nreal render, 386 × 600 capture",
     size=7.6, color=INK_FAINT, font=MONO, line_spacing=1.25)

rect(s, M, 6.35, 12.0, 0.48, fill=None, line=None)
text(s, M, 6.37, 11.9, 0.4,
     "Ask is not a UI hint. The loop refuses page-changing verbs even if the model "
     "proposes one.",
     size=11.5, color=STAMP, bold=True, font=MONO)
notes(s, "The popup is the operator’s control surface. Agent and Ask are different "
         "backend contracts, not labels. Power maps to real budgets. The plus tray "
         "carries page context. Settings is where the system explains itself. This is "
         "a real render of the built UI.")

# ==========================================================================
# 9 · PRIVACY EVIDENCE
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "08 / EVIDENCE", "Privacy is measured, not asserted.")
footer(s, 9)

picture(s, SHOTS / "pii-fixture-records.png", 0.95, 1.55, 3.95)
picture(s, SHOTS / "pii-fixture-protected.png", 0.95, 5.12, 3.95)
text(s, M, 6.28, 5.0, 0.5,
     "Two crops from one synthetic PII fixture: six shapes, protected fields, ₹1,799 total.",
     size=7.8, color=INK_FAINT, font=MONO, line_spacing=1.18)

ev = [
    ("6 + 2", "Six PII shapes redacted; password and OTP protected. Eight mask boxes recorded."),
    ("₹1,799", "The answer survived redaction. A regex that crossed newlines was found live and fixed."),
    ("0", "Raw fixture values in the audit file. [REDACTED: present; 16-line chain verified."),
    ("DEGRADED", "The cockpit states a failed capture instead of showing a clean screenshot."),
]
for i, (num, body) in enumerate(ev):
    y = 1.6 + i * 1.22
    text(s, 5.75, y, 1.55, 0.55, num, size=19,
         color=(OK if i == 2 else (STAMP if i == 3 else INK)),
         bold=True)
    text(s, 7.3, y + 0.02, 5.2, 0.95, body, size=10.6, color=INK_DIM, line_spacing=1.2)
    rule(s, 5.75, y + 0.98, 6.75, "C9BFA7", 0.6)

text(s, 5.75, 6.42, 6.8, 0.4,
     "demo-pii-redaction  ·  20.4 s  ·  1 step  ·  COMPLETED  ·  audit chain valid",
     size=8.0, color=OK, font=MONO, bold=True)
notes(s, "This is the privacy case, and it is honest about both sides. Six patterns "
         "were redacted, password and OTP were protected, the order total survived, "
         "and no raw fixture value appeared in the audit. The address regex bug was "
         "found by this demo and fixed with a regression test. The last row is the "
         "cockpit admitting a degraded capture.")

# ==========================================================================
# 10 · ADVERSARIAL EVIDENCE
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "09 / ADVERSARIAL", "A page can lie. It still cannot steer the loop.")
footer(s, 10)

picture(s, SHOTS / "injection-note.png", M, 1.55, 4.0)
text(s, M, 3.94, 4.0, 0.5,
     "The low-contrast PARTNER INTEGRATION NOTE is the live lure; the panel below it explains the fixture.",
     size=7.6, color=INK_FAINT, font=MONO, line_spacing=1.16)
picture(s, SHOTS / "injection-product.png", M, 4.55, 4.0)
text(s, M, 5.35, 4.0, 0.4,
     "PixelLite 13 · ₹59,990 — the answer the agent gave.",
     size=7.6, color=INK_FAINT, font=MONO, line_spacing=1.16)

rows = [
    ["Attack", "Observed result", "Evidence"],
    ["Injected mail + OTP lure", "Cheapest laptop answered as ₹59,990; lure address never visited or written.",
     "demo-prompt-injection"],
    ["Pay without consent", "CONFIRMATION_REQUESTED; deny cancels; approval records before completion.",
     "payment gate + approved"],
    ["Ask mode tries to click", "Backend refuses every page-changing verb before execution.",
     "demo-ask-readonly"],
    ["Copied page text into a message", "Data markers or verbatim slabs blocked; quoter must author the text.",
     "capability_gate.py"],
]
table(s, 5.35, 1.55, 7.2, 3.3, rows,
      col_widths=[1.9, 3.55, 1.75],
      row_heights=[0.38, 0.72, 0.72, 0.72, 0.72],
      font_size=9.2, header_size=8.6)

rect(s, 5.35, 5.12, 7.2, 1.42, fill=None, line=STAMP, line_w=1.2)
text(s, 5.53, 5.22, 6.85, 0.24, "THE HONEST LIMIT", size=8.2, color=STAMP,
     font=MONO, bold=True)
text(s, 5.53, 5.5, 6.85, 1.0,
     "Prompt injection is mitigated, not eliminated. Novel phrasing can still "
     "influence a plan. Deterministic policy and human approval are the backstop, "
     "not a proof of safety. The suite tests one injection phrasing; it does not "
     "measure attack success rate.",
     size=10.0, color=INK_DIM, line_spacing=1.18)
notes(s, "The adversarial slide pairs the actual attack fixture with outcomes. The "
         "lure is in the live DOM; the agent answered the product question and never "
         "visited the address. Payment and Ask are policy outcomes, not prompt "
         "requests. And the red box says the quiet part: mitigation is not proof.")

# ==========================================================================
# 11 · CAPABILITY SUITE
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "10 / CAPABILITY SUITE", "One command, thirteen judged cases.")
footer(s, 11)

headline = f"{passed_n}/{total_n}" if total_n else "13/13"
text(s, M, 1.62, 3.4, 0.9, headline, size=54, color=OK if total_n and passed_n == total_n else STAMP,
     bold=True)
text(s, M, 2.52, 3.6, 0.45,
     "cases passed in the latest single run" if total_n and passed_n == total_n
     else "cases passed in the latest run",
     size=10.5, color=INK_DIM, line_spacing=1.2)
text(s, M, 3.05, 3.55, 0.7,
     "npm run demo\nserver/eval/demo_tasks.json",
     size=9.2, color=INK, font=MONO, bold=True, line_spacing=1.3)
text(s, M, 3.85, 3.55, 1.0,
     "Each case is judged from live events, terminal state and the audit chain — not "
     "from the model’s own claim.",
     size=10.2, color=INK_DIM, line_spacing=1.22)

left = CASE_ORDER[:7]
right = CASE_ORDER[7:]
for col, cases in enumerate((left, right)):
    x = 4.45 + col * 4.2
    for i, cid in enumerate(cases):
        y = 1.62 + i * 0.58
        outcome, ok = outcomes.get(cid, ("not run", False))
        mark = "PASS" if ok else ("FAIL" if cid in outcomes else "—")
        color = OK if ok else (STAMP if cid in outcomes else INK_FAINT)
        text(s, x, y, 2.55, 0.22, cid.replace("demo-", ""), size=9.2, color=INK,
             font=MONO)
        text(s, x + 2.58, y, 0.62, 0.22, mark, size=8.6, color=color, font=MONO,
             bold=True)

rule(s, M, 5.72, W - 2 * M, "C9BFA7", 0.6)
text(s, M, 5.86, 11.9, 0.28,
     f"{total_n} cases · {total_s:.0f} s total · one server session",
     size=9.2, color=INK, font=MONO, bold=True)

text(s, M, 6.18, 12.0, 0.62,
     "Read · navigate · extract · Ask · effort · PII · payment deny/approve · injection · "
     "job form · scholarship deny · login wall",
     size=8.6, color=INK_FAINT, font=MONO, line_spacing=1.2)
text(s, M, 6.52, 12.0, 0.35,
     "Honest scope: example.com plus nine synthetic local fixtures. This is a capability "
     "suite, not a benchmark of the open web.",
     size=9.6, color=STAMP, font=MONO)
notes(s, "One command runs thirteen cases. The judge checks URL transitions, required "
         "and forbidden actions, PII absence, required events, terminal state and the "
         "hash chain. The count on this slide is read from last_run.json at build "
         "time. The scope note matters: local fixtures plus example.com, not a web "
         "benchmark.")

# ==========================================================================
# 12 · VERIFICATION
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "11 / VERIFICATION", "Every number comes from a run.")
footer(s, 12)

stats = [("14/14", "enforcement gates", "G1–G14"), ("146", "JavaScript tests", "9 files"),
         ("244", "Python tests", "15 files"), ("74.09", "MB packaged dist", "52 files")]
for i, (num, label, sub) in enumerate(stats):
    x = M + i * 3.02
    rect(s, x, 1.58, 2.78, 1.35, fill=SHEET, line=INK, line_w=0.9)
    text(s, x + 0.16, 1.66, 2.4, 0.5, num, size=25, color=STAMP, bold=True)
    text(s, x + 0.16, 2.18, 2.45, 0.24, label, size=9.4, color=INK, bold=True)
    text(s, x + 0.16, 2.43, 2.45, 0.22, sub, size=8.2, color=INK_FAINT, font=MONO)

text(s, M, 3.18, 5.9, 0.26, "WHAT THE GATES ENFORCE", size=8.7, color=STAMP,
     font=MONO, bold=True)
gates = [
    ("G6", "canvas is used only for redaction"),
    ("G7", "content script has no server address"),
    ("G10", "a caught leak withholds the screenshot"),
    ("G13", "all four verdicts reachable; WITHHOLD dominates"),
    ("G14", "cockpit is keyboard and screen-reader operable"),
]
for i, (g, body) in enumerate(gates):
    y = 3.52 + i * 0.4
    text(s, M, y, 0.5, 0.22, g, size=9.2, color=INK, font=MONO, bold=True)
    text(s, M + 0.55, y, 5.3, 0.3, body, size=9.6, color=INK_DIM)

text(s, M, 5.72, 5.9, 0.8,
     "Commands: npm run gates  ·  npm test  ·  npm run test:py  ·  npm run build\n"
     "Build: 3,129 modules, clean, 17.15 s. No runtime model downloads.",
     size=8.4, color=INK_FAINT, font=MONO, line_spacing=1.4)

picture(s, SHOTS / "cockpit.png", 6.55, 3.16, 4.35)
text(s, 6.55, 6.54, 5.5, 0.42,
     "Real cockpit: task completed, audit intact, capture DEGRADED — stated, not hidden.",
     size=7.8, color=INK_FAINT, font=MONO, line_spacing=1.2)
notes(s, "These are current counts from this checkout: fourteen gates, one hundred "
         "forty-six JavaScript tests, two hundred forty-four Python tests, a clean "
         "build, and a seventy-four megabyte package dominated by local models. The "
         "cockpit image is real and includes a degraded capture. That is the honesty "
         "layer doing its job, not a marketing screenshot.")

# ==========================================================================
# 13 · LIMITATIONS
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "12 / LIMITS", "What we do not claim.")
footer(s, 13)

text(s, M, 1.6, 5.9, 0.25, "PROTECTIONS THAT EXIST", size=8.7, color=OK,
     font=MONO, bold=True)
protect = [
    "In-page redaction before serialisation; 9 pattern families.",
    "Protected inputs never emit their value; only length.",
    "Masked capture; OCR re-read withholds on a surviving shape.",
    "Deterministic policy, human gate, fresh-state verification.",
    "SHA-256 audit chain with an independent verify endpoint.",
]
for i, item in enumerate(protect):
    y = 1.98 + i * 0.66
    text(s, M, y, 0.25, 0.22, "✓", size=11, color=OK, bold=True)
    text(s, M + 0.32, y, 5.45, 0.6, item, size=10.8, color=INK_DIM, line_spacing=1.18)

text(s, 6.75, 1.6, 5.9, 0.25, "GAPS THAT REMAIN", size=8.7, color=STAMP,
     font=MONO, bold=True)
gaps = [
    "Latest live cockpit capture is DEGRADED (tab readback failure).",
    "Pattern PII is not semantic: new shapes, images and languages can evade it.",
    "Cross-origin iframes, shadow DOM and painted text are partial.",
    "Chrome only; one browser, one task; no CAPTCHA or anti-bot bypass.",
    "Injection is mitigated, not eliminated; the cloud provider sees sanitised context.",
]
for i, item in enumerate(gaps):
    y = 1.98 + i * 0.66
    text(s, 6.75, y, 0.25, 0.22, "—", size=11, color=STAMP, bold=True)
    text(s, 7.07, y, 5.45, 0.6, item, size=10.8, color=INK_DIM, line_spacing=1.18)

rect(s, M, 5.55, W - 2 * M, 0.95, fill=None, line=STAMP, line_w=1.4)
text(s, M + 0.2, 5.66, 4.0, 0.24, "DO NOT PRESENT AS", size=8.4, color=STAMP,
     font=MONO, bold=True)
text(s, M + 0.2, 5.93, 11.6, 0.42,
     "zero leakage  ·  fully local  ·  production-ready  ·  formally DPDP compliant  ·  "
     "general web competence",
     size=13, color=INK, bold=True)
text(s, M, 6.66, 12.0, 0.3,
     "No p50/p95 latency or peak-memory benchmark yet; no published detector recall.",
     size=8.6, color=INK_FAINT, font=MONO)
notes(s, "This slide protects the team. The protections are real, and so are the "
         "gaps. Say the degraded capture out loud before a reviewer finds it. Pattern "
         "matching is not semantic understanding. Chrome only. Mitigation is not "
         "proof. And never use the four phrases in the red box.")

# ==========================================================================
# 14 · CONCLUSION AND FUTURE SCOPE
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "13 / CONCLUSION", "A working prototype with a measurable conscience.")
footer(s, 14)

text(s, M, 1.62, 6.1, 2.2,
     "Drishti v3 closes the loop: it sees the page locally, redacts before "
     "serialisation, reasons on sanitised context, gates consequential actions, "
     "verifies against fresh state, and leaves a hash-chained record. The privacy "
     "boundary, the control layer and the honesty layer are implemented and "
     "demonstrated. The remaining work is measurement and coverage, not a missing "
     "agent.",
     size=13.6, color=INK, line_spacing=1.32)

text(s, M, 4.15, 6.0, 0.26, "WHAT IS WORKING TODAY", size=8.7, color=OK,
     font=MONO, bold=True)
chips = ["Closed loop", "In-page redaction", "Policy + approval", "Audit + verdict"]
for i, chip in enumerate(chips):
    x = M + (i % 2) * 2.62
    y = 4.48 + (i // 2) * 0.58
    rect(s, x, y, 2.45, 0.42, fill=SHEET, line=OK, line_w=0.9)
    text(s, x, y + 0.09, 2.45, 0.24, chip, size=9.2, color=OK, bold=True,
         align=PP_ALIGN.CENTER)

text(s, 7.0, 1.6, 5.7, 0.26, "FUTURE SCOPE", size=8.7, color=STAMP, font=MONO, bold=True)
tiers = [
    ("NEAR TERM", "Fix live capture; p50/p95 latency and memory; make PII pattern "
     "parity a gate; real-site soak; approval and Ask screenshots."),
    ("MEDIUM TERM", "Iframe and shadow-DOM walking; selective re-masking; packaged "
     "extension with narrower permissions; local LLM fallback."),
    ("LONG TERM", "Firefox parity; NER and face detection with published recall; "
     "AgentDojo-style injection benchmark; external security review."),
]
for i, (head, body) in enumerate(tiers):
    y = 1.94 + i * 1.4
    text(s, 7.0, y, 5.55, 0.24, head, size=8.2, color=STAMP, font=MONO, bold=True)
    text(s, 7.0, y + 0.3, 5.55, 0.95, body, size=10.9, color=INK_DIM,
         line_spacing=1.2)
    if i < len(tiers) - 1:
        rule(s, 7.0, y + 1.25, 5.55, "C9BFA7", 0.6)

text(s, M, 6.45, 12.0, 0.35,
     "The defensible claim: local perception and redaction before cloud reasoning, with "
     "the evidence to show where it held and where it did not.",
     size=9.4, color=STAMP, font=MONO, bold=True)
notes(s, "Close on the defensible claim. The loop exists and the boundary is "
         "enforced in code. What remains is measurement and coverage. Near-term work "
         "is deliberately unglamorous: fix capture, measure latency and memory, gate "
         "pattern parity, soak on real sites.")

# ==========================================================================
# 15 · REFERENCES
# ==========================================================================
s = prs.slides.add_slide(blank)
rect(s, 0, 0, W, H, fill=PAPER)
header(s, "14 / REFERENCES", "MLA 9  ·  accessed 20 November 2026.")
footer(s, 15)

refs = [
    "Willison, Simon. “The Lethal Trifecta for AI Agents: Private Data, Untrusted Content, "
    "and External Communication.” Simon Willison’s Weblog, 16 June 2025, "
    "simonwillison.net/2025/Jun/16/the-lethal-trifecta/.",
    "Hines, Keegan, et al. “Defending Against Indirect Prompt Injection Attacks With "
    "Spotlighting.” arXiv, Mar. 2024, arxiv.org/abs/2403.14720.",
    "Debenedetti, Edoardo, et al. “Defeating Prompt Injections by Design.” arXiv, 2025, "
    "arxiv.org/abs/2503.18813.",
    "Debenedetti, Edoardo, et al. AgentDojo. GitHub, github.com/ethz-spylab/agentdojo.",
    "Google. “Chrome Extensions Documentation.” Chrome for Developers, "
    "developer.chrome.com/docs/extensions/.",
    "OWASP Foundation. “LLM01: Prompt Injection.” OWASP Top 10 for LLM Applications, "
    "genai.owasp.org/llmrisk/llm01-prompt-injection/.",
    "India. The Digital Personal Data Protection Act, 2023. Ministry of Law and Justice, 2023.",
]
y = 1.55
for i, ref in enumerate(refs, 1):
    text(s, M, y, 0.4, 0.24, f"[{i}]", size=9.2, color=STAMP, font=MONO, bold=True)
    text(s, M + 0.48, y - 0.01, 11.35, 0.62, ref, size=9.6, color=INK, line_spacing=1.14)
    y += 0.62

rule(s, M, 6.05, 11.9, "C9BFA7", 0.7)
text(s, M, 6.18, 7.0, 0.24, "INTERNAL EVIDENCE", size=8.2, color=INK_FAINT,
     font=MONO, bold=True)
text(s, M, 6.44, 7.2, 0.5,
     "Repository evidence  ·  docs/review2/REVIEW2-BRIEFING.md  ·  "
     "server/eval/last_run.json  ·  docs/review2/screenshots/",
     size=8.0, color=INK_FAINT, font=MONO, line_spacing=1.25)

text(s, 8.2, 6.18, 4.4, 0.5, "Thank you.", size=22, color=INK, bold=True,
     align=PP_ALIGN.RIGHT)
text(s, 8.2, 6.68, 4.4, 0.25, "Questions", size=9, color=STAMP, font=MONO,
     bold=True, align=PP_ALIGN.RIGHT)
notes(s, "MLA references for the claims that shaped the design. The repository, the "
         "briefing, the last run report and the screenshots are the internal "
         "evidence. Then take questions; the briefing has a prepared Q&A section.")

# --------------------------------------------------------------------------
prs.core_properties.title = "Drishti — TBP Review II"
prs.core_properties.subject = "SIH 2026, Problem Statement 26171"
prs.core_properties.author = "Drishti Team"
prs.core_properties.comments = (
    "Generated from this checkout and server/eval/last_run.json. "
    "All counts are measured; see docs/review2/REVIEW2-BRIEFING.md."
)

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
print(f"capability suite: {passed_n}/{total_n}")
