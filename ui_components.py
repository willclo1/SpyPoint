# ui_components.py
from __future__ import annotations

from typing import Dict, Tuple, List

import altair as alt
import pandas as pd
import streamlit as st

from data_prep import clamp_temp_domain
from drive_io import resolve_image_link


# =============================================================================
# Design System (Palette + Chart Theme)
# =============================================================================

PALETTE = {
    # App surfaces
    "bg": "#0B1220",
    "surface": "#0F1A2E",
    "surface_2": "#111F38",
    "border": "rgba(255,255,255,0.10)",
    "border_2": "rgba(255,255,255,0.16)",

    # Text
    "text": "rgba(255,255,255,0.92)",
    "muted": "rgba(255,255,255,0.65)",
    "muted_2": "rgba(255,255,255,0.50)",

    # Accents (unified system)
    "primary": "#5B8FF9",   # blue
    "secondary": "#61DDAA", # mint
    "info": "#1E88E5",
    "warning": "#FB8C00",
    "success": "#2E7D32",
    "neutral": "#94A3B8",   # for "Other"
}

# Distinct but tasteful categorical palette (non-neon, cohesive)
WILDLIFE_PALETTE = [
    "#4E79A7",  # blue
    "#F28E2B",  # orange
    "#E15759",  # red
    "#76B7B2",  # teal
    "#59A14F",  # green
    "#EDC948",  # yellow
    "#B07AA1",  # purple
    "#FF9DA7",  # pink
    "#9C755F",  # brown
    "#BAB0AC",  # warm gray (spare)
    "#1F77B4",  # vivid blue
    "#D62728",  # vivid red
    "#2CA02C",  # vivid green
    "#9467BD",  # vivid purple
    "#8C564B",  # deep brown
    "#17BECF",  # cyan
]

SECTION_COLORS = {
    "wildlife": PALETTE["success"],
    "people": PALETTE["info"],
    "vehicle": PALETTE["warning"],
}


def stable_color_domain(values: List[str], palette: List[str], *, pin_other_gray: bool = True) -> Tuple[List[str], List[str]]:
    """
    Stable category -> color mapping.
    Sorting ensures repeatability across reruns.
    Optionally pins 'Other' to a neutral gray so it doesn't compete.
    """
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
    """Altair theme for cohesive, modern charts."""
    return {
        "config": {
            "background": "transparent",
            "view": {"stroke": "transparent"},
            "font": "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial",
            "axis": {
                "labelColor": PALETTE["muted"],
                "titleColor": PALETTE["muted"],
                "gridColor": "rgba(255,255,255,0.08)",
                "tickColor": "rgba(255,255,255,0.10)",
                "domainColor": "rgba(255,255,255,0.12)",
                "labelFontSize": 12,
                "titleFontSize": 12,
                "titleFontWeight": 500,
                "labelPadding": 6,
                "titlePadding": 10,
            },
            "legend": {
                "labelColor": PALETTE["muted"],
                "titleColor": PALETTE["muted"],
                "labelFontSize": 12,
                "titleFontSize": 12,
                "titleFontWeight": 600,
                "symbolType": "circle",
                "symbolSize": 90,
                "padding": 8,
            },
            "title": {
                "color": PALETTE["text"],
                "fontSize": 14,
                "fontWeight": 600,
                "anchor": "start",
            },
        }
    }


try:
    alt.themes.register("premium_ui", _altair_theme)
except Exception:
    pass

alt.themes.enable("premium_ui")


def apply_chart_theme(chart: alt.Chart) -> alt.Chart:
    """Extra per-chart polish: consistent padding, axes, etc."""
    return (
        chart
        .configure_view(strokeOpacity=0)
        .configure_axis(grid=True)
        .configure_axisX(labelAngle=0)
    )


# =============================================================================
# Cached IO
# =============================================================================

@st.cache_data(ttl=3600)
def load_thumbnail_cached(file_id: str, _drive_client_factory, _download_bytes_func):
    """Cache thumbnail downloads to avoid repeated API calls."""
    try:
        service = _drive_client_factory()
        img_bytes = _download_bytes_func(service, file_id)
        return img_bytes
    except Exception:
        return None


# =============================================================================
# CSS / Layout
# =============================================================================

