# streamlit_app.py
# Ranch Activity Dashboard (fresh structure)
# Drive root contains:
#   feeder/ , gate/ , events.csv
# CSV includes `camera` column and `filename`

import io
from datetime import datetime
from typing import Dict, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ---------------------------
# Page config + polish
# ---------------------------
st.set_page_config(page_title="Ranch Activity", page_icon="🦌", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 2.5rem; max-width: 1180px; }
      h1, h2, h3 { letter-spacing: -0.02em; }
      .small-muted { opacity: 0.75; font-size: 0.92rem; }
      .card {
        padding: 1rem 1.1rem;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.10);
        background: rgba(255,255,255,0.03);
      }
      div[data-testid="stMetricValue"] { font-size: 1.6rem; }
      div[data-testid="stMetricLabel"] { font-size: 0.95rem; opacity: 0.75; }
      .stDataFrame { border-radius: 14px; overflow: hidden; }
      .stAlert { border-radius: 14px; }
      section[data-testid="stSidebar"] { padding-top: 1rem; }
      button[kind="secondary"], button[kind="primary"] { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Activity")
st.caption("Wildlife, people, and vehicles — separated. Select a sighting to view the photo.")


# ---------------------------
# Secrets / settings
# ---------------------------
def _require_secret(path: str):
    parts = path.split(".")
    cur = st.secrets
    for p in parts:
        if p not in cur:
            raise KeyError(f"Missing secret: {path}")
        cur = cur[p]
    return cur


DRIVE_FILE_ID = _require_secret("gdrive.file_id")                 # events.csv file id
ROOT_FOLDER_ID = _require_secret("gdrive.root_folder_id")         # Incoming folder id
CACHE_TTL_SECONDS = int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60))


