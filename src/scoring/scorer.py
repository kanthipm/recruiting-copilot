"""Transparent, rule-based fit scoring.

Every dimension returns (score 0-10, note). Notes cite the actual evidence found in the
posting and tie it to entries in profile.json, so the reason is specific to the job.
Overall = weighted mean of dimensions (weights in config.py), capped when ineligible.
"""
import json
import re
from dataclasses import dataclass

import config
from .text import classify_role, find_keywords, min_years_required


@dataclass
class ScoreResult:
    overall: float
    tier: str            # HIGH | REVIEW | SKIP
    role_type: str
    breakdown: dict      # {dimension: {"score": n, "note": str}}
    reason: str


def load_profile(path=config.PROFILE_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tier_for(score: float) -> str:
    if score >= config.HIGH_PRIORITY_MIN:
        return "HIGH"
    if score >= config.REVIEW_MIN:
        return "REVIEW"
    return "SKIP"


def _bucket(n: int, steps: list[tuple[int, int]]) -> int:
    """steps = [(min_count, score), ...] ascending; returns score for the highest min_count <= n."""
    out = steps[0][1]
    for min_count, score in steps:
        if n >= min_count:
            out = score
    return out


def _join(items, limit=4):
    items = list(dict.fromkeys(items))[:limit]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class Scorer:
    def __init__(self, profile: dict, companies: dict[str, dict] | None = None):
        self.p = profile
        self.companies = companies or {}
        self.kw = profile["keywords"]
        self.avoid = profile["avoid"]

    # ---- profile lookups used to make reasons concrete ----
    def _orgs_with_tag(self, tag: str) -> str:
        orgs = [e["org"] for e in self.p["experiences"] if tag in e.get("tags", [])]
        return _join(orgs, 3)

    # ---- dimensions ----
    def eligibility(self, title: str, desc: str, role_type: str):
        t = title.lower()
        elig = self.p["eligibility"]

        avoid_hits = [k for k in self.avoid["title_keywords"] if k in t]
        if avoid_hits:
            return 0, f"Title matches your avoid list ('{avoid_hits[0]}')"

        if "intern" in t and not elig.get("consider_internships", False):
            return 3, "Internship; you graduate May 2027 and want full-time roles"

        senior_hits = find_keywords(title, self.avoid["seniority_keywords"])
        if senior_hits:
            return 1, f"Senior-level title ('{senior_hits[0]}')"

        for k in self.avoid.get("description_keywords", []):
            if k in desc.lower():
                return 2, f"Requires '{k}'"

        years = min_years_required(desc)
        grad_hits = find_keywords(title + " " + desc, elig["new_grad_signals"])
        if grad_hits:
            note = f"Early-career friendly ('{grad_hits[0]}')"
            if years is not None and years > elig["max_years_experience"]:
                return 6, note + f", but also mentions {years}+ years of experience"
            return 10, note
        if years is None:
            return 6, "No experience requirement stated; eligibility unclear"
        if years <= elig["max_years_experience"]:
            return 9, f"Asks for {years}+ years of experience (internships count)"
        if years <= 4:
            return 4, f"Asks for {years}+ years of experience; a stretch for a new grad"
        return 1, f"Requires {years}+ years of experience"

    def career(self, role_type: str, title: str):
        interest = self.p["target_roles"].get(role_type, self.p["target_roles"].get("Other", 0.3))
        score = round(interest * 10)
        if role_type == "Other":
            return score, f"Title doesn't map to a target role ('{title}')"
        return score, f"Maps to target role '{role_type}'"

    def technical(self, desc: str, role_type: str):
        hits = find_keywords(desc, self.p["technical_skills"])
        score = _bucket(len(hits), [(0, 2), (1, 4), (2, 5), (3, 6), (4, 7), (6, 8), (8, 9)])
        if role_type in ("Software Engineer", "ML/AI Engineer", "Product Engineer", "AI Product Engineer"):
            score = min(10, score + 1)
        if not hits:
            return score, "No overlap with your listed technical skills"
        orgs = self._orgs_with_tag("swe")
        return score, f"Mentions {_join(hits, 5)} (used at {orgs})"

    def ai(self, title: str, desc: str, company: dict):
        hits = find_keywords(desc, self.kw["ai"])
        score = _bucket(len(hits), [(0, 2), (1, 5), (3, 7), (6, 9)])
        title_ai = find_keywords(title, ["ai", "ml", "machine learning", "llm", "applied scientist", "research"])
        if title_ai:
            score = min(10, score + 2)
        industry = (company.get("industry") or "").lower()
        if "ai" in industry:
            score = min(10, score + 1)
        if not hits and not title_ai:
            return score, "Little or no AI/ML content"
        orgs = self._orgs_with_tag("ai")
        if title_ai:
            return score, f"AI/ML role by title; description covers {_join(hits, 4) or 'AI broadly'} (your {orgs} work)"
        return score, f"Description leans on {_join(hits, 4)} (your {orgs} work)"

    def product(self, title: str, desc: str, role_type: str):
        hits = find_keywords(desc, self.kw["product"])
        if role_type in ("APM/PM", "Technical PM"):
            return 10, "Product-management role; your MedPull founder experience is directly relevant"
        if role_type in ("Product Engineer", "AI Product Engineer"):
            return 9, f"Product-engineering role ({_join(hits, 3) or 'ships user-facing product'})"
        if role_type in ("Founder's Associate", "Product/Strategy"):
            return 8, "Product/strategy-adjacent role"
        score = _bucket(len(hits), [(0, 2), (1, 4), (3, 6), (5, 8)])
        if not hits:
            return score, "No product-ownership signals"
        return score, f"Product signals: {_join(hits, 4)} (you did this founding {self._orgs_with_tag('founder')})"

    def startup(self, desc: str, company: dict):
        ctype = (company.get("company_type") or "unknown").lower()
        stage = (company.get("stage") or "").lower()
        base = {"startup": 9, "ai lab": 8, "scaleup": 7, "unknown": 5, "big tech": 4, "public": 3}.get(ctype, 5)
        if ctype == "startup" and stage in ("seed", "series a"):
            base = 10
        hits = find_keywords(desc, self.kw["startup"])
        score = min(10, base + (1 if hits else 0))
        label = f"{stage} {ctype}".strip() if stage else ctype
        if hits:
            return score, f"{label.title()}; posting says '{hits[0]}'"
        return score, f"Company type: {label}"

    def healthcare(self, desc: str, company: dict):
        industry = (company.get("industry") or "").lower()
        hits = find_keywords(desc, self.kw["healthcare"])
        if "health" in industry:
            return 9, f"Healthcare company; directly relevant to {self._orgs_with_tag('healthcare')}"
        score = _bucket(len(hits), [(0, 3), (1, 6), (3, 8)])
        if not hits:
            return score, "No healthcare angle (bonus only)"
        return score, f"Healthcare mentions: {_join(hits, 3)}"

    def company_quality(self, company: dict):
        q = company.get("quality")
        if q is None:
            return 6, "No quality rating in sources.json (default)"
        return int(q) * 2, f"Your rating for this company: {q}/5 (sources.json)"

    def hybrid(self, title: str, tech_score: int, product_score: int):
        hits = find_keywords(title, self.kw["hybrid"])
        score = min(tech_score, product_score)
        if hits:
            score = min(10, score + 2)
            return score, f"Explicitly hybrid title ('{hits[0]}'): engineering + product ownership"
        if score >= 7:
            return score, "Both engineering and product ownership are present"
        return score, "Weaker on the " + ("product" if product_score < tech_score else "technical") + " side"

    def location(self, loc: str, title: str = ""):
        prefs = self.p["location_preferences"]
        l = loc.lower()
        if not l:
            return 6, "Location not stated"
        haystack = l + " " + title.lower()
        for s in prefs["non_us_signals"]:
            if re.search(r"(?<![a-z])" + re.escape(s.lower()) + r"(?![a-z])", haystack):
                return 2, f"Outside the US ({loc})"
        for city in prefs["preferred"]:
            if city.lower() in l and city.lower() != "remote":
                return 10, f"Preferred location ({loc})"
        if prefs.get("remote_ok") and "remote" in l:
            return 9, f"Remote ({loc})"
        for city in prefs["acceptable"]:
            if re.search(r"(?<![a-z])" + re.escape(city.lower()) + r"(?![a-z])", l):
                return 8, f"Acceptable location ({loc})"
        return 5, f"Unlisted location ({loc})"

    # ---- put it together ----
    def score(self, title: str, description: str, location: str, company_name: str) -> ScoreResult:
        desc = description or ""
        company = self.companies.get(company_name, {})
        role_type = classify_role(title)

        b = {}
        b["eligibility"] = self.eligibility(title, desc, role_type)
        b["career"] = self.career(role_type, title)
        b["technical"] = self.technical(desc, role_type)
        b["ai"] = self.ai(title, desc, company)
        b["product"] = self.product(title, desc, role_type)
        b["hybrid"] = self.hybrid(title, b["technical"][0], b["product"][0])
        b["startup"] = self.startup(desc, company)
        b["company_quality"] = self.company_quality(company)
        b["location"] = self.location(location or "", title)
        b["healthcare"] = self.healthcare(desc, company)

        total_w = sum(config.WEIGHTS.values())
        overall = sum(b[d][0] * w for d, w in config.WEIGHTS.items()) / total_w
        ineligible = b["eligibility"][0] <= 3
        if ineligible:
            overall = min(overall, config.INELIGIBLE_CAP)
        elif b["location"][0] <= 2:
            overall = min(overall, config.NON_US_CAP)
        overall = round(overall, 1)

        breakdown = {d: {"score": s, "note": n} for d, (s, n) in b.items()}
        reason = self._reason(b, ineligible, role_type)
        return ScoreResult(overall, tier_for(overall), role_type, breakdown, reason)

    def _reason(self, b: dict, ineligible: bool, role_type: str) -> str:
        if ineligible:
            return f"Skip: {b['eligibility'][1]}. " + f"(Would otherwise be a {role_type} role: {b['career'][1].lower()}.)"
        ranked = sorted(b.items(), key=lambda kv: -kv[1][0] * config.WEIGHTS[kv[0]])
        strengths = [n for d, (s, n) in ranked if s >= 8][:4]
        concerns = [n for d, (s, n) in b.items() if s <= 4 and d != "healthcare"][:2]
        text = "Why: " + ". ".join(strengths) + "." if strengths else "Few strong signals."
        if concerns:
            text += " Watch out: " + "; ".join(concerns) + "."
        return text
