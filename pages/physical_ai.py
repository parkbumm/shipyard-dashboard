# pages/3_피지컬AI_인력영향.py
"""
Physical AI 도입률 × 직무 × 연도 매트릭스를 기반으로
- AI 대체 인원 계산
- 과부족 GAP 재계산
- 미래 인력 구조 인사이트 제공
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    [data-testid="metric-container"] {
        background: #0f1724;
        border: 1px solid #1e3a5f;
        border-radius: 10px;
        padding: 12px 16px;
    }
    .insight-card {
        background: linear-gradient(135deg, #0f1724 0%, #1a2a3a 100%);
        border: 1px solid #1e3a5f;
        border-left: 4px solid #00d4ff;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 8px 0;
        font-size: 0.92rem;
        line-height: 1.6;
    }
    .insight-card.warning { border-left-color: #ff6b35; }
    .insight-card.success { border-left-color: #00e676; }
    .insight-card.info    { border-left-color: #ffd600; }
    .section-header {
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #00d4ff;
        margin-bottom: 4px;
    }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Supabase 연결 ────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = get_supabase()

# ── 데이터 로드 ──────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_base_data():
    jobs     = pd.DataFrame(supabase.table("jobs").select("*").execute().data)
    demand   = pd.DataFrame(supabase.table("workforce_demand").select("*").execute().data)
    supply   = pd.DataFrame(supabase.table("workforce_supply").select("*").execute().data)
    gap      = pd.DataFrame(supabase.table("gap_analysis").select("*").execute().data)
    ai_rates = pd.DataFrame(supabase.table("job_ai_adoption").select("*").execute().data)
    demand   = demand.merge(jobs[["id","job_name","department"]], left_on="job_id", right_on="id", how="left")
    return jobs, demand, supply, gap, ai_rates

@st.cache_data(ttl=300)
def load_ai_adoption():
    try:
        rows = supabase.table("job_ai_adoption").select("*").execute().data
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()

with st.spinner("데이터 로딩 중..."):
    jobs, demand, supply, gap, ai_rates_db = load_base_data()

YEARS      = list(range(2025, 2031))
JOB_NAMES  = sorted(jobs["job_name"].tolist())
SCENARIOS  = ["BASE", "OPTIMISTIC", "PESSIMISTIC"]

# ── 사이드바 ─────────────────────────────────────────────────────────
st.sidebar.title("🤖 Physical AI 설정")
st.sidebar.markdown("---")

sel_scenario = st.sidebar.selectbox(
    "기준 시나리오",
    SCENARIOS,
    format_func=lambda x: {"BASE":"기준","OPTIMISTIC":"낙관","PESSIMISTIC":"비관"}[x],
)

sel_years = st.sidebar.slider("분석 연도 범위", 2025, 2030, (2025, 2030))

st.sidebar.markdown("---")
st.sidebar.markdown("#### 📥 AI 적용률 저장 / 초기화")

col_save, col_reset = st.sidebar.columns(2)

# ── session_state: AI 적용률 매트릭스 초기화 ────────────────────────
STATE_KEY = "ai_adoption_matrix"

def init_matrix(ai_rates_db, job_names, years):
    """DB 값 있으면 로드, 없으면 0으로 초기화"""
    matrix = {}
    for job in job_names:
        for yr in years:
            matrix[(job, yr)] = 0.0
    if not ai_rates_db.empty:
        for _, row in ai_rates_db.iterrows():
            key = (row["job_name"], int(row["plan_year"]))
            if key in matrix:
                matrix[key] = float(row["ai_rate"])
    return matrix

if STATE_KEY not in st.session_state:
    st.session_state[STATE_KEY] = init_matrix(ai_rates_db, JOB_NAMES, YEARS)

matrix = st.session_state[STATE_KEY]

# ── 저장 / 초기화 버튼 ──────────────────────────────────────────────
with col_save:
    if st.button("💾 저장", use_container_width=True):
        rows = []
        for (job, yr), rate in st.session_state[STATE_KEY].items():
            rows.append({"job_name": job, "plan_year": yr, "ai_rate": rate})
        try:
            for i in range(0, len(rows), 50):
                supabase.table("job_ai_adoption").upsert(
                    rows[i:i+50],
                    on_conflict="job_name,plan_year"
                ).execute()
            load_base_data.clear()
            st.sidebar.success("✅ 저장 완료")
        except Exception as e:
            st.sidebar.error(f"❌ 저장 실패: {e}")

with col_reset:
    if st.button("↺ 초기화", use_container_width=True):
        st.session_state[STATE_KEY] = init_matrix(pd.DataFrame(), JOB_NAMES, YEARS)
        st.rerun()

st.sidebar.markdown("---")

# ── 페이지 타이틀 ────────────────────────────────────────────────────
st.title("🤖 Physical AI 도입 — 인력 구조 영향 분석")
st.caption("직무별 AI 대체율을 연도별로 시뮬레이션하고, 과부족 GAP 재계산 및 미래 인력 구조 인사이트를 제공합니다.")
st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECTION 1: 직무 × 연도 AI 적용률 매트릭스 입력
# ══════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-header">① AI 적용률 매트릭스 입력</p>', unsafe_allow_html=True)
st.caption("직무를 선택하고 연도별 Physical AI 대체율(%)을 입력하세요. 입력 후 사이드바에서 💾 저장하면 DB에 반영됩니다.")

input_col, preview_col = st.columns([1, 2], gap="large")

with input_col:
    sel_input_job = st.selectbox(
        "✏️ 입력할 직무 선택",
        JOB_NAMES,
        key="input_job_select",
    )
    st.markdown(f"**{sel_input_job}** — 연도별 AI 대체율 (%)")
    st.caption("0% = AI 미적용  /  100% = 전면 대체")

    for yr in YEARS:
        cur = float(st.session_state[STATE_KEY].get((sel_input_job, yr), 0.0))
        new_val = st.slider(
            label=f"{yr}년",
            min_value=0.0,
            max_value=100.0,
            value=cur,
            step=5.0,
            format="%.0f%%",
            key=f"ai_{sel_input_job}_{yr}",
        )
        st.session_state[STATE_KEY][(sel_input_job, yr)] = new_val

    st.markdown("---")
    rate_cols = st.columns(len(YEARS))
    for i, yr in enumerate(YEARS):
        rate = st.session_state[STATE_KEY][(sel_input_job, yr)]
        rate_cols[i].metric(label=str(yr), value=f"{rate:.0f}%")

with preview_col:
    st.markdown("##### 전체 AI 적용률 현황 (%)")

    matrix_df = pd.DataFrame(
        {yr: {job: st.session_state[STATE_KEY][(job, yr)] for job in JOB_NAMES} for yr in YEARS}
    )
    matrix_df.index.name = "직무"

    applied_count = sum(
        1 for job in JOB_NAMES
        if any(st.session_state[STATE_KEY][(job, yr)] > 0 for yr in YEARS)
    )
    st.caption(f"AI 적용률 입력 완료 직무: **{applied_count}** / {len(JOB_NAMES)}개")

    fig_matrix = px.imshow(
        matrix_df,
        text_auto=".0f",
        color_continuous_scale="Blues",
        zmin=0, zmax=100,
        aspect="auto",
        labels={"color": "AI 대체율(%)"},
        height=360,
    )
    fig_matrix.update_layout(
        margin=dict(t=10, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(
            title="대체율(%)",
            tickvals=[0, 25, 50, 75, 100],
        ),
    )
    fig_matrix.update_xaxes(tickangle=0)
    if sel_input_job in list(matrix_df.index):
        row_idx = list(matrix_df.index).index(sel_input_job)
        fig_matrix.add_shape(
            type="rect",
            x0=-0.5, x1=len(YEARS) - 0.5,
            y0=row_idx - 0.5, y1=row_idx + 0.5,
            line=dict(color="#00d4ff", width=2),
            fillcolor="rgba(0,212,255,0.06)",
        )
    st.plotly_chart(fig_matrix, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECTION 2: AI 대체 인원 계산 & GAP 재계산
# ══════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-header">② AI 도입 후 GAP 재계산</p>', unsafe_allow_html=True)

# 기준 수요·공급 데이터 준비
demand_filt = demand[
    (demand["scenario"] == sel_scenario) &
    (demand["plan_year"].between(*sel_years))
].copy()

supply_filt = supply[
    supply["supply_year"].between(*sel_years)
].copy()

# 직무별 job_id 매핑
job_id_map = dict(zip(jobs["job_name"], jobs["id"]))

# AI 대체 인원 계산
rows_recalc = []
for _, d_row in demand_filt.iterrows():
    yr        = d_row["plan_year"]
    job_name  = d_row["job_name"]
    req_hc    = d_row["required_headcount"]
    ai_rate   = st.session_state[STATE_KEY].get((job_name, yr), 0.0) / 100.0
    ai_hc     = round(req_hc * ai_rate, 1)          # AI 대체 인원
    adj_req   = round(req_hc * (1 - ai_rate), 1)    # AI 적용 후 실제 필요 인원

    # 공급 조회
    jid = job_id_map.get(job_name)
    sup_row = supply_filt[
        (supply_filt["job_id"] == jid) &
        (supply_filt["supply_year"] == yr)
    ]
    net_sup = float(sup_row["net_supply"].values[0]) if not sup_row.empty else 0.0

    # 원래 GAP vs AI 적용 후 GAP
    orig_gap = round(req_hc - net_sup, 1)
    new_gap  = round(adj_req - net_sup, 1)

    rows_recalc.append({
        "연도":         yr,
        "직무":         job_name,
        "원래_수요":    req_hc,
        "AI대체율(%)":  round(ai_rate * 100, 1),
        "AI대체_인원":  ai_hc,
        "조정수요":     adj_req,
        "공급":         net_sup,
        "원래_GAP":     orig_gap,
        "조정_GAP":     new_gap,
        "GAP개선":      round(orig_gap - new_gap, 1),
    })

recalc_df = pd.DataFrame(rows_recalc)

# ── 연도별 AI 대체 인원 누적 막대 ────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("📉 연도별 AI 대체 인원")
    st.caption("직무별 AI가 대체하는 인원 규모 추이")

    ai_yr = recalc_df.groupby(["연도","직무"])["AI대체_인원"].sum().reset_index()
    fig_ai = px.bar(
        ai_yr, x="연도", y="AI대체_인원", color="직무",
        barmode="stack", text_auto=".1f",
        labels={"AI대체_인원":"AI 대체 인원(명)","연도":"연도"},
        height=380,
        color_discrete_sequence=px.colors.sequential.Blues_r[:len(JOB_NAMES)],
    )
    fig_ai.update_layout(
        legend=dict(orientation="h", y=-0.3),
        margin=dict(t=10, b=60),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickmode="linear", dtick=1),
    )
    st.plotly_chart(fig_ai, use_container_width=True)

with col_b:
    st.subheader("🔄 GAP 변화: AI 적용 전 vs 후")
    st.caption("양수=부족, 음수=과잉 | AI 도입으로 인한 부족 완화 효과")

    gap_compare = recalc_df.groupby("연도")[["원래_GAP","조정_GAP"]].sum().reset_index()
    fig_gap = go.Figure()
    fig_gap.add_trace(go.Bar(
        x=gap_compare["연도"], y=gap_compare["원래_GAP"],
        name="AI 도입 전 GAP", marker_color="#F44336",
        text=gap_compare["원래_GAP"].apply(lambda x: f"{x:+.1f}"),
        textposition="outside",
    ))
    fig_gap.add_trace(go.Bar(
        x=gap_compare["연도"], y=gap_compare["조정_GAP"],
        name="AI 도입 후 GAP", marker_color="#00d4ff",
        text=gap_compare["조정_GAP"].apply(lambda x: f"{x:+.1f}"),
        textposition="outside",
    ))
    fig_gap.add_hline(y=0, line_width=1.5, line_color="gray", line_dash="dot")
    fig_gap.update_layout(
        barmode="group", height=380,
        legend=dict(orientation="h", y=-0.2),
        margin=dict(t=10, b=60),
        yaxis_title="과부족 인원(명)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickmode="linear", dtick=1),
    )
    st.plotly_chart(fig_gap, use_container_width=True)

st.divider()

# ── GAP 히트맵: AI 적용 후 ───────────────────────────────────────────
st.subheader("🗺️ AI 도입 후 직무별 과부족 히트맵")
st.caption("빨강=부족 / 초록=과잉 | AI 도입이 반영된 새 GAP")

gap_pivot_new = recalc_df.pivot_table(
    index="직무", columns="연도", values="조정_GAP", aggfunc="sum"
).round(1)

fig_hm = px.imshow(
    gap_pivot_new, text_auto=".1f",
    color_continuous_scale="RdYlGn_r",
    color_continuous_midpoint=0,
    labels={"color":"과부족(명)"},
    aspect="auto", height=360,
)
fig_hm.update_layout(
    margin=dict(t=10, b=40),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig_hm, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECTION 3: 직무별 수요-공급 추이 (AI 적용 전·후 동시 표시)
# ══════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-header">③ 직무별 수요·공급 상세 비교</p>', unsafe_allow_html=True)

# AI 적용률이 1개 연도 이상 0 초과인 직무만 필터링
ai_applied_jobs = sorted([
    job for job in JOB_NAMES
    if any(
        st.session_state[STATE_KEY].get((job, yr), 0.0) > 0
        for yr in YEARS
    )
])

if not ai_applied_jobs:
    st.info("💡 AI 적용률이 입력된 직무가 없습니다. 위 ① 매트릭스에서 값을 입력하면 이 섹션이 활성화됩니다.")
    st.stop()

sel_job = st.selectbox(
    f"직무 선택 (AI 적용률 입력된 직무만 표시 — {len(ai_applied_jobs)}개)",
    ai_applied_jobs,
    key="detail_job",
)

job_detail = recalc_df[recalc_df["직무"] == sel_job].sort_values("연도")

fig_detail = go.Figure()

# 원래 수요
fig_detail.add_trace(go.Scatter(
    x=job_detail["연도"], y=job_detail["원래_수요"],
    name="수요 (AI 前)", mode="lines+markers",
    line=dict(color="#F44336", width=2, dash="solid"),
    marker=dict(size=7),
))
# 조정 수요
fig_detail.add_trace(go.Scatter(
    x=job_detail["연도"], y=job_detail["조정수요"],
    name="수요 (AI 後)", mode="lines+markers",
    line=dict(color="#00d4ff", width=2.5, dash="solid"),
    marker=dict(size=7),
    fill="tonexty",
    fillcolor="rgba(0,212,255,0.08)",
))
# 공급
fig_detail.add_trace(go.Scatter(
    x=job_detail["연도"], y=job_detail["공급"],
    name="공급 (순 가용)", mode="lines+markers",
    line=dict(color="#00e676", width=2, dash="dot"),
    marker=dict(size=7),
))
# AI 대체 인원 (bar)
fig_detail.add_trace(go.Bar(
    x=job_detail["연도"], y=job_detail["AI대체_인원"],
    name="AI 대체 인원",
    marker_color="rgba(255,214,0,0.35)",
    marker_line_color="#ffd600",
    marker_line_width=1.2,
    yaxis="y2",
))

fig_detail.update_layout(
    height=440,
    title=f"{sel_job} — AI 도입 前·後 수요·공급 비교 ({sel_scenario} 시나리오)",
    xaxis_title="연도",
    yaxis_title="인원(명)",
    yaxis2=dict(
        title="AI 대체 인원(명)",
        overlaying="y", side="right",
        showgrid=False,
        range=[0, job_detail["AI대체_인원"].max() * 3 if job_detail["AI대체_인원"].max() > 0 else 10],
    ),
    legend=dict(orientation="h", y=-0.25),
    hovermode="x unified",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(tickmode="linear", dtick=1),
)
st.plotly_chart(fig_detail, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECTION 4: 미래 인력 구조 인사이트
# ══════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-header">④ 미래 인력 구조 인사이트</p>', unsafe_allow_html=True)

# 인사이트 계산
total_ai_replace   = recalc_df["AI대체_인원"].sum()
total_orig_shortage= recalc_df[recalc_df["원래_GAP"] > 0]["원래_GAP"].sum()
total_new_shortage = recalc_df[recalc_df["조정_GAP"] > 0]["조정_GAP"].sum()
shortage_relief    = total_orig_shortage - total_new_shortage

# 가장 AI 영향 큰 직무 (2030년 기준)
last_yr = recalc_df[recalc_df["연도"] == sel_years[1]]
top_ai_job  = last_yr.sort_values("AI대체_인원", ascending=False).iloc[0] if not last_yr.empty else None
top_gap_job = last_yr.sort_values("조정_GAP", ascending=False).iloc[0] if not last_yr.empty else None
surplus_jobs = last_yr[last_yr["조정_GAP"] < -2].sort_values("조정_GAP")

# KPI 카드
k1, k2, k3, k4 = st.columns(4)
k1.metric("🤖 총 AI 대체 누적 인원", f"{total_ai_replace:.0f}명",
          f"{sel_years[0]}~{sel_years[1]} 누계", delta_color="off")
k2.metric("📉 부족 인원 완화 효과", f"{shortage_relief:.0f}명",
          f"원래 {total_orig_shortage:.0f}명 → 조정 {total_new_shortage:.0f}명",
          delta_color="normal")
k3.metric("🔴 AI 후에도 부족 직무 수",
          f"{len(last_yr[last_yr['조정_GAP'] > 2])}개",
          f"{sel_years[1]}년 기준", delta_color="inverse")
k4.metric("🟢 잉여 전환 직무 수",
          f"{len(surplus_jobs)}개",
          f"{sel_years[1]}년 기준", delta_color="off")

st.markdown("---")

# ── 자동 인사이트 카드 ──────────────────────────────────────────────
st.markdown("#### 📌 주요 인사이트")
insight_col1, insight_col2 = st.columns(2)

with insight_col1:
    # 인사이트 1: AI 대체 효과 총평
    if total_ai_replace > 0:
        st.markdown(f"""
        <div class="insight-card success">
            <b>✅ AI 도입 부족 완화 효과</b><br>
            {sel_years[0]}~{sel_years[1]}년 누계 기준 <b>{total_ai_replace:.0f}명</b> 상당의 업무를
            Physical AI가 대체합니다.<br>
            이를 통해 전체 인력 부족분 중 <b>{shortage_relief:.0f}명</b>이 완화되며,
            {'부족 문제가 상당 부분 해소됩니다.' if shortage_relief > total_orig_shortage * 0.5 else '부족 문제는 여전히 일부 남아 있어 추가 채용 또는 재배치 계획이 필요합니다.'}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="insight-card info">
            <b>ℹ️ AI 적용률 미입력</b><br>
            위 매트릭스에 AI 적용률을 입력하면 인사이트가 자동 생성됩니다.
        </div>
        """, unsafe_allow_html=True)

    # 인사이트 2: 가장 AI 영향 큰 직무
    if top_ai_job is not None and top_ai_job["AI대체_인원"] > 0:
        st.markdown(f"""
        <div class="insight-card info">
            <b>⚡ AI 대체 영향 최대 직무 ({sel_years[1]}년)</b><br>
            <b>'{top_ai_job['직무']}'</b> 직무는 {sel_years[1]}년 기준
            <b>{top_ai_job['AI대체율(%)']:.0f}%</b> 적용률로
            <b>{top_ai_job['AI대체_인원']:.1f}명</b>이 대체됩니다.<br>
            해당 인력은 고숙련 감독·기획 역할로의 전환 또는
            신기술 유지보수 인력으로 재배치를 검토하세요.
        </div>
        """, unsafe_allow_html=True)

with insight_col2:
    # 인사이트 3: 여전히 부족한 직무 경보
    still_short = last_yr[last_yr["조정_GAP"] > 2].sort_values("조정_GAP", ascending=False)
    if not still_short.empty:
        job_list_str = ", ".join([f"<b>{r['직무']}</b>({r['조정_GAP']:+.1f}명)"
                                  for _, r in still_short.iterrows()])
        st.markdown(f"""
        <div class="insight-card warning">
            <b>⚠️ AI 도입 후에도 부족한 직무 ({sel_years[1]}년)</b><br>
            {job_list_str}<br>
            AI 도입만으로는 인력 부족이 해소되지 않습니다.
            중장기 채용계획 또는 아웃소싱 전략을 병행하세요.
        </div>
        """, unsafe_allow_html=True)

    # 인사이트 4: 잉여 전환 직무 재배치 권고
    if not surplus_jobs.empty:
        surplus_str = ", ".join([f"<b>{r['직무']}</b>({abs(r['조정_GAP']):.1f}명 과잉)"
                                 for _, r in surplus_jobs.iterrows()])
        st.markdown(f"""
        <div class="insight-card success">
            <b>🔄 재배치 가능 직무 ({sel_years[1]}년)</b><br>
            AI 도입으로 과잉 전환된 직무: {surplus_str}<br>
            해당 인력을 여전히 부족한 직무로 재배치하거나,
            AI 운영·감독 전문 인력으로 양성하는 전략이 유효합니다.
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ── 연도별 인력 구조 변화 추이 (수요·AI대체·공급 누적) ─────────────
st.subheader("📊 전체 인력 구조 변화 추이")
st.caption("연도별로 AI 대체, 조정 수요, 공급이 어떻게 변화하는지 한눈에 비교")