# ---------------------------
# Google Drive helpers
# ---------------------------
def _drive_client():
    creds_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _download_drive_file_bytes(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()


def drive_view_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_events_from_drive(file_id: str) -> pd.DataFrame:
    service = _drive_client()
    meta = service.files().get(fileId=file_id, fields="name,modifiedTime,size").execute()
    raw = _download_drive_file_bytes(service, file_id)
    df = pd.read_csv(io.BytesIO(raw))
    df.attrs["drive_name"] = meta.get("name", "events.csv")
    df.attrs["drive_modified"] = meta.get("modifiedTime", "")
    df.attrs["drive_size"] = meta.get("size", "")
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def list_camera_folders(root_folder_id: str) -> Dict[str, str]:
    """
    Returns mapping: {folder_name: folder_id} for immediate child folders.
    Ex: {"gate": "...", "feeder": "..."}
    """
    service = _drive_client()
    q = f"'{root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    fields = "files(id,name)"
    resp = service.files().list(q=q, fields=fields, pageSize=1000).execute()
    out = {}
    for f in resp.get("files", []):
        name = (f.get("name") or "").strip()
        fid = (f.get("id") or "").strip()
        if name and fid:
            out[name] = fid
    return out


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def index_images_by_camera(root_folder_id: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Builds:
      image_index[camera][filename] = {"id": <file_id>, "webViewLink": <link>}
    by listing each camera folder once.
    """
    service = _drive_client()
    cam_folders = list_camera_folders(root_folder_id)
    image_index: Dict[str, Dict[str, Dict[str, str]]] = {}

    for cam_name, cam_folder_id in cam_folders.items():
        image_index[cam_name] = {}
        page_token = None
        fields = "nextPageToken, files(id,name,webViewLink,trashed,mimeType)"

        # list all files in that camera folder (no recursion needed for your structure)
        q = f"'{cam_folder_id}' in parents and trashed=false"
        while True:
            resp = (
                service.files()
                .list(q=q, fields=fields, pageToken=page_token, pageSize=1000)
                .execute()
            )
            for f in resp.get("files", []):
                name = (f.get("name") or "").strip()
                fid = (f.get("id") or "").strip()
                link = (f.get("webViewLink") or "").strip()
                if not name or not fid:
                    continue
                # only index common image types (avoid accidentally indexing csv/tsv/etc)
                mt = (f.get("mimeType") or "")
                if mt.startswith("image/") or name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    image_index[cam_name][name] = {
                        "id": fid,
                        "webViewLink": link or drive_view_url(fid),
                    }

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return image_index


def resolve_image_link(camera: str, filename: str, image_index: dict) -> Tuple[str, str]:
    """
    Returns (url, file_id) using Drive traversal:
      Incoming/<camera>/<filename>
    """
    camera = (camera or "").strip()
    filename = (filename or "").strip()
    if not camera or not filename:
        return "", ""

    cam_map = image_index.get(camera, {})
    hit = cam_map.get(filename)
    if not hit:
        return "", ""
    return hit.get("webViewLink", ""), hit.get("id", "")


# ---------------------------
# Cleaning helpers
# ---------------------------
def nice_last_modified(iso: str) -> str:
    if not iso:
        return "?"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso


def clamp_temp_domain(min_v, max_v) -> Tuple[float, float]:
    # Always show at least 10–90 for clear scaling
    try:
        min_v = float(min_v)
    except Exception:
        min_v = 10.0
    try:
        max_v = float(max_v)
    except Exception:
        max_v = 90.0

    lo = min(10.0, min_v)
    hi = max(90.0, max_v)
    if hi - lo < 20:
        mid = (hi + lo) / 2
        lo = mid - 10
        hi = mid + 10
    return lo, hi


def build_datetime(df: pd.DataFrame) -> pd.Series:
    date_s = df.get("date", pd.Series([""] * len(df))).astype(str).fillna("").str.strip()
    time_s = df.get("time", pd.Series([""] * len(df))).astype(str).fillna("").str.strip()
    # Your format looks like: 01/18/2026 + 03:57 PM
    # Let pandas parse; errors coerced to NaT
    return pd.to_datetime((date_s + " " + time_s).str.strip(), errors="coerce")


def normalize_section_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardizes key columns and applies your rules:
      - ignore domestic dog in wildlife views
      - species == "animal" treated as Other (generic)
    """
    out = df.copy()

    # Ensure columns exist
    for col in ["camera", "filename", "event_type", "species", "date", "time"]:
        if col not in out.columns:
            out[col] = ""

    out["camera"] = out["camera"].fillna("").astype(str).str.strip()
    out["filename"] = out["filename"].fillna("").astype(str).str.strip()
    out["event_type"] = out["event_type"].fillna("").astype(str).str.strip().str.lower()
    out["species"] = out["species"].fillna("").astype(str).str.strip().str.lower()

    # temp
    out["temp_f"] = pd.to_numeric(out.get("temp_f", pd.Series([pd.NA] * len(out))), errors="coerce")

    # datetime
    out["datetime"] = build_datetime(out)

    # Clean up species for wildlife charts:
    # - drop domestic dog (we'll filter it out in wildlife section)
    # - map generic 'animal' to 'other'
    out["species_clean"] = out["species"].replace({"animal": "other"})
    out.loc[out["species_clean"] == "", "species_clean"] = "other"

    # Human/vehicle shouldn't show up as "species" in wildlife
    out.loc[out["event_type"].isin(["human", "vehicle"]), "species_clean"] = out["event_type"]

    return out


# ---------------------------
# Load data + index images
# ---------------------------
with st.spinner("Loading events…"):
    raw = load_events_from_drive(DRIVE_FILE_ID)

df = normalize_section_filters(raw)

last_mod_pretty = nice_last_modified(raw.attrs.get("drive_modified", ""))
st.success(f"Loaded **{len(df):,}** rows • Updated: **{last_mod_pretty}**")

# Only index images if we have a root folder id (we do) — cached
with st.spinner("Indexing photos…"):
    image_index = index_images_by_camera(ROOT_FOLDER_ID)

# Validate at least one camera folder indexed
if not image_index:
    st.warning(
        "No camera folders were found under your Drive root folder.\n\n"
        "Make sure `gdrive.root_folder_id` points to the folder that contains `gate/` and `feeder/`."
    )


# ---------------------------
# Sidebar filters
# ---------------------------
st.sidebar.header("Filters")

section = st.sidebar.radio("Section", ["Wildlife", "People", "Vehicles"], index=0)

# Camera filter
camera_options = sorted([c for c in df["camera"].dropna().unique().tolist() if c])
if camera_options:
    selected_cameras = st.sidebar.multiselect("Camera", options=camera_options, default=camera_options)
else:
    selected_cameras = []

# Valid datetime rows only for date range
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

# Temperature filter
temp_series = valid_dt["temp_f"].dropna()
temp_range = None
if not temp_series.empty:
    tmin = int(temp_series.min())
    tmax = int(temp_series.max())
    if tmin == tmax:
        tmin -= 1
        tmax += 1
    temp_range = st.sidebar.slider("Temperature (°F)", min_value=tmin, max_value=tmax, value=(tmin, tmax))

# Wildlife-only species filter (uses cleaned species)
species_filter = []
bar_style = "Stacked"
time_gran = "Hour"

if section == "Wildlife":
    bar_style = st.sidebar.radio("Bar style", ["Stacked", "Grouped"], index=0)
    time_gran = st.sidebar.selectbox("Time granularity", ["Hour", "2-hour", "4-hour"], index=0)

    wild_pool = df[df["event_type"] == "animal"].copy()
    wild_pool = wild_pool[wild_pool["species_clean"].ne("domestic dog")]  # ignore dogs
    sp_opts = sorted([s for s in wild_pool["species_clean"].unique().tolist() if s and s not in ("human", "vehicle")])
    if sp_opts:
        species_filter = st.sidebar.multiselect("Species", options=sp_opts, default=[])

st.sidebar.markdown(f"<div class='small-muted'>Cache: {CACHE_TTL_SECONDS//3600}h</div>", unsafe_allow_html=True)


# ---------------------------
# Apply filters
# ---------------------------
base = df.dropna(subset=["datetime"]).copy()

# camera filter
if selected_cameras:
    base = base[base["camera"].isin(selected_cameras)]

# section filter
if section == "Wildlife":
    base = base[base["event_type"] == "animal"].copy()
    base = base[base["species_clean"].ne("domestic dog")]  # ignore dogs
elif section == "People":
    base = base[base["event_type"] == "human"].copy()
else:
    base = base[base["event_type"] == "vehicle"].copy()

# date filter
start, end = date_range
base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]

# temp filter
if temp_range is not None:
    lo, hi = temp_range
    base = base[base["temp_f"].notna()]
    base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]
