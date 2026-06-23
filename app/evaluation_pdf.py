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
    for filename in ("pines-logo.png", "pines_logo.png", "logo.png", "pines-logo.jpg", "pines_logo.jpg", "logo.jpg"):
        candidate = static_dir / filename
        if candidate.exists():
            return str(candidate)
    return None


def _paragraph(text: Any, style):
    from reportlab.platypus import Paragraph

    return Paragraph(_safe(text), style)


def _score_table(section: str, categories: list[str], scores: Mapping[str, Any], styles):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    data = [[Paragraph("Category", styles["TableHeader"]), Paragraph("Score", styles["TableHeader"]), Paragraph("Category", styles["TableHeader"]), Paragraph("Score", styles["TableHeader"])]]
    pairs = [(category, _score_text(scores.get(category))) for category in categories]
    for index in range(0, len(pairs), 2):
        left = pairs[index]
        right = pairs[index + 1] if index + 1 < len(pairs) else ("", "")
        data.append([
            Paragraph(_safe(left[0]), styles["Small"]),
            Paragraph(_safe(left[1]), styles["Score"]),
            Paragraph(_safe(right[0]), styles["Small"]),
            Paragraph(_safe(right[1]), styles["Score"]),
        ])

    table = Table(data, colWidths=[180, 48, 180, 48], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PINES_LIGHT)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(PINES_GREEN)),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("ALIGN", (3, 1), (3, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
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
        from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
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
            spaceAfter=10,
        ),
        "Section": ParagraphStyle(
            "PinesSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.white,
            backColor=colors.HexColor(PINES_GREEN),
            borderPadding=(6, 8, 6, 8),
            spaceBefore=10,
            spaceAfter=7,
        ),
        "Body": ParagraphStyle(
            "PinesBody",
            parent=base["BodyText"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor(TEXT_DARK),
            spaceAfter=4,
        ),
        "Small": ParagraphStyle(
            "PinesSmall",
            parent=base["BodyText"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor(TEXT_DARK),
        ),
        "TableHeader": ParagraphStyle(
            "PinesTableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor(PINES_GREEN),
        ),
        "Score": ParagraphStyle(
            "PinesScore",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor(TEXT_DARK),
            alignment=TA_CENTER,
        ),
        "CalloutLabel": ParagraphStyle(
            "PinesCalloutLabel",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor(PINES_GREEN),
        ),
        "CalloutValue": ParagraphStyle(
            "PinesCalloutValue",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.HexColor(TEXT_DARK),
        ),
    }

    story = []

    logo_path = _find_logo_path()
    if logo_path:
        logo = Image(logo_path, width=0.9 * inch, height=0.9 * inch, kind="proportional")
        title_block = [
            Paragraph("Pines Player Development Report", styles["Title"]),
            Paragraph(_safe(registration_name or session_name), styles["Subtitle"]),
        ]
        header = Table([[logo, title_block]], colWidths=[0.95 * inch, 5.35 * inch], hAlign="LEFT")
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(header)
    else:
        story.append(Paragraph("Pines Player Development Report", styles["Title"]))
        story.append(Paragraph(_safe(registration_name or session_name), styles["Subtitle"]))

    player_name = summary.get("playerName", "")
    player_info = [summary.get("ageGroup", ""), summary.get("position", "")]
    player_info = " | ".join([str(item) for item in player_info if item])
    scores = summary.get("categoryScores", {})
    section_averages = summary.get("sectionAverages", {})

    overview_data = [
        [Paragraph("Player", styles["CalloutLabel"]), Paragraph("Age / Position", styles["CalloutLabel"]), Paragraph("Weighted Score", styles["CalloutLabel"])],
        [Paragraph(_safe(player_name), styles["CalloutValue"]), Paragraph(_safe(player_info or "-"), styles["CalloutValue"]), Paragraph(_safe(_score_text(summary.get("weightedScore"))), styles["CalloutValue"])],
    ]
    overview = Table(overview_data, colWidths=[220, 175, 95], hAlign="LEFT")
    overview.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PINES_LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(PINES_BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor(PINES_BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(overview)
    story.append(Spacer(1, 10))

    for section, section_categories in categories.items():
        section_title = section
        if section in section_averages:
            section_title = f"{section} - Avg {_score_text(section_averages[section])}"
        story.append(KeepTogether([
            Paragraph(_safe(section_title), styles["Section"]),
            _score_table(section, section_categories, scores, styles),
        ]))

    story.append(Paragraph("Key Strengths", styles["Section"]))
    strengths = summary.get("topStrengths", []) or []
    if strengths:
        for category, score in strengths:
            story.append(Paragraph(f"<b>{_safe(category)}</b>: {_safe(_score_text(score))}", styles["Body"]))
    else:
        story.append(Paragraph("No strengths entered yet.", styles["Body"]))

    story.append(Paragraph("Top Development Priorities", styles["Section"]))
    priorities = summary.get("developmentPriorities", []) or []
    if priorities:
        for category, score in priorities:
            library = development_library.get(category, {})
            priority_lines = [
                Paragraph(f"<b>{_safe(category)}</b> - Score {_safe(_score_text(score))}", styles["Body"]),
                Paragraph(f"<b>What improvement looks like:</b> {_safe(library.get('what_improvement_looks_like', ''))}", styles["Body"]),
                Paragraph(f"<b>Practice focus:</b> {_safe(library.get('practice_focus', ''))}", styles["Body"]),
                Paragraph(f"<b>At-home development:</b> {_safe(library.get('at_home_development', ''))}", styles["Body"]),
                Spacer(1, 5),
            ]
            story.append(KeepTogether(priority_lines))
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
        canvas.drawString(doc_obj.leftMargin, 16, "Pines Athletics - Player Development")
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