yr_summary = recalc_df.groupby("연도").agg(
    원래_수요=("원래_수요","sum"),
    AI대체_인원=("AI대체_인원","sum"),
    조정수요=("조정수요","sum"),
    공급=("공급","sum"),
    조정_GAP=("조정_GAP","sum"),
).reset_index()

fig_summary = go.Figure()
fig_summary.add_trace(go.Bar(
    x=yr_summary["연도"], y=yr_summary["원래_수요"],
    name="원래 수요", marker_color="rgba(244,67,54,0.25)",
    marker_line_color="#F44336", marker_line_width=1.5,
))
fig_summary.add_trace(go.Bar(
    x=yr_summary["연도"], y=yr_summary["AI대체_인원"],
    name="AI 대체분", marker_color="rgba(0,212,255,0.5)",
    marker_line_color="#00d4ff", marker_line_width=1.5,
))
fig_summary.add_trace(go.Scatter(
    x=yr_summary["연도"], y=yr_summary["조정수요"],
    name="AI 후 수요", mode="lines+markers+text",
    text=yr_summary["조정수요"].apply(lambda x: f"{x:.0f}"),
    textposition="top center",
    line=dict(color="#00d4ff", width=2.5),
    marker=dict(size=9),
))
fig_summary.add_trace(go.Scatter(
    x=yr_summary["연도"], y=yr_summary["공급"],
    name="공급 (순 가용)", mode="lines+markers",
    line=dict(color="#00e676", width=2, dash="dot"),
    marker=dict(size=8),
))
fig_summary.update_layout(
    barmode="overlay", height=420,
    legend=dict(orientation="h", y=-0.2),
    yaxis_title="인원(명)",
    xaxis=dict(tickmode="linear", dtick=1),
    hovermode="x unified",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=20, b=60),
)
st.plotly_chart(fig_summary, use_container_width=True)

st.divider()

# ── 상세 테이블 ──────────────────────────────────────────────────────
with st.expander("📋 AI 도입 영향 상세 데이터 (클릭하여 펼치기)", expanded=False):
    display_df = recalc_df[
        recalc_df["연도"].between(*sel_years)
    ].copy().sort_values(["연도","직무"])

    st.dataframe(
        display_df.style
            .background_gradient(subset=["AI대체율(%)"], cmap="Blues")
            .background_gradient(subset=["조정_GAP"], cmap="RdYlGn_r")
            .format({
                "AI대체율(%)": "{:.1f}%",
                "AI대체_인원": "{:.1f}",
                "조정수요":   "{:.1f}",
                "공급":       "{:.1f}",
                "원래_GAP":   "{:+.1f}",
                "조정_GAP":   "{:+.1f}",
                "GAP개선":    "{:+.1f}",
            }),
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    csv = display_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="⬇️ CSV 다운로드",
        data=csv,
        file_name="physical_ai_impact_analysis.csv",
        mime="text/csv",
    )