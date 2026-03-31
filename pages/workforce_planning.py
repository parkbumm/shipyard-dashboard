# pages/2_인력수급계획.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client

st.set_page_config(page_title="인력 수급 계획", page_icon="📊", layout="wide")

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = get_supabase()

@st.cache_data(ttl=300)
def load_planning_data():
    gap      = pd.DataFrame(supabase.table("gap_analysis").select("*").execute().data)
    plans    = pd.DataFrame(supabase.table("production_plans").select("*").execute().data)
    products = pd.DataFrame(supabase.table("products").select("*").execute().data)
    demand   = pd.DataFrame(supabase.table("workforce_demand").select("*").execute().data)
    supply   = pd.DataFrame(supabase.table("workforce_supply").select("*").execute().data)
    jobs     = pd.DataFrame(supabase.table("jobs").select("*").execute().data)

    plans = plans.merge(products[["id","product_name","product_type"]], 
                        left_on="product_id", right_on="id")
    demand = demand.merge(jobs[["id","job_name","department"]], 
                          left_on="job_id", right_on="id")
    return gap, plans, products, demand, supply, jobs

with st.spinner("인력 계획 데이터 로딩 중..."):
    gap, plans, products, demand, supply, jobs = load_planning_data()

# ── 사이드바 ────────────────────────────────────────────────────────
st.sidebar.title("📊 인력 수급 계획 필터")

st.sidebar.markdown("#### 기본 설정")
sel_scenario = st.sidebar.selectbox(
    "시나리오",
    ["BASE", "OPTIMISTIC", "PESSIMISTIC"],
    format_func=lambda x: {
        "BASE": "기준", "OPTIMISTIC": "낙관", "PESSIMISTIC": "비관"
    }[x],
)
sel_years = st.sidebar.slider("분석 연도 범위", 2025, 2030, (2025, 2030))

st.sidebar.divider()
st.sidebar.markdown("#### 🚢 수주/생산 계획 조정")
st.sidebar.caption("슬라이더로 척수 조정 후 저장하면 모든 집계에 반영됩니다.")

year_list = list(range(sel_years[0], sel_years[1] + 1))
prod_list = sorted(products["product_name"].tolist())

# ── plan_base 구성 ───────────────────────────────────────────────────
plan_base = plans[plans["scenario"] == sel_scenario].copy()
if "product_name" not in plan_base.columns:
    plan_base = plan_base.merge(
        products[["id", "product_name", "product_type"]],
        left_on="product_id", right_on="id", how="left"
    )

# ── session_state 초기화 ─────────────────────────────────────────────
state_key = f"custom_plan_{sel_scenario}"
if state_key not in st.session_state:
    init_dict = {}
    for yr in range(2025, 2031):
        for pname in prod_list:
            row = plan_base[
                (plan_base["plan_year"] == yr) &
                (plan_base["product_name"] == pname)
            ]
            init_dict[(yr, pname)] = (
                float(row["planned_ships"].values[0]) if not row.empty else 0.0
            )
    st.session_state[state_key] = init_dict

edited = st.session_state[state_key].copy()

# ── 연도 선택 + 슬라이더 입력 ───────────────────────────────────────
sidebar_year = st.sidebar.selectbox(
    "편집 연도", year_list, key="sidebar_year"
)
st.sidebar.markdown(f"**{sidebar_year}년 선종별 계획 척수**")

for pname in prod_list:
    short_name = pname[:12] + "…" if len(pname) > 12 else pname
    cur_val = edited.get((sidebar_year, pname), 0.0)
    new_val = st.sidebar.slider(
        short_name,
        min_value=0.0,
        max_value=20.0,
        value=cur_val,
        step=0.5,
        format="%.1f척",
        key=f"slider_{sidebar_year}_{pname}",
    )
    edited[(sidebar_year, pname)] = new_val

st.session_state[state_key] = edited