def inject_css():
    """
    Premium UI skin + filter widget theming.
    IMPORTANT: This uses a normal triple-quoted string + token replacement,
    so CSS braces and var(--accent) will NOT break Python.
    """
    css = """
    <style>
      :root {
        --bg: __BG__;
        --surface: __SURFACE__;
        --surface-2: __SURFACE_2__;
        --border: __BORDER__;
        --border-2: __BORDER_2__;
        --text: __TEXT__;
        --muted: __MUTED__;
        --muted-2: __MUTED_2__;

        /* App accent (kills Streamlit red vibe) */
        --accent: __ACCENT__;
        --accent-2: __ACCENT_2__;
        --focus: rgba(91,143,249,0.35);

        --shadow-soft: 0 10px 26px rgba(0,0,0,0.28);
        --radius: 14px;
        --radius-sm: 10px;

        /* Sticky tabs offset */
        --top-offset: 3.25rem;
      }

              /* =========================================================
           FORCE STREAMLIT THEME TOKENS (kills red everywhere)
           ========================================================= */
        
        /* Streamlit theme variables (these drive BaseWeb + widgets) */
        :root, .stApp {
          --primary-color: #5B8FF9 !important;
          --primary-color-rgb: 91, 143, 249 !important;
        
          /* These help prevent red fallback in some builds */
          --text-color: rgba(255,255,255,0.92) !important;
          --background-color: #0B1220 !important;
          --secondary-background-color: #0F1A2E !important;
        }
        
        /* Some Streamlit versions use these names */
        :root, .stApp {
          --primaryColor: #5B8FF9 !important;
          --primaryColorRgb: 91, 143, 249 !important;
        }
        
        /* BaseWeb often reads "currentColor" on controls (radio dot etc.) */
        [data-baseweb="radio"],
        [data-baseweb="checkbox"] {
          color: #5B8FF9 !important;
        }
        
        /* Prevent BaseWeb's accent from leaking anywhere */
        [class*="StyledThumb"],
        [class*="StyledTickBar"],
        input[type="checkbox"]:checked,
        input[type="radio"]:checked {
          background-color: #5B8FF9 !important;
          border-color: #5B8FF9 !important;
        }

      /* =========================================================
         APP SURFACES
         ========================================================= */
      .stApp {
        background: var(--bg);
        color: var(--text);
      }

      /* Sidebar (slightly lighter than main) */
      section[data-testid="stSidebar"] {
        background: var(--surface) !important;
        border-right: 1px solid var(--border-2);
      }

      /* Toasts (metric-like boxes) */
      .stAlert, [data-testid="stNotification"] {
        background: var(--surface-2) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text) !important;
      }

      /* Metrics */
      [data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-weight: 600;
      }
      [data-testid="stMetricLabel"] {
        color: var(--muted) !important;
      }

      /* Cards & containers */
      .element-container, [data-testid="column"] {
        border-radius: var(--radius-sm);
      }

      /* =========================================================
         INPUT WIDGETS (override Streamlit's red defaults)
         ========================================================= */

      /* All text inputs */
      input[type="text"],
      input[type="number"],
      input[type="email"],
      textarea,
      [data-baseweb="input"] input,
      [data-baseweb="textarea"] textarea {
        background: var(--surface-2) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text) !important;
        transition: border 0.15s ease, box-shadow 0.15s ease !important;
      }

      input:focus,
      textarea:focus,
      [data-baseweb="input"] input:focus,
      [data-baseweb="textarea"] textarea:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--focus) !important;
        outline: none !important;
      }

      /* Select boxes (multiselect / selectbox) */
      [data-baseweb="select"] > div,
      [data-baseweb="popover"] {
        background: var(--surface-2) !important;
        border-color: var(--border) !important;
        border-radius: var(--radius-sm) !important;
      }
      [data-baseweb="select"]:focus-within > div {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--focus) !important;
      }

      /* Tags in multiselect */
      [data-baseweb="tag"] {
        background: var(--accent) !important;
        color: white !important;
        border-radius: 6px !important;
      }

      /* Slider */
      [data-baseweb="slider"] [data-testid="stThumbValue"],
      [data-baseweb="slider"] [class*="StyledThumb"] {
        background: var(--accent) !important;
      }
      [data-baseweb="slider"] [class*="StyledTrack"] {
        background: linear-gradient(
          90deg,
          var(--accent) 0%,
          var(--border) 100%
        ) !important;
      }

      /* Date input */
      [data-baseweb="calendar"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
      }
      [data-baseweb="calendar"] [aria-selected="true"] {
        background: var(--accent) !important;
        color: white !important;
      }

      /* Radio / Checkbox accent */
      input[type="radio"]:checked::before,
      input[type="checkbox"]:checked::before {
        background: var(--accent) !important;
      }
      [data-baseweb="radio"] > div > div,
      [data-baseweb="checkbox"] > div > div {
        border-color: var(--accent) !important;
      }

      /* Buttons */
      button[kind="primary"],
      button[kind="primaryFormSubmit"] {
        background: var(--accent) !important;
        border: 1px solid var(--accent) !important;
        color: white !important;
        border-radius: var(--radius-sm) !important;
        font-weight: 600 !important;
        transition: all 0.15s ease !important;
      }
      button[kind="primary"]:hover {
        background: #4a7ad9 !important;
        box-shadow: var(--shadow-soft) !important;
      }

      button[kind="secondary"],
      button[kind="secondaryFormSubmit"] {
        background: var(--surface-2) !important;
        border: 1px solid var(--border-2) !important;
        color: var(--text) !important;
        border-radius: var(--radius-sm) !important;
        font-weight: 500 !important;
      }
      button[kind="secondary"]:hover {
        background: var(--surface) !important;
        border-color: var(--accent) !important;
      }

      /* =========================================================
         CUSTOM CARDS (for gallery)
         ========================================================= */
      .sighting-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        overflow: hidden;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
        margin-bottom: 1.25rem;
      }
      .sighting-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-soft);
        border-color: var(--border-2);
      }

      .card-thumbnail {
        position: relative;
        width: 100%;
        aspect-ratio: 16 / 11;
        background: var(--surface-2);
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
      }
      .card-thumbnail img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .card-content {
        padding: 1rem 1.1rem 1.1rem;
      }
      .card-title {
        font-size: 0.95rem;
        font-weight: 650;
        color: var(--text);
        margin-bottom: 0.35rem;
        line-height: 1.3;
      }
      .card-meta {
        font-size: 0.825rem;
        color: var(--muted);
        margin-bottom: 0.25rem;
      }
      .card-temp {
        display: inline-block;
        font-size: 0.775rem;
        color: var(--muted-2);
        background: var(--surface-2);
        padding: 0.2rem 0.5rem;
        border-radius: 6px;
        margin-top: 0.35rem;
      }
      .card-moon {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.825rem;
        color: var(--muted);
        background: var(--surface-2);
        padding: 0.25rem 0.6rem;
        border-radius: 6px;
        margin-top: 0.35rem;
        margin-left: 0.35rem;
      }

      .load-more-btn {
        text-align: center;
        margin-top: 1.5rem;
      }

      /* =========================================================
         MISC FIXES
         ========================================================= */
      .small-muted {
        font-size: 0.8rem;
        color: var(--muted-2);
      }

      hr {
        border-color: var(--border) !important;
        margin: 1.75rem 0 !important;
      }

      /* Markdown tables */
      table {
        border-collapse: collapse;
        background: var(--surface-2);
        border-radius: var(--radius-sm);
        overflow: hidden;
      }
      th, td {
        border: 1px solid var(--border);
        padding: 0.5rem 0.75rem;
      }
      th {
        background: var(--surface);
        font-weight: 600;
      }

      /* Code blocks */
      code {
        background: var(--surface-2) !important;
        color: var(--accent-2) !important;
        padding: 0.15rem 0.4rem !important;
        border-radius: 4px !important;
      }
      pre {
        background: var(--surface-2) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        padding: 1rem !important;
      }
    </style>
    """.replace("__BG__", PALETTE["bg"]) \
       .replace("__SURFACE__", PALETTE["surface"]) \
       .replace("__SURFACE_2__", PALETTE["surface_2"]) \
       .replace("__BORDER__", PALETTE["border"]) \
       .replace("__BORDER_2__", PALETTE["border_2"]) \
       .replace("__TEXT__", PALETTE["text"]) \
       .replace("__MUTED__", PALETTE["muted"]) \
       .replace("__MUTED_2__", PALETTE["muted_2"]) \
       .replace("__ACCENT__", PALETTE["primary"]) \
       .replace("__ACCENT_2__", PALETTE["secondary"])

    st.markdown(css, unsafe_allow_html=True)


