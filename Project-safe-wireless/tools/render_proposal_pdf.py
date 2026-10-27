"""Render the Markdown research proposal to a review PDF using ReportLab."""
from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "Propuesta_IA_RTI_EM.md"
OUTPUT = ROOT / "report" / "Propuesta_IA_RTI_EM.pdf"
NAVY = colors.HexColor("#18354D")
TEAL = colors.HexColor("#087D81")
PALE = colors.HexColor("#EEF5F6")
LINE = colors.HexColor("#CCDDE1")


def register_fonts():
    fonts = Path(r"C:\Windows\Fonts")
    candidates = {
        "Proposal": [fonts / "segoeui.ttf", fonts / "arial.ttf"],
        "Proposal-Bold": [fonts / "segoeuib.ttf", fonts / "arialbd.ttf"],
        "Proposal-Italic": [fonts / "segoeuii.ttf", fonts / "ariali.ttf"],
    }
    chosen = {}
    for name, paths in candidates.items():
        selected = next((path for path in paths if path.is_file()), None)
        if selected:
            chosen[name] = str(selected)
    if len(chosen) == 3:
        for name, path in chosen.items():
            pdfmetrics.registerFont(TTFont(name, path))
        pdfmetrics.registerFontFamily("Proposal", normal="Proposal", bold="Proposal-Bold", italic="Proposal-Italic", boldItalic="Proposal-Bold")
        return "Proposal", "Proposal-Bold", "Proposal-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


REGULAR, BOLD, ITALIC = register_fonts()
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="ArticleTitle", parent=styles["Title"], fontName=BOLD, fontSize=17, leading=21, textColor=NAVY, alignment=TA_LEFT, spaceAfter=10))
styles.add(ParagraphStyle(name="Author", parent=styles["Normal"], fontName=BOLD, fontSize=10, leading=14, textColor=NAVY, spaceAfter=1))
styles.add(ParagraphStyle(name="Meta", parent=styles["Normal"], fontName=REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#526976"), spaceAfter=2))
styles.add(ParagraphStyle(name="Section", parent=styles["Heading1"], fontName=BOLD, fontSize=13, leading=16, textColor=TEAL, spaceBefore=10, spaceAfter=6, keepWithNext=True))
styles.add(ParagraphStyle(name="Subsection", parent=styles["Heading2"], fontName=BOLD, fontSize=10.5, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=4, keepWithNext=True))
styles.add(ParagraphStyle(name="BodyArticle", parent=styles["BodyText"], fontName=REGULAR, fontSize=9.25, leading=13.2, alignment=TA_LEFT, spaceAfter=6, allowWidows=0, allowOrphans=0))
styles.add(ParagraphStyle(name="Abstract", parent=styles["BodyText"], fontName=REGULAR, fontSize=9, leading=12.4, backColor=PALE, borderColor=LINE, borderWidth=.5, borderPadding=7, spaceBefore=4, spaceAfter=6))
styles.add(ParagraphStyle(name="Keyword", parent=styles["BodyText"], fontName=REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#526976"), spaceAfter=7))
styles.add(ParagraphStyle(name="TableCell", parent=styles["BodyText"], fontName=REGULAR, fontSize=7.1, leading=9.1, spaceAfter=0))
styles.add(ParagraphStyle(name="TableHead", parent=styles["BodyText"], fontName=BOLD, fontSize=7.2, leading=9, textColor=colors.white, spaceAfter=0))
styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontName=REGULAR, fontSize=8, leading=10, textColor=colors.HexColor("#526976"), spaceAfter=4))


def safe_inline(text):
    text = text.replace("\\(", "(").replace("\\)", ")")
    text = text.replace("\\", "")
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace("ρ", "rho").replace("σ", "sigma").replace("γ", "gamma").replace("α", "alpha")
    text = text.replace("×", "x").replace("≥", ">=").replace("≤", "<=")
    text = escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#087D81">\1</link>', text)
    text = re.sub(r"(https?://[^\s<]+)", r'<link href="\1" color="#087D81">\1</link>', text)
    return text


def split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(.5)
    canvas.line(20 * mm, 15 * mm, width - 20 * mm, 15 * mm)
    canvas.setFont(REGULAR, 7.5)
    canvas.setFillColor(colors.HexColor("#657B86"))
    canvas.drawString(20 * mm, 10 * mm, "AI research proposal | Synthetic simulation | 27 October 2026")
    canvas.drawRightString(width - 20 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def render():
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    story = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("| ") or line.startswith("|"):
            raw_rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = split_row(lines[i])
                if not all(re.fullmatch(r":?-{3,}:?", x.replace(" ", "")) for x in row):
                    raw_rows.append(row)
                i += 1
            table_rows = []
            for row_number, row in enumerate(raw_rows):
                style = "TableHead" if row_number == 0 else "TableCell"
                table_rows.append([Paragraph(safe_inline(cell), styles[style]) for cell in row])
            column_count = max(map(len, raw_rows))
            usable = A4[0] - 38 * mm
            if column_count == 4 and raw_rows and len(raw_rows[0]) == 4 and "Reference" in raw_rows[0][0]:
                widths = [32 * mm, 40 * mm, 42 * mm, 58 * mm]
            elif column_count == 4:
                widths = [72 * mm, 35 * mm, 35 * mm, 30 * mm]
            else:
                widths = [usable / column_count] * column_count
            table = LongTable(table_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("GRID", (0, 0), (-1, -1), .35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 5)])
            continue
        if line.startswith("# "):
            story.append(Paragraph(safe_inline(line[2:]), styles["ArticleTitle"]))
            i += 1
            continue
        if line.startswith("## "):
            title = line[3:]
            style = styles["Section"]
            if title in {"Abstract", "Keywords"}:
                style = styles["Subsection"]
            story.append(Paragraph(safe_inline(title), style))
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(safe_inline(line[4:]), styles["Subsection"]))
            i += 1
            continue
        if line.startswith("- "):
            story.append(Paragraph("&#8226; " + safe_inline(line[2:]), styles["BodyArticle"]))
            i += 1
            continue
        if line.startswith("**Camilo"):
            story.append(Paragraph(safe_inline(line), styles["Author"]))
            i += 1
            continue
        if line.startswith("School of Mathematical"):
            story.append(Paragraph(safe_inline(line), styles["Meta"]))
            i += 1
            continue
        if line.startswith(("**Course:", "**Instructor:", "**Article type:")):
            story.append(Paragraph(safe_inline(line), styles["Meta"]))
            i += 1
            continue
        if re.match(r"^\d+\.\s", line):
            story.append(Paragraph(safe_inline(line), styles["BodyArticle"]))
            i += 1
            continue
        paragraph = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line or next_line.startswith(("#", "|", "- ")) or re.match(r"^\d+\.\s", next_line):
                break
            paragraph.append(next_line)
            i += 1
        content = safe_inline(" ".join(paragraph))
        if paragraph[0].startswith("**Keywords:"):
            story.append(Paragraph(content, styles["Keyword"]))
        elif paragraph[0].startswith("**Abstract:**"):
            story.append(Paragraph(content.replace("<b>Abstract:</b>", "<b>Abstract.</b>"), styles["Abstract"]))
        else:
            story.append(Paragraph(content, styles["BodyArticle"]))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=19 * mm, leftMargin=19 * mm,
                            topMargin=17 * mm, bottomMargin=22 * mm,
                            title="Does EM-Based RSS Noise Calibration Improve Radio Tomographic Localization? A Synthetic Study",
                            author="Camilo Vásquez")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Rendered {OUTPUT}")


if __name__ == "__main__":
    render()
