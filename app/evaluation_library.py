"""
Shared player-evaluation categories, scoring helpers, and development text.
"""
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional
import re

CATEGORIES: Dict[str, List[str]] = {
    "Technical/Skills": ["Shooting", "Receiving & Turning", "Passing", "Balls Out of Air", "Dribbling", "Tackling"],
    "Tactical/Decision Making": ["Support Play", "Attacking", "Off Ball Movement", "Defending", "Vision", "Speed of Play"],
    "Physical": ["Speed", "Agility", "Balance", "Power", "Endurance"],
    "Psychological": ["Attitude", "Coachability", "Body Language", "Communication", "Sportsmanship", "Leadership"],
}

CATEGORY_FIELD_MAP = {
    "Shooting": "shooting",
    "Receiving & Turning": "receiving_turning",
    "Passing": "passing",
    "Balls Out of Air": "balls_out_of_air",
    "Dribbling": "dribbling",
    "Tackling": "tackling",
    "Support Play": "support_play",
    "Attacking": "attacking",
    "Off Ball Movement": "off_ball_movement",
    "Defending": "defending",
    "Vision": "vision",
    "Speed of Play": "speed_of_play",
    "Speed": "speed",
    "Agility": "agility",
    "Balance": "balance",
    "Power": "power",
    "Endurance": "endurance",
    "Attitude": "attitude",
    "Coachability": "coachability",
    "Body Language": "body_language",
    "Communication": "communication",
    "Sportsmanship": "sportsmanship",
    "Leadership": "leadership",
}

WEIGHTS = {
    "Technical/Skills": 0.35,
    "Tactical/Decision Making": 0.35,
    "Physical": 0.10,
    "Psychological": 0.20,
}

SCORE_LABELS = {1: "Beginning", 2: "Developing", 3: "Competent", 4: "Advanced", 5: "Elite"}

