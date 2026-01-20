# streamlit_app.py
# Ranch Activity Dashboard (fresh structure)
# Drive root contains:
#   gate/ , feeder/ , ravine/ , events.csv
# CSV includes:
#   camera, filename, date, time, temp_f, event_type, species_clean, species_group, etc.

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


DRIVE_FILE_ID = _require_secret("gdrive.file_id")  # events.csv file id
ROOT_FOLDER_ID = _require_secret("gdrive.root_folder_id")  # Drive folder id that contains camera folders
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
    Ex: {"gate": "...", "feeder": "...", "ravine": "..."}
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
      root/<camera>/<filename>
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
# Cleaning / parsing helpers
# ---------------------------
def nice_last_modified(iso: str) -> str:
    if not iso:
        return "?"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso


def clamp_temp_domain(min_v, max_v) -> Tuple[float, float]:
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
    return pd.to_datetime((date_s + " " + time_s).str.strip(), errors="coerce")


def prep_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trust the pipeline CSV columns:
      - event_type
      - species_clean (normalized)
      - species_group (ranch-friendly grouping)

    Rule:
      - Wildlife: "Other" is unimportant (hide by default via toggle)
      - People/Vehicles: always shown
    """
    out = df.copy()

    for col in ["camera", "filename", "event_type", "species_clean", "species_group", "date", "time", "temp_f"]:
        if col not in out.columns:
            out[col] = ""

    out["camera"] = out["camera"].fillna("").astype(str).str.strip()
    out["filename"] = out["filename"].fillna("").astype(str).str.strip()

    out["event_type"] = (
        out["event_type"].fillna("").astype(str).str.strip().str.lower()
        .replace({"person": "human", "people": "human"})
    )

    out["temp_f"] = pd.to_numeric(out["temp_f"], errors="coerce")
    out["datetime"] = build_datetime(out)

    # Keep display strings as pipeline intended
    out["species_clean"] = out["species_clean"].fillna("").astype(str).str.strip()
    out["species_group"] = out["species_group"].fillna("").astype(str).str.strip()

    # Wildlife label preference: group -> clean -> Other
    out["wildlife_label"] = out["species_group"]
    out.loc[out["wildlife_label"] == "", "wildlife_label"] = out["species_clean"]
    out.loc[out["wildlife_label"] == "", "wildlife_label"] = "Other"

    return out


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
        "Make sure `gdrive.root_folder_id` points to the folder that contains your camera folders (gate/, feeder/, ravine/...)."
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

# Datetime range (only rows with usable datetime)
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

# camera filter
if selected_cameras:
    base = base[base["camera"].isin(selected_cameras)]

# section filter
if section == "Wildlife":
    base = base[base["event_type"] == "animal"].copy()
    if not include_other:
        base = base[base["wildlife_label"] != "Other"]
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

# wildlife animal filter
if section == "Wildlife" and species_filter:
    base = base[base["wildlife_label"].isin(species_filter)]

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
            counts = chart_df.groupby("wildlife_label").size().sort_values(ascending=False)
            top = counts.head(10).index.tolist()
            chart_df["wildlife_group_chart"] = chart_df["wildlife_label"].where(
                chart_df["wildlife_label"].isin(top),
                other="Other",
            )

            color_enc = alt.Color("wildlife_group_chart:N", title="Animal")
            tooltip = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("wildlife_label:N", title="Animal"),
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

    patt["hour"] = patt["datetime"].dt.hour
    if time_gran == "2-hour":
        patt["time_bin"] = (patt["hour"] // 2) * 2
        patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
    elif time_gran == "4-hour":
        patt["time_bin"] = (patt["hour"] // 4) * 4
        patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
    else:
        patt["time_label"] = patt["hour"].astype(int).astype(str) + ":00"

    if section == "Wildlife":
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

        if bar_style == "Grouped":
            time_chart = (
                alt.Chart(by_time)
                .mark_bar()
                .encode(
                    x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Sightings:Q", title="Sightings"),
                    color=alt.Color("animal_group:N", title="Animal"),
                    xOffset="animal_group:N",
                    tooltip=[
                        alt.Tooltip("time_label:N", title="Time"),
                        alt.Tooltip("animal_group:N", title="Animal"),
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
                    color=alt.Color("animal_group:N", title="Animal"),
                    tooltip=[
                        alt.Tooltip("time_label:N", title="Time"),
                        alt.Tooltip("animal_group:N", title="Animal"),
                        alt.Tooltip("Sightings:Q", title="Sightings"),
                    ],
                )
            )

        by_day = patt.groupby(["weekday", "animal_group"]).size().reset_index(name="Sightings")
        by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)
        by_day = by_day.sort_values(["weekday", "animal_group"])

        if bar_style == "Grouped":
            day_chart = (
                alt.Chart(by_day)
                .mark_bar()
                .encode(
                    y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                    x=alt.X("Sightings:Q", title="Sightings"),
                    color=alt.Color("animal_group:N", title="Animal"),
                    yOffset="animal_group:N",
                    tooltip=[
                        alt.Tooltip("weekday:N", title="Day"),
                        alt.Tooltip("animal_group:N", title="Animal"),
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
                    color=alt.Color("animal_group:N", title="Animal"),
                    tooltip=[
                        alt.Tooltip("weekday:N", title="Day"),
                        alt.Tooltip("animal_group:N", title="Animal"),
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
            animal = (r.get("wildlife_label") or "Other").strip()
            return f"{when} • {cam} • {animal} • {t}"
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
        st.markdown(f"**Animal:** {row.get('wildlife_label') or 'Other'}")

    st.markdown(f"**File:** `{fn}`")

    if url:
        st.link_button("Open in Google Drive", url)
    else:
        st.warning(
            "Photo link not found in Drive.\n\n"
            "Checklist:\n"
            "• Does the file exist at root/{camera}/{filename}?\n"
            "• Did you share the root folder with the service account?\n"
            "• Is `gdrive.root_folder_id` set to that root folder ID?"
        )

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
        show_cols.insert(3, "wildlife_label")

    show_cols = [c for c in show_cols if c in view.columns]
    st.dataframe(view[show_cols], width="stretch", hide_index=True)

st.divider()
st.caption(f"Source: {raw.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h")
