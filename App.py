
import os
import glob
from typing import Optional

import streamlit as st
import pandas as pd

# Optional plotting libs if you extend later
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go

# ---------------- Page config (robust to missing icon) ----------------
try:
    st.set_page_config(layout="wide", page_icon="GEM.webp")
except Exception:
    st.set_page_config(layout="wide")
st.title("aFRR Capacity Prices in Germany (2021–2025)")

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
This app presents heatmaps and daily views of aFRR (automatic Frequency Restoration Reserve) 
capacity prices in Germany for the years 2021–2025. 

- **Heatmaps:** Show monthly average, maximal average, and maximal marginal capacity prices per month and 4-hour product.
- **Daily view:** Displays capacity prices for all 12 products for a selected day.

**Data source:** Regelleistung.net

**More insights:** GEM Energy Analytics  
**Connect with me:** Julien Jomaux  
**Email me:** julien.jomaux@gmail.com
"""
)

st.markdown(
    f"""
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
    
    # ---------------- Show first 50 rows ----------------
    st.subheader("First 50 rows of the CSV")
    st.dataframe(df.head(50))

    
    
   
    # ---------------- Monthly totals (2025 only) + Capture plot ----------------

    # 0) Normalize column names (defensive against BOM/ZWSP/spaces)
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)  # BOM
        .str.replace("\u200b", "", regex=False)  # zero-width space
        .str.strip()
    )

    # 1) Identify the date column as the first column (your CSV format)
    date_col = df.columns[0]  # should be "Date (GMT+1)"

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

    # 6) Build dropdown of columns, excluding date, Month, and Day Ahead Auction
    # Try to locate the price column robustly
    price_col = "Day Ahead Auction (DE-LU)"
    if price_col not in df_2025.columns:
        alt = "Day-ahead Auction (DE-LU)"
        if alt in df_2025.columns:
            price_col = alt
        else:
            possibles = [c for c in df_2025.columns if "auction" in c.lower() and "de-lu" in c.lower()]
            price_col = possibles[0] if possibles else None

    meta_cols = {date_col, "Month"}
    exclude_cols = set(meta_cols)
    if price_col is not None:
        exclude_cols.add(price_col)

    value_cols = [c for c in df_2025.columns if c not in exclude_cols]

    st.subheader("Select a column to plot its monthly totals (GWh):")
    selected_col = st.selectbox("Column", options=sorted(value_cols))

    # 7) Ensure numeric types
    df_2025[selected_col] = pd.to_numeric(df_2025[selected_col], errors="coerce")
    if price_col is not None:
        df_2025[price_col] = pd.to_numeric(df_2025[price_col], errors="coerce")

    # 8) Monthly total energy (GWh): sum(MW) * 0.25h / 1000 = sum(MW) / 4000
    monthly_gwh = df_2025.groupby("Month", sort=True)[selected_col].sum() / 4000.0

    st.subheader(f"Monthly Total Energy of '{selected_col}' in 2025 (GWh)")

    # Labels for x-axis (robust handling of index type)
    idx = monthly_gwh.index
    try:
        x_labels = idx.strftime("%Y-%m")
    except Exception:
        x_labels = idx.astype(str)
    y = monthly_gwh.values

    fig1, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(x_labels, y, color="#2E86DE", edgecolor="#1B4F72")
    ax1.set_title(f"Monthly Total Energy – {selected_col} (2025)", fontsize=14, pad=12)
    ax1.set_xlabel("Month (YYYY-MM)", fontsize=12)
    ax1.set_ylabel("Energy (GWh)", fontsize=12)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    st.pyplot(fig1)

    with st.expander("Show raw monthly totals (GWh)"):
        st.write(monthly_gwh.round(3))

    # 9) Capture value (M€ / month): sum over month of (production * price) / 4,000,000
    #    Explanation: production is MW, price is EUR/MWh, 15-min energy = MW*0.25h,
    #    monthly revenue EUR = sum(MW * EUR/MWh * 0.25). In M€ => divide by 1e6 → same as sum(MW*Price)/4,000,000.
    if price_col is None:
        st.warning("Price column 'Day Ahead Auction (DE-LU)' not found; skipping Capture plot.")
    else:
        capture_meur = (df_2025[selected_col] * df_2025[price_col]).groupby(df_2025["Month"]).sum() / 4_000_000.0

        st.subheader(f"Monthly Capture Value for '{selected_col}' in 2025 (M€)")

        idx2 = capture_meur.index
        try:
            x_labels2 = idx2.strftime("%Y-%m")
        except Exception:
            x_labels2 = idx2.astype(str)
        y2 = capture_meur.values

        fig2, ax2 = plt.subplots(figsize=(12, 5))
        ax2.bar(x_labels2, y2, color="#27AE60", edgecolor="#145A32")
        ax2.set_title(f"Monthly Capture Value – {selected_col} × {price_col} (2025)", fontsize=14, pad=12)
        ax2.set_xlabel("Month (YYYY-MM)", fontsize=12)
        ax2.set_ylabel("Capture (M€)", fontsize=12)
        ax2.grid(axis="y", linestyle="--", alpha=0.4)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        st.pyplot(fig2)

        with st.expander("Show raw monthly capture (M€)"):
            st.write(capture_meur.round(3))










