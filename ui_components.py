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


# Chart typography and dark-tuned ink. Altair can't read CSS variables, so
# these mirror the dark design tokens used across the app for a crisp,
# consistent look on the transparent chart surface.
_CHART_FONT = "Inter, ui-sans-serif, -apple-system, 'Segoe UI', sans-serif"
_CHART_INK = "#eef3f8"
_CHART_INK_SOFT = "#9fb0c0"
_CHART_GRID = "#26333f"
_CHART_AXIS = "#3a4a5c"


def apply_chart_theme(chart: alt.Chart) -> alt.Chart:
    """Apply a cohesive dark-theme styling pass to an Altair chart."""
    return (
        chart
        .configure(background="transparent", font=_CHART_FONT)
        .configure_view(strokeOpacity=0)
        .configure_axis(
            grid=True,
            gridColor=_CHART_GRID,
            gridOpacity=0.55,
            gridDash=[2, 4],
            domainColor=_CHART_AXIS,
            domainOpacity=0.7,
            tickColor=_CHART_AXIS,
            tickOpacity=0.7,
            labelColor=_CHART_INK_SOFT,
            titleColor=_CHART_INK,
            labelFontSize=12,
            titleFontSize=12.5,
            titleFontWeight=600,
            labelPadding=7,
            titlePadding=12,
            labelFont=_CHART_FONT,
            titleFont=_CHART_FONT,
        )
        .configure_axisX(labelAngle=0)
        .configure_legend(
            orient="top",
            direction="horizontal",
            labelColor=_CHART_INK_SOFT,
            titleColor=_CHART_INK,
            labelFontSize=12,
            titleFontSize=12.5,
            titleFontWeight=600,
            symbolSize=110,
            symbolType="circle",
            padding=6,
            labelFont=_CHART_FONT,
            titleFont=_CHART_FONT,
        )
        .configure_title(color=_CHART_INK, font=_CHART_FONT, fontSize=14, fontWeight=700, anchor="start")
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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        /* ---- Strictly enforced dark theme -------------------------------
           A single token set. No light-mode media query and no light
           data-theme override, so nothing can flip the palette to light.
           Every light-theme selector below is aliased to the dark tokens as
           a belt-and-suspenders guard against host theme switches.        */
        :root,
        html[data-theme="light"], body[data-theme="light"], [data-theme="light"],
        html[data-theme="dark"],  body[data-theme="dark"],  [data-theme="dark"] {
            color-scheme: dark !important;
            --page: #080b10;
            --page-2: #0b1119;
            --surface: #121a24;
            --surface-raised: #18232f;
            --surface-muted: #0e141c;
            --surface-glass: rgba(20, 29, 40, .74);
            --text: #f0f5fa;
            --text-soft: #b7c3d0;
            --text-faint: #8593a3;
            --border: #253340;
            --border-soft: #1d2833;
            --border-strong: #38495b;
            --hairline: rgba(255,255,255,.045);
            --accent: #6ea8d7;
            --accent-hover: #93c2ea;
            --accent-soft: rgba(110, 168, 215, .14);
            --accent-glow: rgba(110, 168, 215, .45);
            --accent-ink: #06121d;
            --accent2: #e0a458;
            --accent2-soft: rgba(224, 164, 88, .16);
            --positive: #6fce97;
            --focus: rgba(110, 168, 215, .40);
            --table-header: #1b2733;
            --table-row-alt: #101720;
            --shadow-sm: 0 1px 2px rgba(0,0,0,.30);
            --shadow-md: 0 8px 24px -12px rgba(0,0,0,.6);
            --shadow-lg: 0 22px 50px -20px rgba(0,0,0,.72);
            --radius: 9px;
            --radius-lg: 14px;
        }

        html, body, [class*="css"] {
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--text);
            -webkit-font-smoothing: antialiased;
            text-rendering: optimizeLegibility;
        }
        .stApp {
            color: var(--text);
            background:
                radial-gradient(1200px 680px at 84% -10%, rgba(110,168,215,.10) 0%, transparent 58%),
                radial-gradient(1000px 560px at -8% 2%, rgba(224,164,88,.05) 0%, transparent 52%),
                linear-gradient(180deg, var(--page-2) 0%, var(--page) 42%);
            background-attachment: fixed;
        }
        .main .block-container { max-width: 1440px; padding: 1rem 2rem 4.5rem; animation: appFade .5s ease both; }
        @keyframes appFade { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
        @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration:.001ms !important; transition-duration:.001ms !important; } }
        header[data-testid="stHeader"] { background: transparent; backdrop-filter: blur(8px); }
        footer, #MainMenu { visibility: hidden; }

        /* Custom scrollbars for a cohesive dark surface */
        * { scrollbar-color: var(--border-strong) transparent; scrollbar-width: thin; }
        ::-webkit-scrollbar { width: 11px; height: 11px; }
        ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 8px; border: 3px solid transparent; background-clip: content-box; }
        ::-webkit-scrollbar-thumb:hover { background: #4a5c70; background-clip: content-box; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::selection { background: var(--accent-soft); color: var(--text); }

        h1, h2, h3, h4 { color: var(--text) !important; letter-spacing: -.016em; }
        h1 { font-size: 2rem !important; line-height: 1.16 !important; font-weight: 750 !important; }
        h2 { font-size: 1.26rem !important; line-height: 1.3 !important; font-weight: 680 !important; }
        h3 { font-size: 1rem !important; line-height: 1.35 !important; font-weight: 650 !important; }
        p, label, .stCaption { color: var(--text-soft); }

        [data-testid="stSidebar"] { background: linear-gradient(180deg, var(--surface) 0%, var(--surface-muted) 100%); border-right: 1px solid var(--border); }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
        [data-testid="stSidebar"] h3 { font-size:.72rem !important; text-transform:uppercase; letter-spacing:.08em; color:var(--text-faint) !important; font-weight:700 !important; }
        [data-testid="stSidebar"] [data-testid="stMetric"] { min-height: 0; padding: .85rem 1rem; }

        .app-header {
            display:flex; align-items:center; justify-content:space-between; gap:1rem;
            padding:.7rem 0 1.05rem; margin-bottom:1.15rem; position:relative;
        }
        .app-header::after { content:""; position:absolute; left:0; right:0; bottom:0; height:1px;
            background:linear-gradient(90deg, var(--border-strong), var(--border) 30%, transparent); }
        .brand-wrap { display:flex; align-items:center; gap:.8rem; }
        .brand-mark {
            width:42px; height:42px; display:grid; place-items:center; border-radius:11px;
            background:linear-gradient(150deg, var(--accent-hover), var(--accent) 60%, #4f86b8); color:var(--accent-ink);
            font-size:.95rem; font-weight:800; letter-spacing:.02em;
            box-shadow:0 6px 18px -5px var(--accent-glow), inset 0 1px 0 rgba(255,255,255,.35);
        }
        .brand-name { font-size:1.02rem; font-weight:750; color:var(--text); line-height:1.1; letter-spacing:-.01em; }
        .brand-kicker { color:var(--text-faint); font-size:.73rem; margin-top:.22rem; letter-spacing:.02em; }
        .sync-pill {
            display:flex; align-items:center; gap:.5rem; color:var(--text-soft); font-size:.78rem; font-weight:550;
            padding:.4rem .8rem; border:1px solid var(--border); border-radius:999px;
            background:var(--surface-glass); backdrop-filter:blur(8px); box-shadow:var(--shadow-sm);
        }
        .sync-dot { width:8px; height:8px; border-radius:50%; background:var(--positive); position:relative; }
        .sync-dot::after { content:""; position:absolute; inset:-4px; border-radius:50%; border:2px solid var(--positive); opacity:.5; animation:syncPulse 2.4s ease-out infinite; }
        @keyframes syncPulse { 0% { transform:scale(.6); opacity:.6; } 100% { transform:scale(1.6); opacity:0; } }

        .page-hero {
            position:relative; overflow:hidden;
            display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:2rem; align-items:end;
            padding:1.4rem 1.6rem 1.5rem; margin:.15rem 0 1.15rem;
            border:1px solid var(--border); border-radius:var(--radius-lg);
            background:
                radial-gradient(760px 260px at 100% -20%, var(--accent-soft) 0%, transparent 68%),
                linear-gradient(180deg, var(--surface-raised) 0%, var(--surface) 100%);
            box-shadow:var(--shadow-md), inset 0 1px 0 var(--hairline);
        }
        .page-hero::before { content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
            background:linear-gradient(180deg, var(--accent-hover), var(--accent) 55%, var(--accent2)); opacity:.9; }
        .eyebrow { color:var(--accent); font-size:.72rem; font-weight:750; letter-spacing:.09em; text-transform:uppercase; }
        .hero-title {
            font-size:clamp(1.75rem,2.6vw,2.5rem); line-height:1.08; margin:.36rem 0 .55rem; font-weight:760; max-width:820px;
            color:var(--text);
            background:linear-gradient(180deg, #ffffff 0%, #cfe0ee 100%);
            -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
        }
        @supports not ((-webkit-background-clip:text) or (background-clip:text)) {
            .hero-title { -webkit-text-fill-color:var(--text); }
        }
        .hero-copy { max-width:760px; color:var(--text-soft); font-size:.97rem; line-height:1.58; }
        .hero-stat { text-align:right; padding-left:1.6rem; position:relative; }
        .hero-stat::before { content:""; position:absolute; left:0; top:.1rem; bottom:.1rem; width:1px; background:linear-gradient(180deg, transparent, var(--border-strong), transparent); }
        .hero-stat strong { display:block; font-size:1.95rem; color:var(--text); font-variant-numeric:tabular-nums; font-weight:780; letter-spacing:-.02em; }
        .hero-stat span { color:var(--text-faint); font-size:.75rem; }

        .section-heading { display:flex; justify-content:space-between; align-items:end; gap:1rem; margin:2rem 0 .8rem; padding-bottom:.6rem; position:relative; }
        .section-heading::after { content:""; position:absolute; left:0; right:0; bottom:0; height:1px; background:linear-gradient(90deg, var(--border-strong), transparent 65%); }
        .section-heading h2 { margin:0 !important; padding-left:.7rem; border-left:3px solid var(--accent); }
        .section-heading p { margin:.24rem 0 0; font-size:.84rem; padding-left:.7rem; }

        [data-testid="stExpander"] { background:var(--surface); border:1px solid var(--border) !important; border-radius:var(--radius-lg) !important; box-shadow:var(--shadow-sm) !important; overflow:hidden; }
        [data-testid="stExpander"] details { border:0 !important; }
        [data-testid="stExpander"] summary { color:var(--text); font-size:.9rem; font-weight:660; padding:.15rem 0; }
        [data-testid="stExpander"] summary:hover { color:var(--accent-hover); }
        [data-testid="stExpander"] summary svg { color:var(--accent); }

        [data-testid="stMetric"] {
            position:relative; min-height:104px; padding:1rem 1rem 1rem 1.2rem; border-radius:var(--radius-lg);
            background:linear-gradient(180deg, var(--surface-raised), var(--surface)); border:1px solid var(--border);
            box-shadow:var(--shadow-sm), inset 0 1px 0 var(--hairline); overflow:hidden;
            transition:transform .14s ease, border-color .14s ease, box-shadow .14s ease;
        }
        [data-testid="stMetric"]::before { content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:linear-gradient(180deg, var(--accent-hover), var(--accent)); opacity:.9; }
        [data-testid="stMetric"]::after { content:""; position:absolute; right:-30%; top:-60%; width:70%; height:170%; background:radial-gradient(closest-side, var(--accent-soft), transparent); opacity:0; transition:opacity .18s ease; }
        [data-testid="stMetric"]:hover { transform:translateY(-3px); border-color:var(--border-strong); box-shadow:var(--shadow-md); }
        [data-testid="stMetric"]:hover::after { opacity:1; }
        [data-testid="stMetricLabel"] { color:var(--text-faint) !important; font-size:.74rem !important; font-weight:620 !important; text-transform:uppercase; letter-spacing:.05em; }
        [data-testid="stMetricValue"] { color:var(--text) !important; font-size:1.82rem !important; font-weight:760 !important; font-variant-numeric:tabular-nums; letter-spacing:-.02em; }
        [data-testid="stMetricDelta"] { color:var(--accent) !important; }

        .insight-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; margin:.75rem 0 1.15rem; }
        .insight-card { position:relative; overflow:hidden; padding:1rem 1.1rem; border:1px solid var(--border); border-radius:var(--radius); background:linear-gradient(180deg, var(--surface-raised), var(--surface)); box-shadow:var(--shadow-sm), inset 0 1px 0 var(--hairline); transition:transform .14s ease, border-color .14s ease, box-shadow .14s ease; }
        .insight-card::before { content:""; position:absolute; left:0; top:0; height:2px; width:100%; background:linear-gradient(90deg, var(--accent), transparent 70%); opacity:.7; }
        .insight-card:hover { transform:translateY(-3px); border-color:var(--border-strong); box-shadow:var(--shadow-md); }
        .insight-label { color:var(--text-faint); font-size:.72rem; font-weight:650; text-transform:uppercase; letter-spacing:.05em; }
        .insight-value { color:var(--text); font-size:1.02rem; font-weight:750; margin-top:.36rem; letter-spacing:-.01em; }
        .insight-note { color:var(--text-soft); font-size:.78rem; margin-top:.24rem; }

        .stButton > button, .stLinkButton > a {
            min-height:40px; border-radius:9px !important; border:1px solid var(--border-strong) !important;
            background:var(--surface) !important; color:var(--text) !important; font-weight:650 !important;
            box-shadow:var(--shadow-sm) !important; transition:transform .1s ease, background .14s ease, border-color .14s ease, color .14s ease !important;
        }
        .stButton > button:hover, .stLinkButton > a:hover { border-color:var(--accent) !important; background:var(--accent-soft) !important; color:var(--accent-hover) !important; transform:translateY(-1px); }
        .stButton > button:active, .stLinkButton > a:active { transform:translateY(0); }
        .stButton > button:disabled { opacity:.42 !important; transform:none !important; }
        .stButton > button[kind="primary"] { background:linear-gradient(150deg, var(--accent-hover), var(--accent)) !important; color:var(--accent-ink) !important; border-color:var(--accent) !important; box-shadow:0 8px 20px -8px var(--accent-glow) !important; }
        .stButton > button[kind="primary"]:hover { filter:brightness(1.06); color:var(--accent-ink) !important; }
        .stButton > button:focus-visible, .stLinkButton > a:focus-visible { outline:3px solid var(--focus) !important; outline-offset:2px; }

        div[data-baseweb="select"] > div, [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input, .stTextInput input {
            min-height:40px; background:var(--surface) !important; border-color:var(--border-strong) !important;
            color:var(--text) !important; border-radius:9px !important; box-shadow:none !important;
        }
        div[data-baseweb="select"] > div:hover { border-color:var(--accent) !important; }
        div[data-baseweb="select"] > div:focus-within, [data-testid="stDateInput"] input:focus,
        [data-testid="stNumberInput"] input:focus, .stTextInput input:focus { border-color:var(--accent) !important; box-shadow:0 0 0 3px var(--focus) !important; }
        /* Dropdown / popover menus stay on dark surfaces */
        div[data-baseweb="popover"] [role="listbox"], div[data-baseweb="menu"], ul[data-baseweb="menu"] { background:var(--surface-raised) !important; border:1px solid var(--border) !important; border-radius:9px !important; box-shadow:var(--shadow-lg) !important; }
        div[data-baseweb="popover"] li:hover, div[data-baseweb="menu"] li:hover, ul[data-baseweb="menu"] li:hover { background:var(--accent-soft) !important; }
        [data-baseweb="tag"] { background:var(--accent-soft) !important; color:var(--accent-hover) !important; border:1px solid var(--border-strong) !important; border-radius:6px !important; }
        [data-baseweb="tag"] span[role="button"]:hover { color:var(--text) !important; }
        [data-testid="stWidgetLabel"] p { color:var(--text); font-size:.8rem; font-weight:640; }
        [data-testid="stSlider"] [role="slider"] { background:var(--accent) !important; box-shadow:0 0 0 4px var(--accent-soft) !important; }
        [data-testid="stSlider"] [data-baseweb="slider"] div[style*="background"] { background:var(--accent) !important; }

        [data-testid="stToggle"] [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] { background:var(--accent) !important; }

        [data-testid="stAlert"] { border-radius:var(--radius); border:1px solid var(--border); background:linear-gradient(180deg, var(--surface-raised), var(--surface)); color:var(--text); box-shadow:var(--shadow-sm); }
        hr { border-color:var(--border) !important; }

        [data-testid="stSegmentedControl"] {
            position:sticky; top:.55rem; z-index:20; padding:.3rem; margin:.1rem 0 1.1rem;
            border:1px solid var(--border); border-radius:12px; background:var(--surface-glass); backdrop-filter:blur(12px);
            box-shadow:var(--shadow-md), inset 0 1px 0 var(--hairline);
        }
        [data-testid="stSegmentedControl"] button { min-height:40px; border-radius:9px !important; color:var(--text-soft) !important; font-weight:650 !important; transition:background .14s ease, color .14s ease; }
        [data-testid="stSegmentedControl"] button:hover { background:var(--surface-raised) !important; color:var(--text) !important; }
        [data-testid="stSegmentedControl"] button[aria-checked="true"] { background:linear-gradient(150deg, var(--accent-hover), var(--accent)) !important; color:var(--accent-ink) !important; box-shadow:0 5px 14px -6px var(--accent-glow) !important; }

        .gallery-summary { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.75rem 1rem; margin:.6rem 0 1rem; border:1px solid var(--border); border-radius:var(--radius); background:linear-gradient(180deg, var(--surface-raised), var(--surface)); color:var(--text-soft); font-size:.82rem; box-shadow:var(--shadow-sm), inset 0 1px 0 var(--hairline); }
        .gallery-summary strong { color:var(--text); font-size:1rem; font-weight:750; font-variant-numeric:tabular-nums; }

        .sighting-card { position:relative; overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); margin-bottom:1rem; box-shadow:var(--shadow-sm); transition:transform .16s ease, border-color .16s ease, box-shadow .16s ease; }
        .sighting-card:hover { transform:translateY(-4px); border-color:var(--border-strong); box-shadow:var(--shadow-lg); }
        .card-thumbnail { position:relative; background:var(--surface-muted); min-height:230px; display:grid; place-items:center; overflow:hidden; }
        .card-thumbnail img { width:100%; aspect-ratio:16/10; object-fit:cover; display:block; background:var(--surface-muted); transition:transform .35s ease; }
        .sighting-card:hover .card-thumbnail img { transform:scale(1.05); }
        .card-thumbnail::after { content:""; position:absolute; left:0; right:0; bottom:0; height:52%; background:linear-gradient(180deg, transparent, rgba(6,10,15,.72)); pointer-events:none; opacity:.9; }
        .card-badge { position:absolute; top:.7rem; left:.7rem; z-index:2; display:inline-flex; align-items:center; gap:.35rem; padding:.28rem .6rem; border-radius:999px; font-size:.72rem; font-weight:700; letter-spacing:.01em; color:var(--text); background:var(--surface-glass); border:1px solid var(--border-strong); backdrop-filter:blur(6px); box-shadow:var(--shadow-sm); }
        .card-badge::before { content:""; width:7px; height:7px; border-radius:50%; background:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }
        .photo-unavailable, .thumbnail-placeholder { color:var(--text-faint); font-size:.8rem; letter-spacing:.01em; }
        .card-content { padding:.95rem 1.05rem 1.05rem; }
        .card-title { font-size:.97rem; font-weight:720; color:var(--text); letter-spacing:-.01em; }
        .card-meta { color:var(--text-soft); font-size:.8rem; margin-top:.24rem; }
        .card-temp, .card-moon { display:inline-flex; align-items:center; margin-right:.5rem; margin-top:.55rem; padding:.2rem .55rem; border-radius:999px; background:var(--surface-muted); border:1px solid var(--border); color:var(--text-soft); font-size:.72rem; font-weight:550; }
        .card-link { display:inline-flex; align-items:center; gap:.25rem; color:var(--accent) !important; font-size:.82rem; font-weight:660; text-decoration:none; }
        .card-link:hover { color:var(--accent-hover) !important; text-decoration:underline; }
        .embed-wrap { overflow:hidden; border-radius:var(--radius-lg); border:1px solid var(--border); background:var(--surface); box-shadow:var(--shadow-md); }
        .small-muted { color:var(--text-faint); font-size:.76rem; }

        .pagination-shell { margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border); }
        .pagination-status { text-align:center; color:var(--text-soft); font-size:.8rem; padding-top:.3rem; font-variant-numeric:tabular-nums; }

        [data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:var(--radius-lg); overflow:hidden; background:var(--surface); box-shadow:var(--shadow-sm); }
        [data-testid="stDataFrame"] canvas { font-family:Inter,ui-sans-serif,system-ui,sans-serif !important; }
        [data-testid="stDataFrame"] [role="columnheader"] { background:var(--table-header) !important; color:var(--text) !important; font-weight:660 !important; }
        [data-testid="stDataFrame"] [role="gridcell"] { color:var(--text) !important; border-color:var(--border) !important; }

        /* Keep charts responsive: the chart element is what Vega measures for
           sizing, so it must NOT carry padding/border of its own or the plot
           renders full-width and then overflows/clips. Only constrain width. */
        [data-testid="stVegaLiteChart"], [data-testid="stAltairChart"] { max-width:100%; }
        [data-testid="stVegaLiteChart"] > div, [data-testid="stAltairChart"] > div { width:100% !important; }
        [data-testid="stVegaLiteChart"] canvas, [data-testid="stVegaLiteChart"] svg,
        [data-testid="stAltairChart"] canvas, [data-testid="stAltairChart"] svg { max-width:100% !important; }

        @media (max-width:900px) {
            .main .block-container { padding:.75rem .9rem 3rem; }
            .page-hero { grid-template-columns:1fr; gap:.8rem; padding:1.15rem; }
            .hero-stat { text-align:left; padding-left:0; padding-top:.8rem; border-top:1px solid var(--border); }
            .hero-stat::before { display:none; }
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

