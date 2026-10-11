"""Risk detection engine: transparent, deterministic rules (no randomness, no network).

Same inputs always give the same result. Every point of the score comes from a named
rule below, so you can read this file to see exactly why something was flagged.
"""
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse, parse_qs

# --- Rule tables (edit these to tune the engine) -------------------------------------
SUSPICIOUS_TERMS = ["support", "help", "helpdesk", "rewards", "reward", "claim", "giveaway",
                    "bonus", "promo", "prize", "winner", "refund", "airdrop", "verify",
                    "customercare", "freegift", "official"]
APP_TERMS = ["mod", "apk", "hack", "premium", "unlocked", "free"]
SUSPICIOUS_PHRASES = ["claim your", "giveaway", "send dm", "dm us", "free", "limited time",
                      "click the link", "verify your account", "reward", "winner", "urgent",
                      "login here", "send money"]
LEET = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "$": "s", "@": "a"})
W = {"contains_brand": 35, "close_match": 30, "loose_match": 18, "extends_official": 15,
     "leet": 10, "term_first": 25, "term_extra": 10, "term_cap": 40, "term_unrelated": 5,
     "phrase": 15, "phrase_cap": 30, "phrase_unrelated_cap": 15, "digits": 5,
     "publisher_mismatch": 30, "publisher_missing": 15, "same_name_other_publisher": 60,
     "same_name_no_publisher": 30}
LEVELS = [(75, "Critical"), (50, "High"), (25, "Medium"), (0, "Low")]


