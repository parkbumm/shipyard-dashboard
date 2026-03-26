# ── STEP 1: 임포트 & 페이지 설정 ────────────────────────────────────
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client

# 커스텀 CSS — 카드 여백, 폰트 약간 조정
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    [data-testid="metric-container"] {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 12px 16px;
    }
</style>
""", unsafe_allow_html=True)

# ── STEP 2: Supabase 연결 & 데이터 로드 ─────────────────────────────

@st.cache_resource          # 연결 객체는 앱 실행 중 1번만 생성
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

@st.cache_data(ttl=300)     # 5분마다 자동 갱신 (300초)
def load_data():
    # 4개 테이블 전체 조회
    employees = pd.DataFrame(
        supabase.table("employees").select("*").execute().data
    )
    jobs = pd.DataFrame(
        supabase.table("jobs").select("*").execute().data
    )
    employee_skills = pd.DataFrame(
        supabase.table("employee_skills").select("*").execute().data
    )
    skills = pd.DataFrame(
        supabase.table("skills").select("*").execute().data
    )

    # employees ← jobs JOIN (부서명, 직무명, 레벨 붙이기)
    employees = employees.merge(
        jobs[["id", "job_name", "department", "job_level"]],
        left_on="job_id",
        right_on="id",
        suffixes=("", "_job")
    )

    # hire_date 문자열 → datetime 변환
    employees["hire_date"] = pd.to_datetime(employees["hire_date"])

    return employees, jobs, employee_skills, skills

# 로드 중 스피너 표시
with st.spinner("데이터 로딩 중..."):
    emp, jobs, skmap, skills = load_data()

# ── STEP 3: 사이드바 필터 ────────────────────────────────────────────

st.sidebar.title("⚓ 인력 분석 필터")
st.sidebar.markdown("---")

# 부서 필터
dept_options = ["전체"] + sorted(emp["department"].unique().tolist())
sel_dept = st.sidebar.selectbox(
    "🏭 부서 선택",
    options=dept_options,
    index=0,
)

# 퇴직 리스크 필터
sel_risk = st.sidebar.multiselect(
    "⚠️ 퇴직 리스크 등급",
    options=["LOW", "MEDIUM", "HIGH"],
    default=["LOW", "MEDIUM", "HIGH"],
)

# 연령대 범위 필터
age_min, age_max = int(emp["age"].min()), int(emp["age"].max())
sel_age = st.sidebar.slider(
    "👤 연령 범위",
    min_value=age_min,
    max_value=age_max,
    value=(age_min, age_max),
)

# 근속연수 범위 필터
tenure_min = float(emp["years_of_service"].min())
tenure_max = float(emp["years_of_service"].max())
sel_tenure = st.sidebar.slider(
    "📅 근속연수 범위",
    min_value=tenure_min,
    max_value=tenure_max,
    value=(tenure_min, tenure_max),
    step=0.5,
)

st.sidebar.markdown("---")

# ── 필터 적용 ────────────────────────────────────────────────────────
df = emp.copy()

if sel_dept != "전체":
    df = df[df["department"] == sel_dept]

if sel_risk:
    df = df[df["retirement_risk"].isin(sel_risk)]

df = df[
    (df["age"] >= sel_age[0]) & (df["age"] <= sel_age[1]) &
    (df["years_of_service"] >= sel_tenure[0]) &
    (df["years_of_service"] <= sel_tenure[1])
]

# 필터 결과 요약
st.sidebar.info(f"✅ 필터 적용 결과: **{len(df)}명**")

# 빈 결과 조기 처리
if df.empty:
    st.warning("선택한 조건에 해당하는 직원이 없습니다. 필터를 조정해 주세요.")
    st.stop()   # 이하 코드 실행 중단

# ── STEP 4: 제목 & KPI 카드 ──────────────────────────────────────────

st.title("🏗️ 조선소 인력 구조 분석 대시보드")
st.caption(f"기준 데이터: 전체 {len(emp)}명 | 필터 적용: {len(df)}명")
st.divider()

# 4개 컬럼으로 KPI 배치
k1, k2, k3, k4 = st.columns(4)

# 총 인원
k1.metric(
    label="👥 총 인원",
    value=f"{len(df)}명",
    delta=f"전체 대비 {len(df)/len(emp)*100:.1f}%",
)

# 평균 연령
k2.metric(
    label="🎂 평균 연령",
    value=f"{df['age'].mean():.1f}세",
    delta=f"전체 평균 {emp['age'].mean():.1f}세",
    delta_color="off",    # 색상 변화 없이 참고용으로만 표시
)

# 평균 근속연수
k3.metric(
    label="📅 평균 근속연수",
    value=f"{df['years_of_service'].mean():.1f}년",
    delta=f"전체 평균 {emp['years_of_service'].mean():.1f}년",
    delta_color="off",
)

# HIGH 리스크 비율
high_count  = len(df[df["retirement_risk"] == "HIGH"])
high_ratio  = high_count / len(df) * 100
k4.metric(
    label="🚨 HIGH 리스크 인원",
    value=f"{high_count}명",
    delta=f"비율 {high_ratio:.1f}%",
    delta_color="inverse",   # 높을수록 빨간색 (위험)
)

st.divider()

# ── STEP 5: 시각화 차트 ──────────────────────────────────────────────

# ── 5-1 행: 연령 분포 히스토그램 + 부서별 파이차트 ─────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 연령 분포")
    st.caption("리스크 등급별 연령대 분포 — 고령 집중 구간 파악용")

    fig1 = px.histogram(
        df,
        x="age",
        nbins=15,
        color="retirement_risk",
        color_discrete_map={
            "LOW":    "#4CAF50",
            "MEDIUM": "#FF9800",
            "HIGH":   "#F44336",
        },
        labels={"age": "나이", "count": "인원수", "retirement_risk": "리스크"},
        barmode="stack",        # 리스크별로 쌓아서 전체 보기
    )
    fig1.update_layout(
        height=320,
        legend=dict(orientation="h", y=-0.25),
        margin=dict(t=10, b=40),
    )
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.subheader("🏭 부서별 인원 현황")
    st.caption("부서별 인력 비중 — 특정 부서 쏠림 확인용")

    dept_cnt = (
        df.groupby("department")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    fig2 = px.pie(
        dept_cnt,
        values="count",
        names="department",
        hole=0.42,              # 도넛 차트
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig2.update_traces(textposition="inside", textinfo="percent+label")
    fig2.update_layout(
        height=320,
        showlegend=False,       # 라벨이 차트 안에 있으므로 범례 생략
        margin=dict(t=10),
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── 5-2 행: 산점도 + 직무 레벨 막대그래프 ──────────────────────────
col3, col4 = st.columns(2)

with col3:
    st.subheader("🔍 근속연수 vs 연령 분포")
    st.caption("우상단 집중 = 고령·장기근속 → HIGH 리스크 패턴")

    fig3 = px.scatter(
        df,
        x="years_of_service",
        y="age",
        color="retirement_risk",
        color_discrete_map={
            "LOW":    "#4CAF50",
            "MEDIUM": "#FF9800",
            "HIGH":   "#F44336",
        },
        size_max=10,
        hover_data={
            "name": True,
            "job_name": True,
            "department": True,
            "years_of_service": ":.1f",
            "age": True,
        },
        labels={
            "years_of_service": "근속연수(년)",
            "age": "나이",
            "retirement_risk": "리스크",
        },
    )
    # 리스크 구간 배경색 표시 (HIGH 구간 강조)
    fig3.add_shape(
        type="rect",
        x0=15, x1=df["years_of_service"].max() + 1,
        y0=50, y1=df["age"].max() + 1,
        fillcolor="rgba(244,67,54,0.07)",
        line_width=0,
    )
    fig3.add_annotation(
        x=df["years_of_service"].max() - 2, y=51,
        text="HIGH 리스크 구간",
        showarrow=False,
        font=dict(color="#F44336", size=11),
    )
    fig3.update_layout(
        height=340,
        legend=dict(orientation="h", y=-0.25),
        margin=dict(t=10, b=50),
    )
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    st.subheader("📈 직무 레벨별 인원")
    st.caption("숙련 인력(고급·전문가) 비중 — 조직 역량 수준 파악")

    level_order = ["초급", "중급", "고급", "전문가"]

    level_cnt = (
        df.groupby("job_level")
        .size()
        .reindex(level_order, fill_value=0)
        .reset_index(name="count")
    )
    fig4 = px.bar(
        level_cnt,
        x="job_level",
        y="count",
        text="count",
        color="job_level",
        color_discrete_sequence=["#90CAF9", "#42A5F5", "#1565C0", "#0D47A1"],
        category_orders={"job_level": level_order},
        labels={"job_level": "직무 레벨", "count": "인원수"},
    )
    fig4.update_traces(textposition="outside", textfont_size=13)
    fig4.update_layout(
        height=340,
        showlegend=False,
        margin=dict(t=30, b=10),
        yaxis=dict(range=[0, level_cnt["count"].max() * 1.2]),
    )
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── STEP 6: 스킬 히트맵 + 직원 테이블 ──────────────────────────────

# ── 6-1: 직무 × 스킬 숙련도 히트맵 ─────────────────────────────────
st.subheader("🗺️ 직무 × 스킬 숙련도 히트맵")
st.caption("셀 값 = 해당 직무 직원들의 평균 숙련도 (1~5점) | 공백 = 해당 직무에서 스킬 미보유")

# 현재 필터된 직원 ID만 사용
filtered_ids = df["id"].tolist()
skmap_filtered = skmap[skmap["employee_id"].isin(filtered_ids)]

# 3-way JOIN: employee_skills ← skills ← employees(직무명)
merged = (
    skmap_filtered
    .merge(skills[["id", "skill_name", "skill_category"]],
           left_on="skill_id", right_on="id")
    .merge(df[["id", "job_name"]],
           left_on="employee_id", right_on="id")
)

# 피벗 테이블: 행=직무, 열=스킬, 값=평균 숙련도
pivot = (
    merged
    .groupby(["job_name", "skill_name"])["proficiency"]
    .mean()
    .round(1)
    .reset_index()
    .pivot(index="job_name", columns="skill_name", values="proficiency")
)

if not pivot.empty:
    fig5 = px.imshow(
        pivot,
        text_auto=".1f",                   # 셀 안에 숫자 표시
        color_continuous_scale="RdYlGn",   # 빨강(낮음) → 초록(높음)
        zmin=1, zmax=5,
        aspect="auto",
        labels={"color": "평균 숙련도"},
    )
    fig5.update_layout(
        height=420,
        margin=dict(t=10, b=60, l=10, r=10),
        coloraxis_colorbar=dict(
            title="숙련도",
            tickvals=[1, 2, 3, 4, 5],
            ticktext=["1\n(초보)", "2", "3\n(중간)", "4", "5\n(전문)"],
        ),
    )
    fig5.update_xaxes(tickangle=-35)
    st.plotly_chart(fig5, use_container_width=True)
else:
    st.info("선택된 조건에서 스킬 데이터가 없습니다.")

st.divider()

# ── 6-2: 리스크별 요약 바차트 ───────────────────────────────────────
st.subheader("⚠️ 부서별 퇴직 리스크 현황")
st.caption("부서별 HIGH·MEDIUM 리스크 인원 현황 — 대응 우선순위 설정용")

risk_dept = (
    df.groupby(["department", "retirement_risk"])
    .size()
    .reset_index(name="count")
)

fig6 = px.bar(
    risk_dept,
    x="department",
    y="count",
    color="retirement_risk",
    color_discrete_map={
        "LOW":    "#4CAF50",
        "MEDIUM": "#FF9800",
        "HIGH":   "#F44336",
    },
    barmode="group",
    text="count",
    labels={"department": "부서", "count": "인원", "retirement_risk": "리스크"},
)
fig6.update_traces(textposition="outside")
fig6.update_layout(
    height=360,
    legend=dict(orientation="h", y=-0.25),
    margin=dict(t=10, b=60),
    xaxis_tickangle=-20,
)
st.plotly_chart(fig6, use_container_width=True)

st.divider()

# ── 6-3: 직원 상세 테이블 ───────────────────────────────────────────
with st.expander("📋 직원 상세 목록 (클릭하여 펼치기)", expanded=False):

    # 리스크별 색상 표시를 위한 이모지 컬럼 추가
    df_display = df.copy()
    risk_emoji = {"LOW": "🟢 LOW", "MEDIUM": "🟡 MEDIUM", "HIGH": "🔴 HIGH"}
    df_display["리스크"] = df_display["retirement_risk"].map(risk_emoji)

    show_cols = {
        "emp_no":            "사원번호",
        "name":              "이름",
        "age":               "나이",
        "gender":            "성별",
        "department":        "부서",
        "job_name":          "직무",
        "job_level":         "레벨",
        "years_of_service":  "근속(년)",
        "리스크":            "퇴직 리스크",
        "salary":            "급여(원)",
    }

    st.dataframe(
        df_display[list(show_cols.keys())].rename(columns=show_cols),
        use_container_width=True,
        height=420,
        column_config={
            "급여(원)": st.column_config.NumberColumn(format="%,d"),
            "근속(년)": st.column_config.NumberColumn(format="%.1f"),
        },
        hide_index=True,
    )

    # CSV 다운로드 버튼
    csv_data = df_display[list(show_cols.keys())].rename(columns=show_cols).to_csv(
        index=False, encoding="utf-8-sig"   # Excel 한글 깨짐 방지
    )
    st.download_button(
        label="⬇️ CSV 다운로드",
        data=csv_data,
        file_name="shipyard_employees_filtered.csv",
        mime="text/csv",
    )

