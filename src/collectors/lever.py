"""Lever public postings API (no auth).
Docs: https://github.com/lever/postings-api
"""
from datetime import datetime, timezone

from .base import Collector, Job, get_json, html_to_text


class LeverCollector(Collector):
    name = "lever"

    def fetch(self, source: dict) -> list[Job]:
        board = source["board"]
        data = get_json(f"https://api.lever.co/v0/postings/{board}?mode=json")
        jobs = []
        for j in data:
            cats = j.get("categories") or {}
            location = (cats.get("location") or "").strip()
            if (j.get("workplaceType") or "").lower() == "remote" and "remote" not in location.lower():
                location = f"{location} (Remote)".strip()

            parts = [j.get("descriptionPlain") or html_to_text(j.get("description", ""))]
            for section in j.get("lists") or []:
                parts.append(section.get("text", ""))
                parts.append(html_to_text(section.get("content", "")))
            parts.append(j.get("additionalPlain") or "")

            created_ms = j.get("createdAt")
            posted = None
            if created_ms:
                posted = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).date().isoformat()

            jobs.append(Job(
                title=(j.get("text") or "").strip(),
                company=source["company"],
                location=location,
                url=j.get("hostedUrl") or j.get("applyUrl", ""),
                description="\n".join(p for p in parts if p),
                source=self.name,
                date_posted=posted,
                external_id=str(j.get("id", "")),
                company_meta=source,
            ))
        return jobs
