"""Styled PDF builders for player evaluations."""
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Mapping
from xml.sax.saxutils import escape

from fastapi import HTTPException
from fastapi.responses import Response


PINES_GREEN = "#2f6130"
PINES_LIGHT = "#f0f7f0"
PINES_BORDER = "#b3dbb3"
TEXT_DARK = "#1f2937"
TEXT_MUTED = "#4b5563"
PINES_LOGO_URL = "https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg"
REPORT_WIDTH = 524


def _safe(value: Any) -> str:
    return escape(str(value or ""))


def _score_text(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}"
    except (TypeError, ValueError):
        return str(value)


def _find_logo_path() -> str | None:
    static_dir = Path(__file__).resolve().parent / "static"
    for filename in (
        "pines-logo.png",
        "pines_logo.png",
        "logo.png",
        "pines-logo.jpg",
        "pines_logo.jpg",
        "logo.jpg",
        "pines-logo.svg",
        "pines_logo.svg",
        "logo.svg",
    ):
        candidate = static_dir / filename
        if candidate.exists():
            return str(candidate)
    return None


def _logo_flowable(width: float, height: float):
    """Return the app's Pines logo as a ReportLab flowable when available."""
    from reportlab.platypus import Image

    logo_path = _find_logo_path()
    if logo_path and not logo_path.lower().endswith(".svg"):
        return Image(logo_path, width=width, height=height, kind="proportional")

    try:
        from reportlab.graphics.shapes import Drawing
        from svglib.svglib import svg2rlg
    except Exception:
        return None

    drawing = None
    try:
        if logo_path and logo_path.lower().endswith(".svg"):
            drawing = svg2rlg(logo_path)
        else:
            import requests

            response = requests.get(PINES_LOGO_URL, timeout=5)
            response.raise_for_status()
            drawing = svg2rlg(BytesIO(response.content))
    except Exception:
        return None

    if not drawing:
        return None

    scale = min(width / float(drawing.width or width), height / float(drawing.height or height))
    scaled = Drawing(width, height)
    drawing.scale(scale, scale)
    scaled.add(drawing)
    return scaled


def _guidance_for_category(category: str, development_library: Mapping[str, Mapping[str, str]]) -> str:
    library = development_library.get(category, {})
    practice = library.get("practice_focus", "")
    at_home = library.get("at_home_development", "")
    if practice and at_home:
        return f"{_safe(practice)}<br/><font color='{TEXT_MUTED}'>At home: {_safe(at_home)}</font>"
    return _safe(practice or at_home or "Keep training this area with focused, game-like repetitions.")


