"""Greenhouse public job board API (no auth).
Docs: https://developers.greenhouse.io/job-board.html
"""
import html

from .base import Collector, Job, get_json, html_to_text


class GreenhouseCollector(Collector):
    name = "greenhouse"

    def fetch(self, source: dict) -> list[Job]:
        board = source["board"]
        data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
        jobs = []
        for j in data.get("jobs", []):
            posted = j.get("first_published") or j.get("updated_at") or ""
            jobs.append(Job(
                title=j.get("title", "").strip(),
                company=source["company"],
                location=((j.get("location") or {}).get("name") or "").strip(),
                url=j.get("absolute_url", ""),
                description=html_to_text(html.unescape(j.get("content") or "")),
                source=self.name,
                date_posted=posted[:10] or None,
                external_id=str(j.get("id", "")),
                company_meta=source,
            ))
        return jobs
