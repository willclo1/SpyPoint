# ui_components.py
from __future__ import annotations

import html
import re
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
    "slate": "#64748B",
    "blue": "#4C78A8",
    "orange": "#F58518",
    "green": "#54A24B",
    "red": "#E45756",
    "teal": "#72B7B2",
    "purple": "#B279A2",
    "pink": "#FF9DA6",
    "brown": "#9D755D",
    "neutral": "#94A3B8",
}

# An accessible categorical palette that remains distinguishable on both
# Streamlit's dark and light themes. Chart backgrounds and text are inherited
# from Streamlit rather than hard-coded.
WILDLIFE_PALETTE = [
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#E45756",
    "#72B7B2",
    "#B279A2",
    "#FF9DA6",
    "#9D755D",
    "#A0CBE8",
    "#FFBF79",
    "#8CD17D",
    "#FF9D9A",
]

SECTION_COLORS = {
    "wildlife": PALETTE["green"],
    "people": PALETTE["blue"],
    "vehicle": PALETTE["orange"],
    "vehicles": PALETTE["orange"],
}


def stable_color_domain(values: List[str], palette: List[str], *, pin_other_gray: bool = True) -> Tuple[List[str], List[str]]:
    """Return a deterministic category-to-color mapping."""
    cleaned = []
    for value in values:
        if value is None:
            continue
        label = str(value).strip()
        if label:
            cleaned.append(label)

    domain = sorted(set(cleaned))
    if not domain:
        return [], []

    if pin_other_gray and "Other" in domain:
        named = [label for label in domain if label != "Other"]
        colors = [palette[index % len(palette)] for index in range(len(named))]
        return named + ["Other"], colors + [PALETTE["neutral"]]

    return domain, [palette[index % len(palette)] for index in range(len(domain))]