_DEVELOPMENT_DEFAULTS = {
    "Shooting": ("A stronger finisher strikes the ball with consistent technique, chooses appropriate moments to shoot, and can place shots with accuracy and composure.", "Focus on clean contact, accuracy before power, shooting with both feet, and creating a shooting window with the first touch.", "Use a wall, goal, or target area to practice controlled finishing. Start with clean contact and placement, then add movement, angle changes, and weak-foot repetitions."),
    "Receiving & Turning": ("Strong players receive the ball with purpose, use their first touch to create space, and quickly transition into their next action.", "Open your body before receiving, scan before the ball arrives, and use the first touch to set up the next pass, dribble, or shot.", "Practice wall passing with both feet, receiving across the body and directing the first touch into space before playing the ball again."),
    "Passing": ("Advanced passers connect with teammates using proper pace, timing, and accuracy while recognizing the best option early.", "Pass with purpose, improve the weight of each pass, look forward before playing backward, and support after passing.", "Complete wall-passing sets with both feet. Include one-touch, two-touch, and target passing while increasing speed without sacrificing accuracy."),
    "Balls Out of Air": ("Players become comfortable receiving aerial balls with multiple surfaces and can bring the ball under control quickly while preparing for the next action.", "Stay balanced, cushion the ball into space, judge the flight early, and prepare the next touch before the ball arrives.", "Use juggling, self-toss receiving, and controlled first-touch exercises with feet, thighs, and chest."),
    "Dribbling": ("Effective dribblers maintain close control, change direction confidently, and use dribbling to create advantages rather than simply keeping possession.", "Keep the ball close in tight spaces, change speed and direction, use both feet, and attack space with confidence.", "Use ball-mastery routines, cone moves, and change-of-direction patterns with both feet."),
    "Tackling": ("Strong defenders win possession cleanly while staying balanced and disciplined. They choose the right moments to challenge.", "Stay patient, keep a balanced stance, avoid diving in, and time challenges when the attacker exposes the ball.", "Work on defensive footwork, quick recovery steps, and watch defenders to study timing and body position."),
    "Support Play": ("Players consistently provide useful passing options and understand how movement creates opportunities for teammates.", "Move after every pass, create passing angles, stay connected to teammates, and offer support ahead, beside, or behind the ball.", "Watch a match and follow one player off the ball. Notice how they adjust position to support the player in possession."),
    "Attacking": ("Players recognize opportunities to advance play, create chances, and influence attacking moments with confidence and purpose.", "Play forward when possible, attack space aggressively, combine with teammates, and recognize moments to penetrate.", "Study attacking players in your position and identify how they create space before receiving."),
    "Off Ball Movement": ("Advanced players move constantly with purpose to create space, lose defenders, and support teammates even when not directly involved.", "Move with purpose, create separation, time runs well, and anticipate where play is going next.", "Watch one player for several minutes without following the ball. Track their movement and timing."),
    "Defending": ("Strong defenders understand positioning, pressure, cover, and balance. They influence play even when they are not winning the ball.", "Stay goal-side when appropriate, recognize defensive responsibilities, communicate, and recover quickly after being beaten.", "Analyze defensive moments in matches and identify how players position themselves before the ball arrives."),
    "Vision": ("Players regularly scan the field, recognize opportunities early, and make decisions before receiving the ball.", "Check shoulders frequently, identify options before receiving, and look for opportunities to break lines.", "Watch midfielders or players in your position and count how often they scan before receiving."),
    "Speed of Play": ("Players process information quickly and execute decisions efficiently, allowing them to play effectively under pressure.", "Think ahead, reduce unnecessary touches, make decisions earlier, and move the ball before pressure arrives.", "Use one-touch and two-touch wall passing while maintaining accuracy and rhythm."),
    "Speed": ("Players improve acceleration, movement efficiency, and the ability to reach top speed quickly during game actions.", "Focus on quick first steps, sprint mechanics, reaction speed, and explosive transitions.", "Perform short sprint repetitions with full recovery, focusing on technique and fast acceleration."),
    "Agility": ("Players change direction efficiently while maintaining balance, speed, and control.", "Stay low when changing direction, control body movement, react quickly, and recover balance after turns.", "Use ladder work, cone patterns, and short change-of-direction exercises."),
    "Balance": ("Players remain stable under pressure and maintain control while turning, shielding, landing, and competing physically.", "Maintain body control, stay strong through contact, and improve stability while moving with the ball.", "Use single-leg balance work, controlled turns, and bodyweight stability exercises."),
    "Power": ("Players generate force efficiently for sprinting, jumping, striking, and physical challenges.", "Focus on explosive movement, strong body positioning, and efficient use of strength.", "Use age-appropriate jumping, sprinting, and bodyweight strength exercises."),
    "Endurance": ("Players maintain effort, concentration, and technical quality throughout the match.", "Keep a consistent work rate, recover between actions, and maintain focus when fatigued.", "Use regular aerobic activity and age-appropriate interval conditioning."),
    "Attitude": ("Players approach training and competition with enthusiasm, effort, and a positive mindset regardless of circumstances.", "Bring energy to training, embrace challenges, and respond positively after mistakes.", "Reflect after training by writing one thing that went well and one thing to improve next time."),
    "Coachability": ("Players actively seek feedback and apply coaching points quickly and consistently.", "Listen carefully, apply corrections immediately, and ask questions when needed.", "Keep a simple training journal with coaching points and one action step for the next session."),
    "Body Language": ("Players display confidence, resilience, and composure regardless of game situations.", "Respond positively to mistakes, stay engaged when challenged, and show confidence through actions.", "Reflect on emotional responses during games and identify positive ways to reset after mistakes."),
    "Communication": ("Players consistently provide useful information that helps teammates make better decisions.", "Communicate early, use clear and positive language, and support teammates verbally.", "Choose one communication goal for each practice, such as calling for the ball or helping a teammate organize."),
    "Sportsmanship": ("Players consistently demonstrate respect for teammates, opponents, coaches, officials, and the game itself.", "Compete hard while remaining respectful and represent the club positively.", "Reflect on examples of strong sportsmanship from games or professional players."),
    "Leadership": ("Players positively influence teammates through actions, communication, and example.", "Encourage teammates, take responsibility, and lead through effort and behavior.", "Look for one way to support a teammate at each practice or game."),
}

DEVELOPMENT_LIBRARY: Dict[str, Dict[str, str]] = {
    category: {
        "what_improvement_looks_like": values[0],
        "practice_focus": values[1],
        "at_home_development": values[2],
    }
    for category, values in _DEVELOPMENT_DEFAULTS.items()
}


def all_category_names() -> List[str]:
    return [category for section in CATEGORIES.values() for category in section]