# --- Small helpers --------------------------------------------------------------------
def compact(text: str) -> str:
    """Lowercase and keep only letters/digits: 'Nova_Pay!' -> 'novapay'."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def risk_level(score: int) -> str:
    return next(name for floor, name in LEVELS if score >= floor)


def best_window_ratio(needle: str, hay: str) -> float:
    """Best fuzzy match of `needle` against any slice of `hay` (catches 'novapai' ~ 'novapay')."""
    if not needle or not hay:
        return 0.0
    if needle in hay:
        return 1.0
    best = 0.0
    for size in (len(needle) - 1, len(needle), len(needle) + 1):
        for i in range(max(1, len(hay) - size + 1)):
            best = max(best, SequenceMatcher(None, needle, hay[i:i + size]).ratio())
    return best


def extract_username(text: str) -> str:
    """Return the username from '@name', 'name' or a profile URL. '' if none found."""
    text = text.strip()
    if "/" in text or text.lower().startswith("http") or re.match(r"^[\w.-]+\.\w{2,}/", text):
        url = text if "://" in text else "https://" + text
        segs = [s for s in urlparse(url).path.split("/") if s]
        if segs and segs[0].lower() in {"company", "in", "school", "showcase", "pages", "people"}:
            segs = segs[1:]
        text = segs[0] if segs else ""
    return text.lstrip("@").strip()


def extract_app_name(text: str) -> str:
    """Return an app name from plain text or an app-store URL (best effort)."""
    text = text.strip()
    if "/" not in text and not text.lower().startswith("http"):
        return text
    parsed = urlparse(text if "://" in text else "https://" + text)
    if "play.google.com" in parsed.netloc:
        return parse_qs(parsed.query).get("id", [""])[0]
    skip = {"app", "store", "apps", "details", "us", "in", "gb"}
    segs = [s for s in parsed.path.split("/") if s and not re.fullmatch(r"id\d+", s)]
    segs = [s for s in segs if s.lower() not in skip and not re.fullmatch(r"[a-z]{2}", s.lower())] or segs
    return segs[-1].replace("-", " ") if segs else ""


# --- Shared name analysis --------------------------------------------------------------
def _assess_name(candidate, brand_name, official_ids, description, terms):
    """Score how much `candidate` looks like the brand. Returns (points, [(weight, reason)])."""
    cand, brand = compact(candidate), compact(brand_name)
    cand_leet = cand.translate(LEET)
    refs = [brand] + [compact(o) for o in official_ids]
    reasons, points = [], 0

    plain = max((best_window_ratio(r, cand) for r in refs if r), default=0.0)
    leeted = max((best_window_ratio(r, cand_leet) for r in refs if r), default=0.0)
    ratio = max(plain, leeted)
    if len(brand) >= 3 and brand in cand:
        pts, why = W["contains_brand"], f"Name contains the brand name '{brand_name}'."
    elif ratio >= 0.85:
        pts, why = W["close_match"], "Spelling is very close to the brand or an official name."
    elif ratio >= 0.75:
        pts, why = W["loose_match"], "Spelling loosely resembles the brand or an official name."
    else:
        pts, why = 0, ""
    related = pts > 0
    if related:
        points += pts
        reasons.append((pts, why))
        if leeted > plain and cand_leet != cand:
            points += W["leet"]
            reasons.append((W["leet"], "Uses look-alike characters (such as 0 for o)."))
        if any(len(compact(o)) >= 4 and compact(o) in cand and compact(o) != cand for o in official_ids):
            points += W["extends_official"]
            reasons.append((W["extends_official"], "Extends an official name with extra characters."))
        if re.search(r"\d{2,}$", cand):
            points += W["digits"]
            reasons.append((W["digits"], "Ends in a number, common in duplicate accounts."))

    leftover = cand.replace(brand, "") if brand else cand  # don't flag terms that are part of the brand
    found = [t for t in terms if t in leftover]
    found = [t for t in found if not any(t != o and t in o for o in found)]  # drop 'reward' inside 'rewards'
    if found:
        if related:
            pts = min(W["term_first"] + W["term_extra"] * (len(found) - 1), W["term_cap"])
            reasons.append((pts, f"Adds suspicious word(s): {', '.join(found)}."))
        else:
            pts = W["term_unrelated"]
            reasons.append((pts, f"Contains scam-style word(s) ({', '.join(found)}), but nothing links it to your brand."))
        points += pts

    hits = [p for p in SUSPICIOUS_PHRASES if p in (description or "").lower()]
    if hits:
        cap = W["phrase_cap"] if related else W["phrase_unrelated_cap"]
        pts = min(W["phrase"] * len(hits), cap)
        points += pts
        reasons.append((pts, f"Description uses scam-style language ({', '.join(hits[:3])})."))
    return points, reasons


def _result(score, reasons, official, kind, identified, verdict_override=None):
    score = max(0, min(100, int(score)))
    level = "Low" if official else risk_level(score)
    texts = [t for _, t in sorted(reasons, key=lambda r: -r[0])][:3]
    if len(texts) < 2 and not official:
        texts.append("Only the submitted text was analyzed; no live account or store data was retrieved.")
    if official:
        verdict, rec = "Registered official asset", "Registered asset: no action needed."
    else:
        verdict = verdict_override or {"Critical": "Potential impersonation", "High": "Potential impersonation",
                                       "Medium": "Needs review", "Low": "No clear signs of impersonation"}[level]
        if kind == "app":
            rec = "Verify the publisher." if level != "Low" else "No action needed."
        else:
            rec = "Review this profile." if level != "Low" else "No action needed."
    return {"risk_score": 0 if official else score, "risk_level": level, "verdict": verdict,
            "reasons": texts, "recommendation": rec, "is_official": official, "identified": identified}


# --- Public API ------------------------------------------------------------------------
def analyze_social(brand_name, official_handles, submitted, description=""):
    """`submitted` is a username or profile URL."""
    handle = extract_username(submitted)
    if not handle:
        raise ValueError("Could not find a username in that URL. Paste the profile link or type the @username.")
    if handle.lower() in {h.lower().lstrip("@") for h in official_handles}:
        return _result(0, [(0, "Matches a registered official username.")], True, "social", handle)
    pts, reasons = _assess_name(handle, brand_name, official_handles, description, SUSPICIOUS_TERMS)
    return _result(pts, reasons, False, "social", handle)


def analyze_app(brand_name, official_apps, submitted, publisher="", description=""):
    """`official_apps` is a list of {'name':..., 'publisher':...}; `submitted` is a name or store URL."""
    name = extract_app_name(submitted)
    if not name:
        raise ValueError("Could not find an app name in that URL. Type the app name instead.")
    pub = compact(publisher or "")
    for app in official_apps:
        if compact(app["name"]) != compact(name):
            continue
        off_pub = compact(app.get("publisher") or "")
        if not off_pub or (pub and best_window_ratio(off_pub, pub) >= 0.9 and abs(len(pub) - len(off_pub)) <= 3):
            return _result(0, [(0, "Matches a registered official app and publisher.")], True, "app", name)
        if pub:
            why = f"Same name as your official app, but publisher '{publisher}' differs from '{app['publisher']}'."
            return _result(W["same_name_other_publisher"], [(W["same_name_other_publisher"], why)],
                           False, "app", name, "Potential impersonation")
        why = "Same name as your official app, but no publisher was supplied to confirm it."
        return _result(W["same_name_no_publisher"], [(W["same_name_no_publisher"], why)],
                       False, "app", name, "Needs review")
    official_names = [a["name"] for a in official_apps]
    pts, reasons = _assess_name(name, brand_name, official_names, description, SUSPICIOUS_TERMS + APP_TERMS)
    known_pubs = [a["publisher"] for a in official_apps if a.get("publisher")]
    if pts > 0 and known_pubs:
        if not pub:
            pts += W["publisher_missing"]
            reasons.append((W["publisher_missing"], "No publisher supplied, so it can't be checked against your official publisher."))
        elif all(best_window_ratio(compact(p), pub) < 0.9 for p in known_pubs):
            pts += W["publisher_mismatch"]
            reasons.append((W["publisher_mismatch"], f"Publisher '{publisher}' does not match your registered publisher."))
    return _result(pts, reasons, False, "app", name)
