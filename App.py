
import os
import glob
from typing import Optional, List

import streamlit as st
import pandas as pd

# Optional plotting libs if you extend later
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go

from datetime import date

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
    @st.cache_data(show_spinner=True)
    def load_data(files_glob: str = "Germany *.csv"):
        """
        Load one or multiple CSV files (e.g., 'Germany 2021.csv' ... 'Germany 2025.csv'),
        auto-detect delimiter, and return a single DataFrame with best-effort datetime parsing.
        """
        import numpy as np
        paths = sorted(glob.glob(files_glob))
        if not paths:
            if os.path.exists("Germany 2025.csv"):
                paths = ["Germany 2025.csv"]
            else:
                raise FileNotFoundError(
                    "No matching files found. Please place files like 'Germany 2025.csv' "
                    "or 'Germany 2021.csv'…'Germany 2025.csv' in the app folder."
                )
    
        dfs = []
        for p in paths:
            df = pd.read_csv(p, encoding="utf-8-sig", sep=None, engine="python")
            df["__SourceFile"] = os.path.basename(p)
            dfs.append(df)
    
        df_all = pd.concat(dfs, ignore_index=True)
    
        # Identify likely date columns (by name patterns and dtype/object)
        name_candidates = [
            "Date (GMT+1)", "Date", "Datetime", "Timestamp", "Time (GMT+1)",
            "date", "time", "datetime", "period", "delivery_start", "delivery time",
        ]
        # Add heuristic: columns whose name contains 'date' or 'time'
        for c in list(df_all.columns):
            if any(key in c.lower() for key in ["date", "time", "timestamp"]):
                if c not in name_candidates:
                    name_candidates.append(c)
    
        existing_candidates = [c for c in name_candidates if c in df_all.columns]
    
        # We won't parse here; we'll return both and let a parsing function run after user selection.
        return df_all, existing_candidates
    
    
    def try_parse_datetime(series: pd.Series) -> pd.Series:
        """
        Try multiple strategies to coerce a series to datetime.
        Returns a datetime64[ns] series or raises a ValueError with diagnostics.
        """
        s = series.copy()
    
        # Already datetime?
        if pd.api.types.is_datetime64_any_dtype(s):
            return s
    
        # Common issues: commas in date (e.g., "01/02/2025, 12:00"), extra spaces
        s = s.astype(str).str.strip().str.replace("\u200b", "", regex=False)
    
        # Strategy 1: pandas to_datetime with dayfirst=False and infer
        s1 = pd.to_datetime(s, errors="coerce", infer_datetime_format=True, utc=False)
        if s1.notna().mean() > 0.8:
            return s1
    
        # Strategy 2: dayfirst=True (European-style)
        s2 = pd.to_datetime(s, errors="coerce", dayfirst=True, infer_datetime_format=True, utc=False)
        if s2.notna().mean() > 0.8:
            return s2
    
        # Strategy 3: numeric timestamps (seconds or ms)
        # Detect if numeric-like
        s_num = pd.to_numeric(s, errors="coerce")
        if s_num.notna().mean() > 0.8:
            # Try ms first (values very large), then seconds
            s3 = pd.to_datetime(s_num, errors="coerce", unit="ms", utc=False)
            if s3.notna().mean() > 0.8:
                return s3
            s4 = pd.to_datetime(s_num, errors="coerce", unit="s", utc=False)
            if s4.notna().mean() > 0.8:
                return s4
    
        # Strategy 4: last resort—explicit formats commonly seen
        common_formats = [
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%d-%m-%Y %H:%M",
            "%Y.%m.%d %H:%M",
        ]
        for fmt in common_formats:
            try:
                s5 = pd.to_datetime(s, format=fmt, errors="coerce")
                if s5.notna().mean() > 0.8:
                    return s5
            except Exception:
                pass
    
        # If we reach here, parsing failed badly
        na_rate_1 = s1.isna().mean() if 's1' in locals() else 1.0
        na_rate_2 = s2.isna().mean() if 's2' in locals() else 1.0
        raise ValueError(
            "Failed to parse datetime for the selected column.\n"
            f"Sample values: {series.dropna().astype(str).head(5).tolist()}\n"
            f"to_datetime (dayfirst=False) NA ratio: {na_rate_1:.2f}\n"
            f"to_datetime (dayfirst=True) NA ratio: {na_rate_2:.2f}\n"
            "Tip: Ensure the column truly contains date/time values, not labels."
        )
    
    try:
        df, date_col_candidates = load_data()
    except Exception as e:
        st.error(f"❌ Data loading error: {e}")
        st.stop()
    
    st.markdown("### Choose the date/time column")
    if not date_col_candidates:
        st.error(
            "I couldn't auto-detect a date column. "
            "Please verify your CSV has a date/time column (e.g., 'Date (GMT+1)')."
        )
        st.write("Columns detected:", list(df.columns))
        st.stop()
    
    # Let the user override which column is the datetime
    date_col = st.selectbox("Date/Time column", options=date_col_candidates)
    
    # Try parsing with robust logic
    try:
        df[date_col] = try_parse_datetime(df[date_col])
    except Exception as e:
        st.error(f"❌ Date parse error for '{date_col}': {e}")
        with st.expander("Show column samples and dtypes"):
            st.write("Detected columns and dtypes:")
            st.write(df.dtypes)
            st.write("First 10 non-null samples from the selected column:")
            st.write(df[date_col].dropna().head(10))
        st.stop()
    
    # Create Month column
    df["Month"] = df[date_col].dt.to_period("M").dt.to_timestamp()
    
    # ---------------- Technology List ----------------
    non_tech_cols = {date_col, "Month", "__SourceFile"}
    # Consider numeric columns as candidate technologies; filter out obvious non-tech by name
    exclude_keywords = ["price", "avg", "mean", "marginal", "min", "max", "product", "hour", "quarter", "period"]
    candidate_techs = []
    for c in df.columns:
        if c in non_tech_cols:
            continue
        if df[c].dtype == "O":
            continue
        if any(k in c.lower() for k in exclude_keywords):
            continue
        candidate_techs.append(c)
    
    if not candidate_techs:
        # Fallback to your predefined list
        candidate_techs = [
            "Cross border electricity trading","Hydro Run-of-River","Biomass","Fossil brown coal / lignite",
            "Fossil hard coal","Fossil oil","Fossil coal-derived gas","Fossil gas","Geothermal",
            "Hydro water reservoir","Hydro pumped storage","Others","Waste","Wind offshore",
            "Wind onshore","Solar"
        ]
        missing = [c for c in candidate_techs if c not in df.columns]
        if missing:
            st.warning(
                "Some expected technology columns were not found in the data: "
                + ", ".join(missing)
            )
    
    st.subheader("Select the technology to visualize:")
    selected_tech = st.selectbox("Technology", candidate_techs)
    
    if selected_tech not in df.columns:
        st.error(f"Selected technology '{selected_tech}' not found in the data columns.")
        st.stop()
    
    # ---------------- Monthly Aggregation & Chart ----------------
    monthly_gwh = df.groupby('Month')[selected_tech].sum() / 4000.0
    
    st.subheader(f"Monthly Total Production for {selected_tech} (in GWh)")
    st.bar_chart(monthly_gwh)
    
    with st.expander("Show raw monthly values (GWh)"):
        st.write(monthly_gwh.round(2))
    
    st.caption("Total monthly production: values sum per month divided by 4000 (GWh).")


