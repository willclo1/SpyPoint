# ui_components.py
from __future__ import annotations

import html
import re
from contextlib import contextmanager
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
    "slate": "#7C8A99",
    "blue": "#6EA8D7",
    "orange": "#E0A458",
    "green": "#6FCE97",
    "red": "#E4756F",
    "teal": "#72B7B2",
    "purple": "#C98BB9",
    "pink": "#E7A6AD",
    "brown": "#B08968",
    "neutral": "#546472",
}

# A muted categorical palette tuned for the refined dark surface. It leads with
# the app's steel-blue accent so single-series charts read as "on brand," then
# steps through desaturated, evenly-spaced hues that stay legible on dark
# without the saturated punch of library defaults. Chart backgrounds and text
# are inherited from the theme rather than hard-coded.
WILDLIFE_PALETTE = [
    "#6EA8D7",  # steel blue (accent)
    "#E0A458",  # amber
    "#6FCE97",  # sage green
    "#C98BB9",  # muted mauve
    "#E4756F",  # soft red
    "#72B7B2",  # teal
    "#B08968",  # taupe
    "#8FB0C9",  # dusty blue
    "#D2B48C",  # sand
    "#9DC7A8",  # pale green
    "#B39DB0",  # heather
    "#A7B4C2",  # slate
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


# Chart typography and dark-tuned ink. Altair can't read CSS variables, so
# these mirror the design tokens used across the app for a consistent look on
# the transparent chart surface. Grid/axis lines are kept faint on purpose so
# they recede behind the data rather than boxing it in.
_CHART_FONT = "Inter, ui-sans-serif, -apple-system, 'Segoe UI', sans-serif"
_CHART_INK = "#E8EEF4"
_CHART_INK_SOFT = "#A7B4C2"
_CHART_GRID = "#253340"
_CHART_AXIS = "#33465A"

# Sequential ramp for activity heatmaps — quiet page-dark to the steel-blue
# accent at the busy end, staying within the app's single accent hue.
_HEAT_RANGE = ["#131A22", "#1E3A4D", "#2E627F", "#4C89AF", "#8FC0E6"]
# Vega expression that formats an hour-of-day tick (0-23) as a compact 12h label.
_HOUR_LABEL_EXPR = (
    "(datum.value % 12 === 0 ? 12 : datum.value % 12) + (datum.value < 12 ? 'a' : 'p')"
)


def _fmt_hour(hour) -> str:
    """Format an hour-of-day integer (0-23) as a compact label like '5a' or '11p'."""
    try:
        hour = int(hour)
    except (TypeError, ValueError):
        return str(hour)
    suffix = "a" if hour < 12 else "p"
    hour12 = hour % 12 or 12
    return f"{hour12}{suffix}"


def apply_chart_theme(chart: alt.Chart) -> alt.Chart:
    """Apply a cohesive dark-theme styling pass to an Altair chart."""
    return (
        chart
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_axis(
            grid=True,
            gridColor=_CHART_GRID,
            gridOpacity=0.4,
            gridWidth=1,
            domainColor=_CHART_AXIS,
            domainOpacity=0.6,
            tickColor=_CHART_AXIS,
            tickOpacity=0.6,
            labelColor=_CHART_INK_SOFT,
            titleColor=_CHART_INK_SOFT,
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight=500,
            labelPadding=7,
            titlePadding=12,
            labelFont=_CHART_FONT,
            titleFont=_CHART_FONT,
        )
        # Categorical (x) axes rarely need vertical gridlines — dropping them
        # removes chart junk and lets the bars/points read cleanly.
        .configure_axisX(labelAngle=0, grid=False)
        .configure_legend(
            orient="top",
            direction="horizontal",
            labelColor=_CHART_INK_SOFT,
            titleColor=_CHART_INK_SOFT,
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight=500,
            symbolSize=90,
            symbolType="circle",
            padding=6,
            labelFont=_CHART_FONT,
            titleFont=_CHART_FONT,
        )
        .configure_title(color=_CHART_INK, font=_CHART_FONT, fontSize=13.5, fontWeight=600, anchor="start")
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
    """Inject a restrained, flat dark design system.

    The look favors calm surfaces, hairline borders, and a single accent over
    the glow/gradient/animation vocabulary of a typical "dashboard" theme.
    There is one token set and no light-mode branch, so the palette never
    flips regardless of the viewer's OS/browser preference. Surfaces are solid
    fills (no gradients), separation comes from 1px borders rather than heavy
    shadows, and there are no decorative motion effects — hover feedback is a
    quiet border-color shift only. This keeps attention on the data.
    """
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        /* ---- Single dark token set --------------------------------------
           No light-mode media query and no light data-theme override, so the
           palette cannot flip. Neutrals carry the whole UI; the accent marks
           only the few things that matter.                                 */
        :root,
        html[data-theme="light"], body[data-theme="light"], [data-theme="light"],
        html[data-theme="dark"],  body[data-theme="dark"],  [data-theme="dark"] {
            color-scheme: dark !important;
            /* Near-neutral dark greys (a hint cool, not blue-tinted) with a
               single steel-blue accent — the palette a real product ships,
               not a template's saturated navy. */
            --page: #0C0D0F;
            --surface: #161719;
            --surface-raised: #1C1D20;
            --surface-muted: #101113;
            --text: #E7E8EA;
            --text-soft: #9AA0A6;
            --text-faint: #6A6F76;
            --border: #26272B;
            --border-soft: #1E1F22;
            --border-strong: #34363C;
            --accent: #6EA8D7;
            --accent-hover: #8FC0E6;
            --accent-soft: rgba(110, 168, 215, .12);
            --accent-ink: #0A0F14;
            --positive: #6FCE97;
            --focus: rgba(110, 168, 215, .36);
            --table-header: #1C1D20;
            --shadow-sm: 0 1px 2px rgba(0,0,0,.30);
            --radius: 8px;
            --radius-lg: 12px;
        }

        html, body, [class*="css"] {
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--text);
            -webkit-font-smoothing: antialiased;
            text-rendering: optimizeLegibility;
        }
        /* Flat page — no radial glows, no gradient wash. */
        .stApp { color: var(--text); background: var(--page); }
        .main .block-container { max-width: 1360px; padding: 1.25rem 2rem 4.5rem; }
        header[data-testid="stHeader"] { background: transparent; }
        footer, #MainMenu { visibility: hidden; }

        /* Subtle scrollbars */
        * { scrollbar-color: var(--border-strong) transparent; scrollbar-width: thin; }
        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 8px; border: 3px solid transparent; background-clip: content-box; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::selection { background: var(--accent-soft); color: var(--text); }

        /* Typography carries the hierarchy — size/weight/colour, not effects.
           Kept restrained: an internal tool doesn't shout. */
        h1, h2, h3, h4 { color: var(--text) !important; letter-spacing: -.011em; }
        h1 { font-size: 1.4rem !important; line-height: 1.25 !important; font-weight: 600 !important; }
        h2 { font-size: 1.05rem !important; line-height: 1.34 !important; font-weight: 600 !important; }
        h3 { font-size: .92rem !important; line-height: 1.35 !important; font-weight: 600 !important; }
        p, label, .stCaption { color: var(--text-soft); }

        [data-testid="stSidebar"] { background: var(--surface-muted); border-right: 1px solid var(--border); }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
        [data-testid="stSidebar"] h3 { font-size:.72rem !important; text-transform:uppercase; letter-spacing:.07em; color:var(--text-faint) !important; font-weight:700 !important; }
        [data-testid="stSidebar"] [data-testid="stMetric"] { min-height: 0; padding: .85rem 1rem; }

        /* ---- App header: a quiet wordmark row above a hairline rule ----- */
        .app-header {
            display:flex; align-items:center; justify-content:space-between; gap:1rem;
            padding:.5rem 0 .85rem; margin-bottom:1rem; border-bottom:1px solid var(--border);
        }
        .brand-wrap { display:flex; align-items:center; gap:.6rem; }
        .brand-mark {
            width:30px; height:30px; display:grid; place-items:center; border-radius:7px;
            background:var(--surface-raised); border:1px solid var(--border-strong);
            color:var(--text-soft); font-size:.72rem; font-weight:600; letter-spacing:.02em;
        }
        .brand-name { font-size:.92rem; font-weight:600; color:var(--text); line-height:1.1; letter-spacing:-.01em; }
        .brand-kicker { color:var(--text-faint); font-size:.72rem; margin-top:.12rem; }
        .sync-pill {
            display:flex; align-items:center; gap:.45rem; color:var(--text-faint); font-size:.76rem; font-weight:500;
        }
        .sync-dot { width:6px; height:6px; border-radius:50%; background:var(--positive); }

        /* ---- Page head: just a title + one terse line, no hero panel --- */
        .page-head { margin:.35rem 0 1.25rem; }
        .page-head h1 { margin:0; }
        .page-head p { margin:.3rem 0 0; color:var(--text-soft); font-size:.88rem; line-height:1.5; max-width:760px; }

        /* ---- Section headers: quiet label, no boxes -------------------- */
        .section-heading { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; margin:2rem 0 .9rem; }
        .section-heading h2 { margin:0 !important; }
        .section-heading p { margin:.2rem 0 0; font-size:.82rem; color:var(--text-faint); }

        [data-testid="stExpander"] { background:var(--surface); border:1px solid var(--border) !important; border-radius:var(--radius-lg) !important; box-shadow:none !important; overflow:hidden; }
        [data-testid="stExpander"] details { border:0 !important; }
        [data-testid="stExpander"] summary { color:var(--text); font-size:.9rem; font-weight:600; padding:.15rem 0; }
        [data-testid="stExpander"] summary:hover { color:var(--accent-hover); }
        [data-testid="stExpander"] summary svg { color:var(--text-faint); }

        /* ---- Metric tiles: flat cards, no accent bar, no glow ---------- */
        [data-testid="stMetric"] {
            min-height:96px; padding:1rem 1.15rem; border-radius:var(--radius-lg);
            background:var(--surface); border:1px solid var(--border);
            transition:border-color .14s ease;
        }
        [data-testid="stMetric"]:hover { border-color:var(--border-strong); }
        [data-testid="stMetricLabel"] { color:var(--text-faint) !important; font-size:.73rem !important; font-weight:600 !important; text-transform:uppercase; letter-spacing:.04em; }
        [data-testid="stMetricValue"] { color:var(--text) !important; font-size:1.75rem !important; font-weight:700 !important; font-variant-numeric:tabular-nums; letter-spacing:-.02em; }
        [data-testid="stMetricDelta"] { color:var(--text-soft) !important; }

        /* ---- KPI stat strip: one cohesive bar of numbers -------------
           Four (or more) figures share a single card, split by hairlines,
           so the headline metrics read as one instrument panel rather than
           a row of mostly-empty boxes. */
        .stat-strip { display:grid; grid-auto-flow:column; grid-auto-columns:1fr; border:1px solid var(--border); border-radius:var(--radius-lg); background:var(--surface); overflow:hidden; margin:.35rem 0 1rem; box-shadow:var(--shadow-sm); }
        .stat-cell { padding:1rem 1.3rem; border-left:1px solid var(--border); }
        .stat-cell:first-child { border-left:0; }
        .stat-label { color:var(--text-faint); font-size:.72rem; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }
        .stat-value { color:var(--text); font-size:1.7rem; font-weight:650; font-variant-numeric:tabular-nums; letter-spacing:-.02em; margin-top:.45rem; line-height:1; }
        .stat-sub { color:var(--text-soft); font-size:.76rem; margin-top:.45rem; }
        @media (max-width:820px) { .stat-strip { grid-auto-flow:row; grid-auto-columns:auto; grid-template-columns:1fr 1fr; }
            .stat-cell:nth-child(2) { border-left:1px solid var(--border); }
            .stat-cell:nth-child(odd) { border-left:0; } .stat-cell:nth-child(n+3) { border-top:1px solid var(--border); } }

        /* ---- Chart cards: uniform chrome for every plot in the grid ---- */
        [data-testid="stVerticalBlockBorderWrapper"] { border:1px solid var(--border) !important; border-radius:var(--radius-lg) !important; background:var(--surface); box-shadow:var(--shadow-sm); }
        .chart-head { display:flex; align-items:baseline; justify-content:space-between; gap:.75rem; margin:.1rem 0 .6rem; }
        .chart-title { color:var(--text); font-size:.9rem; font-weight:600; letter-spacing:-.005em; }
        .chart-sub { color:var(--text-faint); font-size:.75rem; }

        /* ---- Context strip: secondary facts as a quiet inline row, not a
           second tier of big cards competing with the KPIs above. -------- */
        .context-bar { display:flex; flex-wrap:wrap; align-items:center; gap:.4rem 1.5rem; padding:.7rem .95rem; margin:.7rem 0 1.15rem; border:1px solid var(--border); border-radius:var(--radius); background:var(--surface-muted); }
        .ctx { display:flex; align-items:baseline; gap:.5rem; min-width:0; }
        .ctx-label { color:var(--text-faint); font-size:.75rem; }
        .ctx-value { color:var(--text); font-size:.83rem; font-weight:600; }
        .ctx-note { color:var(--text-faint); font-size:.75rem; }

        /* ---- Buttons: flat surfaces; primary is a solid accent fill ---- */
        .stButton > button, .stLinkButton > a, .stDownloadButton > button {
            min-height:40px; border-radius:8px !important; border:1px solid var(--border-strong) !important;
            background:var(--surface) !important; color:var(--text) !important; font-weight:600 !important;
            box-shadow:none !important; transition:background .14s ease, border-color .14s ease, color .14s ease !important;
        }
        .stButton > button:hover, .stLinkButton > a:hover, .stDownloadButton > button:hover { border-color:var(--accent) !important; color:var(--accent-hover) !important; }
        .stButton > button:disabled, .stDownloadButton > button:disabled { opacity:.42 !important; }
        .stButton > button[kind="primary"] { background:var(--accent) !important; color:var(--accent-ink) !important; border-color:var(--accent) !important; }
        .stButton > button[kind="primary"]:hover { background:var(--accent-hover) !important; color:var(--accent-ink) !important; }
        .stButton > button:focus-visible, .stLinkButton > a:focus-visible, .stDownloadButton > button:focus-visible { outline:2px solid var(--focus) !important; outline-offset:2px; }

        div[data-baseweb="select"] > div, [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input, .stTextInput input {
            min-height:40px; background:var(--surface) !important; border-color:var(--border-strong) !important;
            color:var(--text) !important; border-radius:8px !important; box-shadow:none !important;
        }
        div[data-baseweb="select"] > div:hover { border-color:var(--accent) !important; }
        div[data-baseweb="select"] > div:focus-within, [data-testid="stDateInput"] input:focus,
        [data-testid="stNumberInput"] input:focus, .stTextInput input:focus { border-color:var(--accent) !important; box-shadow:0 0 0 2px var(--focus) !important; }
        /* Dropdown / popover menus stay on dark surfaces */
        div[data-baseweb="popover"] [role="listbox"], div[data-baseweb="menu"], ul[data-baseweb="menu"] { background:var(--surface-raised) !important; border:1px solid var(--border) !important; border-radius:8px !important; box-shadow:var(--shadow-sm) !important; }
        div[data-baseweb="popover"] li:hover, div[data-baseweb="menu"] li:hover, ul[data-baseweb="menu"] li:hover { background:var(--accent-soft) !important; }
        [data-baseweb="tag"] { background:var(--accent-soft) !important; color:var(--accent-hover) !important; border:1px solid var(--border-strong) !important; border-radius:6px !important; }
        [data-baseweb="tag"] span[role="button"]:hover { color:var(--text) !important; }
        [data-testid="stWidgetLabel"] p { color:var(--text); font-size:.8rem; font-weight:600; }
        [data-testid="stSlider"] [role="slider"] { background:var(--accent) !important; box-shadow:0 0 0 3px var(--accent-soft) !important; }
        [data-testid="stSlider"] [data-baseweb="slider"] div[style*="background"] { background:var(--accent) !important; }

        [data-testid="stToggle"] [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] { background:var(--accent) !important; }

        [data-testid="stAlert"] { border-radius:var(--radius); border:1px solid var(--border); background:var(--surface); color:var(--text); box-shadow:none; }
        hr { border-color:var(--border) !important; }

        /* ---- View switcher: understated segmented tabs ----------------
           Active tab is a quiet raised segment with an accent underline —
           reads more "product nav" than a punchy filled pill. */
        [data-testid="stSegmentedControl"] {
            position:sticky; top:.5rem; z-index:20; padding:.25rem; margin:.1rem 0 1.15rem; width:max-content;
            border:1px solid var(--border); border-radius:9px; background:var(--surface);
        }
        [data-testid="stSegmentedControl"] button { min-height:34px; border-radius:6px !important; color:var(--text-soft) !important; font-weight:500 !important; transition:background .14s ease, color .14s ease; }
        [data-testid="stSegmentedControl"] button:hover { background:var(--surface-raised) !important; color:var(--text) !important; }
        [data-testid="stSegmentedControl"] button[aria-checked="true"] { background:var(--surface-raised) !important; color:var(--text) !important; box-shadow:inset 0 -2px 0 var(--accent) !important; }

        .gallery-summary { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.7rem 1rem; margin:.6rem 0 1rem; border:1px solid var(--border); border-radius:var(--radius); background:var(--surface); color:var(--text-soft); font-size:.82rem; }
        .gallery-summary strong { color:var(--text); font-size:1rem; font-weight:700; font-variant-numeric:tabular-nums; }

        /* ---- Sighting cards: flat, hairline border, no zoom/lift ------- */
        .sighting-card { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); margin-bottom:1rem; transition:border-color .16s ease; }
        .sighting-card:hover { border-color:var(--border-strong); }
        .card-thumbnail { position:relative; background:var(--surface-muted); min-height:230px; display:grid; place-items:center; overflow:hidden; }
        .card-thumbnail img { width:100%; aspect-ratio:16/10; object-fit:cover; display:block; background:var(--surface-muted); }
        .card-badge { position:absolute; top:.7rem; left:.7rem; z-index:2; display:inline-flex; align-items:center; gap:.35rem; padding:.26rem .6rem; border-radius:6px; font-size:.72rem; font-weight:600; letter-spacing:.01em; color:var(--text); background:rgba(11,15,20,.78); border:1px solid var(--border-strong); }
        .card-badge::before { content:""; width:6px; height:6px; border-radius:50%; background:var(--accent); }
        .photo-unavailable, .thumbnail-placeholder { color:var(--text-faint); font-size:.8rem; letter-spacing:.01em; }
        .card-content { padding:.9rem 1.05rem 1.05rem; }
        .card-title { font-size:.95rem; font-weight:650; color:var(--text); letter-spacing:-.01em; }
        .card-meta { color:var(--text-soft); font-size:.8rem; margin-top:.24rem; }
        .card-temp, .card-moon { display:inline-flex; align-items:center; margin-right:.5rem; margin-top:.55rem; padding:.2rem .55rem; border-radius:6px; background:var(--surface-muted); border:1px solid var(--border); color:var(--text-soft); font-size:.72rem; font-weight:500; }
        .card-link { display:inline-flex; align-items:center; gap:.25rem; color:var(--accent) !important; font-size:.82rem; font-weight:600; text-decoration:none; }
        .card-link:hover { color:var(--accent-hover) !important; text-decoration:underline; }
        .embed-wrap { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); }
        .small-muted { color:var(--text-faint); font-size:.76rem; }

        /* Active-filter summary chips */
        .filter-summary { display:flex; flex-wrap:wrap; gap:.45rem; margin:.15rem 0 1.05rem; }
        .filter-chip { display:inline-flex; align-items:center; gap:.45rem; padding:.3rem .7rem; border:1px solid var(--border); border-radius:999px; background:var(--surface); color:var(--text-soft); font-size:.77rem; font-weight:500; }
        .filter-chip .fc-key { color:var(--accent); font-size:.66rem; text-transform:uppercase; letter-spacing:.06em; font-weight:700; }

        /* Sidebar "at a glance" facts */
        .sidebar-facts { display:flex; flex-direction:column; gap:.5rem; margin:.3rem 0 .7rem; }
        .fact-row { display:flex; justify-content:space-between; align-items:center; gap:.75rem; padding:.55rem .75rem; border:1px solid var(--border); border-radius:var(--radius); background:var(--surface); }
        .fact-label { color:var(--text-faint); font-size:.7rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }
        .fact-value { color:var(--text); font-size:.82rem; font-weight:700; text-align:right; font-variant-numeric:tabular-nums; }

        .pagination-shell { margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border); }
        .pagination-status { text-align:center; color:var(--text-soft); font-size:.8rem; padding-top:.3rem; font-variant-numeric:tabular-nums; }

        [data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:var(--radius-lg); overflow:hidden; background:var(--surface); box-shadow:none; }
        [data-testid="stDataFrame"] canvas { font-family:Inter,ui-sans-serif,system-ui,sans-serif !important; }
        [data-testid="stDataFrame"] [role="columnheader"] { background:var(--table-header) !important; color:var(--text) !important; font-weight:600 !important; }
        [data-testid="stDataFrame"] [role="gridcell"] { color:var(--text) !important; border-color:var(--border) !important; }

        /* Keep charts responsive: the chart element is what Vega measures for
           sizing, so it must NOT carry padding/border of its own or the plot
           renders full-width and then overflows/clips. Only constrain width. */
        [data-testid="stVegaLiteChart"], [data-testid="stAltairChart"] { max-width:100%; }
        [data-testid="stVegaLiteChart"] > div, [data-testid="stAltairChart"] > div { width:100% !important; }
        [data-testid="stVegaLiteChart"] canvas, [data-testid="stVegaLiteChart"] svg,
        [data-testid="stAltairChart"] canvas, [data-testid="stAltairChart"] svg { max-width:100% !important; }

        @media (max-width:900px) {
            .main .block-container { padding:.85rem .9rem 3rem; }
            .context-bar { flex-direction:column; align-items:flex-start; gap:.5rem; }
            .sync-pill { display:none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def _card(title: str | None = None, subtitle: str | None = None):
    """A bordered chart card with an optional header row.

    Uniform chrome for every plot lets a page of charts read as one grid
    rather than a stack of loose panels. Used as a context manager so the
    caller renders its chart(s) directly inside.
    """
    with st.container(border=True):
        if title:
            sub = f'<span class="chart-sub">{html.escape(subtitle)}</span>' if subtitle else ""
            st.markdown(
                f'<div class="chart-head"><span class="chart-title">{html.escape(title)}</span>{sub}</div>',
                unsafe_allow_html=True,
            )
        yield


def render_timeline(base: pd.DataFrame, section: str):
    """
    Daily timeline with MULTIPLE trend lines when ≤4 species selected.
    Aggregated area chart when >4 species or no species filter.
    """
    if base.empty or "datetime" not in base.columns:
        st.info("No timeline data available")
        return

    chart = None
    caption = None

    # Individual trend lines when a small number of species is in view.
    if section == "Wildlife" and "wildlife_label" in base.columns:
        unique_species = base["wildlife_label"].nunique()
        species_list = base["wildlife_label"].unique().tolist()

        if 0 < unique_species <= 4:
            daily_by_species = (
                base.groupby([base["datetime"].dt.date, "wildlife_label"])
                .size()
                .reset_index(name="Events")
            )
            daily_by_species.columns = ["Date", "Species", "Events"]
            daily_by_species["Date"] = pd.to_datetime(daily_by_species["Date"])

            domain, color_range = stable_color_domain(
                species_list,
                WILDLIFE_PALETTE,
                pin_other_gray=("Other" in species_list),
            )

            chart = (
                alt.Chart(daily_by_species)
                .mark_line(
                    point=alt.OverlayMarkDef(size=32, filled=True),
                    strokeWidth=2.25,
                    opacity=0.95,
                )
                .encode(
                    x=alt.X("Date:T", title="Date", axis=alt.Axis(format="%b %d", labelAngle=0)),
                    y=alt.Y("Events:Q", title="Event Count"),
                    color=alt.Color(
                        "Species:N",
                        scale=alt.Scale(domain=domain, range=color_range),
                        legend=alt.Legend(title="Species", orient="top", direction="horizontal"),
                    ),
                    tooltip=[
                        alt.Tooltip("Date:T", title="Date", format="%B %d, %Y"),
                        alt.Tooltip("Species:N", title="Species"),
                        alt.Tooltip("Events:Q", title="Events"),
                    ],
                )
                .properties(height=320)
            )
            caption = f"Individual trend lines for {unique_species} species"

    # Default: aggregated area chart.
    if chart is None:
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
            .properties(height=320)
        )

    with _card():
        st.altair_chart(apply_chart_theme(chart), width="stretch")
        if caption:
            st.caption(caption)


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

    # ---- Species leaderboard: composition at a glance -------------------
    leaderboard = None
    if section == "Wildlife":
        species_counts = base[group_col].value_counts()
        if len(species_counts) > 1:
            total_events = int(species_counts.sum())
            lead = species_counts.reset_index()
            lead.columns = ["Species", "Events"]
            lead["pct"] = (lead["Events"] / total_events * 100).round(0)
            lead["label"] = [f"{int(count):,} · {int(pct)}%" for count, pct in zip(lead["Events"], lead["pct"])]
            lead_domain, lead_range = stable_color_domain(
                lead["Species"].tolist(), WILDLIFE_PALETTE, pin_other_gray=(not include_other)
            )
            lead_bars = (
                alt.Chart(lead)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, opacity=0.95)
                .encode(
                    y=alt.Y("Species:N", sort="-x", title=None),
                    x=alt.X("Events:Q", title="Events"),
                    color=alt.Color("Species:N", scale=alt.Scale(domain=lead_domain, range=lead_range), legend=None),
                    tooltip=[
                        alt.Tooltip("Species:N", title="Species"),
                        alt.Tooltip("Events:Q", title="Events"),
                        alt.Tooltip("pct:Q", title="Share (%)"),
                    ],
                )
            )
            lead_labels = (
                alt.Chart(lead)
                .mark_text(align="left", baseline="middle", dx=6, fontSize=11, font=_CHART_FONT, color=_CHART_INK_SOFT)
                .encode(y=alt.Y("Species:N", sort="-x"), x=alt.X("Events:Q"), text="label:N")
            )
            leaderboard = (lead_bars + lead_labels).properties(height=min(340, 32 * len(lead) + 20))

    # ---- Activity heatmap: day-of-week x time-of-day --------------------
    # One glance answers "when is the ranch busy?" — dark cells are quiet,
    # bright cells are active. Missing day/time combos are filled with 0 so
    # the grid reads cleanly rather than showing gaps.
    heat_index = pd.MultiIndex.from_product(
        [day_order, sorted(base["time_bin"].dropna().unique().tolist())],
        names=["day_of_week", "time_bin"],
    )
    heat = (
        base.groupby(["day_of_week", "time_bin"]).size()
        .reindex(heat_index, fill_value=0)
        .reset_index(name="Events")
    )
    heatmap = (
        alt.Chart(heat)
        .mark_rect(cornerRadius=2, stroke="#0F151C", strokeWidth=2)
        .encode(
            x=alt.X("time_bin:O", title=time_title, axis=alt.Axis(labelAngle=0, labelExpr=_HOUR_LABEL_EXPR)),
            y=alt.Y("day_of_week:N", title=None, sort=day_order),
            color=alt.Color(
                "Events:Q",
                scale=alt.Scale(range=_HEAT_RANGE),
                legend=alt.Legend(title="Events", orient="top", direction="horizontal"),
            ),
            tooltip=[
                alt.Tooltip("day_of_week:N", title="Day"),
                alt.Tooltip("time_bin:O", title=time_title),
                alt.Tooltip("Events:Q", title="Events"),
            ],
        )
        .properties(height=250)
    )
    heat_caption = None
    if heat["Events"].max() > 0:
        peak = heat.loc[heat["Events"].idxmax()]
        heat_caption = (
            f"Busiest window: **{peak['day_of_week']}s** around **{_fmt_hour(peak['time_bin'])}** "
            f"— {int(peak['Events']):,} events in that slot."
        )

    # Time chart
    if bar_style == "Grouped":
        time_chart = (
            alt.Chart(by_time)
            .mark_bar(opacity=0.9, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("time_bin:O", title=time_title, axis=alt.Axis(labelAngle=0, labelExpr=_HOUR_LABEL_EXPR)),
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
                x=alt.X("time_bin:O", title=time_title, axis=alt.Axis(labelAngle=0, labelExpr=_HOUR_LABEL_EXPR)),
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
    moon_chart = None
    if "moon_phase_clean" in base.columns and base["moon_phase_clean"].notna().any():
        moon_order = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
                      "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
        by_moon = base.groupby(["moon_phase_clean", group_col]).size().reset_index(name="Sightings")
        by_moon.columns = ["moon_phase_clean", "animal_group", "Sightings"]

        if by_moon["moon_phase_clean"].notna().any():
            moon_kwargs = dict(
                y=alt.Y("moon_phase_clean:N", title="Moon Phase", sort=moon_order),
                x=alt.X("Sightings:Q", title="Count"),
                color=color_enc,
                tooltip=[
                    alt.Tooltip("moon_phase_clean:N", title="Moon Phase"),
                    alt.Tooltip("animal_group:N", title=section),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            if bar_style == "Grouped":
                moon_kwargs["yOffset"] = "animal_group:N"
            moon_chart = (
                alt.Chart(by_moon)
                .mark_bar(opacity=0.9, cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(**moon_kwargs)
                .properties(height=280)
            )

    # ---- Render: a bento grid of chart cards ---------------------------
    # Small breakdowns flow two-up; the day×time heatmap takes the full
    # width it needs to stay legible. Uniform card chrome makes the whole
    # section read as one instrument panel.
    tiles = []
    if leaderboard is not None:
        tiles.append(("Most frequent species", leaderboard))
    tiles.append((f"By {time_title.lower()}", time_chart))
    tiles.append(("By day of week", day_chart))
    if moon_chart is not None:
        tiles.append(("By moon phase", moon_chart))

    for i in range(0, len(tiles), 2):
        row = tiles[i:i + 2]
        cols = st.columns(len(row), gap="medium")
        for col, (title, chart) in zip(cols, row):
            with col:
                with _card(title):
                    st.altair_chart(apply_chart_theme(chart), width="stretch")

    with _card("Activity heatmap", "day of week × time of day"):
        st.altair_chart(apply_chart_theme(heatmap), width="stretch")
        if heat_caption:
            st.caption(heat_caption)


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

            badge_markup = f'<div class="card-badge">{safe_label}</div>' if safe_label else ""

            with cols[col_idx]:
                card_markup = f"""
                <article class="sighting-card">
                    <div class="card-thumbnail">{badge_markup}{image_markup}</div>
                    <div class="card-content">
                        <div class="card-title">{safe_cam}</div>
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

