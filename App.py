
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

    # 0) Normalize column names to avoid invisible chars and extra spaces
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)  # BOM
        .str.replace("\u200b", "", regex=False)  # zero-width space
        .str.strip()
    )

    # 1) Determine the date column as the FIRST column, per your file layout
    date_col = df.columns[0]  # should be "Date (GMT+1)"
    # Optional: assert it's the expected name; we keep the first column anyway
    # but this helps you notice if the header changed.
    if "date" not in date_col.lower():
        st.warning(f"The first column doesn't look like a date: '{date_col}'. Proceeding anyway.")

    # 2) Drop the units row (row immediately after the header) if it looks like units
    #    Heuristic: if first data row contains many "Power (MW)" or "Price (" tokens -> drop it
    if not df.empty:
        first_row_str = df.iloc[0].astype(str).str.lower()
        units_hits = first_row_str.str.contains(r"power\s*\(mw\)|price\s*\(", regex=True).mean()
        if units_hits > 0.3:
            df = df.iloc[1:].reset_index(drop=True)

    # 3) Parse the date column robustly:
    #    Use utc=True to parse timezone offsets like +01:00 reliably, then drop tz for .dt ops.
    s = df[date_col].astype(str).str.strip().replace({"": pd.NA})
    df[date_col] = pd.to_datetime(s, errors="coerce", utc=True)

    # Drop rows where date couldn't be parsed
    bad_dates = int(df[date_col].isna().sum())
    if bad_dates > 0:
        st.warning(f"Dropping {bad_dates} rows with unparseable dates in '{date_col}'.")
    df = df[df[date_col].notna()].copy()

    # Remove timezone (make naive) for consistent .dt behavior
    # At this point it's datetime64[ns, UTC]; convert to naive local-like timestamps
    df[date_col] = df[date_col].dt.tz_convert("UTC").dt.tz_localize(None)

    # SAFETY CHECK: ensure datetimelike before using .dt
    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        st.error(
            f"Date column '{date_col}' is not datetimelike after parsing. "
            f"Dtype = {df[date_col].dtype}. Showing samples below."
        )
        st.write(df[[date_col]].head(10))
        st.stop()

    # 4) Create Month column (first day-of-month as Timestamp)
    df["Month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    # 5) Build dropdown of all column names except date and Month
    meta_cols = {date_col, "Month"}
    value_cols = [c for c in df.columns if c not in meta_cols]

    st.subheader("Select a column to plot its monthly average:")
    selected_col = st.selectbox("Column", options=sorted(value_cols))

    # 6) Ensure selected column is numeric (coerce if needed)
    df[selected_col] = pd.to_numeric(df[selected_col], errors="coerce")

   

    # 6) Compute monthly total energy in GWh: sum(MW) * 0.25 h / 1000 = sum(MW) / 4000
    monthly_gwh = df.groupby("Month", sort=True)[selected_col].sum() / 4000.0
    
    # 7) Plot with matplotlib (plt)
    st.subheader(f"Monthly Total Energy of '{selected_col}' (GWh)")
    
    # Robust handling of index types for labels
    idx = monthly_gwh.index
    try:
        # If DatetimeIndex -> strftime works
        x_labels = idx.strftime("%Y-%m")
    except Exception:
        # Fallback: stringify (works for PeriodIndex or plain Index)
        x_labels = idx.astype(str)
    
    y = monthly_gwh.values
    
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x_labels, y, color="#2E86DE", edgecolor="#1B4F72")
    
    ax.set_title(f"Monthly Total Energy – {selected_col}", fontsize=14, pad=12)
    ax.set_xlabel("Month (YYYY-MM)", fontsize=12)
    ax.set_ylabel("Energy (GWh)", fontsize=12)
    
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    
    st.pyplot(fig)
    
    with st.expander("Show raw monthly totals (GWh)"):
        st.write(monthly_gwh.round(3))









