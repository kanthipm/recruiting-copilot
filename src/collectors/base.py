"""Shared job shape + HTTP helpers. Every collector returns a list of Job."""
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
    date_posted: Optional[str]          # ISO date "YYYY-MM-DD" or None
    external_id: str = ""
    company_meta: dict = field(default_factory=dict)  # the sources.json entry

    def to_dict(self):
        return asdict(self)


_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})


def get_json(url: str):
    resp = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def html_to_text(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


class Collector:
    """Subclass this, set `name`, and implement fetch(source) -> list[Job]."""
    name = "base"

    def fetch(self, source: dict) -> list[Job]:
        raise NotImplementedError
