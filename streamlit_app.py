import html

import pandas as pd
import streamlit as st

from data_prep import nice_last_modified, prep_df
from drive_io import load_events_from_drive, _drive_client, _download_drive_file_bytes
from ui_components import inject_css, render_patterns, render_timeline, render_listing_and_viewer

st.set_page_config(
    page_title="Ranch Events",
    page_icon="🦌",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

ADV_GALLERY_URL = "https://willclo1.github.io/SpyPointAdvancedGallery/"


def require_secret(path: str):
    current = st.secrets
    for part in path.split("."):
        if part not in current:
            raise KeyError(f"Missing secret: {path}")
        current = current[part]
    return current


@st.cache_data(show_spinner=False)
def prepare_events(raw_df: pd.DataFrame) -> pd.DataFrame:
    return prep_df(raw_df)


def date_bounds(frame: pd.DataFrame):
    valid = frame.dropna(subset=["datetime"])
    if valid.empty:
        return None
    return valid["datetime"].min(), valid["datetime"].max()


def normalize_date_range(value, fallback_start, fallback_end):
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return value[0], value[1]
    return fallback_start, fallback_end


def apply_common_filters(frame, cameras, dates, temp_range, moon_phases):
    result = frame.dropna(subset=["datetime"]).copy()
    if cameras:
        result = result[result["camera"].isin(cameras)]
    start, end = dates
    result = result[
        (result["datetime"] >= pd.Timestamp(start))
        & (result["datetime"] < pd.Timestamp(end) + pd.Timedelta(days=1))
    ]
    if temp_range is not None:
        result = result[result["temp_f"].between(temp_range[0], temp_range[1], inclusive="both")]
    if moon_phases:
        result = result[result["moon_phase_clean"].isin(moon_phases)]
    return result


def render_header(updated: str):
    st.markdown(
        f"""
        <div class="app-header">
          <div class="brand-wrap">
            <div class="brand-mark">🦌</div>
            <div>
              <div class="brand-name">Ranch Events</div>
              <div class="brand-kicker">Wildlife intelligence</div>
            </div>
          </div>
          <div class="sync-pill"><span class="sync-dot"></span> Updated {html.escape(updated)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hero(kicker: str, title: str, copy: str, total: int, total_label: str):
    st.markdown(
        f"""
        <section class="page-hero">
          <div>
            <div class="eyebrow">{html.escape(kicker)}</div>
            <div class="hero-title">{html.escape(title)}</div>
            <div class="hero-copy">{html.escape(copy)}</div>
          </div>
          <div class="hero-stat"><strong>{total:,}</strong><span>{html.escape(total_label)}</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str, copy: str):
    st.markdown(
        f'<div class="section-heading"><div><h2>{html.escape(title)}</h2><p>{html.escape(copy)}</p></div></div>',
        unsafe_allow_html=True,
    )


def render_insights(base: pd.DataFrame, section: str):
    if base.empty:
        return
    camera_counts = base["camera"].value_counts()
    busiest_camera = camera_counts.index[0] if not camera_counts.empty else "—"
    busiest_count = int(camera_counts.iloc[0]) if not camera_counts.empty else 0
    newest = base["datetime"].max()
    newest_label = newest.strftime("%b %d at %-I:%M %p") if pd.notna(newest) else "—"
    if section == "Wildlife":
        labels = base["wildlife_label"].value_counts()
        top_label = labels.index[0] if not labels.empty else "—"
        top_note = f"{int(labels.iloc[0]):,} sightings" if not labels.empty else "No sightings"
    else:
        top_label = "People" if section == "People" else "Vehicles"
        top_note = f"{len(base):,} recorded events"
    st.markdown(
        f"""
        <div class="insight-grid">
          <div class="insight-card"><div class="insight-label">Most active camera</div><div class="insight-value">{html.escape(str(busiest_camera))}</div><div class="insight-note">{busiest_count:,} matching events</div></div>
          <div class="insight-card"><div class="insight-label">Leading category</div><div class="insight-value">{html.escape(str(top_label))}</div><div class="insight-note">{html.escape(top_note)}</div></div>
          <div class="insight-card"><div class="insight-label">Latest activity</div><div class="insight-value">{html.escape(newest_label)}</div><div class="insight-note">Within the selected filters</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


DRIVE_FILE_ID = require_secret("gdrive.file_id")
ROOT_FOLDER_ID = require_secret("gdrive.root_folder_id")
CACHE_TTL_SECONDS = int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60))

with st.spinner("Syncing ranch activity…"):
    raw = load_events_from_drive(DRIVE_FILE_ID)
df = prepare_events(raw)
last_modified = nice_last_modified(raw.attrs.get("drive_modified", ""))

if "current_view" not in st.session_state:
    st.session_state.current_view = "dashboard"
if "gallery_page" not in st.session_state:
    st.session_state.gallery_page = 1

with st.sidebar:
    st.markdown("### Data status")
    st.metric("Recorded events", f"{len(df):,}")
    st.caption(f"Last updated {last_modified}")
    if st.button("Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.markdown(
        f'<div class="small-muted">Cached for up to {max(1, CACHE_TTL_SECONDS // 3600)} hours</div>',
        unsafe_allow_html=True,
    )

render_header(last_modified)

bounds = date_bounds(df)
if bounds is None:
    st.error("No valid date and time data was found in the events file.")
    st.stop()
min_dt, max_dt = bounds
camera_options = sorted(value for value in df["camera"].dropna().unique().tolist() if value)
moon_options = sorted(value for value in df.get("moon_phase_clean", pd.Series(dtype=str)).dropna().unique().tolist() if value)
temps = df["temp_f"].dropna()
temp_limits = None if temps.empty else (int(temps.min()), int(temps.max()))
if temp_limits and temp_limits[0] == temp_limits[1]:
    temp_limits = (temp_limits[0] - 1, temp_limits[1] + 1)


@st.fragment
def render_app_view():
    view_labels = {
        "Overview": "dashboard",
        "Photo browser": "photos",
        "Advanced gallery": "gallery",
    }
    reverse_labels = {value: label for label, value in view_labels.items()}
    selected_label = st.segmented_control(
        "View",
        options=list(view_labels),
        default=reverse_labels.get(st.session_state.current_view, "Overview"),
        key="primary_navigation",
        label_visibility="collapsed",
        width="stretch",
    )
    if selected_label:
        st.session_state.current_view = view_labels[selected_label]

    if st.session_state.current_view == "dashboard":
        render_hero(
            "Activity overview",
            "Understand what is moving across the ranch.",
            "Explore wildlife, people, and vehicle patterns across time, temperature, cameras, and moon phases.",
            len(df),
            "total recorded events",
        )

        with st.expander("Filters and chart options", expanded=True):
            row1 = st.columns([1, 1.4, 1.2], gap="large")
            with row1[0]:
                section = st.selectbox("Event category", ["Wildlife", "People", "Vehicles"], key="dash_section")
            with row1[1]:
                selected_cameras = st.multiselect("Cameras", camera_options, default=camera_options, key="dash_cameras")
            with row1[2]:
                date_value = st.date_input("Date range", (min_dt.date(), max_dt.date()), min_value=min_dt.date(), max_value=max_dt.date(), key="dash_dates")
                date_range = normalize_date_range(date_value, min_dt.date(), max_dt.date())

            row2 = st.columns([1.2, 1.2, 1], gap="large")
            with row2[0]:
                temp_range = st.slider("Temperature (°F)", temp_limits[0], temp_limits[1], temp_limits, key="dash_temp") if temp_limits else None
            with row2[1]:
                selected_moons = st.multiselect("Moon phases", moon_options, key="dash_moons") if moon_options else []
            with row2[2]:
                time_gran = st.selectbox("Time grouping", ["Hour", "2-hour", "4-hour"], key="dash_time")

            include_other = False
            species_filter = []
            bar_style = "Stacked"
            if section == "Wildlife":
                row3 = st.columns([1, 1, 2], gap="large")
                with row3[0]:
                    include_other = st.toggle("Include Other", value=False, key="dash_other")
                with row3[1]:
                    bar_style = st.selectbox("Bar style", ["Stacked", "Grouped"], key="dash_bar")
                pool = df[df["event_type"] == "animal"]
                if not include_other:
                    pool = pool[pool["wildlife_label"] != "Other"]
                species_options = sorted(value for value in pool["wildlife_label"].unique().tolist() if value)
                with row3[2]:
                    species_filter = st.multiselect("Animals", species_options, key="dash_species")

        base = apply_common_filters(df, selected_cameras, date_range, temp_range, selected_moons)
        event_type = {"Wildlife": "animal", "People": "human", "Vehicles": "vehicle"}[section]
        base = base[base["event_type"] == event_type]
        if section == "Wildlife":
            if not include_other:
                base = base[base["wildlife_label"] != "Other"]
            if species_filter:
                base = base[base["wildlife_label"].isin(species_filter)]

        if base.empty:
            st.info("No events match these filters. Try widening the date, camera, or category selection.")
            return

        active_cameras = base["camera"].nunique()
        avg_temp = base["temp_f"].mean()
        peak = base["datetime"].dt.hour.mode()
        peak_label = "—" if peak.empty else pd.Timestamp(2000, 1, 1, int(peak.iloc[0])).strftime("%-I %p")
        k1, k2, k3, k4 = st.columns(4, gap="large")
        k1.metric("Matching events", f"{len(base):,}")
        k2.metric("Active cameras", f"{active_cameras:,}")
        k3.metric("Average temperature", "—" if pd.isna(avg_temp) else f"{avg_temp:.0f}°F")
        k4.metric("Peak activity", peak_label)
        render_insights(base, section)

        render_section("Activity over time", "Daily event volume makes spikes and quiet periods easy to spot.")
        render_timeline(base, section)
        render_section("Behavior patterns", "Compare activity by hour, weekday, and moon phase.")
        render_patterns(base, section, include_other, bar_style, time_gran)

    elif st.session_state.current_view == "photos":
        render_hero(
            "Visual archive",
            "Browse sightings without loading the entire camera library.",
            "Filter the event log first, then load only the images needed for the current page.",
            len(df),
            "photos available through event records",
        )

        with st.expander("Photo filters", expanded=True):
            row1 = st.columns([1, 1.5, 1.2], gap="large")
            with row1[0]:
                section = st.selectbox("Event category", ["Wildlife", "People", "Vehicles"], key="photo_section")
            with row1[1]:
                selected_cameras = st.multiselect("Cameras", camera_options, default=camera_options, key="photo_cameras")
            with row1[2]:
                date_value = st.date_input("Date range", (min_dt.date(), max_dt.date()), min_value=min_dt.date(), max_value=max_dt.date(), key="photo_dates")
                date_range = normalize_date_range(date_value, min_dt.date(), max_dt.date())

            row2 = st.columns([1.2, 1.2, 1], gap="large")
            with row2[0]:
                temp_range = st.slider("Temperature (°F)", temp_limits[0], temp_limits[1], temp_limits, key="photo_temp") if temp_limits else None
            with row2[1]:
                selected_moons = st.multiselect("Moon phases", moon_options, key="photo_moons") if moon_options else []
            include_other = False
            species_filter = []
            with row2[2]:
                if section == "Wildlife":
                    include_other = st.toggle("Include Other", value=False, key="photo_other")

            if section == "Wildlife":
                pool = df[df["event_type"] == "animal"]
                if not include_other:
                    pool = pool[pool["wildlife_label"] != "Other"]
                species_options = sorted(value for value in pool["wildlife_label"].unique().tolist() if value)
                species_filter = st.multiselect("Animals", species_options, key="photo_species")

        base = apply_common_filters(df, selected_cameras, date_range, temp_range, selected_moons)
        event_type = {"Wildlife": "animal", "People": "human", "Vehicles": "vehicle"}[section]
        base = base[base["event_type"] == event_type]
        if section == "Wildlife":
            if not include_other:
                base = base[base["wildlife_label"] != "Other"]
            if species_filter:
                base = base[base["wildlife_label"].isin(species_filter)]

        signature = (section, tuple(selected_cameras), str(date_range), temp_range, tuple(selected_moons), tuple(species_filter), include_other)
        if st.session_state.get("photo_filter_signature") != signature:
            st.session_state.photo_filter_signature = signature
            st.session_state.gallery_page = 1
            st.session_state.pop("gallery_page_input", None)

        st.markdown(f'<div class="gallery-summary"><span><strong>{len(base):,}</strong> matching sightings</span><span>Newest first</span></div>', unsafe_allow_html=True)
        render_listing_and_viewer(
            base=base,
            section=section,
            include_other=include_other,
            root_folder_id=ROOT_FOLDER_ID,
            drive_client_factory=_drive_client,
            download_bytes_func=_download_drive_file_bytes,
        )

    else:
        render_hero(
            "Event collections",
            "Open the advanced grouped gallery.",
            "Use the embedded gallery for grouped sightings and richer event-level browsing.",
            len(df),
            "events in the source dataset",
        )
        open_col, _ = st.columns([1, 3])
        with open_col:
            st.link_button("Open gallery in a new tab ↗", ADV_GALLERY_URL, width="stretch")
        st.markdown('<div class="embed-wrap">', unsafe_allow_html=True)
        st.components.v1.iframe(ADV_GALLERY_URL, height=1200, scrolling=True)
        st.markdown("</div>", unsafe_allow_html=True)


render_app_view()

st.markdown("---")
st.caption(f"Source: {raw.attrs.get('drive_name', 'events.csv')} · Updated {last_modified}")
