"""Ashby public job board API (no auth).
Docs: https://developers.ashbyhq.com/reference/jobpostingapi
"""
from .base import Collector, Job, get_json, html_to_text


class AshbyCollector(Collector):
    name = "ashby"

    def fetch(self, source: dict) -> list[Job]:
        board = source["board"]
        data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true")
        jobs = []
        for j in data.get("jobs", []):
            location = (j.get("location") or "").strip()
            if j.get("isRemote") and "remote" not in location.lower():
                location = f"{location} (Remote)".strip()
            posted = j.get("publishedAt") or ""
            jobs.append(Job(
                title=(j.get("title") or "").strip(),
                company=source["company"],
                location=location,
                url=j.get("jobUrl") or j.get("applyUrl", ""),
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
                source=self.name,
                date_posted=posted[:10] or None,
                external_id=str(j.get("id", "")),
                company_meta=source,
            ))
        return jobs