def _section_development_table(
    categories: list[str],
    scores: Mapping[str, Any],
    development_library: Mapping[str, Mapping[str, str]],
    styles,
):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    data = [[
        Paragraph("Category", styles["TableHeader"]),
        Paragraph("Score", styles["TableHeader"]),
        Paragraph("How to Work on This", styles["TableHeader"]),
    ]]
    for category in categories:
        data.append([
            Paragraph(_safe(category), styles["SmallBold"]),
            Paragraph(_safe(_score_text(scores.get(category))), styles["Score"]),
            Paragraph(_guidance_for_category(category, development_library), styles["Small"]),
        ])

    table = Table(data, colWidths=[116, 40, 368], hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PINES_LIGHT)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(PINES_GREEN)),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def player_development_pdf_response(
    *,
    session_name: str,
    registration_name: str,
    summary: Mapping[str, Any],
    categories: Mapping[str, list[str]],
    development_library: Mapping[str, Mapping[str, str]],
) -> Response:
    """Build a polished player development PDF with logo, section scores, and IDP content."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise HTTPException(status_code=500, detail="PDF export requires reportlab.") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=44,
        leftMargin=44,
        topMargin=42,
        bottomMargin=42,
    )

    base = getSampleStyleSheet()
    styles: Dict[str, ParagraphStyle] = {
        "Title": ParagraphStyle(
            "PinesTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor(PINES_GREEN),
            spaceAfter=4,
        ),
        "Subtitle": ParagraphStyle(
            "PinesSubtitle",
            parent=base["BodyText"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor(TEXT_MUTED),
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "Wordmark": ParagraphStyle(
            "PinesWordmark",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=colors.HexColor(PINES_GREEN),
            alignment=TA_CENTER,
        ),
        "Section": ParagraphStyle(
            "PinesSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.white,
            backColor=colors.HexColor(PINES_GREEN),
            borderPadding=(5, 8, 5, 8),
            spaceBefore=10,
            spaceAfter=0,
        ),
        "Body": ParagraphStyle(
            "PinesBody",
            parent=base["BodyText"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor(TEXT_DARK),
            spaceAfter=4,
        ),
        "Small": ParagraphStyle(
            "PinesSmall",
            parent=base["BodyText"],
            fontSize=7.6,
            leading=9,
            textColor=colors.HexColor(TEXT_DARK),
        ),
        "SmallBold": ParagraphStyle(
            "PinesSmallBold",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=9,
            textColor=colors.HexColor(TEXT_DARK),
        ),
        "TableHeader": ParagraphStyle(
            "PinesTableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=9,
            textColor=colors.HexColor(PINES_GREEN),
        ),
        "Score": ParagraphStyle(
            "PinesScore",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.2,
            leading=9.5,
            textColor=colors.HexColor(TEXT_DARK),
            alignment=TA_CENTER,
        ),
        "CalloutLabel": ParagraphStyle(
            "PinesCalloutLabel",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=9.5,
            textColor=colors.HexColor(PINES_GREEN),
        ),
        "CalloutValue": ParagraphStyle(
            "PinesCalloutValue",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            textColor=colors.HexColor(TEXT_DARK),
        ),
    }

    story = []

    logo = _logo_flowable(width=1.15 * inch, height=0.75 * inch)
    title_block = [
        Paragraph("Pines Player Development Report", styles["Title"]),
        Paragraph(_safe(registration_name or session_name), styles["Subtitle"]),
    ]
    if logo:
        header = Table([[logo, title_block]], colWidths=[1.3 * inch, REPORT_WIDTH - 1.3 * inch], hAlign="LEFT")
    else:
        wordmark = Paragraph("POSA Sports<br/><font color='#2f6130'>PINES</font>", styles["Wordmark"])
        header = Table([[wordmark, title_block]], colWidths=[1.3 * inch, REPORT_WIDTH - 1.3 * inch], hAlign="LEFT")
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header)

    player_name = summary.get("playerName", "")
    player_info = [summary.get("ageGroup", ""), summary.get("position", "")]
    player_info = " | ".join([str(item) for item in player_info if item])
    evaluator_names = ", ".join(summary.get("evaluatorNames", [])) or "Not specified"
    scores = summary.get("categoryScores", {})
    section_averages = summary.get("sectionAverages", {})

    overview_data = [
        [
            Paragraph("Player", styles["CalloutLabel"]),
            Paragraph("Age / Position", styles["CalloutLabel"]),
            Paragraph("Weighted Score", styles["CalloutLabel"]),
        ],
        [
            Paragraph(_safe(player_name), styles["CalloutValue"]),
            Paragraph(_safe(player_info or "-"), styles["CalloutValue"]),
            Paragraph(_safe(_score_text(summary.get("weightedScore"))), styles["CalloutValue"]),
        ],
        [
            Paragraph("Evaluators", styles["CalloutLabel"]),
            Paragraph(_safe(evaluator_names), styles["Body"]),
            Paragraph("", styles["Body"]),
        ],
    ]
    overview = Table(overview_data, colWidths=[220, 190, 114], hAlign="LEFT")
    overview.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PINES_LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(PINES_BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor(PINES_BORDER)),
        ("SPAN", (1, 2), (2, 2)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(overview)
    story.append(Spacer(1, 8))

    for section, section_categories in categories.items():
        section_title = section
        if section in section_averages:
            section_title = f"{section} - Avg {_score_text(section_averages[section])}"
        story.append(Paragraph(_safe(section_title), styles["Section"]))
        story.append(_section_development_table(section_categories, scores, development_library, styles))

    story.append(Paragraph("Key Strengths", styles["Section"]))
    strengths = summary.get("topStrengths", []) or []
    if strengths:
        for category, score in strengths:
            story.append(Paragraph(f"<b>{_safe(category)}</b>: {_safe(_score_text(score))}", styles["Body"]))
    else:
        story.append(Paragraph("No strengths entered yet.", styles["Body"]))

    story.append(Paragraph("Key Things to Work On", styles["Section"]))
    priorities = summary.get("developmentPriorities", []) or []
    if priorities:
        for index, (category, score) in enumerate(priorities[:5], start=1):
            library = development_library.get(category, {})
            priority_lines = [
                Paragraph(f"<b>{index}. {_safe(category)}</b> - Score {_safe(_score_text(score))}", styles["Body"]),
                Paragraph(f"<b>Why it matters:</b> {_safe(library.get('what_improvement_looks_like', ''))}", styles["Body"]),
                Paragraph(f"<b>Training focus:</b> {_safe(library.get('practice_focus', ''))}", styles["Body"]),
                Paragraph(f"<b>At-home work:</b> {_safe(library.get('at_home_development', ''))}", styles["Body"]),
                Spacer(1, 4),
            ]
            story.extend(priority_lines)
    else:
        story.append(Paragraph("No development priorities available yet.", styles["Body"]))

    story.append(Paragraph("Evaluator Notes", styles["Section"]))
    notes = summary.get("notes", []) or []
    if notes:
        for note in notes:
            story.append(Paragraph(f"- {_safe(note)}", styles["Body"]))
    else:
        story.append(Paragraph("No notes entered yet.", styles["Body"]))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor(PINES_BORDER))
        canvas.line(doc_obj.leftMargin, 28, letter[0] - doc_obj.rightMargin, 28)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(TEXT_MUTED))
        canvas.drawString(doc_obj.leftMargin, 16, "POSA Sports - Pines Player Development")
        canvas.drawRightString(letter[0] - doc_obj.rightMargin, 16, f"Page {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    buffer.close()

    safe_name = str(player_name or "player").lower().replace(" ", "-").replace("/", "-")
    filename = f"{safe_name}-development-report.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