# =============================================================================
# Timeline
# =============================================================================

def render_timeline(base: pd.DataFrame, section: str):
    st.markdown("### Activity Timeline")

    time_df = base.groupby(base["datetime"].dt.date).size().reset_index()
    time_df.columns = ["date", "count"]
    time_df["date"] = pd.to_datetime(time_df["date"])

    min_date = time_df["date"].min()
    max_date = time_df["date"].max()

    temp_series = base["temp_f"].dropna()
    if not temp_series.empty:
        temp_lo, temp_hi = clamp_temp_domain(temp_series.min(), temp_series.max())
    else:
        temp_lo, temp_hi = 10, 90

    color_val = SECTION_COLORS.get(section.lower(), PALETTE["info"])

    base_line = (
        alt.Chart(time_df)
        .mark_line(point=True, strokeWidth=2.5, color=color_val)
        .encode(
            x=alt.X("date:T", title="Date", scale=alt.Scale(domain=[min_date, max_date])),
            y=alt.Y("count:Q", title="Sightings"),
            tooltip=[
                alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                alt.Tooltip("count:Q", title="Count"),
            ],
        )
    )

    temp_valid = base.dropna(subset=["temp_f"]).copy()
    if not temp_valid.empty:
        temp_agg = temp_valid.groupby(temp_valid["datetime"].dt.date)["temp_f"].mean().reset_index()
        temp_agg.columns = ["date", "avg_temp"]
        temp_agg["date"] = pd.to_datetime(temp_agg["date"])

        temp_line = (
            alt.Chart(temp_agg)
            .mark_line(strokeDash=[5, 5], strokeWidth=1.8, color=PALETTE["warning"], opacity=0.7)
            .encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("avg_temp:Q", title="Avg Temp (°F)", scale=alt.Scale(domain=[temp_lo, temp_hi])),
                tooltip=[
                    alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                    alt.Tooltip("avg_temp:Q", title="Avg Temp", format=".1f"),
                ],
            )
        )

        combined = alt.layer(base_line, temp_line).resolve_scale(y="independent").properties(height=280)
    else:
        combined = base_line.properties(height=280)

    st.altair_chart(apply_chart_theme(combined), use_container_width=True)


