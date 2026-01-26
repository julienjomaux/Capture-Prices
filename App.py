
import os
from typing import Optional

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# ---------------- Page config (robust to missing icon) ----------------

st.set_page_config(layout="wide", page_icon="GEM.webp")
st.title("Average Monthly Generation and Capture Prices")

# ---------------- Utilities ----------------
def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Try python-decouple if available; fallback to environment variables.
    """
    try:
        from decouple import config as decouple_config  # type: ignore
        return decouple_config(key, default=default)
    except Exception:
        return os.getenv(key, default)

stripe_link = get_config_value('STRIPE_CHECKOUT_LINK', '#')
secret_password = get_config_value('SECRET_PASSWORD', '')

# ---------------- Description / CTA ----------------
st.markdown(
    """
This app presents the average Generation, captured value and capture prices of Generation in Germany for the last few years. 


**Data source:** Regelleistung.net

**More insights:** GEM Energy Analytics  
**Connect with me:** Julien Jomaux  
**Email me:** julien.jomaux@gmail.com
"""
)

st.markdown(
    """
If you want to access all the apps of GEM Energy Analytics, please sign up following the link below.

Currently, the fee is 30 € per month. When the payment is done, you will receive a password that will grant you access to all apps. Every month, you will receive an email with a new password to access the apps (except if you unsubscribe). 
Feel free to reach out at Julien.jomaux@gmail.com

