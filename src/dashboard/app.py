"""Streamlit dashboard. Run with:  python run.py dashboard"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config
from src.database import db
from src.scoring.scorer import tier_for

st.set_page_config(page_title="Recruiting Copilot", layout="wide")
db.init_db()


def load_jobs() -> pd.DataFrame:
    rows = [dict(r) for r in db.get_jobs()]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[df["fit_score"].notna()].copy()
    df["tier"] = df["fit_score"].apply(tier_for)
    return df


df = load_jobs()
if df.empty:
    st.title("Recruiting Copilot")
    st.info("No scored jobs yet. Run `python run.py daily` first.")
    st.stop()

# ---------------- sidebar filters ----------------
st.sidebar.header("Filters")
min_score = st.sidebar.slider("Minimum score", 0.0, 10.0, 0.0, 0.5)
role_types = st.sidebar.multiselect("Role type", sorted(df["role_type"].dropna().unique()))
companies = st.sidebar.multiselect("Company", sorted(df["company"].unique()))
sources = st.sidebar.multiselect("Source", sorted(df["source"].unique()))
location_q = st.sidebar.text_input("Location contains")
days = st.sidebar.number_input("Found in the last N days (0 = all)", min_value=0, value=0)
show_done = st.sidebar.checkbox("Show applied / skipped", value=False)

f = df[df["fit_score"] >= min_score]
if role_types:
    f = f[f["role_type"].isin(role_types)]
if companies:
    f = f[f["company"].isin(companies)]
if sources:
    f = f[f["source"].isin(sources)]
if location_q:
    f = f[f["location"].str.contains(location_q, case=False, na=False)]
if days:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    f = f[f["date_found"] >= cutoff]
if not show_done:
    f = f[~f["status"].isin(["applied", "skipped"])]

st.title("Recruiting Copilot")
s = db.stats()
st.caption(f"{s['jobs']} jobs from {s['companies']} companies · {len(f)} match filters · "
           f"HIGH ≥ {config.HIGH_PRIORITY_MIN}, REVIEW ≥ {config.REVIEW_MIN}")


# ---------------- job card ----------------
def render_job(row):
    header = f"{row['fit_score']:.1f} | {row['title']} | {row['company']} | {row['location'] or 'n/a'}"
    with st.expander(header):
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
            st.caption(f"Role type: {row['role_type']}")
            st.caption(f"Source: {row['source']} · posted {row['date_posted'] or '?'} · found {row['date_found'][:10]}")
            options = ["new", "saved", "applied", "skipped"]
            current = row["status"] if row["status"] in options else "new"
            new_status = st.selectbox("Status", options, index=options.index(current), key=f"status_{row['id']}")
            if new_status != current:
                db.set_status(int(row["id"]), new_status)
                st.rerun()
        with st.expander("Job description"):
            st.text((row["description"] or "")[:6000])


tabs = st.tabs([f"HIGH PRIORITY ({(f['tier'] == 'HIGH').sum()})",
                f"REVIEW ({(f['tier'] == 'REVIEW').sum()})",
                f"SKIP ({(f['tier'] == 'SKIP').sum()})"])
for tab, tier in zip(tabs, ["HIGH", "REVIEW", "SKIP"]):
    with tab:
        subset = f[f["tier"] == tier].sort_values("fit_score", ascending=False)
        if subset.empty:
            st.write("Nothing here.")
        for _, row in subset.head(100).iterrows():
            if len(subset) > 100 and _ == subset.index[0]:
                st.caption(f"Showing top 100 of {len(subset)}; tighten filters to see more.")
            render_job(row)
