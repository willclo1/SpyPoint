# streamlit_app.py
import streamlit as st

from data_prep import nice_last_modified, prep_df
from drive_io import index_images_by_camera, load_events_from_drive, _drive_client, _download_drive_file_bytes
from ui_components import inject_css, render_patterns, render_timeline, render_listing_and_viewer


st.set_page_config(page_title="Ranch Activity", page_icon="🦌", layout="wide")
inject_css()

# Initialize session state
if "selected_event" not in st.session_state:
    st.session_state.selected_event = None
if "gallery_limit" not in st.session_state:
    st.session_state.gallery_limit = 8


def _require_secret(path: str):
    parts = path.split(".")
    cur = st.secrets
    for p in parts:
        if p not in cur:
            raise KeyError(f"Missing secret: {path}")
        cur = cur[p]
    return cur


DRIVE_FILE_ID = _require_secret("gdrive.file_id")
ROOT_FOLDER_ID = _require_secret("gdrive.root_folder_id")
CACHE_TTL_SECONDS = int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60))


# ---------------------------
# Load data + index images
# ---------------------------
with st.spinner("Loading events..."):
    raw = load_events_from_drive(DRIVE_FILE_ID)
df = prep_df(raw)

last_mod_pretty = nice_last_modified(raw.attrs.get("drive_modified", ""))

with st.spinner("Indexing photos..."):
    image_index = index_images_by_camera(ROOT_FOLDER_ID)

if not image_index:
    st.warning(
        "No camera folders found. Ensure `gdrive.root_folder_id` points to the folder containing camera subfolders."
    )


# ---------------------------
# TOP LEVEL TABS
# ---------------------------
tab1, tab2 = st.tabs(["Data Dashboard", "Photo Browser"])

with tab1:
    st.title("Ranch Activity Dashboard")
    st.caption("Wildlife, people, and vehicle monitoring system")
    
    st.success(f"Loaded **{len(df):,}** events • Last updated: **{last_mod_pretty}**")
    
    # ---------------------------
    # Sidebar filters
    # ---------------------------
    st.sidebar.header("Filters")
    section = st.sidebar.radio("Category", ["Wildlife", "People", "Vehicles"], index=0)

    camera_options = sorted([c for c in df["camera"].dropna().unique().tolist() if c])
    selected_cameras = st.sidebar.multiselect("Cameras", options=camera_options, default=camera_options) if camera_options else []

    valid_dt = df.dropna(subset=["datetime"])
    if valid_dt.empty:
        st.error("No valid date/time data found in events file")
        st.stop()

    min_dt = valid_dt["datetime"].min()
    max_dt = valid_dt["datetime"].max()

    date_range = st.sidebar.date_input(
        "Date Range",
        value=(min_dt.date(), max_dt.date()),
        min_value=min_dt.date(),
        max_value=max_dt.date(),
    )

    temp_series = valid_dt["temp_f"].dropna()
    temp_range = None
    if not temp_series.empty:
        tmin = int(temp_series.min())
        tmax = int(temp_series.max())
        if tmin == tmax:
            tmin -= 1
            tmax += 1
        temp_range = st.sidebar.slider("Temperature (°F)", min_value=tmin, max_value=tmax, value=(tmin, tmax))

    # Wildlife-only filters
    species_filter = []
    include_other = False
    bar_style = "Stacked"
    time_gran = "Hour"

    if section == "Wildlife":
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Wildlife Options**")
        include_other = st.sidebar.checkbox("Include 'Other'", value=False)
        bar_style = st.sidebar.radio("Chart Style", ["Stacked", "Grouped"], index=0)
        time_gran = st.sidebar.selectbox("Time Granularity", ["Hour", "2-hour", "4-hour"], index=0)

        wild_pool = df[df["event_type"] == "animal"].copy()
        if not include_other:
            wild_pool = wild_pool[wild_pool["wildlife_label"] != "Other"]

        sp_opts = sorted([s for s in wild_pool["wildlife_label"].unique().tolist() if s])
        if sp_opts:
            species_filter = st.sidebar.multiselect("Filter Animals", options=sp_opts, default=[])

    st.sidebar.markdown("---")
    st.sidebar.markdown(f'<div class="small-muted">Cache TTL: {CACHE_TTL_SECONDS//3600}h</div>', unsafe_allow_html=True)

    # ---------------------------
    # Apply filters
    # ---------------------------
    base = df.dropna(subset=["datetime"]).copy()

    if selected_cameras:
        base = base[base["camera"].isin(selected_cameras)]

    if section == "Wildlife":
        base = base[base["event_type"] == "animal"].copy()
        if not include_other:
            base = base[base["wildlife_label"] != "Other"]
    elif section == "People":
        base = base[base["event_type"] == "human"].copy()
    else:
        base = base[base["event_type"] == "vehicle"].copy()

    start, end = date_range
    base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]

    if temp_range is not None:
        lo, hi = temp_range
        base = base[base["temp_f"].notna()]
        base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]

    if section == "Wildlife" and species_filter:
        base = base[base["wildlife_label"].isin(species_filter)]

    if base.empty:
        st.info("No events match the current filters")
        st.stop()

    # ---------------------------
    # KPIs
    # ---------------------------
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Sightings", f"{len(base):,}")
    k2.metric("Date Range Start", str(start))
    k3.metric("Date Range End", str(end))

    st.markdown("---")

    # ---------------------------
    # Data Visualizations
    # ---------------------------
    render_timeline(base, section)
    st.markdown("---")
    render_patterns(base, section, include_other, bar_style, time_gran)
    
    # Footer
    st.divider()
    st.caption(
        f"Data source: {raw.attrs.get('drive_name','events.csv')} • "
        f"Updated: {last_mod_pretty} • "
        f"Cache: {CACHE_TTL_SECONDS//3600}h"
    )

