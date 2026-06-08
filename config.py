import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
XLSX_PATH = BASE_DIR / "New - Customer influencer reachouts.xlsx"
CSV_PATH = XLSX_PATH  # legacy alias
STATE_PATH = DATA_DIR / "state.json"
SCORED_PATH = DATA_DIR / "candidates_scored.json"

CHROME_PROFILE_PATH = os.path.expanduser(
    "~/Library/Application Support/Google/Chrome/Default"
)

# Rate limits
DAILY_LIMITS = {
    "page_visit": 80,
    "connection_request": 20,
    "message": 15,
}

DELAYS = {
    "page_navigation": (8, 20),
    "connection_request": (120, 300),
    "message": (180, 420),
    "typing_char_ms": (30, 80),
}

# Message templates
CONNECT_NOTE = (
    "Hi {first_name}, we crossed paths when you posted about Storylane "
    "in our influencer campaign. Loved your take! I'm at Storylane and "
    "would love to connect and chat about a new collab opportunity."
)

CONNECT_NOTE_SHORT = (
    "Hi {first_name}, you posted about Storylane in our creator campaign "
    "— thanks for that! I'd love to reconnect and explore a new collaboration."
)

FOLLOWUP_DM = """Hey {first_name}! Thanks for connecting.

You might remember posting about Storylane a while back as part of our influencer program — really appreciated your support!

We're now building out a group of customer influencers who genuinely use and love Storylane. The idea is simple: we help amplify your content and personal brand, and you share authentic takes on how you use interactive demos in your workflow.

Would you be open to a quick 15-min chat this week to hear more? No pressure at all — just want to see if it's a good fit for both sides.

Talk soon!
Prashil"""

# Scoring keywords
STRONG_FIT_ROLES = [
    "presales", "sales engineer", "solutions engineer", "demo",
    "product marketing", "sales enablement", "growth marketing",
    "demand gen", "revenue", "gtm", "go-to-market", "interactive demo",
]

GOOD_FIT_ROLES = [
    "marketing", "sales", "product", "customer success",
    "account executive", "sdr", "bdr", "partnerships", "enablement",
]

ADJACENT_ROLES = [
    "founder", "ceo", "cro", "cmo", "vp sales", "vp marketing",
    "head of marketing", "head of sales", "director",
]

SAAS_SIGNALS = [
    "saas", "b2b", "software", "platform", "cloud", "tech",
    "startup", "series", "enterprise", "arr", "mrr",
]