# =============================================================================
# Patterns (time-of-day, day-of-week, moon phase)
# =============================================================================

def render_patterns(base: pd.DataFrame, section: str, include_other: bool, bar_style: str, time_gran: str):
    st.markdown("### Activity Patterns")

    patt = base.copy()
    patt["hour"] = patt["datetime"].dt.hour
    patt["weekday"] = patt["datetime"].dt.day_name()

    # Time granularity bins
    if time_gran == "2-hour":
        patt["time_bin"] = (patt["hour"] // 2) * 2
        patt["time_label"] = patt["time_bin"].apply(lambda x: f"{x:02d}–{x+2:02d}")
    elif time_gran == "4-hour":
        patt["time_bin"] = (patt["hour"] // 4) * 4
        patt["time_label"] = patt["time_bin"].apply(lambda x: f"{x:02d}–{x+4:02d}")
    else:
        patt["time_bin"] = patt["hour"]
        patt["time_label"] = patt["hour"].apply(lambda x: f"{x:02d}:00")

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    time_order = sorted(patt["time_label"].unique())

    if section == "Wildlife":
        if not include_other:
            patt = patt[patt["wildlife_label"] != "Other"]
        patt["animal_group"] = patt["wildlife_label"]
    elif section == "People":
        patt["animal_group"] = "Human"
    else:
        patt["animal_group"] = "Vehicle"

    domain, color_range = stable_color_domain(patt["animal_group"].unique().tolist(), WILDLIFE_PALETTE)
    color_enc = alt.Color(
        "animal_group:N",
        scale=alt.Scale(domain=domain, range=color_range),
        legend=alt.Legend(title=section if section == "Wildlife" else "Type"),
    )

    by_time = patt.groupby(["time_label", "animal_group"]).size().reset_index(name="Sightings")
    by_time["time_label"] = pd.Categorical(by_time["time_label"], categories=time_order, ordered=True)
    by_time = by_time.sort_values(["time_label", "animal_group"])

    if bar_style == "Grouped":
        time_chart = (
            alt.Chart(by_time)
            .mark_bar(opacity=0.90, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=color_enc,
                xOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("time_label:N", title="Time"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )
    else:
        time_chart = (
            alt.Chart(by_time)
            .mark_bar(opacity=0.90, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=color_enc,
                tooltip=[
                    alt.Tooltip("time_label:N", title="Time"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )

    by_day = patt.groupby(["weekday", "animal_group"]).size().reset_index(name="Sightings")
    by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)
    by_day = by_day.sort_values(["weekday", "animal_group"])

    if bar_style == "Grouped":
        day_chart = (
            alt.Chart(by_day)
            .mark_bar(opacity=0.90, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Count"),
                color=color_enc,
                yOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("weekday:N", title="Day"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )
    else:
        day_chart = (
            alt.Chart(by_day)
            .mark_bar(opacity=0.90, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Count"),
                color=color_enc,
                tooltip=[
                    alt.Tooltip("weekday:N", title="Day"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )

    # Moon phase chart
    moon_valid = patt[patt["moon_phase_clean"] != ""].copy()
    if not moon_valid.empty:
        # Define moon phase order
        moon_order = [
            "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
            "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"
        ]
        
        by_moon = moon_valid.groupby(["moon_phase_clean", "animal_group"]).size().reset_index(name="Sightings")
        by_moon["moon_phase_clean"] = pd.Categorical(by_moon["moon_phase_clean"], categories=moon_order, ordered=True)
        by_moon = by_moon.sort_values(["moon_phase_clean", "animal_group"])

        if bar_style == "Grouped":
            moon_chart = (
                alt.Chart(by_moon)
                .mark_bar(opacity=0.90, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
                .encode(
                    y=alt.Y("moon_phase_clean:N", title="Moon Phase", sort=moon_order),
                    x=alt.X("Sightings:Q", title="Count"),
                    color=color_enc,
                    yOffset="animal_group:N",
                    tooltip=[
                        alt.Tooltip("moon_phase_clean:N", title="Moon Phase"),
                        alt.Tooltip("animal_group:N", title="Animal"),
                        alt.Tooltip("Sightings:Q", title="Count"),
                    ],
                )
                .properties(height=250)
            )
        else:
            moon_chart = (
                alt.Chart(by_moon)
                .mark_bar(opacity=0.90, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
                .encode(
                    y=alt.Y("moon_phase_clean:N", title="Moon Phase", sort=moon_order),
                    x=alt.X("Sightings:Q", title="Count"),
                    color=color_enc,
                    tooltip=[
                        alt.Tooltip("moon_phase_clean:N", title="Moon Phase"),
                        alt.Tooltip("animal_group:N", title="Animal"),
                        alt.Tooltip("Sightings:Q", title="Count"),
                    ],
                )
                .properties(height=250)
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


# =============================================================================
# Insights
# =============================================================================

def _calculate_insights(row, base: pd.DataFrame, section: str):
    """Generate contextual insights for selected sighting."""
    insights = []

    cam = row.get("camera", "").strip()
    dt = row.get("datetime")
    if pd.isna(dt):
        return insights

    same_day = base[(base["camera"] == cam) & (base["datetime"].dt.date == dt.date())]
    if len(same_day) > 1:
        if section == "Wildlife":
            animal = row.get("wildlife_label", "")
            same_animal_count = len(same_day[same_day["wildlife_label"] == animal])
            if same_animal_count > 1:
                insights.append(f"{same_animal_count} {animal} sightings at {cam} today")
            else:
                insights.append(f"{len(same_day)} total sightings at {cam} today")
        else:
            insights.append(f"{len(same_day)} sightings at {cam} today")

    temp = row.get("temp_f")
    if pd.notna(temp):
        yesterday = dt - pd.Timedelta(days=1)
        yesterday_data = base[(base["datetime"] >= yesterday) & (base["datetime"] < dt - pd.Timedelta(hours=12))]
        if not yesterday_data.empty and yesterday_data["temp_f"].notna().any():
            avg_yesterday = yesterday_data["temp_f"].mean()
            diff = temp - avg_yesterday
            if abs(diff) > 5:
                direction = "warmer" if diff > 0 else "cooler"
                insights.append(f"{abs(int(diff))}°F {direction} than previous day")

    if section == "Wildlife":
        animal = row.get("wildlife_label", "")
        animal_data = base[base["wildlife_label"] == animal]
        if len(animal_data) > 5:
            hour_counts = animal_data["datetime"].dt.hour.value_counts()
            peak_hour = hour_counts.idxmax()
            insights.append(f"Peak activity: {peak_hour}:00–{peak_hour+1}:00")

    return insights


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
    """
    Photo gallery - filtered data passed in
    """
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
                        meta_line += f'<span class="card-temp">{temp_str}</span>'
                    if moon_phase and moon_emoji:
                        meta_line += f'<span class="card-moon">{moon_emoji} {moon_phase}</span>'
                    meta_line += '</div>'
                    st.markdown(meta_line, unsafe_allow_html=True)

                if url:
                    st.markdown(
                        f'<div style="margin-top:0.55rem;"><a href="{url}" target="_blank" style="font-size:0.85rem; opacity:0.9;">View in Drive</a></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("</div>", unsafe_allow_html=True)  # card-content
                st.markdown("</div>", unsafe_allow_html=True)  # sighting-card

    # Load More button (single, deduped)
    if len(view) > st.session_state.gallery_limit:
        remaining = len(view) - st.session_state.gallery_limit
        st.markdown('<div class="load-more-btn">', unsafe_allow_html=True)
        if st.button(f"Load More ({remaining} remaining)", key=f"load_more_{section}"):
            st.session_state.gallery_limit += 8
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
