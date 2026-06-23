"""Routes for tryout/player evaluations and development-plan exports."""
from io import BytesIO
from typing import Any, Dict, List, Optional
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.evaluation_library import (
    CATEGORIES,
    CATEGORY_FIELD_MAP,
    DEVELOPMENT_LIBRARY,
    all_category_names,
    build_ai_prompt,
    summarize_rows,
)
from app.models import Player, Registration
from app.models_evaluations import EvaluationScore, EvaluationSession, PlayerEvaluation

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _age_group_from_birth_year(birth_year: Optional[int]) -> str:
    if not birth_year:
        return ""
    age = 2026 - int(birth_year)
    return f"U{age}" if age > 0 else ""


def _year_from_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"20\d{2}", str(value))
    return match.group(0) if match else None


def _division_from_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"\bU\s?(\d{1,2})\b", str(value), re.IGNORECASE)
    return f"U{match.group(1)}" if match else None


def _get_registration_meta(registration_id: str) -> Dict[str, str]:
    from app.services.sportsengine import (
        get_all_registrations,
        extract_season_from_registration_name,
        extract_sport_from_registration_name,
    )

    forms = get_all_registrations()
    selected = next((form for form in forms if str(form.get("id")) == str(registration_id)), None)
    if not selected:
        raise HTTPException(status_code=404, detail="SportsEngine registration not found")

    name = selected.get("name") or f"Registration {registration_id}"
    return {
        "id": str(registration_id),
        "name": name,
        "sport": extract_sport_from_registration_name(name),
        "season_name": extract_season_from_registration_name(name),
        "division_name": _division_from_text(name) or "",
    }


def _serialize_session(session: EvaluationSession, db: Session) -> Dict[str, Any]:
    player_count = (
        db.query(func.count(func.distinct(PlayerEvaluation.player_name)))
        .filter(PlayerEvaluation.session_id == session.id)
        .scalar()
        or 0
    )
    evaluation_count = (
        db.query(func.count(PlayerEvaluation.id))
        .filter(PlayerEvaluation.session_id == session.id)
        .scalar()
        or 0
    )
    return {
        "id": session.id,
        "name": session.name,
        "sport": session.sport,
        "seasonName": session.season_name,
        "divisionName": session.division_name,
        "sportsengineRegistrationId": session.sportsengine_registration_id,
        "sportsengineRegistrationName": session.sportsengine_registration_name,
        "playerCount": player_count,
        "evaluationCount": evaluation_count,
        "createdAt": session.created_at.isoformat() if session.created_at else None,
    }


def _rows_for_player(session_id: int, player_name: str, db: Session) -> List[Dict[str, Any]]:
    evaluations = (
        db.query(PlayerEvaluation)
        .filter(PlayerEvaluation.session_id == session_id)
        .filter(func.lower(PlayerEvaluation.player_name) == player_name.lower())
        .all()
    )
    rows: List[Dict[str, Any]] = []
    for evaluation in evaluations:
        row: Dict[str, Any] = {
            "playerId": evaluation.player_id,
            "playerName": evaluation.player_name,
            "ageGroup": evaluation.age_group or _age_group_from_birth_year(evaluation.birth_year),
            "position": evaluation.primary_position or "",
            "Future Potential": evaluation.future_potential,
            "Biggest Strength": evaluation.biggest_strength,
            "Biggest Growth Area": evaluation.biggest_growth_area,
            "Notes": evaluation.notes,
        }
        for score in evaluation.scores:
            row[score.category] = score.score
        rows.append(row)
    return rows


def _summaries_for_session(session: EvaluationSession, db: Session) -> List[Dict[str, Any]]:
    names = [
        row[0]
        for row in db.query(PlayerEvaluation.player_name)
        .filter(PlayerEvaluation.session_id == session.id)
        .group_by(PlayerEvaluation.player_name)
        .order_by(PlayerEvaluation.player_name)
        .all()
    ]
    summaries: List[Dict[str, Any]] = []
    for name in names:
        rows = _rows_for_player(session.id, name, db)
        if rows:
            summaries.append(summarize_rows(rows))
    return summaries


def _pdf_response(title: str, lines: List[str]) -> Response:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except Exception as exc:
        raise HTTPException(status_code=500, detail="PDF export requires reportlab.") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for line in lines:
        safe_line = str(line).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if not safe_line.strip():
            story.append(Spacer(1, 8))
        elif safe_line.endswith(":") or safe_line.startswith(("1.", "2.", "3.", "4.", "5.")):
            story.append(Paragraph(f"<b>{safe_line}</b>", styles["Heading3"]))
        else:
            story.append(Paragraph(safe_line, styles["BodyText"]))
            story.append(Spacer(1, 4))
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    filename = title.lower().replace(" ", "-").replace("/", "-") + ".pdf"
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/categories")
def get_categories():
    return {"categories": CATEGORIES, "categoryFieldMap": CATEGORY_FIELD_MAP, "developmentLibrary": DEVELOPMENT_LIBRARY}