# ── 저장 함수 ────────────────────────────────────────────────────────
def save_plans_and_recalc(edited_dict, scenario, supabase_client):
    """
    1) production_plans upsert
    2) workforce_demand 재계산 후 upsert
    """
    WORKING_DAYS = 250
    DAILY_HOURS  = 8.0
    ANNUAL_HOURS = WORKING_DAYS * DAILY_HOURS  # 2000

    # ── 1. production_plans upsert ───────────────────────────────────
    upsert_plans = []
    for (yr, pname), ships in edited_dict.items():
        pid_row = products[products["product_name"] == pname]
        if pid_row.empty:
            continue
        upsert_plans.append({
            "plan_year":     yr,
            "product_id":    int(pid_row["id"].values[0]),
            "planned_ships": ships,
            "scenario":      scenario,
        })

    supabase_client.table("production_plans").upsert(
        upsert_plans,
        on_conflict="plan_year,product_id,scenario"
    ).execute()

    # ── 2. workforce_demand 재계산 ───────────────────────────────────
    # 공수 표준 테이블 로드
    mh_df = pd.DataFrame(
        supabase_client.table("product_job_manhours").select("*").execute().data
    )

    # 편집된 계획을 DataFrame으로 변환
    plan_rows = []
    for (yr, pname), ships in edited_dict.items():
        pid_row = products[products["product_name"] == pname]
        if pid_row.empty:
            continue
        plan_rows.append({
            "plan_year":  yr,
            "product_id": int(pid_row["id"].values[0]),
            "planned_ships": ships,
        })
    plan_edited_df = pd.DataFrame(plan_rows)

    demand_upsert = []
    for year in range(2025, 2031):
        p_yr = plan_edited_df[plan_edited_df["plan_year"] == year]
        ship_dict = dict(zip(p_yr["product_id"], p_yr["planned_ships"]))

        mh_calc = mh_df.copy()
        mh_calc["ships"]    = mh_calc["product_id"].map(ship_dict).fillna(0)
        mh_calc["total_mh"] = mh_calc["manhours_per_ship"] * mh_calc["ships"]

        job_demand = (
            mh_calc.groupby("job_id")["total_mh"]
            .sum()
            .reset_index()
            .rename(columns={"total_mh": "total_manhours"})
        )

        for _, row in job_demand.iterrows():
            total_mh = int(row["total_manhours"])
            req_hc   = round(total_mh / ANNUAL_HOURS, 1)
            demand_upsert.append({
                "plan_year":         year,
                "job_id":            int(row["job_id"]),
                "scenario":          scenario,
                "total_manhours":    total_mh,
                "required_headcount": req_hc,
                "working_days":      WORKING_DAYS,
                "daily_hours":       DAILY_HOURS,
            })

    # 50건씩 upsert
    for i in range(0, len(demand_upsert), 50):
        supabase_client.table("workforce_demand").upsert(
            demand_upsert[i:i+50],
            on_conflict="plan_year,job_id,scenario"
        ).execute()

    return len(upsert_plans), len(demand_upsert)

# ── 저장 / 초기화 버튼 ──────────────────────────────────────────────
col_save, col_reset = st.sidebar.columns(2)

with col_save:
    if st.button("💾 저장", use_container_width=True):
        with st.spinner("저장 및 집계 중..."):
            try:
                n_plans, n_demand = save_plans_and_recalc(
                    st.session_state[state_key],
                    sel_scenario,
                    supabase,
                )
                # 캐시 초기화 → 최신 데이터 리로드
                load_planning_data.clear()
                st.sidebar.success(
                    f"✅ 저장 완료\n"
                    f"- 생산계획 {n_plans}건\n"
                    f"- 수요 재계산 {n_demand}건"
                )
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"❌ 저장 실패: {e}")

with col_reset:
    if st.button("↺ 초기화", use_container_width=True):
        if state_key in st.session_state:
            del st.session_state[state_key]
        load_planning_data.clear()
        st.rerun()

st.sidebar.divider()

