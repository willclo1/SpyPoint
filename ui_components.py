# ui_components.py
from __future__ import annotations

from typing import Dict, Tuple, List

import altair as alt
import pandas as pd
import streamlit as st

from data_prep import clamp_temp_domain
from drive_io import resolve_page_images


# =============================================================================
# Design System - Exact Ranch Wildlife Theme
# =============================================================================

PALETTE = {
    # Exact earth-tone palette from website
    "earth_dark": "#1a1612",
    "earth_charcoal": "#2d2520",
    "earth_brown": "#3d332c",
    "earth_clay": "#4a3f35",
    "earth_tan": "#8b7355",
    "earth_sand": "#c4a77d",
    "earth_cream": "#e8d5b7",
    
    # Nature accent colors from website
    "sage": "#8a9a5b",
    "forest": "#4a5d3f",
    "sunset": "#d97642",
    "sky": "#7ea8be",
    
    # UI colors - exact from website
    "text_primary": "#f5f1ea",
    "text_muted": "rgba(245, 241, 234, 0.7)",
    "text_dim": "rgba(245, 241, 234, 0.45)",
    "border": "rgba(245, 241, 234, 0.12)",
    "border_strong": "rgba(245, 241, 234, 0.22)",
    
    # Semantic colors
    "success": "#8a9a5b",
    "info": "#7ea8be",
    "warning": "#d97642",
    "neutral": "#94A3B8",
}

# Wildlife colors - vibrant but earthy
WILDLIFE_PALETTE = [
    "#8a9a5b",  # sage
    "#d97642",  # sunset
    "#7ea8be",  # sky
    "#c4a77d",  # sand
    "#4a5d3f",  # forest
    "#8b7355",  # tan
    "#4E79A7",  # blue
    "#E15759",  # red
    "#76B7B2",  # teal
    "#59A14F",  # green
    "#EDC948",  # yellow
    "#B07AA1",  # purple
    "#FF9DA7",  # pink
    "#9C755F",  # brown
    "#BAB0AC",  # warm gray
    "#17BECF",  # cyan
]

SECTION_COLORS = {
    "wildlife": PALETTE["sage"],
    "people": PALETTE["sky"],
    "vehicle": PALETTE["sunset"],
}


def stable_color_domain(values: List[str], palette: List[str], *, pin_other_gray: bool = True) -> Tuple[List[str], List[str]]:
    """Stable category -> color mapping."""
    cleaned = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            cleaned.append(s)

    domain = sorted(set(cleaned))
    if not domain:
        return [], []

    if pin_other_gray and "Other" in domain:
        domain_no_other = [d for d in domain if d != "Other"]
        range_no_other = [palette[i % len(palette)] for i in range(len(domain_no_other))]
        return domain_no_other + ["Other"], range_no_other + [PALETTE["neutral"]]

    color_range = [palette[i % len(palette)] for i in range(len(domain))]
    return domain, color_range


def _altair_theme():
    """Altair theme matching website exactly."""
    return {
        "config": {
            "background": "transparent",
            "view": {"stroke": "transparent"},
            "font": "'DM Sans', -apple-system, system-ui, sans-serif",
            "axis": {
                "labelColor": PALETTE["text_muted"],
                "titleColor": PALETTE["text_muted"],
                "gridColor": "rgba(245, 241, 234, 0.08)",
                "tickColor": "rgba(245, 241, 234, 0.10)",
                "domainColor": "rgba(245, 241, 234, 0.12)",
                "labelFontSize": 12,
                "titleFontSize": 13,
                "titleFontWeight": 600,
                "labelPadding": 8,
                "titlePadding": 12,
            },
            "legend": {
                "labelColor": PALETTE["text_muted"],
                "titleColor": PALETTE["text_primary"],
                "labelFontSize": 12,
                "titleFontSize": 13,
                "titleFontWeight": 700,
                "symbolType": "circle",
                "symbolSize": 100,
                "padding": 10,
                "orient": "top",
            },
            "title": {
                "color": PALETTE["text_primary"],
                "fontSize": 16,
                "fontWeight": 700,
                "anchor": "start",
                "font": "'Crimson Pro', Georgia, serif",
            },
        }
    }