else:
    lo, hi = 10, 90

# wildlife species filter
if section == "Wildlife" and species_filter:
    base = base[base["species_clean"].isin(species_filter)]

if base.empty:
    st.info("No sightings match your filters.")
    st.stop()

Y_LO, Y_HI = clamp_temp_domain(base["temp_f"].min(), base["temp_f"].max())


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
    st.subheader("Timeline")
    st.caption("Each dot is one sighting.")

    chart_df = base.dropna(subset=["datetime", "temp_f"]).copy()
    if chart_df.empty:
        st.info("No temperature data available for charting.")
    else:
        if section == "Wildlife":
            # Keep legend readable: top species + Other
            counts = chart_df.groupby("species_clean").size().sort_values(ascending=False)
            top = counts.head(10).index.tolist()
            chart_df["species_group"] = chart_df["species_clean"].where(chart_df["species_clean"].isin(top), other="other")

            color_enc = alt.Color("species_group:N", title="Species")
            tooltip = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("species_clean:N", title="Species"),
                alt.Tooltip("camera:N", title="Camera"),
                alt.Tooltip("filename:N", title="File"),
            ]
        else:
            chart_df["type_label"] = section.lower()
            color_enc = alt.Color("type_label:N", legend=None)
            tooltip = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("camera:N", title="Camera"),
                alt.Tooltip("filename:N", title="File"),
            ]

        scatter = (
            alt.Chart(chart_df)
            .mark_circle(size=240, opacity=0.86)
            .encode(
                x=alt.X("datetime:T", title="Time"),
                y=alt.Y("temp_f:Q", title="Temperature (°F)", scale=alt.Scale(domain=[Y_LO, Y_HI])),
                color=color_enc,
                tooltip=tooltip,
            )
            .interactive()
        )
        st.altair_chart(scatter, width="stretch")

    st.markdown("---")
    st.subheader("Patterns")

    patt = base.dropna(subset=["datetime"]).copy()
    patt["weekday"] = patt["datetime"].dt.day_name()
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # Time binning
    patt["hour"] = patt["datetime"].dt.hour
    if section == "Wildlife":
        if time_gran == "2-hour":
            patt["time_bin"] = (patt["hour"] // 2) * 2
            patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
        elif time_gran == "4-hour":
            patt["time_bin"] = (patt["hour"] // 4) * 4
            patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
        else:
            patt["time_label"] = patt["hour"].astype(int).astype(str) + ":00"
    else:
        patt["time_label"] = patt["hour"].astype(int).astype(str) + ":00"

    if section == "Wildlife":
        # group species for readable bars
        sp_counts = patt.groupby("species_clean").size().sort_values(ascending=False)
        top_species = sp_counts.head(8).index.tolist()
        patt["species_group"] = patt["species_clean"].where(patt["species_clean"].isin(top_species), other="other")

        # ---- By time of day
        by_time = (
            patt.groupby(["time_label", "species_group"])
            .size()
            .reset_index(name="Sightings")
        )

        # ensure time order
        def _time_sort_key(x: str) -> int:
            try:
                return int(x.split(":")[0])
            except Exception:
                return 0

        time_order = sorted(by_time["time_label"].unique().tolist(), key=_time_sort_key)

        if bar_style == "Grouped":
            time_chart = (
                alt.Chart(by_time)
                .mark_bar()
                .encode(
                    x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Sightings:Q", title="Sightings"),
                    color=alt.Color("species_group:N", title="Species"),
                    xOffset="species_group:N",
                    tooltip=[
                        alt.Tooltip("time_label:N", title="Time"),
                        alt.Tooltip("species_group:N", title="Species"),
                        alt.Tooltip("Sightings:Q", title="Sightings"),
                    ],
                )
            )
        else:
            time_chart = (
                alt.Chart(by_time)
                .mark_bar()
                .encode(
                    x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Sightings:Q", title="Sightings"),
                    color=alt.Color("species_group:N", title="Species"),
                    tooltip=[
                        alt.Tooltip("time_label:N", title="Time"),
                        alt.Tooltip("species_group:N", title="Species"),
                        alt.Tooltip("Sightings:Q", title="Sightings"),
                    ],
                )
            )

        # ---- By weekday
        by_day = (
            patt.groupby(["weekday", "species_group"])
            .size()
            .reset_index(name="Sightings")
        )
        by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)
        by_day = by_day.sort_values(["weekday", "species_group"])

        if bar_style == "Grouped":
            day_chart = (
                alt.Chart(by_day)
                .mark_bar()
                .encode(
                    y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                    x=alt.X("Sightings:Q", title="Sightings"),
                    color=alt.Color("species_group:N", title="Species"),
                    yOffset="species_group:N",
                    tooltip=[
                        alt.Tooltip("weekday:N", title="Day"),
                        alt.Tooltip("species_group:N", title="Species"),
                        alt.Tooltip("Sightings:Q", title="Sightings"),
                    ],
                )
            )
        else:
            day_chart = (
                alt.Chart(by_day)
                .mark_bar()
                .encode(
                    y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                    x=alt.X("Sightings:Q", title="Sightings"),
                    color=alt.Color("species_group:N", title="Species"),
                    tooltip=[
                        alt.Tooltip("weekday:N", title="Day"),
                        alt.Tooltip("species_group:N", title="Species"),
                        alt.Tooltip("Sightings:Q", title="Sightings"),
                    ],
                )
            )

        cA, cB = st.columns(2)
        with cA:
            st.markdown("**Time of day**")
            st.altair_chart(time_chart, width="stretch")
        with cB:
            st.markdown("**Day of week**")
            st.altair_chart(day_chart, width="stretch")

    else:
        # People/Vehicles: simple counts
        by_time = patt.groupby("time_label").size().reset_index(name="Sightings")
        # ensure time order
        by_time["__h"] = by_time["time_label"].str.split(":").str[0].astype(int)
        by_time = by_time.sort_values("__h")

        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=by_time["time_label"].tolist(), axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("time_label:N", title="Time"), alt.Tooltip("Sightings:Q", title="Sightings")],
            )
        )

        by_day = patt.groupby("weekday").size().reindex(weekday_order, fill_value=0).reset_index(name="Sightings")
        by_day.columns = ["weekday", "Sightings"]

        day_chart = (
            alt.Chart(by_day)
            .mark_bar()
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("weekday:N", title="Day"), alt.Tooltip("Sightings:Q", title="Sightings")],
            )
        )

        cA, cB = st.columns(2)
        with cA:
            st.markdown("**Time of day**")
            st.altair_chart(time_chart, width="stretch")
        with cB:
            st.markdown("**Day of week**")
            st.altair_chart(day_chart, width="stretch")


