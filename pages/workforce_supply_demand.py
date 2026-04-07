"""
pages/workforce_supply_demand.py
──────────────────────────────────────────────────────────────────────────────
전략적 인력 예측 및 Physical AI 전환 통합 페이지
기존 shipyard-dashboard (parkbumm/shipyard-dashboard) 멀티페이지 구조에 추가

의존 테이블 (Supabase):
  - employees          : id, name, job_id, type(직영/협력/재고용), skill_grade, retirement_year
  - jobs               : id, name, category
  - production_plans   : id, ship_type, year, planned_mh
  - workforce_demand   : id, year, ship_type, required_mh
  - workforce_supply   : id, year, direct_mh, partner_mh, rehire_mh, total_mh
  - job_ai_adoption    : id, job_id, year, automation_rate, reskilled_count (기존 테이블)
  - partner_grades     : id, partner_name, job_id, grade_a_pct, grade_b_pct, grade_c_pct

신규 테이블 (이 페이지에서 사용, 없으면 mock 데이터로 fallback):
  - mh_standard        : id, ship_type, job_id, std_mh_per_m, actual_mh_per_m, year
──────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np

# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
try:
    from supabase import create_client
    from utils import get_supabase_client  # 기존 dashboard 유틸 재사용
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False


@st.cache_resource
def get_client():
    if _HAS_SUPABASE:
        try:
            return get_supabase_client()
        except Exception:
            return None
    return None


def fetch_table(table: str, columns: str = "*") -> pd.DataFrame:
    """Supabase 테이블 조회. 실패 시 빈 DataFrame 반환."""
    client = get_client()
    if client is None:
        return pd.DataFrame()
    try:
        res = client.table(table).select(columns).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.warning(f"[DB] {table} 조회 실패: {e} — 샘플 데이터로 표시합니다.", icon="⚠️")
        return pd.DataFrame()


# ── Mock 데이터 (Supabase 연결 전 / 데모용) ──────────────────────────────────
YEARS = list(range(2024, 2030))
SHIP_TYPES = ["LNGC", "컨테이너", "탱커", "LPG", "벌크"]
JOB_NAMES = ["용접", "도장", "의장", "선각", "전장"]
PARTNER_NAMES = ["A협력사", "B협력사", "C협력사", "D협력사", "E협력사"]


def mock_supply_demand(rehire_pct: int, partner_pct: int, ai_rate: int) -> pd.DataFrame:
    base_demand = [280, 295, 310, 325, 340, 330]
    base_direct = [107, 106, 105, 104, 102, 100]
    rows = []
    for i, yr in enumerate(YEARS):
        rehire_add = (rehire_pct - 11) * 1.5
        partner_add = (partner_pct - 51) * 1.2
        ai_add = ai_rate * 4.0
        total_supply = base_direct[i] + (partner_pct / 100) * base_demand[i] + rehire_add + ai_add
        rows.append({
            "year": yr,
            "required_mh": base_demand[i],
            "direct_mh": base_direct[i],
            "partner_mh": round(partner_pct / 100 * base_demand[i], 1),
            "rehire_mh": round(rehire_pct / 100 * base_demand[i] + rehire_add, 1),
            "total_supply": round(total_supply, 1),
            "gap": round(total_supply - base_demand[i], 1),
        })
    return pd.DataFrame(rows)


def mock_job_ai(ai_rate: int) -> pd.DataFrame:
    rows = []
    base_auto = {"용접": 18, "도장": 8, "의장": 3, "선각": 12, "전장": 5}
    reskill_base = {"용접": 94, "도장": 28, "의장": 12, "선각": 41, "전장": 19}
    for job in JOB_NAMES:
        for yr in YEARS:
            delta = (yr - 2024) * (ai_rate / 8)
            rows.append({
                "job": job,
                "year": yr,
                "automation_rate": min(round(base_auto[job] + delta, 1), 90),
                "reskilled_count": reskill_base[job] + (yr - 2024) * (ai_rate // 3),
            })
    return pd.DataFrame(rows)


def mock_partner_grades() -> pd.DataFrame:
    a_base = [55, 42, 38, 30, 22]
    b_base = [30, 38, 35, 40, 35]
    return pd.DataFrame({
        "partner": PARTNER_NAMES,
        "grade_a": a_base,
        "grade_b": b_base,
        "grade_c": [100 - a - b for a, b in zip(a_base, b_base)],
    })


def mock_mh_standard() -> pd.DataFrame:
    std = [2.8, 2.1, 2.4, 2.5, 1.9]
    actual = [3.1, 2.3, 2.5, 2.6, 2.0]
    return pd.DataFrame({"ship_type": SHIP_TYPES, "std_mh": std, "actual_mh": actual})


def mock_heatmap() -> pd.DataFrame:
    quarters = ["1Q", "2Q", "3Q", "4Q", "1Q+1", "2Q+1"]
    data = {
        "용접": [2, 3, 5, 4, 3, 2],
        "도장": [3, 4, 4, 5, 4, 3],
        "의장": [4, 5, 6, 5, 4, 3],
        "선각": [2, 3, 3, 4, 3, 2],
        "전장": [3, 3, 4, 5, 5, 4],
    }
    return pd.DataFrame(data, index=quarters)


def mock_kpis(rehire_pct, partner_pct, ai_rate, df_sd):
    gap_2028 = df_sd.loc[df_sd.year == 2028, "gap"].values
    gap_val = round(gap_2028[0] * 100, 0) if len(gap_2028) > 0 else -4200
    return {
        "total_mh": "284,500 MH",
        "direct_pct": "38%",
        "partner_pct": f"{partner_pct}%",
        "rehire_pct": f"{rehire_pct}%",
        "gap_2028": f"{gap_val:+,.0f} MH/월",
        "retire_3y": "312명",
        "rehire_pool": "187명",
        "new_hire": "380명",
        "automation": f"{18 + ai_rate // 2}%",
        "reskilled": f"{94 + ai_rate * 3}명",
        "cost_save": "₩38억",
        "mentor_pct": "31%",
    }


# ── 차트 함수들 ───────────────────────────────────────────────────────────────
PALETTE = {
    "blue": "#185FA5",
    "teal": "#1D9E75",
    "amber": "#E8A020",
    "red": "#E24B4A",
    "purple": "#7B3FA0",
    "gray": "#7A8EA8",
    "light_blue": "#B8D4F5",
}


def chart_supply_demand(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    # Gap fill
    fig.add_trace(go.Scatter(
        x=df.year.tolist() + df.year.tolist()[::-1],
        y=df.required_mh.tolist() + df.total_supply.tolist()[::-1],
        fill="toself",
        fillcolor="rgba(226,75,74,0.08)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Gap 구간",
        showlegend=True,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df.year, y=df.required_mh,
        mode="lines+markers",
        name="필요 공수 (수요)",
        line=dict(color=PALETTE["red"], width=2.5),
        marker=dict(size=6),
    ))
    fig.add_trace(go.Scatter(
        x=df.year, y=df.total_supply,
        mode="lines+markers",
        name="가용 공수 (공급)",
        line=dict(color=PALETTE["blue"], width=2.5),
        marker=dict(size=6),
    ))
    # Gap annotation at 2028
    row_2028 = df[df.year == 2028]
    if not row_2028.empty:
        gap = row_2028.iloc[0]["gap"]
        color = PALETTE["teal"] if gap >= 0 else PALETTE["red"]
        fig.add_annotation(
            x=2028, y=row_2028.iloc[0]["required_mh"],
            text=f"Gap: {gap:+.0f}만 MH",
            showarrow=True, arrowhead=2, arrowcolor=color,
            font=dict(color=color, size=12), bgcolor="white",
            bordercolor=color, borderwidth=1,
        )
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=-0.15),
        xaxis=dict(title="", tickmode="array", tickvals=YEARS, gridcolor="#E8EEF5"),
        yaxis=dict(title="만 MH", gridcolor="#E8EEF5"),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    return fig


def chart_stacked_supply(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df.year, y=df.direct_mh, name="직영", marker_color=PALETTE["blue"]))
    fig.add_trace(go.Bar(x=df.year, y=df.partner_mh, name="협력사", marker_color="#9FE1CB"))
    fig.add_trace(go.Bar(x=df.year, y=df.rehire_mh, name="재고용", marker_color=PALETTE["amber"]))
    fig.update_layout(
        barmode="stack", height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", y=-0.18),
        xaxis=dict(tickmode="array", tickvals=YEARS),
        yaxis=dict(title="만 MH", gridcolor="#E8EEF5"),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_heatmap(df_hm: pd.DataFrame) -> go.Figure:
    colorscale = [
        [0.0, "#C8E6C9"], [0.2, "#AED581"],
        [0.4, "#FFF176"], [0.6, "#FFB74D"],
        [0.8, "#EF9A9A"], [1.0, "#C62828"],
    ]
    fig = go.Figure(go.Heatmap(
        z=df_hm.values.T.tolist(),
        x=df_hm.index.tolist(),
        y=df_hm.columns.tolist(),
        colorscale=colorscale,
        zmin=1, zmax=6,
        text=df_hm.values.T.tolist(),
        texttemplate="%{text}",
        showscale=True,
        colorbar=dict(title="위험도", tickvals=[1,2,3,4,5,6], thickness=12),
    ))
    fig.update_layout(
        height=220,
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis=dict(title=""),
        yaxis=dict(title=""),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_ai_adoption(df_ai: pd.DataFrame, selected_year: int) -> go.Figure:
    df_yr = df_ai[df_ai.year == selected_year].copy()
    fig = make_subplots(rows=1, cols=2, subplot_titles=["자동화율 (%)", "Reskilling 완료 인원 (명)"])
    fig.add_trace(go.Bar(
        x=df_yr.job, y=df_yr.automation_rate,
        marker_color=PALETTE["teal"], name="자동화율",
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=df_yr.job, y=df_yr.reskilled_count,
        marker_color=PALETTE["purple"], name="Reskilling",
    ), row=1, col=2)
    fig.update_layout(
        height=280, showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_yaxes(gridcolor="#E8EEF5")
    return fig


def chart_ai_trend(df_ai: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    colors = [PALETTE["blue"], PALETTE["teal"], PALETTE["amber"], PALETTE["red"], PALETTE["purple"]]
    for i, job in enumerate(JOB_NAMES):
        df_j = df_ai[df_ai.job == job]
        fig.add_trace(go.Scatter(
            x=df_j.year, y=df_j.automation_rate,
            mode="lines+markers", name=job,
            line=dict(color=colors[i], width=2),
            marker=dict(size=5),
        ))
    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", y=-0.2),
        xaxis=dict(tickmode="array", tickvals=YEARS, gridcolor="#E8EEF5"),
        yaxis=dict(title="자동화율 (%)", gridcolor="#E8EEF5"),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    return fig


def chart_partner_grade(df_pg: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(y=df_pg.partner, x=df_pg.grade_a, name="A등급", marker_color=PALETTE["blue"], orientation="h"))
    fig.add_trace(go.Bar(y=df_pg.partner, x=df_pg.grade_b, name="B등급", marker_color=PALETTE["amber"], orientation="h"))
    fig.add_trace(go.Bar(y=df_pg.partner, x=df_pg.grade_c, name="C등급", marker_color=PALETTE["red"], orientation="h"))
    fig.update_layout(
        barmode="stack", height=240,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", y=-0.22),
        xaxis=dict(title="%", range=[0, 100], gridcolor="#E8EEF5"),
        yaxis=dict(title=""),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_mh_comparison(df_mh: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_mh.ship_type, y=df_mh.std_mh,
        name="표준 MH/m", marker_color=PALETTE["light_blue"],
        text=df_mh.std_mh, textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=df_mh.ship_type, y=df_mh.actual_mh,
        name="실적 MH/m", marker_color=PALETTE["red"],
        text=df_mh.actual_mh, textposition="outside",
    ))
    fig.update_layout(
        barmode="group", height=240,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", y=-0.22),
        xaxis=dict(gridcolor="#E8EEF5"),
        yaxis=dict(title="MH/m", gridcolor="#E8EEF5", range=[0, 4]),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_sankey(ai_rate: int) -> go.Figure:
    base = 380
    robot_op = round(base * (0.32 + ai_rate * 0.004))
    expert = round(base * 0.27)
    mentor = round(base * 0.18)
    other = base - robot_op - expert - mentor
    labels = ["일반 용접공 (현)", "로봇 오퍼레이터", "고난도 전문용접", "기술 멘토 (재고용)", "타 공정 전환"]
    source = [0, 0, 0, 0]
    target = [1, 2, 3, 4]
    values = [robot_op, expert, mentor, other]
    colors_link = ["rgba(29,158,117,0.4)", "rgba(123,63,160,0.4)", "rgba(232,160,32,0.4)", "rgba(122,142,168,0.4)"]
    fig = go.Figure(go.Sankey(
        node=dict(
            pad=15, thickness=20,
            label=labels,
            color=[PALETTE["blue"], PALETTE["teal"], PALETTE["purple"], PALETTE["amber"], PALETTE["gray"]],
        ),
        link=dict(source=source, target=target, value=values, color=colors_link),
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_waterfall(ai_rate: int) -> go.Figure:
    save = round(38 + ai_rate * 0.8)
    op_cost = -round(18 + ai_rate * 0.3)
    train = -9
    elite = round(15 + ai_rate * 0.2)
    new_job = round(22 + ai_rate * 0.5)
    net = save + op_cost + train + elite + new_job
    labels = ["협력사\n외주절감", "로봇\n운영비", "재교육비", "직영\n정예화", "신직무\n창출", "순효과"]
    values = [save, op_cost, train, elite, new_job, net]
    colors = [PALETTE["teal"] if v > 0 else PALETTE["red"] for v in values]
    colors[-1] = PALETTE["blue"]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=[f"{v:+}억" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(gridcolor="#E8EEF5"),
        yaxis=dict(title="억원", gridcolor="#E8EEF5"),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── KPI 카드 헬퍼 ─────────────────────────────────────────────────────────────
def kpi_card(label: str, value: str, delta: str = "", delta_up: bool | None = None):
    delta_color = ""
    if delta_up is True:
        delta_color = "color:#1D9E75;"
    elif delta_up is False:
        delta_color = "color:#E24B4A;"
    delta_html = f'<p style="font-size:11px;margin:2px 0 0 0;{delta_color}">{delta}</p>' if delta else ""
    st.markdown(f"""
    <div style="background:#F4F6F9;border-radius:8px;padding:12px 14px;border-top:3px solid #185FA5;">
      <p style="font-size:11px;color:#4A5F72;margin:0 0 4px 0;">{label}</p>
      <p style="font-size:22px;font-weight:600;color:#0C2340;margin:0;">{value}</p>
      {delta_html}
    </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PAGE