try:
    alt.themes.register("ranch_theme", _altair_theme)
except Exception:
    pass

alt.themes.enable("ranch_theme")


def apply_chart_theme(chart: alt.Chart) -> alt.Chart:
    """Polish charts to match website."""
    return (
        chart
        .configure_view(strokeOpacity=0)
        .configure_axis(grid=True, gridOpacity=0.4)
        .configure_axisX(labelAngle=0)
    )


# =============================================================================
# Cached IO
# =============================================================================

@st.cache_data(ttl=3600)
def load_thumbnail_cached(file_id: str, _drive_client_factory, _download_bytes_func):
    """Cache thumbnail downloads."""
    try:
        service = _drive_client_factory()
        img_bytes = _download_bytes_func(service, file_id)
        return img_bytes
    except Exception:
        return None


# =============================================================================
# CSS / Layout - EXACT Website Match
# =============================================================================

def inject_css():
    """Inject the application-wide visual system."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,600;6..72,700&display=swap');

        :root {
            --bg: #0d1511;
            --surface: #142019;
            --surface-2: #19281f;
            --surface-3: #203229;
            --text: #f6f3eb;
            --muted: #aebbb1;
            --faint: #78867c;
            --line: rgba(235, 242, 236, .11);
            --line-strong: rgba(235, 242, 236, .19);
            --accent: #a8bd79;
            --accent-2: #d6a268;
            --accent-soft: rgba(168, 189, 121, .13);
            --danger: #d97863;
            --radius-sm: 10px;
            --radius: 16px;
            --radius-lg: 24px;
            --shadow: 0 16px 48px rgba(0,0,0,.22);
        }

        html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
        .stApp {
            color: var(--text);
            background:
                radial-gradient(circle at 10% -10%, rgba(168,189,121,.13), transparent 30%),
                radial-gradient(circle at 95% 5%, rgba(214,162,104,.09), transparent 25%),
                var(--bg);
        }
        .main .block-container {
            max-width: 1380px;
            padding: 1.4rem 2.2rem 4rem;
        }
        header[data-testid="stHeader"] { background: transparent; }
        footer { visibility: hidden; }
        #MainMenu { visibility: hidden; }

        h1, h2, h3 {
            font-family: 'Newsreader', Georgia, serif !important;
            color: var(--text) !important;
            letter-spacing: -.025em !important;
        }
        h1 { font-size: clamp(2rem, 3vw, 3.25rem) !important; line-height: 1.04 !important; }
        h2 { font-size: 1.65rem !important; }
        h3 { font-size: 1.25rem !important; }
        p, label, .stCaption { color: var(--muted); }

        [data-testid="stSidebar"] {
            background: rgba(16, 27, 21, .94);
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.25rem; }
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 { font-family: 'DM Sans', sans-serif !important; letter-spacing: 0 !important; }

        .app-header {
            display:flex; align-items:center; justify-content:space-between; gap:1rem;
            padding: .75rem 0 1.35rem; border-bottom:1px solid var(--line); margin-bottom:1.2rem;
        }
        .brand-wrap { display:flex; align-items:center; gap:.85rem; }
        .brand-mark {
            width:46px; height:46px; display:grid; place-items:center; border-radius:14px;
            background: var(--accent-soft); border:1px solid rgba(168,189,121,.25); font-size:1.45rem;
        }
        .brand-name { font-family:'Newsreader',serif; font-size:1.45rem; font-weight:700; color:var(--text); line-height:1; }
        .brand-kicker { color:var(--faint); font-size:.72rem; text-transform:uppercase; letter-spacing:.12em; margin-top:.28rem; }
        .sync-pill {
            display:inline-flex; align-items:center; gap:.45rem; padding:.5rem .72rem; border-radius:999px;
            background:rgba(255,255,255,.035); border:1px solid var(--line); color:var(--muted); font-size:.8rem;
        }
        .sync-dot { width:7px; height:7px; border-radius:99px; background:var(--accent); box-shadow:0 0 0 4px rgba(168,189,121,.12); }

        .page-hero {
            display:grid; grid-template-columns:minmax(0,1fr) auto; gap:1.5rem; align-items:end;
            margin:1.4rem 0 1.25rem;
        }
        .eyebrow { color:var(--accent); text-transform:uppercase; letter-spacing:.13em; font-size:.72rem; font-weight:700; }
        .hero-title { font-family:'Newsreader',serif; font-size:clamp(2rem,3.4vw,3.4rem); line-height:1; color:var(--text); margin:.32rem 0 .55rem; font-weight:700; }
        .hero-copy { max-width:720px; color:var(--muted); font-size:1rem; }
        .hero-stat { text-align:right; }
        .hero-stat strong { display:block; font-family:'Newsreader',serif; font-size:2rem; color:var(--text); }
        .hero-stat span { color:var(--faint); font-size:.78rem; }

        .section-heading { display:flex; justify-content:space-between; align-items:end; gap:1rem; margin:2rem 0 .8rem; }
        .section-heading h2 { margin:0 !important; }
        .section-heading p { margin:.2rem 0 0; font-size:.9rem; }

        .filter-shell, [data-testid="stExpander"] {
            background:rgba(20,32,25,.78) !important; border:1px solid var(--line) !important;
            border-radius:var(--radius-lg) !important; box-shadow:none !important;
        }
        [data-testid="stExpander"] details { border:0 !important; }
        [data-testid="stExpander"] summary { font-weight:700; color:var(--text); padding:.35rem .25rem; }

        [data-testid="stMetric"] {
            min-height:132px; padding:1.15rem 1.2rem; border-radius:var(--radius-lg);
            background:linear-gradient(145deg, rgba(31,49,39,.92), rgba(20,32,25,.92));
            border:1px solid var(--line); box-shadow:none;
        }
        [data-testid="stMetricLabel"] { color:var(--muted) !important; font-size:.78rem !important; text-transform:uppercase; letter-spacing:.07em; }
        [data-testid="stMetricValue"] { font-family:'Newsreader',serif !important; color:var(--text) !important; font-size:2.25rem !important; }
        [data-testid="stMetricDelta"] { color:var(--accent) !important; }

        .insight-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; margin:.8rem 0 1.2rem; }
        .insight-card { padding:1rem 1.05rem; border:1px solid var(--line); border-radius:var(--radius); background:rgba(255,255,255,.025); }
        .insight-label { color:var(--faint); font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; }
        .insight-value { color:var(--text); font-size:1rem; font-weight:700; margin-top:.3rem; }
        .insight-note { color:var(--muted); font-size:.78rem; margin-top:.25rem; }

        .stButton > button {
            border-radius:12px !important; border:1px solid var(--line-strong) !important;
            background:rgba(255,255,255,.035) !important; color:var(--text) !important;
            font-weight:650 !important; box-shadow:none !important; transition:.18s ease !important;
        }
        .stButton > button:hover { border-color:rgba(168,189,121,.55) !important; background:var(--accent-soft) !important; transform:translateY(-1px); }
        .stButton > button[kind="primary"] { background:var(--accent) !important; color:#122016 !important; border-color:var(--accent) !important; }
        .stButton > button[kind="primary"]:hover { background:#b6c98d !important; }

        div[data-baseweb="select"] > div,
        [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input,
        .stTextInput input {
            background:rgba(255,255,255,.035) !important; border-color:var(--line) !important;
            color:var(--text) !important; border-radius:12px !important;
        }
        [data-testid="stSlider"] [role="slider"] { background:var(--accent) !important; }
        [data-testid="stSlider"] div[data-testid="stTickBarMin"], [data-testid="stSlider"] div[data-testid="stTickBarMax"] { color:var(--muted); }

        [data-testid="stAlert"] { border-radius:14px; border:1px solid var(--line); background:rgba(255,255,255,.035); }
        hr { border-color:var(--line) !important; }

        .sighting-card {
            overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--line);
            background:linear-gradient(180deg, rgba(31,49,39,.98), rgba(20,32,25,.98));
            margin-bottom:1rem; transition:transform .18s ease, border-color .18s ease;
        }
        .sighting-card:hover { transform:translateY(-2px); border-color:rgba(168,189,121,.4); }
        .card-thumbnail { background:#0b120e; min-height:260px; display:grid; place-items:center; overflow:hidden; }
        .card-thumbnail img { width:100%; aspect-ratio:16/10; object-fit:cover; display:block; }
        .card-content { padding:1rem 1.05rem 1.1rem; }
        .card-title { font-size:1.02rem; font-weight:700; color:var(--text); }
        .card-meta { color:var(--muted); font-size:.82rem; margin-top:.25rem; }
        .card-temp, .card-moon { display:inline-flex; margin-right:.45rem; margin-top:.45rem; padding:.28rem .48rem; border-radius:999px; background:rgba(255,255,255,.045); color:var(--muted); font-size:.75rem; }

        .gallery-summary { display:flex; justify-content:space-between; align-items:center; gap:1rem; margin:.6rem 0 1rem; color:var(--muted); font-size:.86rem; }

        [data-testid="stSegmentedControl"] {
            position: sticky; top: .65rem; z-index: 20;
            padding: .4rem; margin: .15rem 0 1rem;
            border: 1px solid var(--line); border-radius: 16px;
            background: rgba(13, 21, 17, .88);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
        }
        [data-testid="stSegmentedControl"] button {
            min-height: 42px; border-radius: 11px !important;
            transition: background .16s ease, color .16s ease, transform .16s ease !important;
        }
        [data-testid="stSegmentedControl"] button:hover { transform: translateY(-1px); }
        [data-testid="stSegmentedControl"] button[aria-checked="true"] {
            background: var(--accent-soft) !important;
            color: var(--text) !important;
        }
        [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] {
            animation: ranch-fade-in .16s ease-out;
        }
        @keyframes ranch-fade-in {
            from { opacity: .72; transform: translateY(2px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .embed-wrap { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--line); background:var(--surface); }
        .small-muted { color:var(--faint); font-size:.78rem; }

        @media (max-width: 900px) {
            .main .block-container { padding:1rem 1rem 3rem; }
            .page-hero { grid-template-columns:1fr; }
            .hero-stat { text-align:left; }
            .insight-grid { grid-template-columns:1fr; }
            .app-header { align-items:flex-start; }
            .sync-pill { display:none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_timeline(base: pd.DataFrame, section: str):
    """
    Daily timeline with MULTIPLE trend lines when ≤4 species selected.
    Aggregated area chart when >4 species or no species filter.
    """
    st.subheader("📅 Daily Activity Timeline")
    
    if base.empty or "datetime" not in base.columns:
        st.info("No timeline data available")
        return
    
    # Determine if we should show individual lines
    if section == "Wildlife" and "wildlife_label" in base.columns:
        unique_species = base["wildlife_label"].nunique()
        species_list = base["wildlife_label"].unique().tolist()
        
        # Show individual lines if 4 or fewer species
        if unique_species <= 4 and unique_species > 0:
            # Create daily counts by species
            daily_by_species = (
                base.groupby([base["datetime"].dt.date, "wildlife_label"])
                .size()
                .reset_index(name="Events")
            )
            daily_by_species.columns = ["Date", "Species", "Events"]
            daily_by_species["Date"] = pd.to_datetime(daily_by_species["Date"])
            
            # Get stable colors for species
            domain, color_range = stable_color_domain(
                species_list,
                WILDLIFE_PALETTE,
                pin_other_gray=("Other" in species_list),
            )
            
            # Create multi-line chart
            chart = (
                alt.Chart(daily_by_species)
                .mark_line(
                    point=True,
                    strokeWidth=3,
                    opacity=0.9,
                )
                .encode(
                    x=alt.X("Date:T", title="Date", axis=alt.Axis(format="%b %d", labelAngle=0)),
                    y=alt.Y("Events:Q", title="Event Count"),
                    color=alt.Color(
                        "Species:N",
                        scale=alt.Scale(domain=domain, range=color_range),
                        legend=alt.Legend(
                            title="Species",
                            orient="top",
                            direction="horizontal",
                            titleFontSize=14,
                            titleFontWeight=700,
                            labelFontSize=12,
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("Date:T", title="Date", format="%B %d, %Y"),
                        alt.Tooltip("Species:N", title="Species"),
                        alt.Tooltip("Events:Q", title="Events"),
                    ],
                )
                .properties(height=350)
            )
            
            st.altair_chart(apply_chart_theme(chart), width="stretch")
            st.caption(f"Showing individual trend lines for {unique_species} species")
            return
    
    # Default: Aggregated area chart
    daily = base.groupby(base["datetime"].dt.date).size().reset_index(name="Events")
    daily.columns = ["Date", "Events"]
    daily["Date"] = pd.to_datetime(daily["Date"])
    
    color = SECTION_COLORS.get(section.lower(), PALETTE["sage"])
    
    chart = (
        alt.Chart(daily)
        .mark_area(
            line={"color": color, "strokeWidth": 2},
            color=alt.Gradient(
                gradient="linear",
                stops=[
                    alt.GradientStop(color=color, offset=0),
                    alt.GradientStop(color=PALETTE["earth_dark"], offset=1),
                ],
                x1=0, x2=0, y1=0, y2=1,
            ),
            opacity=0.75,
        )
        .encode(
            x=alt.X("Date:T", title="Date", axis=alt.Axis(format="%b %d", labelAngle=0)),
            y=alt.Y("Events:Q", title="Event Count"),
            tooltip=[
                alt.Tooltip("Date:T", title="Date", format="%B %d, %Y"),
                alt.Tooltip("Events:Q", title="Events"),
            ],
        )
        .properties(height=350)
    )
    
    st.altair_chart(apply_chart_theme(chart), width="stretch")


def render_patterns(base: pd.DataFrame, section: str, include_other: bool, bar_style: str, time_gran: str):
    """Pattern analysis charts with earth-tone wildlife palette."""
    st.subheader("📊 Activity Patterns")
    
    if base.empty:
        st.info("No pattern data available")
        return
    
    # Determine grouping column
    if section == "Wildlife":
        group_col = "wildlife_label"
    else:
        group_col = "event_type"
    
    # Time granularity
    if time_gran == "Hour":
        base["time_bin"] = base["datetime"].dt.hour
        time_title = "Hour of Day"
    elif time_gran == "2-hour":
        base["time_bin"] = (base["datetime"].dt.hour // 2) * 2
        time_title = "2-Hour Block"
    else:  # 4-hour
        base["time_bin"] = (base["datetime"].dt.hour // 4) * 4
        time_title = "4-Hour Block"
    
    base["day_of_week"] = base["datetime"].dt.day_name()
    
    # By time of day
    by_time = base.groupby(["time_bin", group_col]).size().reset_index(name="Sightings")
    by_time.columns = ["time_bin", "animal_group", "Sightings"]
    
    # By day of week
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day = base.groupby(["day_of_week", group_col]).size().reset_index(name="Sightings")
    by_day.columns = ["day_of_week", "animal_group", "Sightings"]
    
    # Color encoding
    domain, color_range = stable_color_domain(
        base[group_col].unique().tolist(),
        WILDLIFE_PALETTE,
        pin_other_gray=(not include_other),
    )
    
    color_enc = alt.Color(
        "animal_group:N",
        scale=alt.Scale(domain=domain, range=color_range),
        legend=alt.Legend(
            title=section,
            orient="top",
            direction="horizontal",
        ),
    )
    
    # Time chart
    if bar_style == "Grouped":
        time_chart = (
            alt.Chart(by_time)
            .mark_bar(opacity=0.9, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("time_bin:O", title=time_title, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=color_enc,
                xOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("time_bin:O", title=time_title),
                    alt.Tooltip("animal_group:N", title=section),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=320)
        )
    else:  # Stacked
        time_chart = (
            alt.Chart(by_time)
            .mark_bar(opacity=0.9, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("time_bin:O", title=time_title, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=color_enc,
                tooltip=[
                    alt.Tooltip("time_bin:O", title=time_title),
                    alt.Tooltip("animal_group:N", title=section),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=320)
        )
    
    # Day chart
    if bar_style == "Grouped":
        day_chart = (
            alt.Chart(by_day)
            .mark_bar(opacity=0.9, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("day_of_week:N", title="Day of Week", sort=day_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=color_enc,
                xOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("day_of_week:N", title="Day"),
                    alt.Tooltip("animal_group:N", title=section),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=320)
        )
    else:  # Stacked
        day_chart = (
            alt.Chart(by_day)
            .mark_bar(opacity=0.9, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("day_of_week:N", title="Day of Week", sort=day_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=color_enc,
                tooltip=[
                    alt.Tooltip("day_of_week:N", title="Day"),
                    alt.Tooltip("animal_group:N", title=section),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=320)
        )
    
    # Moon phase chart (if available)
    if "moon_phase_clean" in base.columns and base["moon_phase_clean"].notna().any():
        moon_order = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", 
                      "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
        by_moon = base.groupby(["moon_phase_clean", group_col]).size().reset_index(name="Sightings")
        by_moon.columns = ["moon_phase_clean", "animal_group", "Sightings"]
        
        if by_moon["moon_phase_clean"].notna().any():
            if bar_style == "Grouped":
                moon_chart = (
                    alt.Chart(by_moon)
                    .mark_bar(opacity=0.9, cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                    .encode(
                        y=alt.Y("moon_phase_clean:N", title="Moon Phase", sort=moon_order),
                        x=alt.X("Sightings:Q", title="Count"),
                        color=color_enc,
                        yOffset="animal_group:N",
                        tooltip=[
                            alt.Tooltip("moon_phase_clean:N", title="Moon Phase"),
                            alt.Tooltip("animal_group:N", title=section),
                            alt.Tooltip("Sightings:Q", title="Count"),
                        ],
                    )
                    .properties(height=280)
                )
            else:
                moon_chart = (
                    alt.Chart(by_moon)
                    .mark_bar(opacity=0.9, cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                    .encode(
                        y=alt.Y("moon_phase_clean:N", title="Moon Phase", sort=moon_order),
                        x=alt.X("Sightings:Q", title="Count"),
                        color=color_enc,
                        tooltip=[
                            alt.Tooltip("moon_phase_clean:N", title="Moon Phase"),
                            alt.Tooltip("animal_group:N", title=section),
                            alt.Tooltip("Sightings:Q", title="Count"),
                        ],
                    )
                    .properties(height=280)
                )
            
            # Render all three charts
            cA, cB = st.columns(2)
            with cA:
                st.markdown("**By Time of Day**")
                st.altair_chart(apply_chart_theme(time_chart), width="stretch")
            with cB:
                st.markdown("**By Day of Week**")
                st.altair_chart(apply_chart_theme(day_chart), width="stretch")
            
            st.markdown("**By Moon Phase**")
            st.altair_chart(apply_chart_theme(moon_chart), width="stretch")
        else:
            # No moon data - just show time and day
            cA, cB = st.columns(2)
            with cA:
                st.markdown("**By Time of Day**")
                st.altair_chart(apply_chart_theme(time_chart), width="stretch")
            with cB:
                st.markdown("**By Day of Week**")
                st.altair_chart(apply_chart_theme(day_chart), width="stretch")
    else:
        # No moon_phase_clean column - just show time and day
        cA, cB = st.columns(2)
        with cA:
            st.markdown("**By Time of Day**")
            st.altair_chart(apply_chart_theme(time_chart), width="stretch")
        with cB:
            st.markdown("**By Day of Week**")
            st.altair_chart(apply_chart_theme(day_chart), width="stretch")


# =============================================================================
# Gallery
# =============================================================================

def render_listing_and_viewer(
    base: pd.DataFrame,
    section: str,
    include_other: bool,
    root_folder_id: str,
    drive_client_factory,
    download_bytes_func,
):
    """Render a paginated gallery and resolve only current-page images."""
    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    if section == "Wildlife" and not include_other:
        view = view[view["wildlife_label"] != "Other"]

    if view.empty:
        st.info("No sightings match your filters")
        return

    page_size = st.selectbox(
        "Photos per page",
        options=[8, 12, 20, 40],
        index=1,
        key="gallery_page_size",
    )
    total_items = len(view)
    total_pages = max(1, (total_items + page_size - 1) // page_size)

    if "gallery_page" not in st.session_state:
        st.session_state.gallery_page = 1
    st.session_state.gallery_page = min(max(1, st.session_state.gallery_page), total_pages)

    nav_left, nav_center, nav_right = st.columns([1, 2, 1])
    with nav_left:
        if st.button(
            "← Previous",
            disabled=st.session_state.gallery_page <= 1,
            width="stretch",
            key="gallery_previous",
        ):
            st.session_state.gallery_page -= 1
            st.rerun(scope="fragment")
    with nav_center:
        selected_page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=st.session_state.gallery_page,
            step=1,
            key="gallery_page_input",
        )
        if selected_page != st.session_state.gallery_page:
            st.session_state.gallery_page = int(selected_page)
            st.rerun(scope="fragment")
        st.caption(f"Page {st.session_state.gallery_page:,} of {total_pages:,} • {total_items:,} sightings")
    with nav_right:
        if st.button(
            "Next →",
            disabled=st.session_state.gallery_page >= total_pages,
            width="stretch",
            key="gallery_next",
        ):
            st.session_state.gallery_page += 1
            st.rerun(scope="fragment")

    page_start = (st.session_state.gallery_page - 1) * page_size
    page_end = min(page_start + page_size, total_items)
    display_view = view.iloc[page_start:page_end]

    page_items = tuple(
        (str(row.camera).strip(), str(row.filename).strip())
        for row in display_view[["camera", "filename"]].itertuples(index=False)
    )
    with st.spinner("Loading this page's photos..."):
        page_images = resolve_page_images(root_folder_id, page_items)

    cols_per_row = 2
    rows = (len(display_view) + cols_per_row - 1) // cols_per_row

    for row_idx in range(rows):
        cols = st.columns(cols_per_row, gap="large")
        for col_idx in range(cols_per_row):
            item_idx = row_idx * cols_per_row + col_idx
            if item_idx >= len(display_view):
                break

            row = display_view.iloc[item_idx]
            cam = str(row.get("camera", "")).strip()
            fn = str(row.get("filename", "")).strip()
            dt = row.get("datetime")
            temp = row.get("temp_f")
            moon_emoji = row.get("moon_emoji", "")
            moon_phase = row.get("moon_phase_clean", "")
            label = row.get("wildlife_label", "Other") if section == "Wildlife" else str(row.get("event_type", "")).capitalize()
            time_str = dt.strftime("%b %d, %I:%M %p") if pd.notna(dt) else "Unknown time"
            temp_str = f"{int(temp)}°F" if pd.notna(temp) else ""
            hit = page_images.get((cam, fn), {})
            file_id = hit.get("id", "")
            url = hit.get("webViewLink", "")

            with cols[col_idx]:
                st.markdown('<div class="sighting-card">', unsafe_allow_html=True)
                if file_id:
                    img_bytes = load_thumbnail_cached(file_id, drive_client_factory, download_bytes_func)
                    if img_bytes:
                        st.markdown('<div class="card-thumbnail">', unsafe_allow_html=True)
                        st.image(img_bytes, width="stretch")
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="card-thumbnail"><div style="font-size:2.2rem; opacity:0.35;">📷</div></div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="card-thumbnail"><div style="font-size:2.2rem; opacity:0.35;">📷</div></div>', unsafe_allow_html=True)

                st.markdown('<div class="card-content">', unsafe_allow_html=True)
                st.markdown(f'<div class="card-title">{label} • {cam}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card-meta">{time_str}</div>', unsafe_allow_html=True)
                if temp_str or moon_phase:
                    meta_line = '<div style="margin-top: 0.35rem;">'
                    if temp_str:
                        meta_line += f'<span class="card-temp">🌡️ {temp_str}</span>'
                    if moon_phase and moon_emoji:
                        meta_line += f'<span class="card-moon">{moon_emoji} {moon_phase}</span>'
                    meta_line += '</div>'
                    st.markdown(meta_line, unsafe_allow_html=True)
                if url:
                    st.markdown(f'<div style="margin-top:0.7rem;"><a href="{url}" target="_blank" style="font-size:0.85rem; color: var(--sage); font-weight: 600; text-decoration: none;">View in Drive ↗</a></div>', unsafe_allow_html=True)
                st.markdown("</div></div>", unsafe_allow_html=True)

    st.caption(f"Showing {page_start + 1:,}–{page_end:,} of {total_items:,}")

