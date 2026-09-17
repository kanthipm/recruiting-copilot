"""Streamlit dashboard. Run with:  python run.py dashboard"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config
from src.database import db
from src.scoring.scorer import load_profile, tier_for

PROFILE = load_profile()
_LOC = PROFILE["location_preferences"]
REGIONS = [
    ("SF Bay Area", ["san francisco", "sf", "bay area", "palo alto", "mountain view", "menlo park", "sunnyvale",
                     "san jose", "oakland", "redwood city", "san mateo", "berkeley"]),
    ("New York", ["new york", "nyc", "brooklyn", "manhattan"]),
    ("Seattle", ["seattle", "redmond", "bellevue", "kirkland"]),
    ("Boston", ["boston", "cambridge, ma"]),
    ("LA", ["los angeles", "santa monica", "irvine"]),
    ("Austin", ["austin"]),
    ("Chicago", ["chicago"]),
    ("DC", ["washington, d", "washington dc", "arlington", "virginia", "maryland"]),
    ("NC", ["durham", "raleigh", "chapel hill", "charlotte"]),
]


def region_of(location: str) -> str:
    l = (location or "").lower()
    if not l:
        return "Unknown"
    for s in _LOC["non_us_signals"]:
        if re.search(r"(?<![a-z])" + re.escape(s.lower()) + r"(?![a-z])", l):
            return "Non-US"
    hits = [name for name, keys in REGIONS if any(k in l for k in keys)]
    if hits:
        return hits[0]
    return "Remote (US)" if "remote" in l else "Other US"

st.set_page_config(page_title="Recruiting Copilot", layout="wide")


def _scored_jobs(path) -> int:
    if not path.exists():
        return 0
    try:
        conn = sqlite3.connect(path)
        n = conn.execute("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL").fetchone()[0]
        conn.close()
        return n
    except sqlite3.Error:
        return 0


# Hosted (Streamlit Cloud): no local database with data, so use the slim copy committed to git.
HOSTED = _scored_jobs(config.DB_PATH) == 0 and config.SLIM_DB_PATH.exists()
if HOSTED:
    config.DB_PATH = config.SLIM_DB_PATH
db.init_db()


def load_jobs() -> pd.DataFrame:
    df = pd.DataFrame([dict(r) for r in db.get_jobs()])
    if df.empty:
        return df
    df = df[df["fit_score"].notna()].copy()
    df["tier"] = df["fit_score"].apply(tier_for)
    df["date_posted"] = pd.to_datetime(df["date_posted"], errors="coerce")
    df["region"] = df["location"].apply(region_of)
    return df


df = load_jobs()
if df.empty:
    st.title("Recruiting Copilot")
    st.info("No scored jobs yet. Run `python run.py daily` first.")
    st.stop()

# ---------------- sidebar filters ----------------
st.sidebar.header("Filters")
sort_by = st.sidebar.radio("Sort by", ["Highest score", "Newest posted"], horizontal=True)
min_score = st.sidebar.slider("Minimum score", 0.0, 10.0, 0.0, 0.5)
role_types = st.sidebar.multiselect("Role type (PM, SWE, ...)", sorted(df["role_type"].dropna().unique()))
regions = st.sidebar.multiselect("Location", sorted(df["region"].unique()))
companies = st.sidebar.multiselect("Company", sorted(df["company"].unique()))
sources = st.sidebar.multiselect("Source", sorted(df["source"].unique()))
location_q = st.sidebar.text_input("Location contains")
title_q = st.sidebar.text_input("Title contains")
posted_days = st.sidebar.number_input("Posted in the last N days (0 = all)", min_value=0, value=config.RECENT_DAYS)
show_done = st.sidebar.checkbox("Show applied / skipped", value=False)

f = df[df["fit_score"] >= min_score]
if role_types:
    f = f[f["role_type"].isin(role_types)]
if regions:
    f = f[f["region"].isin(regions)]
if companies:
    f = f[f["company"].isin(companies)]
if sources:
    f = f[f["source"].isin(sources)]
if location_q:
    f = f[f["location"].str.contains(location_q, case=False, na=False)]
if title_q:
    f = f[f["title"].str.contains(title_q, case=False, na=False)]
if posted_days:
    cutoff = pd.Timestamp(datetime.now(timezone.utc).date() - timedelta(days=posted_days))  # calendar days, like the CLI
    f = f[f["date_posted"] >= cutoff]
if not show_done:
    f = f[~f["status"].isin(["applied", "skipped"])]

if sort_by == "Newest posted":
    f = f.sort_values(["date_posted", "fit_score"], ascending=[False, False], na_position="last")
else:
    f = f.sort_values(["fit_score", "date_posted"], ascending=[False, False], na_position="last")

st.title("Recruiting Copilot")
s = db.stats()
st.caption(f"{s['jobs']} jobs from {s['companies']} companies · {len(f)} match filters · "
           f"HIGH ≥ {config.HIGH_PRIORITY_MIN}, REVIEW ≥ {config.REVIEW_MIN}")
if HOSTED:
    st.caption("Hosted copy: shows jobs above the REVIEW line, refreshed daily by GitHub Actions. "
               "Status changes here are not saved; use the local dashboard for that.")

TABLE_COLS = ["fit_score", "title", "company", "role_type", "region", "location", "date_posted", "status", "source", "url"]
COLUMN_CONFIG = {
    "fit_score": st.column_config.NumberColumn("Score", format="%.1f", width="small"),
    "title": st.column_config.TextColumn("Title", width="large"),
    "company": st.column_config.TextColumn("Company", width="medium"),
    "region": st.column_config.TextColumn("Region", width="small"),
    "location": st.column_config.TextColumn("Location", width="medium"),
    "role_type": st.column_config.TextColumn("Role type", width="small"),
    "date_posted": st.column_config.DateColumn("Posted", format="MMM D", width="small"),
    "status": st.column_config.TextColumn("Status", width="small"),
    "source": st.column_config.TextColumn("Source", width="small"),
    "url": st.column_config.LinkColumn("Apply", display_text="open ↗", width="small"),
}


def render_detail(row):
    st.subheader(f"{row['fit_score']:.1f} · {row['title']} · {row['company']}")
    left, right = st.columns([3, 1])
    with left:
        st.write(row["fit_reason"])
        breakdown = json.loads(row["fit_breakdown"] or "{}")
        table = pd.DataFrame(
            [{"dimension": d, "score": v["score"], "weight": config.WEIGHTS.get(d, 0), "evidence": v["note"]}
             for d, v in breakdown.items()]
        )
        st.dataframe(table, hide_index=True, width="stretch")
    with right:
        st.link_button("Open application ↗", row["url"], width="stretch")
        posted = row["date_posted"].date().isoformat() if pd.notna(row["date_posted"]) else "?"
        st.caption(f"{row['location'] or 'n/a'} · {row['role_type']}")
        st.caption(f"Source: {row['source']} · posted {posted} · found {row['date_found'][:10]}")
        options = ["new", "saved", "applied", "skipped"]
        current = row["status"] if row["status"] in options else "new"
        new_status = st.selectbox("Status", options, index=options.index(current), key=f"status_{row['id']}")
        if new_status != current:
            db.set_status(int(row["id"]), new_status)
            st.rerun()
    with st.expander("Job description"):
        st.text((row["description"] or "")[:6000])


def render_tab(tier: str, subset: pd.DataFrame):
    if subset.empty:
        st.write("Nothing here.")
        return
    st.caption("Click a row to see why it fits and update its status.")
    event = st.dataframe(
        subset[TABLE_COLS],
        column_config=COLUMN_CONFIG,
        hide_index=True,
        width="stretch",
        height=min(600, 38 * (len(subset) + 1)),
        on_select="rerun",
        selection_mode="single-row",
        key=f"table_{tier}",
    )
    selected = event.selection.rows if event and event.selection else []
    if selected:
        st.divider()
        render_detail(subset.iloc[selected[0]])


tabs = st.tabs([f"HIGH PRIORITY ({(f['tier'] == 'HIGH').sum()})",
                f"REVIEW ({(f['tier'] == 'REVIEW').sum()})",
                f"SKIP ({(f['tier'] == 'SKIP').sum()})"])
for tab, tier in zip(tabs, ["HIGH", "REVIEW", "SKIP"]):
    with tab:
        render_tab(tier, f[f["tier"] == tier].reset_index(drop=True))
