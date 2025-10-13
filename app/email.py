import os
import re
import email
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from .models import Player, Registration
from .services.assign import assign_jersey_number

logger = logging.getLogger(__name__)

PROMO_CODES = {
    1: "Pines1Player",
    2: "Pines2Players",
    3: "Pines3Players",
    4: "Pines4Players",
    5: "Pines5Players",
    6: "Pines6Players",
    7: "Pines7Players",
}

UNIFORM_ORDER_URL = "https://treblemade.com/products/pines-soccer-reversible-jersey?_pos=1&_sid=0fa41b461&_ss=r"
DEFAULT_CC_EMAIL = "tim@posasports.org"

DIVISION_ORDER = {
    "U3": -1,
    "U4": 0,
    "U5": 1,
    "U6": 2,
    "U8": 3,
    "U10": 4,
    "U12": 5,
    "U14": 6,
    "Pend Oreille Pines (High School Club Team)": 7,
}

DIVISION_ALIASES = {
    "U3": "U3",
    "UNDER3": "U3",
    "U4": "U4",
    "UNDER4": "U4",
    "U5": "U5",
    "UNDER5": "U5",
    "U6": "U6",
    "UNDER6": "U6",
    "U8": "U8",
    "UNDER8": "U8",
    "U10": "U10",
    "UNDER10": "U10",
    "U12": "U12",
    "UNDER12": "U12",
    "U14": "U14",
    "UNDER14": "U14",
    "HIGHSCHOOL": "Pend Oreille Pines (High School Club Team)",
    "HS": "Pend Oreille Pines (High School Club Team)",
    "PENDOREILLEPINESHIGHSCHOOLCLUBTEAM": "Pend Oreille Pines (High School Club Team)",
}

def normalize_division(raw: str, birth_year: int | None = None) -> str:
    key = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    if key in DIVISION_ALIASES:
        return DIVISION_ALIASES[key]
    if birth_year == 2022:
        return "U3"
    division = DIVISION_ALIASES.get(key, key)
    return division if division in DIVISION_ORDER else "Unknown"

# --- Email senders and inbound logic (same as your previous working version) ---
# (keep your SendGrid email sending, save_inbound_email, and process_inbound_email here unchanged)
