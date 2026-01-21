# app.py
import streamlit as st

from data_prep import nice_last_modified, prep_df
from drive_io import index_images_by_camera, load_events_from_drive, _drive_client, _download_drive_file_bytes
from ui_components import inject_css, render_patterns, render_timeline, render_listing_and_viewer


st.set_page_config(page_title="Ranch Activity", page_icon="🦌", layout="wide")
inject_css()

st.title("Ranch Activity")
st.caption("Wildlife, people, and vehicles — separated. Select a sighting to view the photo.")


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
with st.spinner("Loading events…"):
    raw = load_events_from_drive(DRIVE_FILE_ID)
df = prep_df(raw)

last_mod_pretty = nice_last_modified(raw.attrs.get("drive_modified", ""))
st.success(f"Loaded **{len(df):,}** rows • Updated: **{last_mod_pretty}**")

with st.spinner("Indexing photos…"):
    image_index = index_images_by_camera(ROOT_FOLDER_ID)

if not image_index:
    st.warning(
        "No camera folders were found under your Drive root folder.\n\n"
        "Make sure `gdrive.root_folder_id` points to the folder that contains camera folders (gate/, feeder/, ravine/...)."
    )


# ---------------------------
# Sidebar filters
# ---------------------------
st.sidebar.header("Filters")
section = st.sidebar.radio("Section", ["Wildlife", "People", "Vehicles"], index=0)

camera_options = sorted([c for c in df["camera"].dropna().unique().tolist() if c])
selected_cameras = st.sidebar.multiselect("Camera", options=camera_options, default=camera_options) if camera_options else []

valid_dt = df.dropna(subset=["datetime"])
if valid_dt.empty:
    st.error("No usable date/time rows found in events.csv.")
    st.stop()

min_dt = valid_dt["datetime"].min()
max_dt = valid_dt["datetime"].max()

date_range = st.sidebar.date_input(
    "Date range",
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
    include_other = st.sidebar.checkbox("Include 'Other'", value=False)
    bar_style = st.sidebar.radio("Bar style", ["Stacked", "Grouped"], index=0)
    time_gran = st.sidebar.selectbox("Time granularity", ["Hour", "2-hour", "4-hour"], index=0)

    wild_pool = df[df["event_type"] == "animal"].copy()
    if not include_other:
        wild_pool = wild_pool[wild_pool["wildlife_label"] != "Other"]

    sp_opts = sorted([s for s in wild_pool["wildlife_label"].unique().tolist() if s])
    if sp_opts:
        species_filter = st.sidebar.multiselect("Animals", options=sp_opts, default=[])

st.sidebar.markdown(f"<div class='small-muted'>Cache: {CACHE_TTL_SECONDS//3600}h</div>", unsafe_allow_html=True)


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
    st.info("No sightings match your filters.")
    st.stop()


# ---------------------------
# KPIs
# ---------------------------
k1, k2, k3 = st.columns(3)
k1.metric("Sightings", f"{len(base):,}")
k2.metric("First day", str(start))
k3.metric("Last day", str(end))


# ---------------------------
# Layout
# ---------------------------
left, right = st.columns([2.2, 1])

with left:
    render_timeline(base, section)
    st.markdown("---")
    render_patterns(base, section, include_other, bar_style, time_gran)

with right:
    render_listing_and_viewer(
        base=base,
        section=section,
        include_other=include_other,
        image_index=image_index,
        drive_client_factory=_drive_client,
        download_bytes_func=_download_drive_file_bytes,
    )

st.divider()
st.caption(f"Source: {raw.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h")
