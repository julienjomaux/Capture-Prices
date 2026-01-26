
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

    
    # ---------------- Monthly average bar chart (dropdown + chart) ----------------

    # 0) Normalize column names to avoid hidden chars (BOM/ZWSP) and trailing spaces
    df.columns = (
        df.columns
          .astype(str)
          .str.replace("\ufeff", "", regex=False)   # BOM
          .str.replace("\u200b", "", regex=False)   # zero-width space
          .str.strip()
    )

    # 1) Skip the units row (the row immediately after the header)
    #    Heuristic: if the first data row contains many "Power (MW)" / "Price (" tokens → drop it
    if not df.empty:
        first_row_str = df.iloc[0].astype(str).str.lower()
        units_hits = first_row_str.str.contains(r"power\s*\(mw\)|price\s*\(", regex=True).mean()
        if units_hits > 0.3:
            df = df.iloc[1:].reset_index(drop=True)

    # 2) Parse the date column (first column): "Date (GMT+1)" like 2025-01-01T00:00+01:00
    #    (Make sure the name exists after normalization)
    date_col = "Date (GMT+1)"
    if date_col not in df.columns:
        # Try to auto-find a similar name if it was slightly different
        possible = [c for c in df.columns if "date" in c.lower()]
        st.error(
            f"Expected date column '{date_col}' not found. "
            f"Columns with 'date' detected: {possible}"
        )
        st.stop()

    # Parse to datetime (timezone-aware)
    # Use explicit format to match e.g. '2025-01-01T00:15+01:00'
    df[date_col] = pd.to_datetime(
        df[date_col].astype(str).str.strip(),
        format="%Y-%m-%dT%H:%M%z",
        errors="coerce"
    )

    # Drop rows where date couldn't be parsed
    bad_dates = df[date_col].isna().sum()
    if bad_dates > 0:
        st.warning(f"Dropping {bad_dates} rows with unparseable dates.")
    df = df[df[date_col].notna()].copy()

    # Remove timezone to make timestamps naive for consistent .dt ops
    if pd.api.types.is_datetime64tz_dtype(df[date_col]):
        try:
            df[date_col] = df[date_col].dt.tz_localize(None)
        except (TypeError, AttributeError):
            df[date_col] = df[date_col].dt.tz_convert("UTC").dt.tz_localize(None)

    # Safety diagnostics (very helpful if something goes wrong)
    # st.write("Date dtype:", df[date_col].dtype)
    # st.write("Sample dates:", df[date_col].head(5))

    # 3) Create a Month column for grouping
    #    (Now that the dtype is datetime64[ns], .dt works without error)
    df["Month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    # 4) Dropdown of all columns except Date and Month
    meta_cols = {date_col, "Month"}
    value_cols = [c for c in df.columns if c not in meta_cols]

    st.subheader("Select a column to plot its monthly average:")
    selected_col = st.selectbox("Column", options=sorted(value_cols))

    # 5) Ensure the selected column is numeric (coerce if needed)
    df[selected_col] = pd.to_numeric(df[selected_col], errors="coerce")

    # 6) Compute monthly average (mean over all timestamps within each month)
    monthly_avg = df.groupby("Month", sort=True)[selected_col].mean()

    # 7) Show the bar chart
    st.subheader(f"Monthly Average of '{selected_col}'")
    st.bar_chart(monthly_avg)

    # Optional: show raw values
    with st.expander("Show raw monthly averages"):
        st.write(monthly_avg.round(3))