# ── 편집값 → plan_filtered DataFrame (탭에서 사용) ───────────────────
custom_rows = []
for (yr, pname), ships in st.session_state[state_key].items():
    pid_row = products[products["product_name"] == pname]
    if pid_row.empty:
        continue
    custom_rows.append({
        "plan_year":     yr,
        "product_name":  pname,
        "product_id":    int(pid_row["id"].values[0]),
        "planned_ships": ships,
        "scenario":      sel_scenario,
        "product_type":  pid_row["product_type"].values[0],
    })

custom_plans_df = pd.DataFrame(custom_rows)
plan_filtered = custom_plans_df[
    custom_plans_df["plan_year"].between(*sel_years)
].copy()

yearly_total = (
    plan_filtered.groupby("plan_year")["planned_ships"]
    .sum()
    .reset_index()
    .rename(columns={"planned_ships": "total_ships"})
)

# ── 탭 구성 ─────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📦 제품별 생산계획",
    "⚙️ 직무별 공수 분석",
    "⚠️ 인력 과부족 현황",
    "🔮 미래 인력 로드맵",
])

# ── TAB 1: 제품별 생산계획 ───────────────────────────────────────────
with tab1:
    st.subheader("제품별 연도별 수주·생산 계획")

    # 연도별 합계 계산
    yearly_total = (
        plan_filtered.groupby("plan_year")["planned_ships"]
        .sum()
        .reset_index()
        .rename(columns={"planned_ships": "total_ships"})
    )

    # 선종별 연도별 척수 히트맵
    pivot_plan = plan_filtered.pivot_table(
        index="product_name", columns="plan_year",
        values="planned_ships", aggfunc="sum"
    ).fillna(0)

    # ✅ 합계 행 추가
    pivot_plan.loc["── 합계 ──"] = pivot_plan.sum()

    fig = px.imshow(
        pivot_plan, text_auto=".1f",
        color_continuous_scale="Blues",
        labels={"color": "계획 척수"},
        aspect="auto", height=360,
    )
    # 합계 행 강조 (마지막 행 배경색 다르게)
    fig.add_hline(
        y=len(pivot_plan) - 1.5,   # 합계 행 위 구분선
        line_width=2, line_color="steelblue", line_dash="dot",
    )
    fig.update_layout(margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    # 연도별 수주량 추이 (선종별 누적 막대 + 합계 라인)
    st.subheader("연도별 수주량 추이 (선종별 누적)")

    fig2 = px.bar(
        plan_filtered, x="plan_year", y="planned_ships",
        color="product_name", barmode="stack",
        text_auto=".1f",
        labels={
            "plan_year": "연도",
            "planned_ships": "척수",
            "product_name": "선종"
        },
        height=420,
    )

    # ✅ 합계 수치를 막대 위에 표시
    fig2.add_trace(go.Scatter(
        x=yearly_total["plan_year"],
        y=yearly_total["total_ships"],
        mode="lines+markers+text",
        name="연도 합계",
        text=yearly_total["total_ships"].apply(lambda x: f"<b>{x:.1f}척</b>"),
        textposition="top center",
        textfont=dict(size=13, color="#1565C0"),
        line=dict(color="#1565C0", width=2, dash="dot"),
        marker=dict(size=9, color="#1565C0"),
    ))

    fig2.update_layout(
        legend=dict(orientation="h", y=-0.25),
        yaxis_title="척수",
        xaxis=dict(tickmode="linear", dtick=1),
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ✅ 연도별 합계 요약 테이블
    st.subheader("연도별 합계 요약")

    summary = plan_filtered.pivot_table(
        index="product_name",
        columns="plan_year",
        values="planned_ships",
        aggfunc="sum"
    ).fillna(0)

    # 합계 행/열 추가
    summary.loc["합계"] = summary.sum()
    summary["전체합계"] = summary.sum(axis=1)

    # 소수점 1자리 포맷으로 표시
    st.dataframe(
        summary.style.format("{:.1f}")
               .background_gradient(cmap="Blues", subset=summary.columns[:-1])
               .highlight_between(subset=["전체합계"], color="#D6EAF8"),
        use_container_width=True,
        height=320,
    )

# ── TAB 2: 직무별 공수 분석 ─────────────────────────────────────────
with tab2:
    st.subheader("직무별 연간 필요 공수 (맨아워)")

    demand_filtered = demand[
        (demand["scenario"] == sel_scenario) &
        (demand["plan_year"].between(*sel_years))
    ]

    # 직무별 연도별 필요 인원 추이
    fig3 = px.line(
        demand_filtered, x="plan_year", y="required_headcount",
        color="job_name", markers=True,
        labels={"plan_year":"연도","required_headcount":"필요 인원(명)","job_name":"직무"},
        height=400,
    )
    fig3.update_layout(legend=dict(orientation="h", y=-0.3))
    st.plotly_chart(fig3, use_container_width=True)

    # 직무별 총 공수 막대
    st.subheader("직무별 누적 총 공수 (맨아워)")
    total_mh = demand_filtered.groupby("job_name")["total_manhours"].sum().reset_index()
    fig4 = px.bar(
        total_mh.sort_values("total_manhours", ascending=True),
        x="total_manhours", y="job_name", orientation="h",
        text_auto=",d",
        labels={"total_manhours":"총 공수(맨아워)","job_name":"직무"},
        height=360,
    )
    st.plotly_chart(fig4, use_container_width=True)

# ── TAB 3: 인력 과부족 현황 ─────────────────────────────────────────
with tab3:
    st.subheader("직무별 인력 과부족 현황 (수요 - 공급)")
    st.caption("+ 부족 / - 과잉 | BASE 시나리오 기준")

    gap_filtered = gap[gap["year"].between(*sel_years)]

    # 연도별 직무별 GAP 히트맵
    gap_pivot = gap_filtered.pivot_table(
        index="job_name", columns="year", values="gap"
    )
    fig5 = px.imshow(
        gap_pivot, text_auto=".1f",
        color_continuous_scale="RdYlGn_r",   # 빨강=부족, 초록=과잉
        color_continuous_midpoint=0,
        labels={"color":"과부족(명)"},
        aspect="auto", height=380,
    )
    st.plotly_chart(fig5, use_container_width=True)

    # 연도 선택하여 상세 보기
    sel_year_detail = st.select_slider("상세 조회 연도", options=list(range(*sel_years, 1)) + [sel_years[1]])
    gap_year = gap_filtered[gap_filtered["year"] == sel_year_detail].copy()
    gap_year = gap_year.sort_values("gap", ascending=False)

    colors = gap_year["gap"].apply(
        lambda x: "#F44336" if x > 5 else "#FF9800" if x > 0 else "#4CAF50" if x > -5 else "#1976D2"
    )
    fig6 = go.Figure(go.Bar(
        x=gap_year["gap"], y=gap_year["job_name"],
        orientation="h",
        marker_color=colors,
        text=gap_year["gap"].apply(lambda x: f"{x:+.1f}명"),
        textposition="outside",
    ))
    fig6.add_vline(x=0, line_width=1.5, line_color="gray")
    fig6.update_layout(
        height=380, title=f"{sel_year_detail}년 직무별 과부족",
        xaxis_title="과부족 인원(명)", yaxis_title="",
        margin=dict(t=40),
    )
    st.plotly_chart(fig6, use_container_width=True)

    # 심각 부족 직무 경보
    critical = gap_year[gap_year["gap_status"] == "심각 부족"]
    if not critical.empty:
        st.error(f"🚨 {sel_year_detail}년 심각 부족 직무: " +
                 ", ".join(critical["job_name"].tolist()))

# ── TAB 4: 미래 인력 로드맵 ─────────────────────────────────────────
with tab4:
    st.subheader("직무별 인력 수요·공급 비교 (연도별 추이)")

    # 수요·공급 데이터가 모두 존재하는 직무만 필터링
    jobs_with_demand = set(
        demand[
            (demand["scenario"] == sel_scenario) &
            (demand["plan_year"].between(*sel_years)) &
            (demand["required_headcount"] > 0)
        ]["job_name"].tolist()
    )
    jobs_with_supply = set(
        jobs[jobs["id"].isin(
            supply[
                (supply["supply_year"].between(*sel_years)) &
                (supply["net_supply"] > 0)
            ]["job_id"].tolist()
        )]["job_name"].tolist()
    )
    active_jobs = sorted(jobs_with_demand & jobs_with_supply)

    if not active_jobs:
        st.info("선택한 연도 범위 내 수요·공급 데이터가 모두 존재하는 직무가 없습니다.")
        st.stop()

    sel_job = st.selectbox(
        f"직무 선택 (수요·공급 데이터 보유 직무 — {len(active_jobs)}개)",
        active_jobs,
    )
    job_id  = int(jobs[jobs["job_name"] == sel_job]["id"].values[0])

    dem_j = demand[
        (demand["job_name"] == sel_job) &
        (demand["scenario"] == sel_scenario) &
        (demand["plan_year"].between(*sel_years))
    ].sort_values("plan_year").reset_index(drop=True)

    sup_j = supply[
        (supply["job_id"] == job_id) &
        (supply["supply_year"].between(*sel_years))
    ].sort_values("supply_year").reset_index(drop=True)

    # ✅ 핵심 수정: .values 대신 연도 기준으로 merge 후 계산
    merged_j = dem_j[["plan_year", "required_headcount"]].merge(
        sup_j[["supply_year", "net_supply"]],
        left_on="plan_year",
        right_on="supply_year",
        how="inner"   # 양쪽에 연도가 모두 있는 행만 사용
    )

    if merged_j.empty:
        st.warning("선택한 직무의 수요·공급 데이터가 일치하는 연도가 없습니다.")
    else:
        merged_j["gap"] = merged_j["required_headcount"] - merged_j["net_supply"]

        fig7 = go.Figure()
        fig7.add_trace(go.Scatter(
            x=merged_j["plan_year"],
            y=merged_j["required_headcount"],
            name="수요 (필요 인원)", mode="lines+markers",
            line=dict(color="#F44336", width=2.5),
            marker=dict(size=8),
        ))
        fig7.add_trace(go.Scatter(
            x=merged_j["plan_year"],
            y=merged_j["net_supply"],
            name="공급 (순 가용 인원)", mode="lines+markers",
            line=dict(color="#1976D2", width=2.5, dash="dot"),
            marker=dict(size=8),
        ))
        fig7.add_trace(go.Scatter(
            x=merged_j["plan_year"],
            y=merged_j["gap"],
            name="과부족 GAP", mode="lines",
            fill="tozeroy",
            line=dict(color="#FF9800", width=1),
            fillcolor="rgba(255,152,0,0.15)",
        ))
        fig7.update_layout(
            height=420,
            title=f"{sel_job} — 수요 vs 공급 ({sel_scenario} 시나리오)",
            xaxis_title="연도", yaxis_title="인원(명)",
            legend=dict(orientation="h", y=-0.2),
            hovermode="x unified",
        )
        st.plotly_chart(fig7, use_container_width=True)

    # 시나리오 비교
    st.subheader(f"{sel_job} — 시나리오별 수요 비교")
    dem_all = demand[
        (demand["job_name"] == sel_job) &
        (demand["plan_year"].between(*sel_years))
    ]
    fig8 = px.line(
        dem_all, x="plan_year", y="required_headcount",
        color="scenario",
        color_discrete_map={
            "BASE": "#1976D2",
            "OPTIMISTIC": "#4CAF50",
            "PESSIMISTIC": "#F44336"
        },
        markers=True,
        labels={
            "plan_year": "연도",
            "required_headcount": "필요 인원(명)",
            "scenario": "시나리오"
        },
        height=340,
    )
    if not sup_j.empty:
        fig8.add_hline(
            y=sup_j["net_supply"].mean(),
            line_dash="dash", line_color="gray",
            annotation_text="현재 평균 공급",
            annotation_position="right",
        )
    st.plotly_chart(fig8, use_container_width=True)