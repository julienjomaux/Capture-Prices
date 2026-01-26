
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
    @st.cache_data(show_spinner=True)
    def load_data(files_glob: str = "Germany *.csv"):
        """
        Load one or multiple CSV files (e.g., 'Germany 2021.csv' ... 'Germany 2025.csv'),
        auto-detect delimiter, and return a single DataFrame along with likely date columns.
        Also drops a second 'units' header row if present (e.g., ',Power (MW),Power (MW),...').
        """
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
            # Let pandas sniff the delimiter
            df = pd.read_csv(p, encoding="utf-8-sig", sep=None, engine="python")
            df["__SourceFile"] = os.path.basename(p)

            # If the very first data row looks like a units row (Power (MW), Price (EUR/MWh), etc.), drop it.
            if not df.empty:
                first_row_str = df.iloc[0].astype(str)
                # Count how many columns contain 'power (mw)' or 'price (' => heuristic for a units header row
                units_hits = first_row_str.str.lower().str.contains(r"power\s*\(mw\)|price\s*\(", regex=True).mean()
                # If > 30% of columns are 'units', this row is almost certainly the units header => drop it
                if units_hits > 0.3:
                    df = df.iloc[1:].reset_index(drop=True)

            dfs.append(df)

        df_all = pd.concat(dfs, ignore_index=True)

        # Identify likely date columns (by name patterns)
        name_candidates = [
            "Date (GMT+1)", "Date", "Datetime", "Timestamp", "Time (GMT+1)",
            "date", "time", "datetime", "period", "delivery_start", "delivery time",
        ]
        # Also include any column whose name contains date-like words
        for c in list(df_all.columns):
            if any(key in str(c).lower() for key in ["date", "time", "timestamp"]):
                if c not in name_candidates:
                    name_candidates.append(c)

        existing_candidates = [c for c in name_candidates if c in df_all.columns]
        return df_all, existing_candidates

    def try_parse_datetime(series: pd.Series) -> pd.Series:
        """
        Try multiple strategies to coerce a series to datetime.
        Specifically supports ISO 8601 with timezone (e.g., 2025-01-01T00:00+01:00).
        Returns a datetime series; raises if parsing fails badly.
        """
        s = series.copy()

        # Already datetime?
        if pd.api.types.is_datetime64_any_dtype(s):
            return s

        # Clean stray spaces/zero-width chars
        s = s.astype(str).str.strip().str.replace("\u200b", "", regex=False)
        # Empty strings -> NaT
        s = s.replace({"": pd.NA})

        # Strategy A: ISO8601 (with timezone like +01:00)
        s_iso = pd.to_datetime(s, errors="coerce", utc=False, format=None)
        if s_iso.notna().mean() > 0.8:
            return s_iso

        # Strategy B: explicit common formats (with and without timezone)
        common_formats = [
            "%Y-%m-%dT%H:%M%z",     # 2025-01-01T00:00+01:00
            "%Y-%m-%d %H:%M%z",
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
            s_try = pd.to_datetime(s, format=fmt, errors="coerce", utc=False)
            if s_try.notna().mean() > 0.8:
                return s_try

        # Strategy C: numeric timestamps (ms then s)
        s_num = pd.to_numeric(s, errors="coerce")
        if s_num.notna().mean() > 0.8:
            s_ms = pd.to_datetime(s_num, errors="coerce", unit="ms", utc=False)
            if s_ms.notna().mean() > 0.8:
                return s_ms
            s_s = pd.to_datetime(s_num, errors="coerce", unit="s", utc=False)
            if s_s.notna().mean() > 0.8:
                return s_s

        raise ValueError(
            "Failed to parse datetime for the selected column.\n"
            f"Sample values: {series.dropna().astype(str).head(5).tolist()}\n"
        )

    # ---------------- Load & Parse ----------------
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
    date_col = st.selectbox("Date/Time column", options=date_col_candidates, index=0)

    # Try parsing with robust logic
    try:
        df[date_col] = try_parse_datetime(df[date_col])
        # Drop timezone so .dt.to_period('M') works consistently on naive timestamps
        if pd.api.types.is_datetime64tz_dtype(df[date_col]):
            # Try to just remove tz info (keep local time as shown in the CSV)
            try:
                df[date_col] = df[date_col].dt.tz_localize(None)
            except (TypeError, AttributeError):
                # For some tz-aware types, convert to UTC then drop tz
                df[date_col] = df[date_col].dt.tz_convert("UTC").dt.tz_localize(None)
    except Exception as e:
        st.error(f"❌ Date parse error for '{date_col}': {e}")
        with st.expander("Show column samples and dtypes"):
            st.write("Detected columns and dtypes:")
            st.write(df.dtypes)
            st.write("First 10 non-null samples from the selected column:")
            st.write(df[date_col].dropna().head(10))
        st.stop()

    # Remove rows without a valid datetime
    df = df[df[date_col].notna()].copy()

    # Create Month column (first day of the month timestamp)
    df["Month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    # ---------------- Make numeric value columns numeric ----------------
    # Convert all non-date, non-meta columns to numeric where possible
    meta_cols = {date_col, "Month", "__SourceFile"}
    value_cols = [c for c in df.columns if c not in meta_cols]
    for c in value_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # ---------------- Technology List ----------------
    # Derive candidates from numeric columns and exclude obvious non-tech columns
    exclude_keywords = [
        "price", "avg", "mean", "marginal", "min", "max", "product",
        "hour", "quarter", "period", "auction", "load"
    ]
    numeric_cols = set(df.select_dtypes(include="number").columns)
    candidate_techs = []
    for c in sorted(numeric_cols):
        if c in meta_cols:
            continue
        # exclude via name keywords
        low = str(c).lower()
        if any(k in low for k in exclude_keywords):
            continue
        candidate_techs.append(c)

    # Fallback list if nothing is detected
    if not candidate_techs:
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

    # ---------------- Monthly Aggregations ----------------
    # Average monthly production (as average power in MW):
    monthly_avg_mw = df.groupby("Month", sort=True)[selected_tech].mean()

    # Total monthly energy in GWh (sum of 15-min MW -> MWh -> GWh):
    # Each 15-min interval contributes MW * 0.25 hours = MWh; divide by 1000 for GWh.
    # => sum(MW) * (0.25 / 1000) = sum(MW) / 4000
    monthly_gwh = df.groupby("Month", sort=True)[selected_tech].sum() / 4000.0

    # ---------------- Charts ----------------
    st.subheader(f"Monthly Production for {selected_tech}")
    tabs = st.tabs(["Average (MW)", "Total (GWh)"])

    with tabs[0]:
        st.bar_chart(monthly_avg_mw)
        with st.expander("Show raw monthly averages (MW)"):
            st.write(monthly_avg_mw.round(2))

    with tabs[1]:
        st.bar_chart(monthly_gwh)
        with st.expander("Show raw monthly totals (GWh)"):
            st.write(monthly_gwh.round(3))

    st.caption(
        "Notes: Average monthly production is the average power (MW) across all 15‑minute intervals in the month. "
        "Total monthly energy equals the sum of MW across 15‑minute intervals divided by 4000 (GWh)."
    )
