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
    "text_primary": "#17211b",
    "text_muted": "#4f5d54",
    "text_dim": "#6e7b72",
    "border": "#d9dfda",
    "border_strong": "#bcc7bf",
    
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
            "background": "#ffffff",
            "view": {"stroke": "transparent"},
            "font": "Inter, -apple-system, system-ui, sans-serif",
            "axis": {
                "labelColor": PALETTE["text_muted"],
                "titleColor": PALETTE["text_muted"],
                "gridColor": "#e3e8e4",
                "tickColor": "#d9dfda",
                "domainColor": "#bcc7bf",
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
                "font": "Inter, -apple-system, system-ui, sans-serif",
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
    """Inject a restrained, high-legibility application design system."""
    st.markdown(
        """
        <style>
        :root {
            --page: #f4f6f3;
            --surface: #ffffff;
            --surface-subtle: #f8faf7;
            --surface-strong: #eef2ed;
            --text: #17211b;
            --text-soft: #4f5d54;
            --text-faint: #6e7b72;
            --border: #d9dfda;
            --border-strong: #bcc7bf;
            --brand: #244b36;
            --brand-hover: #183c2a;
            --brand-soft: #e6efe9;
            --focus: #2d6b4a;
            --warning: #8a4b16;
            --radius: 8px;
            --radius-lg: 12px;
        }

        html, body, [class*="css"] {
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--text);
        }
        .stApp { background: var(--page); color: var(--text); }
        .main .block-container { max-width: 1440px; padding: 1rem 2rem 4rem; }
        header[data-testid="stHeader"] { background: var(--page); }
        footer, #MainMenu { visibility: hidden; }

        h1, h2, h3, h4 { color: var(--text) !important; letter-spacing: -.015em; }
        h1 { font-size: 2rem !important; line-height: 1.15 !important; font-weight: 680 !important; }
        h2 { font-size: 1.25rem !important; line-height: 1.3 !important; font-weight: 670 !important; }
        h3 { font-size: 1rem !important; line-height: 1.35 !important; font-weight: 660 !important; }
        p, label, .stCaption { color: var(--text-soft); }

        [data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
        [data-testid="stSidebar"] [data-testid="stMetric"] { min-height: 0; padding: .8rem; }

        .app-header {
            display:flex; align-items:center; justify-content:space-between; gap:1rem;
            padding:.7rem 0 1rem; border-bottom:1px solid var(--border); margin-bottom:1rem;
        }
        .brand-wrap { display:flex; align-items:center; gap:.7rem; }
        .brand-mark {
            width:38px; height:38px; display:grid; place-items:center; border-radius:8px;
            background:var(--brand); color:white; font-size:1rem; font-weight:700;
        }
        .brand-name { font-size:1rem; font-weight:700; color:var(--text); line-height:1.1; }
        .brand-kicker { color:var(--text-faint); font-size:.72rem; margin-top:.2rem; }
        .sync-pill { display:flex; align-items:center; gap:.45rem; color:var(--text-soft); font-size:.78rem; }
        .sync-dot { width:7px; height:7px; border-radius:50%; background:#2f7b4f; }

        .page-hero {
            display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:2rem; align-items:end;
            padding:1rem 0 1.25rem; margin-bottom:.8rem;
        }
        .eyebrow { color:var(--brand); font-size:.75rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
        .hero-title { color:var(--text); font-size:clamp(1.75rem,2.6vw,2.55rem); line-height:1.08; margin:.35rem 0 .55rem; font-weight:680; max-width:800px; }
        .hero-copy { max-width:760px; color:var(--text-soft); font-size:.98rem; line-height:1.55; }
        .hero-stat { text-align:right; border-left:1px solid var(--border); padding-left:1.5rem; }
        .hero-stat strong { display:block; font-size:1.65rem; color:var(--text); font-variant-numeric: tabular-nums; }
        .hero-stat span { color:var(--text-faint); font-size:.75rem; }

        .section-heading { display:flex; justify-content:space-between; align-items:end; gap:1rem; margin:1.8rem 0 .65rem; }
        .section-heading h2 { margin:0 !important; }
        .section-heading p { margin:.2rem 0 0; font-size:.84rem; }

        [data-testid="stExpander"] { background:var(--surface); border:1px solid var(--border) !important; border-radius:var(--radius-lg) !important; box-shadow:none !important; }
        [data-testid="stExpander"] details { border:0 !important; }
        [data-testid="stExpander"] summary { color:var(--text); font-size:.9rem; font-weight:650; }

        [data-testid="stMetric"] { min-height:104px; padding:1rem; border-radius:var(--radius-lg); background:var(--surface); border:1px solid var(--border); box-shadow:none; }
        [data-testid="stMetricLabel"] { color:var(--text-faint) !important; font-size:.75rem !important; font-weight:600 !important; }
        [data-testid="stMetricValue"] { color:var(--text) !important; font-size:1.8rem !important; font-weight:670 !important; font-variant-numeric:tabular-nums; }
        [data-testid="stMetricDelta"] { color:var(--brand) !important; }

        .insight-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.75rem; margin:.7rem 0 1.1rem; }
        .insight-card { padding:.9rem 1rem; border:1px solid var(--border); border-radius:var(--radius); background:var(--surface); }
        .insight-label { color:var(--text-faint); font-size:.72rem; font-weight:600; }
        .insight-value { color:var(--text); font-size:.95rem; font-weight:670; margin-top:.3rem; }
        .insight-note { color:var(--text-soft); font-size:.78rem; margin-top:.2rem; }

        .stButton > button, .stLinkButton > a {
            min-height:38px; border-radius:7px !important; border:1px solid var(--border-strong) !important;
            background:var(--surface) !important; color:var(--text) !important; font-weight:620 !important;
            box-shadow:none !important; transition:background .1s ease,border-color .1s ease !important;
        }
        .stButton > button:hover, .stLinkButton > a:hover { border-color:var(--brand) !important; background:var(--brand-soft) !important; color:var(--brand) !important; }
        .stButton > button[kind="primary"] { background:var(--brand) !important; color:white !important; border-color:var(--brand) !important; }
        .stButton > button[kind="primary"]:hover { background:var(--brand-hover) !important; color:white !important; }
        .stButton > button:focus-visible, .stLinkButton > a:focus-visible { outline:3px solid rgba(45,107,74,.25) !important; outline-offset:2px; }

        div[data-baseweb="select"] > div, [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input, .stTextInput input {
            min-height:40px; background:var(--surface) !important; border-color:var(--border-strong) !important;
            color:var(--text) !important; border-radius:7px !important; box-shadow:none !important;
        }
        div[data-baseweb="select"] > div:focus-within, [data-testid="stDateInput"] input:focus,
        [data-testid="stNumberInput"] input:focus, .stTextInput input:focus { border-color:var(--focus) !important; box-shadow:0 0 0 3px rgba(45,107,74,.12) !important; }
        [data-testid="stWidgetLabel"] p { color:var(--text); font-size:.8rem; font-weight:620; }
        [data-testid="stSlider"] [role="slider"] { background:var(--brand) !important; }

        [data-testid="stAlert"] { border-radius:8px; border:1px solid var(--border); background:var(--surface); color:var(--text); }
        hr { border-color:var(--border) !important; }

        [data-testid="stSegmentedControl"] {
            position:sticky; top:.55rem; z-index:20; padding:.25rem; margin:.1rem 0 .9rem;
            border:1px solid var(--border); border-radius:9px; background:rgba(255,255,255,.96);
            box-shadow:0 1px 2px rgba(23,33,27,.04);
        }
        [data-testid="stSegmentedControl"] button { min-height:38px; border-radius:6px !important; color:var(--text-soft) !important; font-weight:620 !important; }
        [data-testid="stSegmentedControl"] button:hover { background:var(--surface-subtle) !important; }
        [data-testid="stSegmentedControl"] button[aria-checked="true"] { background:var(--brand) !important; color:white !important; }

        .gallery-summary { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.65rem .8rem; margin:.6rem 0 .8rem; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--text-soft); font-size:.82rem; }
        .sighting-card { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); margin-bottom:1rem; }
        .card-thumbnail { background:#e8ece8; min-height:230px; display:grid; place-items:center; overflow:hidden; }
        .card-thumbnail img { width:100%; aspect-ratio:16/10; object-fit:cover; display:block; }
        .card-content { padding:.9rem 1rem 1rem; }
        .card-title { font-size:.95rem; font-weight:670; color:var(--text); }
        .card-meta { color:var(--text-soft); font-size:.8rem; margin-top:.2rem; }
        .card-temp, .card-moon { display:inline-flex; margin-right:.65rem; margin-top:.5rem; color:var(--text-soft); font-size:.75rem; }
        .embed-wrap { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); }
        .small-muted { color:var(--text-faint); font-size:.76rem; }

        [data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:var(--radius-lg); overflow:hidden; background:var(--surface); }
        [data-testid="stDataFrame"] canvas { font-family:Inter,ui-sans-serif,system-ui,sans-serif !important; }
        [data-testid="stDataFrame"] [role="columnheader"] { background:var(--surface-strong) !important; color:var(--text) !important; font-weight:650 !important; }

        @media (max-width:900px) {
            .main .block-container { padding:.75rem .9rem 3rem; }
            .page-hero { grid-template-columns:1fr; gap:.8rem; }
            .hero-stat { text-align:left; border-left:0; border-top:1px solid var(--border); padding:.75rem 0 0; }
            .insight-grid { grid-template-columns:1fr; }
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
                    st.markdown(f'<div style="margin-top:0.7rem;"><a href="{url}" target="_blank" style="font-size:0.85rem; color: var(--brand); font-weight: 600; text-decoration: none;">View in Drive ↗</a></div>', unsafe_allow_html=True)
                st.markdown("</div></div>", unsafe_allow_html=True)

    st.caption(f"Showing {page_start + 1:,}–{page_end:,} of {total_items:,}")

