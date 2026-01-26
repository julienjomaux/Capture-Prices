
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

# ---------------- Data Loading ----------------
@st.cache_data(show_spinner=True)
def load_data(files_glob: str = "Germany *.csv") -> pd.DataFrame:
    """
    Load one or multiple CSV files (e.g., 'Germany 2021.csv' ... 'Germany 2025.csv'),
    auto-detect delimiter, parse dates, and return a single DataFrame.

    Expected date column name: 'Date (GMT+1)' (case-insensitive tolerant).
    """
    paths = sorted(glob.glob(files_glob))
    if not paths:
        # Fallback: try a single file commonly used
        if os.path.exists("Germany 2025.csv"):
            paths = ["Germany 2025.csv"]
        else:
            raise FileNotFoundError(
                "No matching files found. Please place files like 'Germany 2025.csv' "
                "or 'Germany 2021.csv'…'Germany 2025.csv' in the app folder."
            )

    dfs: List[pd.DataFrame] = []
    for p in paths:
        # sep=None + engine='python' auto-detects comma/semicolon, etc.
        df = pd.read_csv(p, encoding="utf-8-sig", sep=None, engine="python")
        df["__SourceFile"] = os.path.basename(p)
        dfs.append(df)

    df_all = pd.concat(dfs, ignore_index=True)

    # Normalize date column name
    date_col_candidates = [
        "Date (GMT+1)", "Date", "Datetime", "Timestamp", "Time (GMT+1)", "time", "date"
    ]
    date_col = None
    for c in date_col_candidates:
        if c in df_all.columns:
            date_col = c
            break
    if date_col is None:
        # Try case-insensitive match
        lower_map = {c.lower(): c for c in df_all.columns}
        for c in [x.lower() for x in date_col_candidates]:
            if c in lower_map:
                date_col = lower_map[c]
                break
    if date_col is None:
        raise KeyError(
            f"Could not find a date column among {date_col_candidates}. "
            f"Columns found: {list(df_all.columns)}"
        )

    # Parse dates
    df_all[date_col] = pd.to_datetime(df_all[date_col], errors="coerce")
    df_all = df_all.dropna(subset=[date_col])
    df_all = df_all.sort_values(by=date_col)

    # Add a unified 'Month' column for grouping
    df_all["Month"] = df_all[date_col].dt.to_period("M").dt.to_timestamp()

    return df_all, date_col

try:
    df, date_col = load_data()
except Exception as e:
    st.error(f"❌ Data loading error: {e}")
    st.stop()

# ---------------- Technology List ----------------
# Try to build from columns; exclude non-tech columns
non_tech_cols = {date_col, "Month", "__SourceFile"}
candidate_techs = [c for c in df.columns if c not in non_tech_cols and df[c].dtype != "O"]

# If the CSV doesn’t contain these tech columns, fallback to your manual list
if not candidate_techs:
    candidate_techs = [
        "Cross border electricity trading", "Hydro Run-of-River", "Biomass", "Fossil brown coal / lignite",
        "Fossil hard coal", "Fossil oil", "Fossil coal-derived gas", "Fossil gas", "Geothermal",
        "Hydro water reservoir", "Hydro pumped storage", "Others", "Waste", "Wind offshore",
        "Wind onshore", "Solar"
    ]
    # Warn if they aren't found
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
# Assumption: values are in MWh per 15-min or hourly; your original note divides by 4000 to get GWh.
# Keeping your original logic: sum per month / 4000 => GWh
monthly_gwh = df.groupby('Month')[selected_tech].sum() / 4000.0

st.subheader(f"Monthly Total Production for {selected_tech} (in GWh)")
st.bar_chart(monthly_gwh)

with st.expander("Show raw monthly values (GWh)"):
    st.write(monthly_gwh.round(2))

st.caption("Total monthly production: values sum per month divided by 4000 (GWh).")
