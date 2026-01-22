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

# Brand palette (tuned for a "premium" neutral UI + tasteful accents)
PALETTE = {
    "bg": "#0B1220",         # deep navy background (reads premium, avoids pure black)
    "surface": "#0F1A2E",    # cards/panels
    "surface_2": "#111F38",  # slightly elevated surface
    "border": "rgba(255,255,255,0.10)",
    "border_2": "rgba(255,255,255,0.16)",
    "text": "rgba(255,255,255,0.92)",
    "muted": "rgba(255,255,255,0.65)",
    "muted_2": "rgba(255,255,255,0.50)",

    # Accents
    "primary": "#5B8FF9",    # calm blue
    "secondary": "#61DDAA",  # mint
    "warning": "#FB8C00",    # refined orange
    "info": "#1E88E5",       # richer blue
    "success": "#2E7D32",    # deep green
    "neutral": "#94A3B8",    # slate for "Other"
}

# Wildlife categorical palette (distinct, non-neon, cohesive)
WILDLIFE_PALETTE = [
    "#5B8FF9",  # blue
    "#61DDAA",  # mint
    "#7262FD",  # violet
    "#F6BD16",  # warm yellow
    "#78D3F8",  # sky
    "#9661BC",  # purple
    "#F6903D",  # orange
    "#008685",  # teal
    "#F08BB4",  # pink
    "#B8E986",  # soft green
    "#65789B",  # slate
    "#D3ADF7",  # lavender
]

SECTION_COLORS = {
    "wildlife": PALETTE["success"],
    "people": PALETTE["info"],
    "vehicle": PALETTE["warning"],
}


def stable_color_domain(values: List[str], palette: List[str], *, pin_other_gray: bool = True) -> Tuple[List[str], List[str]]:
    """
    Stable mapping category -> color.
    - Sorted domain ensures repeatable mapping across reruns.
    - Optionally pins "Other" to neutral gray for de-emphasis.
    """
    cleaned = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            cleaned.append(s)

    domain = sorted(set(cleaned))
    color_range: List[str] = []

    # Pin "Other" to neutral gray so it doesn't compete visually
    if pin_other_gray and "Other" in domain:
        domain_no_other = [d for d in domain if d != "Other"]
        range_no_other = [palette[i % len(palette)] for i in range(len(domain_no_other))]
        domain = domain_no_other + ["Other"]
        color_range = range_no_other + [PALETTE["neutral"]]
    else:
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


# Register once (safe to call multiple times; Streamlit reruns can re-import)
try:
    alt.themes.register("premium_ui", _altair_theme)
except Exception:
    pass

alt.themes.enable("premium_ui")


