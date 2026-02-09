import os
from typing import Optional
import re
import glob

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# ---------------- Page config ----------------

st.set_page_config(layout="wide", page_icon="GEM.webp")
st.title("Average Monthly Generation and Capture Prices")

# ---------------- Description / CTA ----------------
st.markdown(
    """
This app presents the average Generation, captured value and capture prices of Generation in Germany for the last few years. 

**Data source:** Downloaded data from https://www.energy-charts.info/ 

**More insights:** [GEM Energy Analytics](https://gemenergyanalytics.substack.com/)  
**Connect with me:** Julien Jomaux  
**Email me:** julien.jomaux@gmail.com

If you want to support, please consider becoming a paying member of [GEM Energy Analytics](https://gemenergyanalytics.substack.com/).
"""
)


# -------------------------------------------------------------------------
# 🔓 PAYWALL REMOVED — CONTENT ALWAYS AVAILABLE
# -------------------------------------------------------------------------

# ---------------- Data Loading ----------------
@st.cache_data
def load_df(filepath: str):
    return pd.read_csv(
        filepath,
        encoding="utf-8-sig",   # handles BOM safely
        sep=",",
        engine="python"
    )

# ---- Discover available years automatically ----
BASE_PREFIX = "Germany"

def list_available_years(prefix: str = BASE_PREFIX):
    years = []
    for path in glob.glob(f"{prefix} *.csv"):
        fname = os.path.basename(path)
        m = re.match(rf"^{re.escape(prefix)}\s+(\d{{4}})\.csv$", fname)
        if m:
            years.append(int(m.group(1)))
    return sorted(set(years))

available_years = list_available_years()
if not available_years:
    st.error(f"No CSV files found with pattern '{BASE_PREFIX} <YEAR>.csv' in this folder.")
    st.stop()

default_index = len(available_years) - 1
selected_year = st.selectbox("Select year", options=available_years, index=default_index)

CSV_FILE = f"{BASE_PREFIX} {selected_year}.csv"

try:
    df = load_df(CSV_FILE)
except Exception as e:
    st.error(f"Failed to load CSV '{CSV_FILE}': {e}")
    st.stop()

# ---------------- Cleaning / Preparation ----------------

df.columns = (
    df.columns.astype(str)
    .str.replace("\ufeff", "", regex=False)
    .str.replace("\u200b", "", regex=False)
    .str.strip()
)

date_col = df.columns[0]

# Drop units row
if not df.empty:
    first_row_str = df.iloc[0].astype(str).str.lower()
    units_hits = first_row_str.str.contains(r"power\s*\(mw\)|price\s*\(", regex=True).mean()
    if units_hits > 0.3:
        df = df.iloc[1:].reset_index(drop=True)

# Parse datetime robustly
s = df[date_col].astype(str).str.strip().replace({"": pd.NA})
df[date_col] = pd.to_datetime(s, errors="coerce", utc=True)
df = df[df[date_col].notna()].copy()
df[date_col] = df[date_col].dt.tz_convert("UTC").dt.tz_localize(None)

df["Month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

df_year = df[df["Month"].dt.year == selected_year].copy()
if df_year.empty:
    st.warning(f"No data available for {selected_year} after filtering.")
    st.stop()

# Identify Day-Ahead price column
price_col = "Day Ahead Auction (DE-LU)"
if price_col not in df_year.columns:
    alt = "Day-ahead Auction (DE-LU)"
    if alt in df_year.columns:
        price_col = alt
    else:
        possibles = [c for c in df_year.columns if "auction" in c.lower() and "de-lu" in c.lower()]
        price_col = possibles[0] if possibles else None

# Select energy column
meta_cols = {date_col, "Month"}
exclude_cols = set(meta_cols)
if price_col:
    exclude_cols.add(price_col)

value_cols = [c for c in df_year.columns if c not in exclude_cols]
selected_col = st.selectbox("Select the column to analyze (energy series in MW):", sorted(value_cols))

df_year[selected_col] = pd.to_numeric(df_year[selected_col], errors="coerce")
if price_col:
    df_year[price_col] = pd.to_numeric(df_year[price_col], errors="coerce")

# ---------------- Aggregations ----------------

# Monthly total energy (GWh)
monthly_gwh = df_year.groupby("Month", sort=True)[selected_col].sum() / 4000.0

# Capture value
if price_col is None:
    st.warning("Price column 'Day Ahead Auction (DE-LU)' not found; skipping Capture calculations.")
    capture_meur = pd.Series(dtype=float)
    capture_price_eur_per_mwh = pd.Series(dtype=float)
else:
    capture_meur = (df_year[selected_col] * df_year[price_col]).groupby(df_year["Month"]).sum() / 4_000_000.0

    common_index = monthly_gwh.index.intersection(capture_meur.index)
    monthly_gwh_aligned = monthly_gwh.reindex(common_index)
    capture_meur_aligned = capture_meur.reindex(common_index)

    with pd.option_context("mode.use_inf_as_na", True):
        capture_price_eur_per_mwh = (capture_meur_aligned / monthly_gwh_aligned) * 1000.0
        capture_price_eur_per_mwh = capture_price_eur_per_mwh.replace([pd.NA], 0).fillna(0)

# ---------------- Plots ----------------

def _labels(idx):
    try:
        return idx.strftime("%Y-%m")
    except Exception:
        return idx.astype(str)

fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(14, 12), sharex=True)
plt.subplots_adjust(hspace=0.35)

# 1 — Monthly energy
ax = axes[0]
x1 = _labels(monthly_gwh.index)
ax.bar(x1, monthly_gwh.values, color="#2E86DE", edgecolor="#1B4F72")
ax.set_title(f"Monthly Total Energy – {selected_col} ({selected_year})", fontsize=14, pad=12)
ax.set_ylabel("Energy (GWh)")
ax.grid(axis="y", linestyle="--", alpha=0.4)

# 2 — Capture Value
ax = axes[1]
if not capture_meur.empty:
    x2 = _labels(capture_meur.index)
    ax.bar(x2, capture_meur.values, color="#27AE60", edgecolor="#145A32")
    ax.set_title(f"Monthly Capture Value – {selected_col} × {price_col} ({selected_year})", fontsize=14)
    ax.set_ylabel("Capture (M€)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
else:
    ax.text(0.5, 0.5, "Price column not found – capture value unavailable", ha="center", va="center")
    ax.axis("off")

# 3 — Capture price
ax = axes[2]
if not capture_meur.empty and not capture_price_eur_per_mwh.empty:
    x3 = _labels(capture_price_eur_per_mwh.index)
    ax.bar(x3, capture_price_eur_per_mwh.values, color="#8E44AD", edgecolor="#4A235A")
    ax.set_title(f"Monthly Capture Price – {selected_col} ({selected_year})", fontsize=14)
    ax.set_xlabel("Month (YYYY-MM)")
    ax.set_ylabel("Capture Price (€/MWh)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
else:
    ax.text(0.5, 0.5, "Price column not found – capture price unavailable", ha="center", va="center")
    ax.axis("off")

st.pyplot(fig, use_container_width=True)

# ---------------- Raw data table ----------------
with st.expander("Show raw aggregated data (click to expand)"):
    out = pd.DataFrame(index=monthly_gwh.index)
    out["Monthly Energy (GWh)"] = monthly_gwh.round(3)
    if not capture_meur.empty:
        out["Monthly Capture (M€)"] = capture_meur.reindex(out.index).round(3)
    if not capture_price_eur_per_mwh.empty:
        out["Monthly Capture Price (€/MWh)"] = capture_price_eur_per_mwh.reindex(out.index).round(2)
    st.dataframe(out)