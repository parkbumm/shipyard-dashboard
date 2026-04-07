# app.py 최종
import streamlit as st
from pages import workforce_supply_demand

st.set_page_config(
    page_title="조선소 HR 대시보드",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="expanded",
)

pg = st.navigation([
    st.Page("pages/home.py",               title="인력 구조 분석",   icon="🏗️"),
    st.Page("pages/workforce_planning.py", title="인력 수급 계획",   icon="📊"),
    st.Page("pages/physical_ai.py",        title="Physical AI 영향", icon="🤖"),
    st.Page("pages/workforce_supply_demand", title="인력수급 & AI 전환", icon="📊"),
])
pg.run()