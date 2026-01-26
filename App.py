import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
from datetime import date
import os
import glob
from typing import Optional, List, Dict

st.set_page_config(layout="wide", page_icon="GEM.webp")
st.title("aFRR Capacity Prices in Germany (2021–2025)")


# -------------------------------


# ---------------- Top: Sign-up / Login section ----------------

def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    # Try python-decouple if available; fallback to environment variables
    try:
        from decouple import config as decouple_config  # type: ignore
        return decouple_config(key, default=default)
    except Exception:
        return os.getenv(key, default)


stripe_link = get_config_value('STRIPE_CHECKOUT_LINK', '#')
secret_password = get_config_value('SECRET_PASSWORD', '')

# Description and data source
# -------------------------------
st.markdown(
    """
This app presents heatmaps and daily views of aFRR (automatic Frequency Restoration Reserve) 
capacity prices in Germany for the years 2021–2025. 

- **Heatmaps:** Show monthly average, maximal average, and maximal marginal capacity prices per month and 4-hour product.
- **Daily view:** Displays capacity prices for all 12 products for a selected day.

**Data source:** [Regelleistung.net](https://www.regelleistung.net/)

**More insights:** [GEM Energy Analytics](https://gemenergyanalytics.substack.com/)  
**Connect with me:** [Julien Jomaux](https://www.linkedin.com/in/julien-jomaux/)  
**Email me:** [julien.jomaux@gmail.com](mailto:julien.jomaux@gmail.com)
"""
)

st.markdown(
    f"""
    If you want to access all the apps of GEM Energy Analytics, please sign up following the link below. 

    Currently, the fee is 30 € per month. When the payment is done, you will receive an password that will grant you access to all apps. Every month, you will receive an email with a new password to access the apps (except if you unsubscribe). 
    Feel free to reach out at Julien.jomaux@gmail.com

    [Sign Up Now :metal:]({stripe_link})
    """
)

with st.form("login_form"):
    st.write("Login")
    # Email removed as requested; password only
    password = st.text_input('Enter Your Password', type="password")
    submitted = st.form_submit_button("Login")

if submitted:
    if secret_password and (password == secret_password):
        st.session_state['logged_in'] = True
        st.success('Successfully Logged In!')
    else:
        st.session_state['logged_in'] = False
        st.error('Incorrect login credentials.')

# --------------- GATED CONTENT: only visible after successful login ---------------
is_logged_in = st.session_state.get('logged_in', False)

if not is_logged_in:
    st.info("🔒 Please log in with the password above to access the charts.")
else:
    @st.cache_data
    def load_data():
        file_path = "Germany 2025.csv"
        with open(file_path, encoding="utf-8-sig") as f:
            lines = f.readlines()
        # Remove blank lines if any
        st.write(repr(lines[:5]))
        lines = [line for line in lines if line.strip()]
        # Keep header, skip second line, use rest
        csv_content = ''.join([lines[0]] + lines[2:])
        # If comma separator is used, do NOT specify delimiter
        # If semicolon, add delimiter=';'
        df = pd.read_csv(io.StringIO(csv_content))
        # If you need semicolon delimiter:
        # df = pd.read_csv(io.StringIO(csv_content), delimiter=';')
        df['Date (GMT+1)'] = pd.to_datetime(df['Date (GMT+1)'])
    return df
    
    technologies = [
        "Cross border electricity trading","Hydro Run-of-River","Biomass","Fossil brown coal / lignite",
        "Fossil hard coal","Fossil oil","Fossil coal-derived gas","Fossil gas","Geothermal",
        "Hydro water reservoir","Hydro pumped storage","Others","Waste","Wind offshore",
        "Wind onshore","Solar"
    ]
    
    st.subheader("Select the technology to visualize:")
    selected_tech = st.selectbox("Technology", technologies)
    
    # Create Month column for grouping
    df['Month'] = df['Date (GMT+1)'].dt.to_period('M').dt.to_timestamp()
    
    # Aggregate total production per month (sum, divided by 4000 -> GWh)
    monthly_gwh = df.groupby('Month')[selected_tech].sum() / 4000
    
    st.subheader(f"Monthly Total Production for {selected_tech} (in GWh)")
    st.bar_chart(monthly_gwh)
    
    with st.expander("Show raw monthly values (GWh)"):
        st.write(monthly_gwh.round(2))
    
    st.caption("Total monthly production: values sum per month divided by 4000 (GWh).")





