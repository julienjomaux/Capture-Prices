
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

    

    # ---------------- Load & Parse ----------------
    try:
        df, date_col_candidates = load_data()
    except Exception as e:
        st.error(f"❌ Data loading error: {e}")
        st.stop()


    # Create Month column (first day of the month timestamp)
    
    st.dataframe(df.head(50))


    # ---------------- Make numeric value columns numeric ----------------
    