def to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def unique_values(values: Iterable[Any]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def unique_evaluator_names(values: Iterable[Any]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        for part in re.split(r"[,;\n]+", str(value or "")):
            clean = part.strip()
            if not clean or clean.lower() == "evaluator":
                continue
            key = re.sub(r"\s+", " ", clean).lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(clean)
    return result


def summarize_rows(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    if not rows:
        raise ValueError("No evaluations supplied")

    first = rows[0]
    averaged: Dict[str, float] = {}
    for category in all_category_names() + ["Future Potential"]:
        scores = [to_float(row.get(category)) for row in rows]
        scores = [score for score in scores if score is not None]
        if scores:
            averaged[category] = round(mean(scores), 2)

    section_averages: Dict[str, float] = {}
    for section, categories in CATEGORIES.items():
        scores = [averaged[category] for category in categories if category in averaged]
        if scores:
            section_averages[section] = round(mean(scores), 2)

    weighted_score = round(
        sum(section_averages.get(section, 0) * weight for section, weight in WEIGHTS.items()),
        2,
    )

    ranked_low = sorted(
        [(category, averaged[category]) for category in all_category_names() if category in averaged],
        key=lambda item: item[1],
    )
    ranked_high = sorted(
        [(category, averaged[category]) for category in all_category_names() if category in averaged],
        key=lambda item: item[1],
        reverse=True,
    )

    return {
        "playerId": first.get("playerId"),
        "playerName": first.get("playerName") or "",
        "ageGroup": first.get("ageGroup") or "",
        "position": first.get("position") or "",
        "categoryScores": averaged,
        "sectionAverages": section_averages,
        "weightedScore": weighted_score,
        "topStrengths": ranked_high[:3],
        "developmentPriorities": ranked_low[:3],
        "evaluatorNames": unique_evaluator_names(row.get("evaluatorName") or row.get("Evaluator Name") for row in rows),
        "evaluatorStrengths": unique_values(row.get("Biggest Strength", "") for row in rows),
        "evaluatorGrowthAreas": unique_values(row.get("Biggest Growth Area", "") for row in rows),
        "notes": unique_values(row.get("Notes", "") for row in rows),
    }


def build_ai_prompt(summary: Mapping[str, Any]) -> str:
    scores = summary.get("categoryScores", {})
    lines = [
        "Create a parent-friendly soccer Individual Development Plan.",
        "",
        "Tone: Positive, encouraging, honest, development-focused, specific, and not overly score-focused.",
        "",
        f"Player Name: {summary.get('playerName', '')}",
        f"Age Group: {summary.get('ageGroup', '')}",
        f"Primary Position(s): {summary.get('position', '')}",
        "Evaluators: " + ", ".join(summary.get("evaluatorNames", [])),
        "",
    ]

    for section, categories in CATEGORIES.items():
        lines.append(f"{section} Scores:")
        for category in categories:
            lines.append(f"{category}: {scores.get(category, '')}")
        lines.append("")

    lines.extend([
        f"Future Potential: {scores.get('Future Potential', '')}",
        "Top Strengths: " + ", ".join(category for category, _ in summary.get("topStrengths", [])),
        "Development Priorities: " + ", ".join(category for category, _ in summary.get("developmentPriorities", [])),
        "",
        "Development Library for Priorities:",
    ])

    for category, score in summary.get("developmentPriorities", []):
        library = DEVELOPMENT_LIBRARY.get(category, {})
        lines.extend([
            "",
            f"{category} ({score}):",
            f"What Improvement Looks Like: {library.get('what_improvement_looks_like', '')}",
            f"Practice Focus: {library.get('practice_focus', '')}",
            f"At-Home Development: {library.get('at_home_development', '')}",
        ])

    lines.extend([
        "",
        "Evaluator Strength Comments: " + "; ".join(summary.get("evaluatorStrengths", [])),
        "Evaluator Growth Comments: " + "; ".join(summary.get("evaluatorGrowthAreas", [])),
        "Evaluator Notes: " + "; ".join(summary.get("notes", [])),
        "",
        "Report Structure:",
        "1. Player Snapshot",
        "2. Key Strengths",
        "3. Top 3 Development Priorities, each with Current Assessment, What Improvement Looks Like, Practice Focus, and At-Home Development",
        "4. 30-Day Development Goal",
        "5. Coach Notes",
    ])
    return "\n".join(lines)