with right:
    st.subheader("Photo Viewer")

    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    def _row_label(r):
        when = r["datetime"].strftime("%b %d • %I:%M %p")
        t = f"{int(round(r['temp_f']))}°F" if pd.notna(r.get("temp_f")) else "—"
        cam = (r.get("camera") or "").strip() or "unknown"
        if section == "Wildlife":
            spec = (r.get("species_clean") or "other").strip()
            return f"{when} • {cam} • {spec} • {t}"
        return f"{when} • {cam} • {section} • {t}"

    view["label"] = view.apply(_row_label, axis=1)

    chosen_idx = st.selectbox(
        "Select a sighting",
        options=view.index.tolist(),
        format_func=lambda i: view.loc[i, "label"],
    )

    row = view.loc[chosen_idx]
    cam = str(row.get("camera", "")).strip()
    fn = str(row.get("filename", "")).strip()
    url, fid = resolve_image_link(cam, fn, image_index)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"**Camera:** {cam or '—'}")
    st.markdown(f"**When:** {row.get('datetime')}")
    if pd.notna(row.get("temp_f")):
        st.markdown(f"**Temperature:** {int(round(float(row.get('temp_f'))))} °F")
    else:
        st.markdown("**Temperature:** —")

    if section == "Wildlife":
        st.markdown(f"**Species:** {row.get('species_clean') or 'other'}")

    st.markdown(f"**File:** `{fn}`")

    if url:
        st.link_button("Open in Google Drive", url)
    else:
        st.warning(
            "Photo link not found in Drive.\n\n"
            "Checklist:\n"
            "• Does the file exist at Incoming/{camera}/{filename}?\n"
            "• Did you share the Incoming folder with the service account?\n"
            "• Is `gdrive.root_folder_id` set to the Incoming folder ID?"
        )

    # Inline preview (optional)
    if fid and st.toggle("Show preview", value=True):
        try:
            service = _drive_client()
            img_bytes = _download_drive_file_bytes(service, fid)
            st.image(img_bytes, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Table")

    show_cols = ["datetime", "camera", "temp_f", "filename"]
    if section == "Wildlife":
        show_cols.insert(3, "species_clean")

    show_cols = [c for c in show_cols if c in view.columns]
    st.dataframe(view[show_cols], width="stretch", hide_index=True)

st.divider()
st.caption(f"Source: {raw.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h")