Sign Up Now :metal:
"""
)

# ---------------- Login Gate ----------------
with st.form("login_form"):
    st.write("Login")
    password = st.text_input('Enter Your Password', type="password")
    submitted = st.form_submit_button("Login")

if submitted:
    if secret_password and (password == secret_password):
        st.session_state['logged_in'] = True
        st.success('Successfully Logged In!')
    else:
        st.session_state['logged_in'] = False
        st.error('Incorrect login credentials.')

is_logged_in = st.session_state.get('logged_in', False)

if not is_logged_in:
    st.info("🔒 Please log in with the password above to access the charts.")
    st.stop()
else:
    # ---------------- Data Loading ----------------
    @st.cache_data
    def load_df(filepath: str):
        return pd.read_csv(
            filepath,
            encoding="utf-8-sig",   # handles BOM safely
            sep=",",                # your file is comma-separated
            engine="python"
        )
    
    # Change this if needed
    CSV_FILE = "Germany 2025.csv"
    
    try:
        df = load_df(CSV_FILE)
        st.success("CSV loaded successfully ✅")
    except Exception as e:
        st.error(f"Failed to load CSV: {e}")
        st.stop()
    
    # ---------------- Cleaning / Preparation ----------------
    # 0) Normalize column names (defensive against BOM/ZWSP/spaces)
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)  # BOM
        .str.replace("\u200b", "", regex=False)  # zero-width space
        .str.strip()
    )

    # 1) Identify the date column as the first column (your CSV format)
    date_col = df.columns[0]  # should be "Date (GMT+1)" or similar

    # 2) Drop the units row if present (the row just after header)
    if not df.empty:
        first_row_str = df.iloc[0].astype(str).str.lower()
        units_hits = first_row_str.str.contains(r"power\s*\(mw\)|price\s*\(", regex=True).mean()
        if units_hits > 0.3:
            df = df.iloc[1:].reset_index(drop=True)

    # 3) Parse datetime robustly, accepting timezone (+01:00), then drop tz
    s = df[date_col].astype(str).str.strip().replace({"": pd.NA})
    df[date_col] = pd.to_datetime(s, errors="coerce", utc=True)
    df = df[df[date_col].notna()].copy()
    df[date_col] = df[date_col].dt.tz_convert("UTC").dt.tz_localize(None)

    # 4) Month column
    df["Month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    # 5) Keep only months in 2025
    df_2025 = df[df["Month"].dt.year == 2025].copy()
    if df_2025.empty:
        st.warning("No data available for 2025 after filtering.")
        st.stop()

    # 6) Try to locate the price column robustly
    price_col = "Day Ahead Auction (DE-LU)"
    if price_col not in df_2025.columns:
        alt = "Day-ahead Auction (DE-LU)"
        if alt in df_2025.columns:
            price_col = alt
        else:
            possibles = [c for c in df_2025.columns if "auction" in c.lower() and "de-lu" in c.lower()]
            price_col = possibles[0] if possibles else None

    # Build list of selectable energy columns (exclude date/month/price)
    meta_cols = {date_col, "Month"}
    exclude_cols = set(meta_cols)
    if price_col is not None:
        exclude_cols.add(price_col)
    value_cols = [c for c in df_2025.columns if c not in exclude_cols]

    selected_col = st.selectbox("Select the column to analyze (energy series in MW):", options=sorted(value_cols))

    # Ensure numeric
    df_2025[selected_col] = pd.to_numeric(df_2025[selected_col], errors="coerce")
    if price_col is not None:
        df_2025[price_col] = pd.to_numeric(df_2025[price_col], errors="coerce")

    # ---------------- Aggregations ----------------
    # Monthly total energy (GWh): sum(MW) * 0.25h / 1000 = sum(MW) / 4000
    monthly_gwh = df_2025.groupby("Month", sort=True)[selected_col].sum() / 4000.0

    # Capture value (M€ / month): sum(MW * EUR/MWh * 0.25) / 1e6 = sum(MW*Price)/4_000_000
    if price_col is None:
        st.warning("Price column 'Day Ahead Auction (DE-LU)' not found; skipping Capture calculations.")
        capture_meur = pd.Series(dtype=float)
        capture_price_eur_per_mwh = pd.Series(dtype=float)
    else:
        capture_meur = (df_2025[selected_col] * df_2025[price_col]).groupby(df_2025["Month"]).sum() / 4_000_000.0

        # Capture Price (€/MWh) = (Monthly Capture M€ / Monthly Production GWh) * 1000
        common_index = monthly_gwh.index.intersection(capture_meur.index)
        monthly_gwh_aligned = monthly_gwh.reindex(common_index)
        capture_meur_aligned = capture_meur.reindex(common_index)

        with pd.option_context("mode.use_inf_as_na", True):
            capture_price_eur_per_mwh = (capture_meur_aligned / monthly_gwh_aligned) * 1000.0
            capture_price_eur_per_mwh = capture_price_eur_per_mwh.replace([pd.NA], 0).fillna(0)

    # ---------------- Plots: all in subplots ----------------
    # Prepare x labels once
    def _labels(idx):
        try:
            return idx.strftime("%Y-%m")
        except Exception:
            return idx.astype(str)

    # Create a single figure with 3 rows of subplots
    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(14, 12), sharex=True)
    plt.subplots_adjust(hspace=0.35)

    # Subplot 1: Monthly Total Energy (GWh)
    ax = axes[0]
    x1 = _labels(monthly_gwh.index)
    ax.bar(x1, monthly_gwh.values, color="#2E86DE", edgecolor="#1B4F72")
    ax.set_title(f"Monthly Total Energy – {selected_col} (2025)", fontsize=14, pad=12)
    ax.set_ylabel("Energy (GWh)", fontsize=12)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Subplot 2: Monthly Capture Value (M€)
    ax = axes[1]
    if not capture_meur.empty:
        x2 = _labels(capture_meur.index)
        ax.bar(x2, capture_meur.values, color="#27AE60", edgecolor="#145A32")
        ax.set_title(f"Monthly Capture Value – {selected_col} × {price_col} (2025)", fontsize=14, pad=12)
        ax.set_ylabel("Capture (M€)", fontsize=12)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
    else:
        ax.text(0.5, 0.5, "Price column not found – capture value unavailable", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")

    # Subplot 3: Monthly Capture Price (€/MWh)
    ax = axes[2]
    if not capture_meur.empty and not capture_price_eur_per_mwh.empty:
        x3 = _labels(capture_price_eur_per_mwh.index)
        ax.bar(x3, capture_price_eur_per_mwh.values, color="#8E44AD", edgecolor="#4A235A")
        ax.set_title(f"Monthly Capture Price – {selected_col} (2025)", fontsize=14, pad=12)
        ax.set_xlabel("Month (YYYY-MM)", fontsize=12)
        ax.set_ylabel("Capture Price (€/MWh)", fontsize=12)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    else:
        ax.text(0.5, 0.5, "Price column not found – capture price unavailable", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")

    st.pyplot(fig, use_container_width=True)

    # ---------------- Raw data at the end only ----------------
    with st.expander("Show raw aggregated data (click to expand)"):
        out = pd.DataFrame(index=monthly_gwh.index)
        out["Monthly Energy (GWh)"] = monthly_gwh.round(3)
        if not capture_meur.empty:
            out["Monthly Capture (M€)"] = capture_meur.reindex(out.index).round(3)
        if not capture_price_eur_per_mwh.empty:
            out["Monthly Capture Price (€/MWh)"] = capture_price_eur_per_mwh.reindex(out.index).round(2)
        st.dataframe(out)