def apply_chart_theme(chart: alt.Chart) -> alt.Chart:
    """Extra per-chart polish: consistent padding, nicer axes, etc."""
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
    st.markdown(
        f"""
        <style>
          :root {{
            --bg: {PALETTE["bg"]};
            --surface: {PALETTE["surface"]};
            --surface-2: {PALETTE["surface_2"]};
            --border: {PALETTE["border"]};
            --border-2: {PALETTE["border_2"]};
            --text: {PALETTE["text"]};
            --muted: {PALETTE["muted"]};
            --muted-2: {PALETTE["muted_2"]};

            /* App accent (kills the Streamlit red vibe) */
            --accent: {PALETTE["primary"]};
            --accent-2: {PALETTE["secondary"]};
            --focus: rgba(91,143,249,0.35);

            --shadow: 0 14px 40px rgba(0,0,0,0.35);
            --shadow-soft: 0 10px 26px rgba(0,0,0,0.28);
            --radius: 14px;
            --radius-sm: 10px;
            --top-offset: 3.25rem;
          }}

          /* =========================================================
             GLOBAL
             ========================================================= */
          .stApp {{
            background: radial-gradient(1200px 700px at 20% -10%, rgba(91,143,249,0.18) 0%, rgba(0,0,0,0) 55%),
                        radial-gradient(900px 600px at 90% 0%, rgba(97,221,170,0.12) 0%, rgba(0,0,0,0) 50%),
                        var(--bg);
            color: var(--text);
          }}

          .block-container {{
            padding-top: 4.2rem;
            padding-bottom: 2.75rem;
            max-width: 1320px;
          }}

          header[data-testid="stHeader"] {{
            background: rgba(11,18,32,0.65);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.06);
          }}

          h1, h2, h3 {{
            letter-spacing: -0.02em;
            font-weight: 650;
            color: var(--text);
          }}

          /* =========================================================
             NAV / TABS FIX (sticky + clickable)
             ========================================================= */
          .stTabs [data-baseweb="tab-list"] {{
            position: sticky;
            top: var(--top-offset);
            z-index: 999;
            background: rgba(15,26,46,0.92);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
            padding: 0.35rem 0.35rem;
            margin-top: 0.4rem;
            margin-bottom: 1.0rem;
            box-shadow: var(--shadow-soft);
          }}

          .stTabs [data-baseweb="tab"] {{
            border-radius: 10px !important;
            color: var(--muted) !important;
            font-weight: 650 !important;
            padding: 0.55rem 0.85rem !important;
          }}

          .stTabs [aria-selected="true"] {{
            color: var(--text) !important;
            background: rgba(91,143,249,0.16) !important;
            border: 1px solid rgba(91,143,249,0.25) !important;
          }}

          /* =========================================================
             WIDGET THEME OVERRIDES (filters)
             - Removes red defaults
             - Unifies accent + focus styles
             ========================================================= */

          /* Make default Streamlit accent feel like your palette */
          html, body, [class*="st-"] {{
            accent-color: var(--accent);
          }}

          /* Focus ring */
          :is(button, input, textarea, select, [role="slider"], [role="combobox"]):focus,
          :is(button, input, textarea, select, [role="slider"], [role="combobox"]):focus-visible {{
            outline: none !important;
            box-shadow: 0 0 0 3px var(--focus) !important;
            border-color: rgba(91,143,249,0.35) !important;
          }}

          /* Text inputs / number inputs / textareas */
          div[data-testid="stTextInput"] input,
          div[data-testid="stNumberInput"] input,
          div[data-testid="stTextArea"] textarea {{
            background: rgba(255,255,255,0.03) !important;
            color: var(--text) !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            border-radius: 10px !important;
          }}
          div[data-testid="stTextInput"] input:hover,
          div[data-testid="stNumberInput"] input:hover,
          div[data-testid="stTextArea"] textarea:hover {{
            border-color: rgba(255,255,255,0.16) !important;
          }}

          /* Selectbox / Multiselect baseweb styling */
          div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
          div[data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
            background: rgba(255,255,255,0.03) !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            border-radius: 10px !important;
          }}
          div[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
          div[data-testid="stMultiSelect"] [data-baseweb="select"] > div:hover {{
            border-color: rgba(255,255,255,0.16) !important;
          }}

          /* Multiselect "pills" */
          div[data-testid="stMultiSelect"] [data-baseweb="tag"] {{
            background: rgba(91,143,249,0.16) !important;
            border: 1px solid rgba(91,143,249,0.25) !important;
            color: var(--text) !important;
            border-radius: 999px !important;
          }}
          div[data-testid="stMultiSelect"] [data-baseweb="tag"] span {{
            color: var(--text) !important;
          }}

          /* Dropdown menu surface */
          [data-baseweb="popover"] [role="listbox"] {{
            background: rgba(15,26,46,0.98) !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            border-radius: 12px !important;
            box-shadow: var(--shadow-soft) !important;
          }}
          [data-baseweb="popover"] [role="option"] {{
            color: var(--text) !important;
          }}
          [data-baseweb="popover"] [role="option"][aria-selected="true"] {{
            background: rgba(91,143,249,0.16) !important;
          }}
          [data-baseweb="popover"] [role="option"]:hover {{
            background: rgba(255,255,255,0.06) !important;
          }}

          /* Sliders */
          div[data-testid="stSlider"] [role="slider"] {{
            color: var(--accent) !important;
          }}
          /* Track + fill (baseweb) */
          div[data-testid="stSlider"] [data-baseweb="slider"] div[role="presentation"] > div {{
            background: rgba(255,255,255,0.10) !important;
          }}
          div[data-testid="stSlider"] [data-baseweb="slider"] div[role="presentation"] > div > div {{
            background: rgba(91,143,249,0.75) !important;
          }}

          /* Checkbox + Radio */
          div[data-testid="stCheckbox"] input[type="checkbox"],
          div[data-testid="stRadio"] input[type="radio"] {{
            accent-color: var(--accent) !important;
          }}

          /* Toggle (st.toggle uses checkbox under the hood) */
          div[data-testid="stToggle"] input {{
            accent-color: var(--accent) !important;
          }}

          /* Buttons */
          button[kind="primary"] {{
            background: linear-gradient(180deg, rgba(91,143,249,0.95), rgba(91,143,249,0.80)) !important;
            border: 1px solid rgba(91,143,249,0.35) !important;
          }}
          button[kind="secondary"] {{
            background: rgba(255,255,255,0.04) !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            color: var(--text) !important;
          }}
          button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 10px 24px rgba(0,0,0,0.25);
          }}

          /* =========================================================
             Gallery Cards
             ========================================================= */
          .sighting-card {{
            background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 14px;
            padding: 0;
            transition: transform 0.14s ease, border-color 0.14s ease, box-shadow 0.14s ease;
            position: relative;
            overflow: hidden;
            box-shadow: 0 12px 28px rgba(0,0,0,0.22);
          }}
          .sighting-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(255,255,255,0.18);
            box-shadow: 0 18px 46px rgba(0,0,0,0.32);
          }}

          .card-thumbnail {{
            width: 100%;
            height: 170px;
            background: rgba(0,0,0,0.35);
            margin-bottom: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
          }}
          .card-thumbnail img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
          }}
          .card-thumbnail::after {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, rgba(0,0,0,0.10) 0%, rgba(0,0,0,0.40) 100%);
            pointer-events: none;
          }}

          .card-content {{
            padding: 0.95rem 0.95rem 0.9rem;
          }}
          .card-title {{
            font-size: 1.02rem;
            font-weight: 750;
            margin-bottom: 0.35rem;
            line-height: 1.25;
            color: var(--text);
          }}
          .card-meta {{
            font-size: 0.88rem;
            color: var(--muted);
            margin-bottom: 0.25rem;
          }}
          .card-temp {{
            font-size: 0.88rem;
            color: var(--muted-2);
          }}

          .load-more-btn {{
            text-align: center;
            margin-top: 1.25rem;
          }}

          .vega-embed {{
            padding: 0 !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# Charts
# =============================================================================

def render_timeline(base: pd.DataFrame, section: str):
    st.subheader("Timeline")
    st.caption("Each dot represents one sighting")

    chart_df = base.dropna(subset=["datetime", "temp_f"]).copy()
    if chart_df.empty:
        st.info("No temperature data available for timeline visualization")
        return

    tooltip = [
        alt.Tooltip("datetime:T", title="Time"),
        alt.Tooltip("temp_f:Q", title="Temperature", format=".0f"),
        alt.Tooltip("camera:N", title="Camera"),
    ]

    if section == "Wildlife":
        counts = chart_df.groupby("wildlife_label").size().sort_values(ascending=False)
        top = counts.head(10).index.tolist()
        chart_df["wildlife_group_chart"] = chart_df["wildlife_label"].where(
            chart_df["wildlife_label"].isin(top),
            other="Other",
        )

        domain, color_range = stable_color_domain(
            chart_df["wildlife_group_chart"].unique().tolist(),
            WILDLIFE_PALETTE,
            pin_other_gray=True,
        )

        color_enc = alt.Color(
            "wildlife_group_chart:N",
            title="Animal",
            scale=alt.Scale(domain=domain, range=color_range),
        )

        tooltip = [
            alt.Tooltip("datetime:T", title="Time"),
            alt.Tooltip("temp_f:Q", title="Temperature", format=".0f"),
            alt.Tooltip("wildlife_label:N", title="Animal"),
            alt.Tooltip("camera:N", title="Camera"),
        ]
    else:
        chart_df["type_label"] = section.lower()
        color = SECTION_COLORS.get(section.lower(), SECTION_COLORS["wildlife"])
        color_enc = alt.Color("type_label:N", legend=None, scale=alt.Scale(range=[color]))

    y_lo, y_hi = clamp_temp_domain(chart_df["temp_f"].min(), chart_df["temp_f"].max())

    scatter = (
        alt.Chart(chart_df)
        .mark_circle(size=120, opacity=0.80, stroke="rgba(255,255,255,0.45)", strokeWidth=0.6)
        .encode(
            x=alt.X("datetime:T", title="Date & Time"),
            y=alt.Y("temp_f:Q", title="Temperature (°F)", scale=alt.Scale(domain=[y_lo, y_hi])),
            color=color_enc,
            tooltip=tooltip,
        )
        .properties(height=320)
        .interactive()
    )

    st.altair_chart(apply_chart_theme(scatter), use_container_width=True)


def render_patterns(base: pd.DataFrame, section: str, include_other: bool, bar_style: str, time_gran: str):
    st.subheader("Activity Patterns")

    patt = base.dropna(subset=["datetime"]).copy()
    patt["weekday"] = patt["datetime"].dt.day_name()
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    patt["hour"] = patt["datetime"].dt.hour
    if time_gran == "2-hour":
        patt["time_bin"] = (patt["hour"] // 2) * 2
        patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
    elif time_gran == "4-hour":
        patt["time_bin"] = (patt["hour"] // 4) * 4
        patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
    else:
        patt["time_label"] = patt["hour"].astype(int).astype(str) + ":00"

    # People / Vehicles (single-series)
    if section != "Wildlife":
        chart_color = SECTION_COLORS.get(section.lower(), SECTION_COLORS["wildlife"])

        by_time = patt.groupby("time_label").size().reset_index(name="Sightings")
        by_time["__h"] = by_time["time_label"].str.split(":").str[0].astype(int)
        by_time = by_time.sort_values("__h")

        time_chart = (
            alt.Chart(by_time)
            .mark_bar(color=chart_color, opacity=0.88, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=by_time["time_label"].tolist(), axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                tooltip=[alt.Tooltip("time_label:N", title="Time"), alt.Tooltip("Sightings:Q", title="Count")],
            )
            .properties(height=250)
        )

        by_day = patt.groupby("weekday").size().reindex(weekday_order, fill_value=0).reset_index(name="Sightings")
        by_day.columns = ["weekday", "Sightings"]

        day_chart = (
            alt.Chart(by_day)
            .mark_bar(color=chart_color, opacity=0.88, cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Count"),
                tooltip=[alt.Tooltip("weekday:N", title="Day"), alt.Tooltip("Sightings:Q", title="Count")],
            )
            .properties(height=250)
        )

        cA, cB = st.columns(2)
        with cA:
            st.markdown("**By Time of Day**")
            st.altair_chart(apply_chart_theme(time_chart), use_container_width=True)
        with cB:
            st.markdown("**By Day of Week**")
            st.altair_chart(apply_chart_theme(day_chart), use_container_width=True)
        return

    # Wildlife (multi-series)
    if not include_other:
        patt = patt[patt["wildlife_label"] != "Other"]

    sp_counts = patt.groupby("wildlife_label").size().sort_values(ascending=False)
    top_species = sp_counts.head(8).index.tolist()
    patt["animal_group"] = patt["wildlife_label"].where(patt["wildlife_label"].isin(top_species), other="Other")

    by_time = patt.groupby(["time_label", "animal_group"]).size().reset_index(name="Sightings")

    def _time_sort_key(x: str) -> int:
        try:
            return int(x.split(":")[0])
        except Exception:
            return 0

    time_order = sorted(by_time["time_label"].unique().tolist(), key=_time_sort_key)

    # Stable wildlife color mapping (consistent across time/day charts)
    domain_w, range_w = stable_color_domain(by_time["animal_group"].unique().tolist(), WILDLIFE_PALETTE, pin_other_gray=True)
    color_enc = alt.Color("animal_group:N", title="Animal", scale=alt.Scale(domain=domain_w, range=range_w))

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

    # Same camera, same day
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

    # Temperature context
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

    # Peak activity time
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

            if section == "Wildlife":
                label = row.get("wildlife_label", "Other")
            else:
                label = (row.get("event_type", "")).capitalize()

            time_str = dt.strftime("%b %d, %I:%M %p") if pd.notna(dt) else "Unknown time"
            temp_str = f"{int(temp)}°F" if pd.notna(temp) else ""

            with cols[col_idx]:
                url, fid = resolve_image_link(cam, fn, image_index)

                st.markdown('<div class="sighting-card">', unsafe_allow_html=True)

                # Thumbnail
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

                # Content
                st.markdown('<div class="card-content">', unsafe_allow_html=True)
                st.markdown(f'<div class="card-title">{label} • {cam}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card-meta">{time_str}</div>', unsafe_allow_html=True)
                if temp_str:
                    st.markdown(f'<div class="card-temp">{temp_str}</div>', unsafe_allow_html=True)

                if url:
                    st.markdown(
                        f'<div style="margin-top:0.55rem;"><a href="{url}" target="_blank" style="font-size:0.85rem; opacity:0.9;">View in Drive</a></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("</div>", unsafe_allow_html=True)  # card-content
                st.markdown("</div>", unsafe_allow_html=True)  # sighting-card

    # Load More button (single, deduped)
    if len(view) > st.session_state.gallery_limit:
        st.markdown('<div class="load-more-btn">', unsafe_allow_html=True)
        remaining = len(view) - st.session_state.gallery_limit
        if st.button(f"Load More ({remaining} remaining)", key=f"load_more_{section}"):
            st.session_state.gallery_limit += 8
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
