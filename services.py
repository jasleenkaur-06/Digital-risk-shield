"""Business logic between the API and the engine/storage. No web framework code here,
so it can be tested without FastAPI."""
import re
from . import engine

PLATFORMS = ["Instagram", "Facebook", "X", "LinkedIn", "Other"]
DEMO_BRAND = {"name": "NovaPay", "website": "https://novapay.example",
              "socials": ["novapay_official"],
              "apps": [{"name": "NovaPay Wallet", "publisher": "NovaPay Technologies Ltd"}]}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean(value, field, required=False, max_len=200):
    """Trim text, reject control characters and over-long input."""
    value = (value or "").strip()
    if _CONTROL.search(value):
        raise ValueError(f"{field} contains invalid characters.")
    if len(value) > max_len:
        raise ValueError(f"{field} is too long (max {max_len} characters).")
    if required and not value:
        raise ValueError(f"{field} is required.")
    return value


def is_demo_brand(name):
    return (name or "").strip().lower() == DEMO_BRAND["name"].lower()


def get_profile(repo):
    profiles = repo.list_profiles()
    return profiles[0] if profiles else None   # the first brand is the saved profile


def save_profile(repo, name, website="", socials=(), apps=()):
    name = clean(name, "Brand name", required=True, max_len=80)
    website = clean(website, "Official website", max_len=200)
    socials = [clean(s, "Social username", max_len=100) for s in socials if s.strip()]
    apps = [{"name": clean(a.get("name", ""), "App name", max_len=100),
             "publisher": clean(a.get("publisher", ""), "Publisher", max_len=100)} for a in apps if a.get("name", "").strip()]
    current = get_profile(repo)
    return repo.save_profile(name, website, socials, apps, brand_id=current["id"] if current else None)


def load_demo_brand(repo):
    current = get_profile(repo)
    if current and not is_demo_brand(current["name"]):
        raise ValueError("A brand profile already exists. Edit it in Brand Setup, or use a fresh database for the demo.")
    d = DEMO_BRAND
    return save_profile(repo, d["name"], d["website"], d["socials"], d["apps"])


def _brand_for_scan(repo, brand_name):
    """Use the saved profile (or another known brand) with this name; otherwise create it with no assets."""
    for p in repo.list_profiles():
        if p["name"].lower() == brand_name.lower():
            return p
    return repo.save_profile(brand_name, "", [], [])


def _store(repo, brand, scan_type, submitted, platform, result):
    reasons = result["reasons"]
    row = repo.add_scan(brand["id"], scan_type, submitted, platform, result["risk_score"], result["risk_level"], reasons)
    return {**result, "id": row["id"], "created_at": row["created_at"], "scan_type": scan_type,
            "brand_name": brand["name"], "submitted": submitted, "platform": platform,
            "fictional_demo": is_demo_brand(brand["name"]), "stored_in": repo.mode}


def scan_social(repo, brand_name, submitted, platform, description=""):
    brand_name = clean(brand_name, "Brand name", True, 80)
    submitted = clean(submitted, "Profile username or URL", True, 200)
    description = clean(description, "Description", max_len=500)
    if platform not in PLATFORMS:
        raise ValueError("Choose a platform from the list.")
    brand = _brand_for_scan(repo, brand_name)
    result = engine.analyze_social(brand["name"], brand["socials"], submitted, description)
    return _store(repo, brand, "social", submitted, platform, result)


def scan_app(repo, brand_name, submitted, publisher="", description=""):
    brand_name = clean(brand_name, "Brand name", True, 80)
    submitted = clean(submitted, "App name or store URL", True, 300)
    publisher = clean(publisher, "Publisher", max_len=100)
    description = clean(description, "Description", max_len=500)
    brand = _brand_for_scan(repo, brand_name)
    result = engine.analyze_app(brand["name"], brand["apps"], submitted, publisher, description)
    return _store(repo, brand, "app", submitted, None, result)


def dashboard(repo):
    scans = repo.recent_scans(10)
    for s in scans:
        s["fictional_demo"] = is_demo_brand(s.get("brand_name"))
    return {"stats": repo.stats(), "recent": scans, "profile": get_profile(repo)}
