"""Small text helpers: keyword matching and title -> role type classification."""
import re
from functools import lru_cache

# Ordered: first match wins. Patterns are matched against the lowercased title.
ROLE_PATTERNS = [
    ("Technical PM", r"technical product manager|technical pm\b|\btpm\b"),
    ("APM/PM", r"associate product manager|\bapm\b|product manager|product management|product lead\b|product owner"),
    ("Founder's Associate", r"founder'?s? associate|founder associate|chief of staff|founders? office|office of the ceo"),
    ("Product/Strategy", r"\bstrategy\b|strategic|business operations|\bbizops\b|\bbiz ops\b|operations associate|growth associate|product operations|product analyst|product specialist"),
    ("AI Product Engineer", r"ai product engineer|ai engineer, product|product engineer, ai|forward.?deployed|applied ai engineer|ai solutions engineer"),
    ("Product Engineer", r"product engineer|full.?stack product|founding engineer|solutions engineer|solutions architect|deployment strategist|implementation engineer"),
    ("ML/AI Engineer", r"machine learning|\bml\b|\bai\b|applied scientist|research engineer|research scientist|data scientist|deep learning|nlp|computer vision|member of technical staff|\bmts\b"),
    ("Software Engineer", r"software engineer|software developer|software development|\bswe\b|\bsde\b|full.?stack|back.?end|front.?end|platform engineer|infrastructure engineer|web developer|mobile engineer|ios engineer|android engineer|data engineer|security engineer|site reliability|devops|cloud engineer|systems software"),
]


def classify_role(title: str) -> str:
    t = title.lower()
    for role, pattern in ROLE_PATTERNS:
        if re.search(pattern, t):
            return role
    return "Other"


@lru_cache(maxsize=4096)
def _pattern(kw: str):
    k = kw.lower()
    if len(k) <= 3 or k.isalnum():
        return re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])")
    return re.compile(re.escape(k))


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    """Return the keywords that appear in text (case-insensitive, word-boundary aware).
    Short tokens like 'ai' or 'ml' use strict word boundaries so 'email' doesn't match 'ai'.
    """
    low = text.lower()
    return [kw for kw in keywords if _pattern(kw).search(low)]


def has_any(text: str, keywords: list[str]) -> bool:
    return bool(find_keywords(text, keywords))


_YEARS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b[^.\n]{0,60}?experience",
    re.IGNORECASE,
)


def min_years_required(text: str):
    """Smallest 'N+ years ... experience' number mentioned, or None if not stated."""
    values = []
    for m in _YEARS.finditer(text):
        values.append(int(m.group(1)))
    return min(values) if values else None
