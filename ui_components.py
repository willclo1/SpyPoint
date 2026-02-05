# ui_components.py
from __future__ import annotations

from typing import Dict, Tuple, List

import altair as alt
import pandas as pd
import streamlit as st

from data_prep import clamp_temp_domain
from drive_io import resolve_image_link


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
    """Exact ranch wildlife theme from website."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;600;700;900&family=DM+Sans:wght@400;500;700&display=swap');
        
        :root {
            /* Exact earth-tone palette from website */
            --earth-dark: #1a1612;
            --earth-charcoal: #2d2520;
            --earth-brown: #3d332c;
            --earth-clay: #4a3f35;
            --earth-tan: #8b7355;
            --earth-sand: #c4a77d;
            --earth-cream: #e8d5b7;
            
            /* Nature accents from website */
            --sage: #8a9a5b;
            --forest: #4a5d3f;
            --sunset: #d97642;
            --sky: #7ea8be;
            
            /* UI colors from website */
            --text-primary: #f5f1ea;
            --text-muted: rgba(245, 241, 234, 0.7);
            --text-dim: rgba(245, 241, 234, 0.45);
            --border: rgba(245, 241, 234, 0.12);
            --border-strong: rgba(245, 241, 234, 0.22);
            
            /* Effects from website */
            --shadow-soft: 0 4px 24px rgba(0, 0, 0, 0.3);
            --shadow-strong: 0 8px 40px rgba(0, 0, 0, 0.5);
            --radius: 16px;
            --radius-lg: 24px;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        /* EXACT background from website */
        .stApp {
            background: 
                radial-gradient(ellipse 1200px 800px at 15% -5%, rgba(138, 154, 91, 0.08), transparent 70%),
                radial-gradient(ellipse 900px 600px at 85% 10%, rgba(217, 118, 66, 0.06), transparent 60%),
                linear-gradient(180deg, #1a1612 0%, #2d2520 100%) !important;
            font-family: 'DM Sans', -apple-system, system-ui, sans-serif !important;
            color: var(--text-primary) !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }
        
        /* Main content area background */
        .main .block-container {
            background: transparent !important;
            padding-top: 2rem !important;
        }
        
        /* Headers - Crimson Pro like website */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Crimson Pro', Georgia, serif !important;
            color: var(--text-primary) !important;
            letter-spacing: -0.02em !important;
            font-weight: 700 !important;
        }
        
        h1 {
            font-weight: 900 !important;
            font-size: 2.5rem !important;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--earth-sand) 100%);
            -webkit-background-clip: text !important;
            -webkit-text-fill-color: transparent !important;
            background-clip: text !important;
            margin-bottom: 0.5rem !important;
        }
        
        h2 {
            font-size: 1.8rem !important;
            color: var(--earth-cream) !important;
        }
        
        h3 {
            font-size: 1.4rem !important;
            font-weight: 700 !important;
        }
        
        /* Body text */
        p, span, div, label {
            font-family: 'DM Sans', sans-serif !important;
        }
        
        /* Buttons - EXACT website style */
        .stButton > button {
            background: linear-gradient(145deg, rgba(61, 51, 44, 0.6) 0%, rgba(45, 37, 32, 0.8) 100%) !important;
            border: 1px solid var(--border-strong) !important;
            border-radius: var(--radius) !important;
            color: var(--text-primary) !important;
            font-weight: 600 !important;
            transition: var(--transition) !important;
            box-shadow: var(--shadow-soft) !important;
            padding: 0.75rem 1.5rem !important;
            font-size: 1rem !important;
            position: relative;
        }
        
        .stButton > button::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--sage) 0%, var(--sunset) 50%, var(--sky) 100%);
            opacity: 0;
            transition: opacity 0.3s ease;
            border-radius: var(--radius) var(--radius) 0 0;
        }
        
        .stButton > button:hover {
            background: linear-gradient(145deg, rgba(61, 51, 44, 0.8) 0%, rgba(45, 37, 32, 1) 100%) !important;
            border-color: var(--earth-tan) !important;
            transform: translateY(-4px) !important;
            box-shadow: var(--shadow-strong) !important;
        }
        
        .stButton > button:hover::before {
            opacity: 1;
        }
        
        /* Primary buttons - sage/forest gradient */
        .stButton > button[kind="primary"],
        .stButton > button[data-baseweb="button"][kind="primary"] {
            background: linear-gradient(135deg, var(--sage) 0%, var(--forest) 100%) !important;
            border: 1px solid rgba(138, 154, 91, 0.5) !important;
            color: var(--text-primary) !important;
            box-shadow: 0 4px 16px rgba(138, 154, 91, 0.3) !important;
            font-weight: 700 !important;
        }
        
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #9bb16c 0%, #5a6e4f 100%) !important;
            box-shadow: 0 6px 24px rgba(138, 154, 91, 0.45) !important;
            transform: translateY(-2px) scale(1.02) !important;
        }
        
        /* Metrics - website style */
        [data-testid="stMetricValue"] {
            font-family: 'Crimson Pro', Georgia, serif !important;
            font-size: 2.2rem !important;
            font-weight: 700 !important;
            color: var(--sage) !important;
            line-height: 1 !important;
        }
        
        [data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
            color: var(--text-dim) !important;
            text-transform: uppercase !important;
            letter-spacing: 0.1em !important;
            font-weight: 600 !important;
            margin-bottom: 0.5rem !important;
        }
        
        div[data-testid="stMetric"] {
            background: rgba(61, 51, 44, 0.4) !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            padding: 1rem 1.25rem !important;
            transition: var(--transition) !important;
        }
        
        div[data-testid="stMetric"]:hover {
            background: rgba(61, 51, 44, 0.6) !important;
            border-color: var(--border-strong) !important;
            transform: translateY(-2px) !important;
        }
        
        /* Input widgets - earth tones */
        .stSelectbox > div > div,
        .stMultiSelect > div > div,
        .stDateInput > div > div > div,
        .stTextInput > div > div,
        .stNumberInput > div > div {
            background: rgba(61, 51, 44, 0.5) !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            color: var(--text-primary) !important;
            transition: var(--transition) !important;
        }
        
        .stSelectbox > div > div:hover,
        .stMultiSelect > div > div:hover,
        .stDateInput > div > div > div:hover {
            border-color: var(--border-strong) !important;
            background: rgba(61, 51, 44, 0.7) !important;
        }
        
        .stSelectbox > div > div:focus-within,
        .stMultiSelect > div > div:focus-within {
            border-color: var(--sage) !important;
            box-shadow: 0 0 0 2px rgba(138, 154, 91, 0.2) !important;
        }
        
        /* Dropdown menus */
        [data-baseweb="popover"] {
            background: rgba(45, 37, 32, 0.98) !important;
            border: 1px solid var(--border-strong) !important;
            border-radius: 12px !important;
            backdrop-filter: blur(20px) !important;
        }
        
        [data-baseweb="menu"] {
            background: transparent !important;
        }
        
        /* Radio buttons */
        .stRadio > div {
            background: rgba(61, 51, 44, 0.3) !important;
            border-radius: 12px !important;
            padding: 0.75rem !important;
        }
        
        .stRadio > div > label {
            color: var(--text-muted) !important;
            padding: 0.5rem 0.75rem !important;
            border-radius: 8px !important;
            transition: var(--transition) !important;
        }
        
        .stRadio > div > label:hover {
            background: rgba(138, 154, 91, 0.1) !important;
            color: var(--text-primary) !important;
        }
        
        .stRadio > div > label[data-checked="true"] {
            background: linear-gradient(135deg, var(--sage) 0%, var(--forest) 100%) !important;
            color: var(--text-primary) !important;
            font-weight: 700 !important;
        }
        
        /* Checkboxes */
        .stCheckbox {
            color: var(--text-muted) !important;
        }
        
        .stCheckbox > label > div[data-baseweb="checkbox"] {
            border-color: var(--border-strong) !important;
            background: rgba(61, 51, 44, 0.5) !important;
        }
        
        .stCheckbox > label > div[data-baseweb="checkbox"][data-checked="true"] {
            background: var(--sage) !important;
            border-color: var(--sage) !important;
        }
        
        /* Sliders */
        .stSlider > div > div > div > div {
            background: var(--sage) !important;
        }
        
        .stSlider > div > div > div > div[role="slider"] {
            background: var(--sage) !important;
            border: 3px solid var(--earth-charcoal) !important;
            box-shadow: 0 2px 8px rgba(138, 154, 91, 0.4) !important;
        }
        
        /* Success/Info/Warning boxes - website style */
        .stSuccess, .stInfo, .stWarning, .stError {
            background: rgba(61, 51, 44, 0.5) !important;
            border: 1px solid var(--border-strong) !important;
            border-radius: var(--radius) !important;
            color: var(--text-primary) !important;
            padding: 1rem 1.25rem !important;
            backdrop-filter: blur(10px) !important;
        }
        
        .stSuccess {
            border-left: 4px solid var(--sage) !important;
        }
        
        .stInfo {
            border-left: 4px solid var(--sky) !important;
        }
        
        .stWarning {
            border-left: 4px solid var(--sunset) !important;
        }
        
        /* Divider */
        hr {
            border: none !important;
            height: 1px !important;
            background: linear-gradient(90deg, transparent, var(--border-strong), transparent) !important;
            margin: 2rem 0 !important;
        }
        
        /* Sidebar - EXACT website modal styling */
        [data-testid="stSidebar"] {
            background: linear-gradient(145deg, 
                rgba(45, 37, 32, 0.95) 0%, 
                rgba(26, 22, 18, 0.98) 100%) !important;
            border-right: 1px solid var(--border-strong) !important;
            backdrop-filter: blur(20px) saturate(180%) !important;
        }
        
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--text-primary) !important;
        }
        
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--text-muted) !important;
        }
        
        /* Photo gallery cards - EXACT website card style */
        .sighting-card {
            position: relative;
            background: linear-gradient(145deg, 
                rgba(61, 51, 44, 0.6) 0%, 
                rgba(45, 37, 32, 0.8) 100%);
            border: 1px solid var(--border-strong);
            border-radius: var(--radius-lg);
            overflow: hidden;
            box-shadow: var(--shadow-soft);
            transition: var(--transition);
            margin-bottom: 1.5rem;
        }
        
        .sighting-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, 
                var(--sage) 0%, 
                var(--sunset) 50%, 
                var(--sky) 100%);
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: 1;
        }
        
        .sighting-card:hover::before {
            opacity: 1;
        }
        
        .sighting-card:hover {
            transform: translateY(-6px) scale(1.02);
            border-color: var(--earth-tan);
            box-shadow: var(--shadow-strong);
        }
        
        .card-thumbnail {
            height: 220px;
            background: var(--earth-dark);
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
        }
        
        .card-thumbnail::before {
            content: '';
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at 30% 30%, 
                rgba(138, 154, 91, 0.15), 
                transparent 70%);
            opacity: 0;
            transition: opacity 0.4s ease;
            z-index: 1;
        }
        
        .sighting-card:hover .card-thumbnail::before {
            opacity: 1;
        }
        
        .card-thumbnail::after {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, 
                rgba(26, 22, 18, 0) 0%, 
                rgba(26, 22, 18, 0.7) 100%);
            pointer-events: none;
            z-index: 1;
        }
        
        .card-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .sighting-card:hover .card-thumbnail img {
            transform: scale(1.08);
        }
        
        .card-content {
            padding: 1.25rem 1.4rem 1.5rem;
        }
        
        .card-title {
            font-family: 'Crimson Pro', Georgia, serif;
            font-weight: 700;
            font-size: 1.3rem;
            color: var(--earth-cream);
            margin-bottom: 0.5rem;
            letter-spacing: -0.01em;
            line-height: 1.3;
        }
        
        .card-meta {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin: 0.3rem 0;
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }
        
        .card-meta::before {
            content: '•';
            color: var(--sage);
            font-size: 1.2rem;
            line-height: 1;
        }
        
        .card-temp, .card-moon {
            display: inline-block;
            margin-right: 1rem;
            color: var(--text-muted);
            font-size: 0.85rem;
        }
        
        /* Load more button */
        .load-more-btn {
            display: flex;
            justify-content: center;
            margin: 2rem 0;
        }
        
        /* Scrollbar - website style */
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }
        
        ::-webkit-scrollbar-track {
            background: var(--earth-charcoal);
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--earth-tan);
            border-radius: 5px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--earth-sand);
        }
        
        /* Caption text */
        .stCaption, [data-testid="stCaptionContainer"] {
            color: var(--text-muted) !important;
            font-style: italic;
            font-family: 'Crimson Pro', Georgia, serif !important;
        }
        
        /* Small muted text */
        .small-muted {
            font-size: 0.85rem;
            color: var(--text-dim);
            font-style: italic;
        }
        
        /* Chart containers */
        .element-container {
            background: transparent !important;
        }
        
        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 1rem;
            background: transparent !important;
            border-bottom: 1px solid var(--border) !important;
        }
        
        .stTabs [data-baseweb="tab"] {
            background: rgba(61, 51, 44, 0.3) !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px 12px 0 0 !important;
            color: var(--text-muted) !important;
            font-weight: 600 !important;
            padding: 0.75rem 1.5rem !important;
            transition: var(--transition) !important;
        }
        
        .stTabs [data-baseweb="tab"]:hover {
            background: rgba(61, 51, 44, 0.5) !important;
            border-color: var(--border-strong) !important;
            color: var(--text-primary) !important;
        }
        
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, var(--sage) 0%, var(--forest) 100%) !important;
            color: var(--text-primary) !important;
            border-color: var(--sage) !important;
            font-weight: 700 !important;
        }
        
        /* Expander styling */
        .streamlit-expanderHeader {
            background: rgba(61, 51, 44, 0.4) !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            color: var(--text-primary) !important;
            font-weight: 600 !important;
        }
        
        .streamlit-expanderHeader:hover {
            background: rgba(61, 51, 44, 0.6) !important;
            border-color: var(--border-strong) !important;
        }
        
        /* Dataframe styling */
        .stDataFrame {
            background: rgba(61, 51, 44, 0.3) !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# Visualizations
# =============================================================================

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
            
            st.altair_chart(apply_chart_theme(chart), use_container_width=True)
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
    
    st.altair_chart(apply_chart_theme(chart), use_container_width=True)


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
                st.altair_chart(apply_chart_theme(time_chart), use_container_width=True)
            with cB:
                st.markdown("**By Day of Week**")
                st.altair_chart(apply_chart_theme(day_chart), use_container_width=True)
            
            st.markdown("**By Moon Phase**")
            st.altair_chart(apply_chart_theme(moon_chart), use_container_width=True)
        else:
            # No moon data - just show time and day
            cA, cB = st.columns(2)
            with cA:
                st.markdown("**By Time of Day**")
                st.altair_chart(apply_chart_theme(time_chart), use_container_width=True)
            with cB:
                st.markdown("**By Day of Week**")
                st.altair_chart(apply_chart_theme(day_chart), use_container_width=True)
    else:
        # No moon_phase_clean column - just show time and day
        cA, cB = st.columns(2)
        with cA:
            st.markdown("**By Time of Day**")
            st.altair_chart(apply_chart_theme(time_chart), use_container_width=True)
        with cB:
            st.markdown("**By Day of Week**")
            st.altair_chart(apply_chart_theme(day_chart), use_container_width=True)


# =============================================================================
# Gallery
# =============================================================================

def render_listing_and_viewer(
    base: pd.DataFrame,
    section: str,
    include_other: bool,
    image_index: Dict,
    drive_client_factory,
    download_bytes_func,
):
    """Photo gallery with exact ranch wildlife card styling."""
    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    if section == "Wildlife" and not include_other:
        view = view[view["wildlife_label"] != "Other"]

    if view.empty:
        st.info("No sightings match your filters")
        return

    if "gallery_limit" not in st.session_state:
        st.session_state.gallery_limit = 8

    display_view = view.head(st.session_state.gallery_limit)

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

            if section == "Wildlife":
                label = row.get("wildlife_label", "Other")
            else:
                label = (row.get("event_type", "")).capitalize()

            time_str = dt.strftime("%b %d, %I:%M %p") if pd.notna(dt) else "Unknown time"
            temp_str = f"{int(temp)}°F" if pd.notna(temp) else ""

            with cols[col_idx]:
                url, fid = resolve_image_link(cam, fn, image_index)

                st.markdown('<div class="sighting-card">', unsafe_allow_html=True)

                if fid:
                    img_bytes = load_thumbnail_cached(fid, drive_client_factory, download_bytes_func)
                    if img_bytes:
                        st.markdown('<div class="card-thumbnail">', unsafe_allow_html=True)
                        st.image(img_bytes, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(
                            '<div class="card-thumbnail"><div style="font-size:2.2rem; opacity:0.35;">📷</div></div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(
                        '<div class="card-thumbnail"><div style="font-size:2.2rem; opacity:0.35;">📷</div></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown('<div class="card-content">', unsafe_allow_html=True)
                st.markdown(f'<div class="card-title">{label} • {cam}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card-meta">{time_str}</div>', unsafe_allow_html=True)
                
                # Temperature and moon phase on same line
                if temp_str or moon_phase:
                    meta_line = '<div style="margin-top: 0.35rem;">'
                    if temp_str:
                        meta_line += f'<span class="card-temp">🌡️ {temp_str}</span>'
                    if moon_phase and moon_emoji:
                        meta_line += f'<span class="card-moon">{moon_emoji} {moon_phase}</span>'
                    meta_line += '</div>'
                    st.markdown(meta_line, unsafe_allow_html=True)

                if url:
                    st.markdown(
                        f'<div style="margin-top:0.7rem;"><a href="{url}" target="_blank" style="font-size:0.85rem; color: var(--sage); font-weight: 600; text-decoration: none; transition: var(--transition);">View in Drive ↗</a></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("</div>", unsafe_allow_html=True)  # card-content
                st.markdown("</div>", unsafe_allow_html=True)  # sighting-card

    # Load More button
    if len(view) > st.session_state.gallery_limit:
        remaining = len(view) - st.session_state.gallery_limit
        st.markdown('<div class="load-more-btn">', unsafe_allow_html=True)
        if st.button(f"Load More ({remaining} remaining)", key=f"load_more_{section}"):
            st.session_state.gallery_limit += 8
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