# ══════════════════════════════════════════════════════════════════════════════
def main():
    st.title("전략적 인력수급 & Physical AI 전환")
    st.caption("직영 · 협력사 · 재고용 · 로봇 통합 공수 최적화 | 수주 전략 연동 시뮬레이션")

    # ── 사이드바: 시뮬레이션 파라미터 ────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙ 시뮬레이션 파라미터")
        st.caption("슬라이더를 조작하면 모든 차트가 실시간으로 업데이트됩니다.")

        rehire_pct = st.slider(
            "재고용 비중 (%)", min_value=0, max_value=30, value=11, step=1,
            help="전체 공수 중 재고용 투입 비중"
        )
        partner_pct = st.slider(
            "협력사 비중 (%)", min_value=40, max_value=70, value=51, step=1,
            help="전체 공수 중 협력사 투입 비중"
        )
        ai_rate = st.slider(
            "AI 대체율 (%)", min_value=0, max_value=40, value=8, step=1,
            help="용접·도장 등 자동화 공정 대체 비율"
        )

        st.markdown("---")
        view_year = st.select_slider(
            "조회 기준 연도", options=YEARS, value=2026,
            help="AI & Reskilling 탭에서 해당 연도 데이터를 표시합니다."
        )

        st.markdown("---")
        st.markdown("**데이터 연결 상태**")
        if get_client():
            st.success("Supabase 연결됨", icon="✅")
        else:
            st.warning("샘플 데이터 사용 중", icon="⚠️")
            st.caption("Supabase 연결 후 실데이터로 전환됩니다.")

    # ── 데이터 로드 (DB 우선 → fallback mock) ────────────────────────────────
    df_sd_raw = fetch_table("workforce_demand")
    df_supply_raw = fetch_table("workforce_supply")
    df_ai_raw = fetch_table("job_ai_adoption")
    df_pg_raw = fetch_table("partner_grades")
    df_mh_raw = fetch_table("mh_standard")

    # mock fallback
    df_sd = mock_supply_demand(rehire_pct, partner_pct, ai_rate) if df_sd_raw.empty else df_sd_raw
    df_ai = mock_job_ai(ai_rate) if df_ai_raw.empty else df_ai_raw
    df_pg = mock_partner_grades() if df_pg_raw.empty else df_pg_raw
    df_mh = mock_mh_standard() if df_mh_raw.empty else df_mh_raw
    df_hm = mock_heatmap()
    kpis = mock_kpis(rehire_pct, partner_pct, ai_rate, df_sd)

    # ── 탭 구성 ───────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 생산 공수 현황",
        "🔮 인력 예측 시뮬레이션",
        "🤖 Physical AI · 재배치",
        "🔩 직무별 전략 (용접)",
    ])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1: 생산 공수 현황
    # ─────────────────────────────────────────────────────────────────────────
    with tab1:
        col1, col2, col3, col4 = st.columns(4)
        with col1: kpi_card("총 투입 공수", kpis["total_mh"], "▲ 3.2% vs 계획", True)
        with col2: kpi_card("직영 비중", kpis["direct_pct"], "▼ 목표 45% 미달", False)
        with col3: kpi_card("협력사 의존도", kpis["partner_pct"], "▲ 리스크 주시", False)
        with col4: kpi_card("재고용 투입", kpis["rehire_pct"], "▲ 확대 추세", True)

        st.warning(
            "⚠️ **LNGC 의장 공정** — 협력사 A등급 기량 부족 감지. "
            "3개 공구 공기 지연 리스크 **D+18일**",
            icon="🚨"
        )

        col_l, col_r = st.columns([1.1, 1])
        with col_l:
            st.markdown("##### 선종별 인력 구성비")
            st.plotly_chart(
                chart_stacked_supply(df_sd),
                use_container_width=True, key="stacked_supply"
            )
        with col_r:
            st.markdown("##### 공기 지연 리스크 히트맵")
            st.caption("1 = 저위험 · 6 = 고위험 (공정 × 분기)")
            st.plotly_chart(
                chart_heatmap(df_hm),
                use_container_width=True, key="heatmap"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2: 인력 예측 시뮬레이션
    # ─────────────────────────────────────────────────────────────────────────
    with tab2:
        col1, col2, col3, col4 = st.columns(4)
        gap_val = df_sd.loc[df_sd.year == 2028, "gap"].values[0] * 100 if "gap" in df_sd.columns else -4200
        gap_color = "normal" if gap_val >= 0 else "inverse"
        with col1: kpi_card("2028 Gap 예측", kpis["gap_2028"], "긴급 대응 필요", gap_val >= 0)
        with col2: kpi_card("정년 예정 (3년)", kpis["retire_3y"], "숙련도 손실 위험", False)
        with col3: kpi_card("재고용 가용 Pool", kpis["rehire_pool"], "의사 확인 완료", True)
        with col4: kpi_card("신규 채용 필요", kpis["new_hire"], "2026-28 누적", False)

        st.markdown("##### 인력 수급 전망 (수요 vs 공급)")
        st.caption(
            f"현재 설정: 재고용 {rehire_pct}% · 협력사 {partner_pct}% · AI 대체 {ai_rate}%  "
            f"→  2028년 Gap: **{gap_val:+,.0f} MH/월**"
        )
        st.plotly_chart(
            chart_supply_demand(df_sd),
            use_container_width=True, key="supply_demand"
        )

        # 시나리오 비교 카드
        st.markdown("##### 시나리오 비교")
        sc_cols = st.columns(3)
        scenarios = [
            ("시나리오 A: 현상 유지",    "재고용 11% · AI 0%",  -4200, False),
            ("시나리오 B: 재고용 확대",  "재고용 25% · AI 8%",  -1800, False),
            ("시나리오 C: AI + 재고용", "재고용 25% · AI 25%",  +500, True),
        ]
        for col, (title, desc, gap, good) in zip(sc_cols, scenarios):
            with col:
                kpi_card(title, f"{gap:+,} MH/월", desc, good)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3: Physical AI & 재배치
    # ─────────────────────────────────────────────────────────────────────────
    with tab3:
        col1, col2, col3, col4 = st.columns(4)
        with col1: kpi_card("용접 자동화율", kpis["automation"], "목표 45% (2030)", True)
        with col2: kpi_card("Reskilling 완료", kpis["reskilled"], "로봇 오퍼레이터", True)
        with col3: kpi_card("외주비 절감 (연)", kpis["cost_save"], "AI 대체 효과", True)
        with col4: kpi_card("멘토링 비중", kpis["mentor_pct"], "재고용 숙련공", None)

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("##### 인력 재배치 흐름 (Sankey)")
            st.plotly_chart(chart_sankey(ai_rate), use_container_width=True, key="sankey")
        with col_r:
            st.markdown("##### AI 도입 비용·효과 (Waterfall)")
            st.plotly_chart(chart_waterfall(ai_rate), use_container_width=True, key="waterfall")

        st.markdown("---")
        col_l2, col_r2 = st.columns(2)
        with col_l2:
            st.markdown(f"##### 직무별 자동화율 트렌드")
            st.plotly_chart(chart_ai_trend(df_ai), use_container_width=True, key="ai_trend")
        with col_r2:
            st.markdown(f"##### {view_year}년 직무별 현황")
            st.plotly_chart(chart_ai_adoption(df_ai, view_year), use_container_width=True, key="ai_adoption")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4: 직무별 전략 — 용접
    # ─────────────────────────────────────────────────────────────────────────
    with tab4:
        col1, col2, col3, col4 = st.columns(4)
        with col1: kpi_card("LNGC 표준 MH/m", "2.8", "실적 3.1 · +10.7% 초과", False)
        with col2: kpi_card("협력사 A등급 비중", "41%", "목표 60% 미달", False)
        with col3: kpi_card("Master Re-hire", "23명", "고난도 구간 전담", True)
        with col4: kpi_card("로봇 대체율", "19%", "직선 구간 기준", True)

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("##### 협력사별 기량 등급 분포")
            st.plotly_chart(chart_partner_grade(df_pg), use_container_width=True, key="partner_grade")
        with col_r:
            st.markdown("##### 선종별 MH/m — 표준 vs 실적")
            st.plotly_chart(chart_mh_comparison(df_mh), use_container_width=True, key="mh_comparison")

        st.markdown("---")
        st.markdown("##### Master Re-hire 전략 가이드라인")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.info(
                "**고난도 구간 전담**\n\n"
                "특수강·곡면 용접 등 로봇이 대체하기 어려운\n"
                "구간에 Master Re-hire를 우선 배치합니다.",
                icon="🎯"
            )
        with col_b:
            st.info(
                "**주니어 멘토링**\n\n"
                "직접 생산 40% + 기술 지도 60% 비율을 목표로\n"
                "숙련도 단절을 방지합니다.",
                icon="🎓"
            )
        with col_c:
            st.info(
                "**로봇 오퍼레이션 감독**\n\n"
                "자동 용접 로봇 품질 검수·파라미터 최적화를\n"
                "현장 경험을 통해 담당합니다.",
                icon="🤖"
            )

        st.markdown("---")
        st.markdown("##### 용접 직무 관리 전략 요약")
        strategy_data = {
            "구분": ["표준 공수", "협력사 관리", "재고용 (Master)", "Physical AI"],
            "관리 전략": [
                "선종별 난이도에 따른 용접 연장(m)당 MH 정규화 및 실적 편차 모니터링",
                "협력사별 기량 A/B/C 등급 분포 추적 및 공사 기성(대금) 적정성 연계 평가",
                "퇴직 숙련공을 고난도 구간 전담 및 주니어 멘토로 배치 (직접생산 40% : 멘토링 60%)",
                "자동 용접 로봇 도입 시 협력사 외주 물량 회수 및 직영 정예화 비중 산출",
            ],
            "KPI": [
                "MH/m 표준 대비 실적 편차 ±5% 이내",
                "A등급 비중 60% 이상 유지",
                "멘토링 시간 비중 ≥ 60%",
                "직선 구간 자동화율 ≥ 45% (2030)",
            ],
        }
        st.dataframe(
            pd.DataFrame(strategy_data),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    st.set_page_config(
        page_title="전략적 인력수급 & Physical AI",
        page_icon="🏗️",
        layout="wide",
    )
    main()