with tab2:
    st.title("Photo Browser")
    st.caption("Browse and view individual sightings")
    
    # ---------------------------
    # Sidebar filters (reuse from tab1)
    # ---------------------------
    st.sidebar.header("Filters")
    section_photos = st.sidebar.radio("Category", ["Wildlife", "People", "Vehicles"], index=0, key="section_photos")

    camera_options_photos = sorted([c for c in df["camera"].dropna().unique().tolist() if c])
    selected_cameras_photos = st.sidebar.multiselect("Cameras", options=camera_options_photos, default=camera_options_photos, key="cameras_photos") if camera_options_photos else []

    valid_dt_photos = df.dropna(subset=["datetime"])
    if not valid_dt_photos.empty:
        min_dt_photos = valid_dt_photos["datetime"].min()
        max_dt_photos = valid_dt_photos["datetime"].max()

        date_range_photos = st.sidebar.date_input(
            "Date Range",
            value=(min_dt_photos.date(), max_dt_photos.date()),
            min_value=min_dt_photos.date(),
            max_value=max_dt_photos.date(),
            key="date_range_photos"
        )

        temp_series_photos = valid_dt_photos["temp_f"].dropna()
        temp_range_photos = None
        if not temp_series_photos.empty:
            tmin_photos = int(temp_series_photos.min())
            tmax_photos = int(temp_series_photos.max())
            if tmin_photos == tmax_photos:
                tmin_photos -= 1
                tmax_photos += 1
            temp_range_photos = st.sidebar.slider("Temperature (°F)", min_value=tmin_photos, max_value=tmax_photos, value=(tmin_photos, tmax_photos), key="temp_photos")

        # Wildlife-only filters
        species_filter_photos = []
        include_other_photos = False

        if section_photos == "Wildlife":
            st.sidebar.markdown("---")
            st.sidebar.markdown("**Wildlife Options**")
            include_other_photos = st.sidebar.checkbox("Include 'Other'", value=False, key="include_other_photos")

            wild_pool_photos = df[df["event_type"] == "animal"].copy()
            if not include_other_photos:
                wild_pool_photos = wild_pool_photos[wild_pool_photos["wildlife_label"] != "Other"]

            sp_opts_photos = sorted([s for s in wild_pool_photos["wildlife_label"].unique().tolist() if s])
            if sp_opts_photos:
                species_filter_photos = st.sidebar.multiselect("Filter Animals", options=sp_opts_photos, default=[], key="species_photos")

        # Apply filters for photos
        base_photos = df.dropna(subset=["datetime"]).copy()

        if selected_cameras_photos:
            base_photos = base_photos[base_photos["camera"].isin(selected_cameras_photos)]

        if section_photos == "Wildlife":
            base_photos = base_photos[base_photos["event_type"] == "animal"].copy()
            if not include_other_photos:
                base_photos = base_photos[base_photos["wildlife_label"] != "Other"]
        elif section_photos == "People":
            base_photos = base_photos[base_photos["event_type"] == "human"].copy()
        else:
            base_photos = base_photos[base_photos["event_type"] == "vehicle"].copy()

        start_photos, end_photos = date_range_photos
        base_photos = base_photos[(base_photos["datetime"].dt.date >= start_photos) & (base_photos["datetime"].dt.date <= end_photos)]

        if temp_range_photos is not None:
            lo_photos, hi_photos = temp_range_photos
            base_photos = base_photos[base_photos["temp_f"].notna()]
            base_photos = base_photos[(base_photos["temp_f"] >= lo_photos) & (base_photos["temp_f"] <= hi_photos)]

        if section_photos == "Wildlife" and species_filter_photos:
            base_photos = base_photos[base_photos["wildlife_label"].isin(species_filter_photos)]

        render_listing_and_viewer(
            base=base_photos,
            section=section_photos,
            include_other=include_other_photos,
            image_index=image_index,
            drive_client_factory=_drive_client,
            download_bytes_func=_download_drive_file_bytes,
        )