@router.get("/sportsengine/registrations")
def get_tryout_registrations():
    """List SportsEngine registrations for the evaluation import picker."""
    from app.services.sportsengine import is_configured, get_all_registrations, extract_sport_from_registration_name

    if not is_configured():
        return JSONResponse(status_code=400, content={"status": "error", "detail": "SportsEngine not configured"})

    forms = get_all_registrations()
    registrations = []
    for form in forms:
        name = form.get("name") or ""
        sport = extract_sport_from_registration_name(name)
        if sport == "Unknown" and not any(word in name.lower() for word in ["tryout", "soccer", "pines"]):
            continue
        registrations.append({"id": str(form.get("id")), "name": name, "status": form.get("status"), "sport": sport})
    return {"status": "success", "registrations": registrations}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    sessions = db.query(EvaluationSession).order_by(EvaluationSession.created_at.desc()).all()
    return {"sessions": [_serialize_session(session, db) for session in sessions]}


@router.post("/sessions")
async def create_session(request: Request, db: Session = Depends(get_db)):
    """Create a session from exactly one selected SportsEngine registration and sync only that registration."""
    data = await request.json()
    registration_id = str(data.get("sportsengine_registration_id") or data.get("registration_id") or "").strip()
    if not registration_id:
        raise HTTPException(status_code=400, detail="A SportsEngine registration must be selected for tryout import.")

    from app.services.sportsengine import is_configured, sync_registration

    if not is_configured():
        raise HTTPException(status_code=400, detail="SportsEngine not configured")

    meta = _get_registration_meta(registration_id)
    session_name = data.get("name") or meta["name"]

    session = (
        db.query(EvaluationSession)
        .filter(EvaluationSession.sportsengine_registration_id == registration_id)
        .filter(EvaluationSession.name == session_name)
        .first()
    )
    if session:
        if not session.division_name:
            session.division_name = meta.get("division_name")
    else:
        session = EvaluationSession(
            name=session_name,
            sport=meta["sport"],
            season_name=meta["season_name"],
            division_name=data.get("division_name") or meta.get("division_name"),
            sportsengine_registration_id=registration_id,
            sportsengine_registration_name=meta["name"],
        )
        db.add(session)
        db.flush()

    sync_results = sync_registration(registration_id, db)
    db.commit()

    return {"status": "success", "session": _serialize_session(session, db), "syncResults": sync_results}


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(EvaluationSession).filter(EvaluationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Evaluation session not found")
    return {"session": _serialize_session(session, db), "summaries": _summaries_for_session(session, db)}


@router.get("/sessions/{session_id}/players")
def list_session_players(session_id: int, db: Session = Depends(get_db)):
    session = db.query(EvaluationSession).filter(EvaluationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Evaluation session not found")

    reg_name = session.sportsengine_registration_name or ""
    year = _year_from_text(session.season_name) or _year_from_text(reg_name)
    division = session.division_name or _division_from_text(reg_name)

    base = db.query(Player, Registration).join(Registration, Registration.player_id == Player.id)

    exact_query = base.filter(Registration.program == reg_name)
    if session.sport and session.sport != "Unknown":
        exact_query = exact_query.filter(func.lower(Registration.sport) == session.sport.lower())

    fallback_query = base
    if session.sport and session.sport != "Unknown":
        fallback_query = fallback_query.filter(func.lower(Registration.sport) == session.sport.lower())
    if year:
        fallback_query = fallback_query.filter(Registration.season.contains(year))
    if division:
        fallback_query = fallback_query.filter(or_(Registration.division == division, Registration.division.ilike(f"%{division}%")))

    rows = list(exact_query.all())
    existing_ids = {player.id for player, _ in rows}
    for player, registration in fallback_query.all():
        if player.id not in existing_ids:
            rows.append((player, registration))
            existing_ids.add(player.id)

    rows.sort(key=lambda item: (item[0].full_name or "").lower())

    players = []
    for player, registration in rows:
        players.append({
            "playerId": player.id,
            "playerName": player.full_name,
            "birthYear": player.birth_year,
            "ageGroup": _age_group_from_birth_year(player.birth_year),
            "division": registration.division,
            "jerseyNumber": player.jersey_number,
            "parentEmail": player.parent_email,
        })
    return {"players": players, "count": len(players), "match": {"year": year, "division": division, "sport": session.sport}}


@router.post("/sessions/{session_id}/evaluations")
async def save_evaluation(session_id: int, request: Request, db: Session = Depends(get_db)):
    session = db.query(EvaluationSession).filter(EvaluationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Evaluation session not found")

    data = await request.json()
    player_name = (data.get("player_name") or data.get("playerName") or "").strip()
    evaluator_name = (data.get("evaluator_name") or data.get("evaluatorName") or "").strip()
    if not player_name:
        raise HTTPException(status_code=400, detail="player_name is required")
    if not evaluator_name:
        raise HTTPException(status_code=400, detail="evaluator_name is required")

    player_id = data.get("player_id") or data.get("playerId")
    player = db.query(Player).filter(Player.id == player_id).first() if player_id else None

    evaluation = PlayerEvaluation(
        session_id=session.id,
        player_id=player.id if player else None,
        player_name=player.full_name if player else player_name,
        birth_year=player.birth_year if player else data.get("birth_year") or data.get("birthYear"),
        age_group=data.get("age_group") or data.get("ageGroup"),
        primary_position=data.get("primary_position") or data.get("primaryPosition"),
        evaluator_name=evaluator_name,
        future_potential=data.get("future_potential") or data.get("futurePotential"),
        biggest_strength=data.get("biggest_strength") or data.get("biggestStrength"),
        biggest_growth_area=data.get("biggest_growth_area") or data.get("biggestGrowthArea"),
        notes=data.get("notes"),
    )
    db.add(evaluation)
    db.flush()

    scores = data.get("scores") or {}
    for category in all_category_names():
        value = scores.get(category)
        if value is None:
            value = data.get(CATEGORY_FIELD_MAP[category])
        if value is None or value == "":
            continue
        try:
            score_value = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid score for {category}")
        if score_value < 1 or score_value > 5:
            raise HTTPException(status_code=400, detail=f"Score for {category} must be between 1 and 5")
        db.add(EvaluationScore(evaluation_id=evaluation.id, category=category, score=score_value))

    db.commit()
    return {"status": "success", "evaluationId": evaluation.id}


@router.get("/sessions/{session_id}/summary")
def session_summary(session_id: int, db: Session = Depends(get_db)):
    session = db.query(EvaluationSession).filter(EvaluationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Evaluation session not found")
    return {"session": _serialize_session(session, db), "summaries": _summaries_for_session(session, db)}


@router.get("/sessions/{session_id}/players/{player_name}/prompt")
def player_prompt(session_id: int, player_name: str, db: Session = Depends(get_db)):
    rows = _rows_for_player(session_id, player_name, db)
    if not rows:
        raise HTTPException(status_code=404, detail="No evaluations found for player")
    summary = summarize_rows(rows)
    return {"summary": summary, "prompt": build_ai_prompt(summary)}


@router.get("/sessions/{session_id}/players/{player_name}/pdf")
def player_pdf(session_id: int, player_name: str, db: Session = Depends(get_db)):
    rows = _rows_for_player(session_id, player_name, db)
    if not rows:
        raise HTTPException(status_code=404, detail="No evaluations found for player")
    summary = summarize_rows(rows)
    lines = [
        f"Player: {summary.get('playerName', player_name)}",
        f"Age Group: {summary.get('ageGroup', '')}",
        f"Primary Position(s): {summary.get('position', '')}",
        "",
        "Player Snapshot:",
        f"Weighted development score: {summary.get('weightedScore', '')}",
        "",
        "Key Strengths:",
    ]
    for category, score in summary.get("topStrengths", []):
        lines.append(f"{category}: {score}")
    lines.extend(["", "Top Development Priorities:"])
    for category, score in summary.get("developmentPriorities", []):
        library = DEVELOPMENT_LIBRARY.get(category, {})
        lines.extend([
            f"{category}: {score}",
            f"What Improvement Looks Like: {library.get('what_improvement_looks_like', '')}",
            f"Practice Focus: {library.get('practice_focus', '')}",
            f"At-Home Development: {library.get('at_home_development', '')}",
            "",
        ])
    lines.extend(["Evaluator Notes:", "; ".join(summary.get("notes", [])) or "No notes entered."])
    return _pdf_response(f"{summary.get('playerName', player_name)} Development Plan", lines)


@router.get("/sessions/{session_id}/pdf")
def session_pdf(session_id: int, db: Session = Depends(get_db)):
    session = db.query(EvaluationSession).filter(EvaluationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Evaluation session not found")
    summaries = _summaries_for_session(session, db)
    lines = [
        f"Session: {session.name}",
        f"Registration: {session.sportsengine_registration_name}",
        f"Sport: {session.sport or ''}",
        f"Season: {session.season_name or ''}",
        "",
        "Player Summaries:",
    ]
    for summary in summaries:
        priorities = ", ".join(category for category, _ in summary.get("developmentPriorities", []))
        strengths = ", ".join(category for category, _ in summary.get("topStrengths", []))
        lines.extend([
            f"{summary.get('playerName')}",
            f"Weighted Score: {summary.get('weightedScore', '')}",
            f"Strengths: {strengths}",
            f"Development Priorities: {priorities}",
            "",
        ])
    return _pdf_response(f"{session.name} Evaluation Summary", lines)