def apply_chart_theme(chart: alt.Chart) -> alt.Chart:
    """Apply structural chart styling while allowing Streamlit to theme colors."""
    return (
        chart
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_axis(
            grid=True,
            gridOpacity=0.16,
            domainOpacity=0.45,
            tickOpacity=0.45,
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight=600,
            labelPadding=7,
            titlePadding=10,
        )
        .configure_axisX(labelAngle=0)
        .configure_legend(
            orient="top",
            direction="horizontal",
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight=600,
            symbolSize=90,
            padding=4,
        )
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


def _large_thumbnail_url(url: str, width: int = 900) -> str:
    """Ask Drive for a larger browser-rendered thumbnail."""
    if not url:
        return ""
    if re.search(r"=[sw]\d+$", url):
        return re.sub(r"=[sw]\d+$", f"=w{width}", url)
    return f"{url}=w{width}"


# =============================================================================
# CSS / Layout - EXACT Website Match
# =============================================================================

def inject_css():
    """Inject a strictly dark, low-noise application design system.

    Dark mode is enforced unconditionally: there is no light palette and no
    ``prefers-color-scheme`` branch, so the app renders identically regardless
    of the viewer's OS/browser theme preference.
    """
    st.markdown(
        """
        <style>
        /* ---- Strictly enforced dark theme -------------------------------
           A single token set. No light-mode media query and no light
           data-theme override, so nothing can flip the palette to light.
           Every light-theme selector below is aliased to the dark tokens as
           a belt-and-suspenders guard against host theme switches.        */
        :root,
        html[data-theme="light"], body[data-theme="light"], [data-theme="light"],
        html[data-theme="dark"],  body[data-theme="dark"],  [data-theme="dark"] {
            color-scheme: dark !important;
            --page: #0a0e13;
            --page-glow: #101a26;
            --surface: #111821;
            --surface-raised: #17212c;
            --surface-muted: #0f151d;
            --text: #eef3f8;
            --text-soft: #b4c0cd;
            --text-faint: #8493a3;
            --border: #273444;
            --border-strong: #3a4a5c;
            --accent: #6ea8d7;
            --accent-hover: #8bbce3;
            --accent-soft: rgba(110, 168, 215, .14);
            --accent-ink: #06121d;
            --positive: #72b58d;
            --focus: rgba(110, 168, 215, .38);
            --table-header: #1b2733;
            --table-row-alt: #101720;
            --shadow-sm: 0 1px 2px rgba(0,0,0,.28);
            --shadow-md: 0 6px 20px -8px rgba(0,0,0,.55);
            --shadow-lg: 0 18px 44px -18px rgba(0,0,0,.7);
            --radius: 8px;
            --radius-lg: 12px;
        }

        html, body, [class*="css"] {
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--text);
        }
        .stApp {
            color: var(--text);
            background:
                radial-gradient(1100px 620px at 82% -8%, var(--page-glow) 0%, transparent 60%),
                radial-gradient(900px 500px at -6% 4%, #0d151f 0%, transparent 55%),
                var(--page);
            background-attachment: fixed;
        }
        .main .block-container { max-width: 1420px; padding: 1rem 2rem 4rem; }
        header[data-testid="stHeader"] { background: transparent; backdrop-filter: blur(6px); }
        footer, #MainMenu { visibility: hidden; }

        /* Custom scrollbars for a cohesive dark surface */
        * { scrollbar-color: var(--border-strong) transparent; scrollbar-width: thin; }
        ::-webkit-scrollbar { width: 11px; height: 11px; }
        ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 8px; border: 3px solid transparent; background-clip: content-box; }
        ::-webkit-scrollbar-thumb:hover { background: #4a5c70; background-clip: content-box; }
        ::-webkit-scrollbar-track { background: transparent; }

        h1, h2, h3, h4 { color: var(--text) !important; letter-spacing: -.014em; }
        h1 { font-size: 2rem !important; line-height: 1.16 !important; font-weight: 700 !important; }
        h2 { font-size: 1.24rem !important; line-height: 1.3 !important; font-weight: 670 !important; }
        h3 { font-size: 1rem !important; line-height: 1.35 !important; font-weight: 650 !important; }
        p, label, .stCaption { color: var(--text-soft); }

        [data-testid="stSidebar"] { background: linear-gradient(180deg, var(--surface) 0%, var(--surface-muted) 100%); border-right: 1px solid var(--border); }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
        [data-testid="stSidebar"] [data-testid="stMetric"] { min-height: 0; padding: .8rem; }

        .app-header {
            display:flex; align-items:center; justify-content:space-between; gap:1rem;
            padding:.65rem 0 1rem; border-bottom:1px solid var(--border); margin-bottom:1rem;
        }
        .brand-wrap { display:flex; align-items:center; gap:.72rem; }
        .brand-mark {
            width:40px; height:40px; display:grid; place-items:center; border-radius:9px;
            background:linear-gradient(150deg, var(--accent-hover), var(--accent)); color:var(--accent-ink);
            font-size:.92rem; font-weight:800; letter-spacing:.02em;
            box-shadow:0 4px 14px -4px rgba(110,168,215,.55), inset 0 1px 0 rgba(255,255,255,.25);
        }
        .brand-name { font-size:1rem; font-weight:700; color:var(--text); line-height:1.1; }
        .brand-kicker { color:var(--text-faint); font-size:.73rem; margin-top:.2rem; }
        .sync-pill {
            display:flex; align-items:center; gap:.45rem; color:var(--text-soft); font-size:.78rem;
            padding:.34rem .7rem; border:1px solid var(--border); border-radius:999px; background:var(--surface);
        }
        .sync-dot { width:7px; height:7px; border-radius:50%; background:var(--positive); box-shadow:0 0 0 3px rgba(114,181,141,.18); }

        .page-hero {
            display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:2rem; align-items:end;
            padding:1.1rem 1.35rem 1.25rem; margin:.15rem 0 1rem;
            border:1px solid var(--border); border-radius:var(--radius-lg);
            background:
                radial-gradient(680px 220px at 100% 0%, var(--accent-soft) 0%, transparent 70%),
                linear-gradient(180deg, var(--surface-raised) 0%, var(--surface) 100%);
            box-shadow:var(--shadow-md);
        }
        .eyebrow { color:var(--accent); font-size:.72rem; font-weight:700; letter-spacing:.055em; text-transform:uppercase; }
        .hero-title { color:var(--text); font-size:clamp(1.7rem,2.5vw,2.45rem); line-height:1.1; margin:.32rem 0 .52rem; font-weight:700; max-width:820px; }
        .hero-copy { max-width:760px; color:var(--text-soft); font-size:.96rem; line-height:1.55; }
        .hero-stat { text-align:right; border-left:1px solid var(--border); padding-left:1.5rem; }
        .hero-stat strong { display:block; font-size:1.75rem; color:var(--text); font-variant-numeric:tabular-nums; font-weight:720; }
        .hero-stat span { color:var(--text-faint); font-size:.75rem; }

        .section-heading { display:flex; justify-content:space-between; align-items:end; gap:1rem; margin:1.9rem 0 .7rem; padding-bottom:.55rem; border-bottom:1px solid var(--border); }
        .section-heading h2 { margin:0 !important; }
        .section-heading p { margin:.2rem 0 0; font-size:.84rem; }

        [data-testid="stExpander"] { background:var(--surface); border:1px solid var(--border) !important; border-radius:var(--radius-lg) !important; box-shadow:var(--shadow-sm) !important; }
        [data-testid="stExpander"] details { border:0 !important; }
        [data-testid="stExpander"] summary { color:var(--text); font-size:.9rem; font-weight:650; }
        [data-testid="stExpander"] summary:hover { color:var(--accent-hover); }

        [data-testid="stMetric"] {
            position:relative; min-height:102px; padding:1rem 1rem 1rem 1.15rem; border-radius:var(--radius-lg);
            background:linear-gradient(180deg, var(--surface-raised), var(--surface)); border:1px solid var(--border);
            box-shadow:var(--shadow-sm); overflow:hidden; transition:transform .12s ease, border-color .12s ease, box-shadow .12s ease;
        }
        [data-testid="stMetric"]::before { content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:linear-gradient(180deg, var(--accent-hover), var(--accent)); opacity:.85; }
        [data-testid="stMetric"]:hover { transform:translateY(-2px); border-color:var(--border-strong); box-shadow:var(--shadow-md); }
        [data-testid="stMetricLabel"] { color:var(--text-faint) !important; font-size:.75rem !important; font-weight:600 !important; }
        [data-testid="stMetricValue"] { color:var(--text) !important; font-size:1.76rem !important; font-weight:700 !important; font-variant-numeric:tabular-nums; }
        [data-testid="stMetricDelta"] { color:var(--accent) !important; }

        .insight-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.75rem; margin:.7rem 0 1.1rem; }
        .insight-card { padding:.95rem 1.05rem; border:1px solid var(--border); border-radius:var(--radius); background:linear-gradient(180deg, var(--surface-raised), var(--surface)); box-shadow:var(--shadow-sm); transition:transform .12s ease, border-color .12s ease, box-shadow .12s ease; }
        .insight-card:hover { transform:translateY(-2px); border-color:var(--border-strong); box-shadow:var(--shadow-md); }
        .insight-label { color:var(--text-faint); font-size:.72rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }
        .insight-value { color:var(--text); font-size:.98rem; font-weight:700; margin-top:.34rem; }
        .insight-note { color:var(--text-soft); font-size:.78rem; margin-top:.22rem; }

        .stButton > button, .stLinkButton > a {
            min-height:38px; border-radius:8px !important; border:1px solid var(--border-strong) !important;
            background:var(--surface) !important; color:var(--text) !important; font-weight:640 !important;
            box-shadow:var(--shadow-sm) !important; transition:transform .1s ease, background .12s ease, border-color .12s ease, color .12s ease !important;
        }
        .stButton > button:hover, .stLinkButton > a:hover { border-color:var(--accent) !important; background:var(--accent-soft) !important; color:var(--accent-hover) !important; transform:translateY(-1px); }
        .stButton > button:active, .stLinkButton > a:active { transform:translateY(0); }
        .stButton > button:disabled { opacity:.45 !important; transform:none !important; }
        .stButton > button[kind="primary"] { background:linear-gradient(150deg, var(--accent-hover), var(--accent)) !important; color:var(--accent-ink) !important; border-color:var(--accent) !important; box-shadow:0 6px 18px -8px rgba(110,168,215,.65) !important; }
        .stButton > button[kind="primary"]:hover { filter:brightness(1.05); color:var(--accent-ink) !important; }
        .stButton > button:focus-visible, .stLinkButton > a:focus-visible { outline:3px solid var(--focus) !important; outline-offset:2px; }

        div[data-baseweb="select"] > div, [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input, .stTextInput input {
            min-height:40px; background:var(--surface) !important; border-color:var(--border-strong) !important;
            color:var(--text) !important; border-radius:8px !important; box-shadow:none !important;
        }
        div[data-baseweb="select"] > div:focus-within, [data-testid="stDateInput"] input:focus,
        [data-testid="stNumberInput"] input:focus, .stTextInput input:focus { border-color:var(--accent) !important; box-shadow:0 0 0 3px var(--focus) !important; }
        /* Dropdown / popover menus stay on dark surfaces */
        div[data-baseweb="popover"] [role="listbox"], div[data-baseweb="menu"] { background:var(--surface-raised) !important; border:1px solid var(--border) !important; }
        div[data-baseweb="popover"] li:hover, div[data-baseweb="menu"] li:hover { background:var(--accent-soft) !important; }
        [data-baseweb="tag"] { background:var(--accent-soft) !important; color:var(--accent-hover) !important; border:1px solid var(--border-strong) !important; }
        [data-testid="stWidgetLabel"] p { color:var(--text); font-size:.8rem; font-weight:640; }
        [data-testid="stSlider"] [role="slider"] { background:var(--accent) !important; box-shadow:0 0 0 4px var(--accent-soft) !important; }
        [data-testid="stSlider"] [data-baseweb="slider"] div[style*="background"] { background:var(--accent) !important; }

        [data-testid="stAlert"] { border-radius:var(--radius); border:1px solid var(--border); background:var(--surface); color:var(--text); box-shadow:var(--shadow-sm); }
        hr { border-color:var(--border) !important; }

        [data-testid="stSegmentedControl"] {
            position:sticky; top:.55rem; z-index:20; padding:.28rem; margin:.1rem 0 1rem;
            border:1px solid var(--border); border-radius:11px; background:rgba(17,24,33,.82); backdrop-filter:blur(10px);
            box-shadow:var(--shadow-md);
        }
        [data-testid="stSegmentedControl"] button { min-height:38px; border-radius:8px !important; color:var(--text-soft) !important; font-weight:640 !important; transition:background .12s ease, color .12s ease; }
        [data-testid="stSegmentedControl"] button:hover { background:var(--surface-raised) !important; color:var(--text) !important; }
        [data-testid="stSegmentedControl"] button[aria-checked="true"] { background:linear-gradient(150deg, var(--accent-hover), var(--accent)) !important; color:var(--accent-ink) !important; box-shadow:0 4px 12px -6px rgba(110,168,215,.6) !important; }

        .gallery-summary { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.7rem .9rem; margin:.6rem 0 .9rem; border:1px solid var(--border); border-radius:var(--radius); background:linear-gradient(180deg, var(--surface-raised), var(--surface)); color:var(--text-soft); font-size:.82rem; box-shadow:var(--shadow-sm); }
        .gallery-summary strong { color:var(--text); font-variant-numeric:tabular-nums; }
        .sighting-card { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); margin-bottom:1rem; box-shadow:var(--shadow-sm); transition:transform .14s ease, border-color .14s ease, box-shadow .14s ease; }
        .sighting-card:hover { transform:translateY(-3px); border-color:var(--border-strong); box-shadow:var(--shadow-lg); }
        .card-thumbnail { background:var(--surface-muted); min-height:230px; display:grid; place-items:center; overflow:hidden; }
        .card-thumbnail img { width:100%; aspect-ratio:16/10; object-fit:cover; display:block; background:var(--surface-muted); transition:transform .3s ease; }
        .sighting-card:hover .card-thumbnail img { transform:scale(1.045); }
        .photo-unavailable, .thumbnail-placeholder { color:var(--text-faint); font-size:.8rem; letter-spacing:.01em; }
        .card-content { padding:.9rem 1rem 1rem; }
        .card-title { font-size:.95rem; font-weight:680; color:var(--text); }
        .card-meta { color:var(--text-soft); font-size:.8rem; margin-top:.2rem; }
        .card-temp, .card-moon { display:inline-flex; margin-right:.7rem; margin-top:.5rem; padding:.16rem .5rem; border-radius:999px; background:var(--surface-muted); border:1px solid var(--border); color:var(--text-soft); font-size:.72rem; }
        .card-link { color:var(--accent) !important; font-size:.82rem; font-weight:640; text-decoration:none; }
        .card-link:hover { color:var(--accent-hover) !important; text-decoration:underline; }
        .embed-wrap { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); box-shadow:var(--shadow-md); }
        .small-muted { color:var(--text-faint); font-size:.76rem; }

        .pagination-shell { margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border); }
        .pagination-status { text-align:center; color:var(--text-soft); font-size:.8rem; padding-top:.25rem; }

        [data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:var(--radius-lg); overflow:hidden; background:var(--surface); box-shadow:var(--shadow-sm); }
        [data-testid="stDataFrame"] canvas { font-family:Inter,ui-sans-serif,system-ui,sans-serif !important; }
        [data-testid="stDataFrame"] [role="columnheader"] { background:var(--table-header) !important; color:var(--text) !important; font-weight:650 !important; }
        [data-testid="stDataFrame"] [role="gridcell"] { color:var(--text) !important; border-color:var(--border) !important; }

        @media (max-width:900px) {
            .main .block-container { padding:.75rem .9rem 3rem; }
            .page-hero { grid-template-columns:1fr; gap:.8rem; padding:1rem; }
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
    
    color = SECTION_COLORS.get(section.lower(), PALETTE["green"])
    
    chart = (
        alt.Chart(daily)
        .mark_area(
            line={"color": color, "strokeWidth": 2.25},
            color=color,
            opacity=0.24,
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

    page_start = (st.session_state.gallery_page - 1) * page_size
    page_end = min(page_start + page_size, total_items)
    display_view = view.iloc[page_start:page_end]

    page_items = tuple(
        (str(row.camera).strip(), str(row.filename).strip())
        for row in display_view[["camera", "filename"]].itertuples(index=False)
    )
    # Resolve only metadata for the visible page. Drive thumbnail URLs are
    # rendered by the browser, so Streamlit does not block while downloading
    # every image and the previous view is never covered by a loading overlay.
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
            url = hit.get("webViewLink", "")
            thumbnail_url = _large_thumbnail_url(hit.get("thumbnailLink", ""))
            safe_label = html.escape(str(label))
            safe_cam = html.escape(cam)
            safe_time = html.escape(time_str)
            safe_temp = html.escape(temp_str)
            safe_moon = html.escape(str(moon_phase))
            safe_url = html.escape(url, quote=True)
            safe_thumb = html.escape(thumbnail_url, quote=True)

            if safe_thumb:
                image_markup = (
                    f'<img src="{safe_thumb}" alt="{safe_label} at {safe_cam}" '
                    'loading="lazy" decoding="async" referrerpolicy="no-referrer">'
                )
            else:
                image_markup = '<div class="photo-unavailable">Image unavailable</div>'

            metadata = ""
            if safe_temp:
                metadata += f'<span class="card-temp">Temperature {safe_temp}</span>'
            if safe_moon:
                metadata += f'<span class="card-moon">Moon {safe_moon}</span>'
            metadata_markup = f'<div style="margin-top:.35rem;">{metadata}</div>' if metadata else ""
            link_markup = (
                f'<div style="margin-top:.7rem;"><a href="{safe_url}" target="_blank" '
                'rel="noopener noreferrer" class="card-link">View in Drive ↗</a></div>'
                if safe_url else ""
            )

            with cols[col_idx]:
                card_markup = f"""
                <article class="sighting-card">
                    <div class="card-thumbnail">{image_markup}</div>
                    <div class="card-content">
                        <div class="card-title">{safe_label} · {safe_cam}</div>
                        <div class="card-meta">{safe_time}</div>
                        {metadata_markup}
                        {link_markup}
                    </div>
                </article>
                """
                st.markdown(card_markup, unsafe_allow_html=True)

    st.markdown('<div class="pagination-shell"></div>', unsafe_allow_html=True)
    nav_left, nav_center, nav_right = st.columns([1, 1.35, 1])
    with nav_left:
        if st.button(
            "Previous",
            disabled=st.session_state.gallery_page <= 1,
            width="stretch",
            key="gallery_previous",
        ):
            st.session_state.gallery_page -= 1
            st.session_state.pop("gallery_page_jump", None)
            st.rerun(scope="fragment")
    with nav_center:
        page_options = list(range(1, total_pages + 1))
        selected_page = st.selectbox(
            "Page",
            options=page_options,
            index=st.session_state.gallery_page - 1,
            format_func=lambda page: f"Page {page} of {total_pages}",
            key="gallery_page_jump",
            label_visibility="collapsed",
        )
        if selected_page != st.session_state.gallery_page:
            st.session_state.gallery_page = int(selected_page)
            st.rerun(scope="fragment")
        st.markdown(
            f'<div class="pagination-status">Showing {page_start + 1:,}–{page_end:,} of {total_items:,} sightings</div>',
            unsafe_allow_html=True,
        )
    with nav_right:
        if st.button(
            "Next",
            disabled=st.session_state.gallery_page >= total_pages,
            width="stretch",
            key="gallery_next",
        ):
            st.session_state.gallery_page += 1
            st.session_state.pop("gallery_page_jump", None)
            st.rerun(scope="fragment")

