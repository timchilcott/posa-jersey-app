"""
Shared player-evaluation categories, scoring helpers, and development text.
"""
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional

CATEGORIES: Dict[str, List[str]] = {
    "Technical/Skills": [
        "Shooting",
        "Receiving & Turning",
        "Passing",
        "Balls Out of Air",
        "Dribbling",
        "Tackling",
    ],
    "Tactical/Decision Making": [
        "Support Play",
        "Attacking",
        "Off Ball Movement",
        "Defending",
        "Vision",
        "Speed of Play",
    ],
    "Physical": [
        "Speed",
        "Agility",
        "Balance",
        "Power",
        "Endurance",
    ],
    "Psychological": [
        "Attitude",
        "Coachability",
        "Body Language",
        "Communication",
        "Sportsmanship",
        "Leadership",
    ],
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

SCORE_LABELS = {
    1: "Beginning",
    2: "Developing",
    3: "Competent",
    4: "Advanced",
    5: "Elite",
}

DEVELOPMENT_LIBRARY = {
    "Shooting": {
        "what_improvement_looks_like": "A stronger finisher strikes the ball with consistent technique, chooses appropriate moments to shoot, and can place shots with accuracy and composure.",
        "practice_focus": "Focus on clean contact, accuracy before power, shooting with both feet, and creating a shooting window with the first touch.",
        "at_home_development": "Use a wall, goal, or target area to practice controlled finishing. Start with clean contact and placement, then add movement, angle changes, and weak-foot repetitions.",
    },
    "Receiving & Turning": {
        "what_improvement_looks_like": "Strong players receive the ball with purpose, use their first touch to create space, and quickly transition into their next action.",
        "practice_focus": "Open your body before receiving, scan before the ball arrives, and use the first touch to set up the next pass, dribble, or shot.",
        "at_home_development": "Practice wall passing with both feet, receiving across the body and directing the first touch into space before playing the ball again.",
    },
    "Passing": {
        "what_improvement_looks_like": "Advanced passers connect with teammates using proper pace, timing, and accuracy while recognizing the best option early.",
        "practice_focus": "Pass with purpose, improve the weight of each pass, look forward before playing backward, and support after passing.",
        "at_home_development": "Complete wall-passing sets with both feet. Include one-touch, two-touch, and target passing while increasing speed without sacrificing accuracy.",
    },
    "Balls Out of Air": {
        "what_improvement_looks_like": "Players become comfortable receiving aerial balls with multiple surfaces and can bring the ball under control quickly while preparing for the next action.",
        "practice_focus": "Stay balanced, cushion the ball into space, judge the flight early, and prepare the next touch before the ball arrives.",
        "at_home_development": "Use juggling, self-toss receiving, and controlled first-touch exercises with feet, thighs, and chest.",
    },
    "Dribbling": {
        "what_improvement_looks_like": "Effective dribblers maintain close control, change direction confidently, and use dribbling to create advantages rather than simply keeping possession.",
        "practice_focus": "Keep the ball close in tight spaces, change speed and direction, use both feet, and attack space with confidence.",
        "at_home_development": "Use ball-mastery routines, cone moves, and change-of-direction patterns with both feet.",
    },
    "Tackling": {
        "what_improvement_looks_like": "Strong defenders win possession cleanly while staying balanced and disciplined. They choose the right moments to challenge.",
        "practice_focus": "Stay patient, keep a balanced stance, avoid diving in, and time challenges when the attacker exposes the ball.",
        "at_home_development": "Work on defensive footwork, quick recovery steps, and watch defenders to study timing and body position.",
    },
    "Support Play": {
        "what_improvement_looks_like": "Players consistently provide useful passing options and understand how movement creates opportunities for teammates.",
        "practice_focus": "Move after every pass, create passing angles, stay connected to teammates, and offer support ahead, beside, or behind the ball.",
        "at_home_development": "Watch a match and follow one player off the ball. Notice how they adjust position to support the player in possession.",
    },
    "Attacking": {
        "what_improvement_looks_like": "Players recognize opportunities to advance play, create chances, and influence attacking moments with confidence and purpose.",
        "practice_focus": "Play forward when possible, attack space aggressively, combine with teammates, and recognize moments to penetrate.",
        "at_home_development": "Study attacking players in your position and identify how they create space before receiving.",
    },
    "Off Ball Movement": {
        "what_improvement_looks_like": "Advanced players move constantly with purpose to create space, lose defenders, and support teammates even when not directly involved.",
        "practice_focus": "Move with purpose, create separation, time runs well, and anticipate where play is going next.",
        "at_home_development": "Watch one player for several minutes without following the ball. Track their movement and timing.",
    },
    "Defending": {
        "what_improvement_looks_like": "Strong defenders understand positioning, pressure, cover, and balance. They influence play even when they are not winning the ball.",
        "practice_focus": "Stay goal-side when appropriate, recognize defensive responsibilities, communicate, and recover quickly after being beaten.",
        "at_home_development": "Analyze defensive moments in matches and identify how players position themselves before the ball arrives.",
    },
    "Vision": {
        "what_improvement_looks_like": "Players regularly scan the field, recognize opportunities early, and make decisions before receiving the ball.",
        "practice_focus": "Check shoulders frequently, identify options before receiving, and look for opportunities to break lines.",
        "at_home_development": "Watch midfielders or players in your position and count how often they scan before receiving.",
    },
    "Speed of Play": {
        "what_improvement_looks_like": "Players process information quickly and execute decisions efficiently, allowing them to play effectively under pressure.",
        "practice_focus": "Think ahead, reduce unnecessary touches, make decisions earlier, and move the ball before pressure arrives.",
        "at_home_development": "Use one-touch and two-touch wall passing while maintaining accuracy and rhythm.",
    },
    "Speed": {
        "what_improvement_looks_like": "Players improve acceleration, movement efficiency, and the ability to reach top speed quickly during game actions.",
        "practice_focus": "Focus on quick first steps, sprint mechanics, reaction speed, and explosive transitions.",
        "at_home_development": "Perform short sprint repetitions with full recovery, focusing on technique and fast acceleration.",
    },
    "Agility": {
        "what_improvement_looks_like": "Players change direction efficiently while maintaining balance, speed, and control.",
        "practice_focus": "Stay low when changing direction, control body movement, react quickly, and recover balance after turns.",
        "at_home_development": "Use ladder work, cone patterns, and short change-of-direction exercises.",
    },
    "Balance": {
        "what_improvement_looks_like": "Players remain stable under pressure and maintain control while turning, shielding, landing, and competing physically.",
        "practice_focus": "Maintain body control, stay strong through contact, and improve stability while moving with the ball.",
        "at_home_development": "Use single-leg balance work, controlled turns, and bodyweight stability exercises.",
    },
    "Power": {
        "what_improvement_looks_like": "Players generate force efficiently for sprinting, jumping, striking, and physical challenges.",
        "practice_focus": "Focus on explosive movement, strong body positioning, and efficient use of strength.",
        "at_home_development": "Use age-appropriate jumping, sprinting, and bodyweight strength exercises.",
    },
    "Endurance": {
        "what_improvement_looks_like": "Players maintain effort, concentration, and technical quality throughout the match.",
        "practice_focus": "Keep a consistent work rate, recover between actions, and maintain focus when fatigued.",
        "at_home_development": "Use regular aerobic activity and age-appropriate interval conditioning.",
    },
    "Attitude": {
        "what_improvement_looks_like": "Players approach training and competition with enthusiasm, effort, and a positive mindset regardless of circumstances.",
        "practice_focus": "Bring energy to training, embrace challenges, and respond positively after mistakes.",
        "at_home_development": "Reflect after training by writing one thing that went well and one thing to improve next time.",
    },
    "Coachability": {
        "what_improvement_looks_like": "Players actively seek feedback and apply coaching points quickly and consistently.",
        "practice_focus": "Listen carefully, apply corrections immediately, and ask questions when needed.",
        "at_home_development": "Keep a simple training journal with coaching points and one action step for the next session.",
    },
    "Body Language": {
        "what_improvement_looks_like": "Players display confidence, resilience, and composure regardless of game situations.",
        "practice_focus": "Respond positively to mistakes, stay engaged when challenged, and show confidence through actions.",
        "at_home_development": "Reflect on emotional responses during games and identify positive ways to reset after mistakes.",
    },
    "Communication": {
        "what_improvement_looks_like": "Players consistently provide useful information that helps teammates make better decisions.",
        "practice_focus": "Communicate early, use clear and positive language, and support teammates verbally.",
        "at_home_development": "Choose one communication goal for each practice, such as calling for the ball or helping a teammate organize.",
    },
    "Sportsmanship": {
        "what_improvement_looks_like": "Players consistently demonstrate respect for teammates, opponents, coaches, officials, and the game itself.",
        "practice_focus": "Compete hard while remaining respectful and represent the club positively.",
        "at_home_development": "Reflect on examples of strong sportsmanship from games or professional players.",
    },
    "Leadership": {
        "what_improvement_looks_like": "Players positively influence teammates through actions, communication, and example.",
        "practice_focus": "Encourage teammates, take responsibility, and lead through effort and behavior.",
        "at_home_development": "Look for one way to support a teammate at each practice or game.",
    },
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
        "evaluatorStrengths": [row.get("Biggest Strength", "") for row in rows if row.get("Biggest Strength")],
        "evaluatorGrowthAreas": [row.get("Biggest Growth Area", "") for row in rows if row.get("Biggest Growth Area")],
        "notes": [row.get("Notes", "") for row in rows if row.get("Notes")],
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
