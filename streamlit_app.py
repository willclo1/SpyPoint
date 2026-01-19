# streamlit_app.py
# Ranch Activity Dashboard — camera-aware Drive indexing (images/<camera>/<file>)

import io
from datetime import datetime

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


DRIVE_FILE_ID = _require_secret("gdrive.file_id")
ROOT_FOLDER_ID = (st.secrets.get("gdrive", {}).get("root_folder_id") or "").strip()
IMAGES_FOLDER_ID = (st.secrets.get("gdrive", {}).get("images_folder_id") or "").strip()  # optional fallback
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


def _list_all(service, q: str, fields: str, page_size: int = 1000) -> list[dict]:
    out = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(q=q, fields=f"nextPageToken,{fields}", pageToken=page_token, pageSize=page_size)
            .execute()
        )
        out.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def build_image_index_from_root(root_folder_id: str) -> dict:
    """
    Builds dict keyed by (camera, filename):
      { "feeder::IMG.jpg": {"id": "...", "webViewLink": "..."} }

    Expected Drive layout:
      <root>/
        images/
          feeder/
            *.jpg
          gate/
            *.jpg
    """
    if not root_folder_id:
        return {}

    service = _drive_client()

    # Find images/ folder under root
    images_folder_q = (
        f"'{root_folder_id}' in parents and trashed=false and "
        "mimeType='application/vnd.google-apps.folder' and name='images'"
    )
    images_folders = _list_all(service, images_folder_q, "files(id,name)")
    if not images_folders:
        return {}  # root set but no images folder found
    images_folder_id = images_folders[0]["id"]

    # List camera subfolders under images/
    cam_folder_q = (
        f"'{images_folder_id}' in parents and trashed=false and "
        "mimeType='application/vnd.google-apps.folder'"
    )
    cam_folders = _list_all(service, cam_folder_q, "files(id,name)")
    if not cam_folders:
        return {}

    index = {}

    # For each camera folder, list image files
    for cf in cam_folders:
        cam_name = (cf.get("name") or "").strip()
        cam_id = cf.get("id")
        if not cam_name or not cam_id:
            continue

        files_q = f"'{cam_id}' in parents and trashed=false"
        files = _list_all(service, files_q, "files(id,name,webViewLink,mimeType)")
        for f in files:
            name = (f.get("name") or "").strip()
            if not name:
                continue
            # only keep likely images (still okay if Drive doesn't set mimeType perfectly)
            mt = (f.get("mimeType") or "").lower()
            if "folder" in mt:
                continue

            key = f"{cam_name}::{name}"
            index[key] = {
                "id": f.get("id", ""),
                "webViewLink": f.get("webViewLink", "") or drive_view_url(f.get("id", "")),
            }

    return index


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def list_images_in_folder_flat(folder_id: str) -> dict:
    """
    Flat fallback: { filename: {id, webViewLink} }
    """
    if not folder_id:
        return {}
    service = _drive_client()
    out = {}
    files_q = f"'{folder_id}' in parents and trashed=false"
    files = _list_all(service, files_q, "files(id,name,webViewLink,mimeType)")
    for f in files:
        name = (f.get("name") or "").strip()
        if name:
            out[name] = {
                "id": f.get("id", ""),
                "webViewLink": f.get("webViewLink", "") or drive_view_url(f.get("id", "")),
            }
    return out


def resolve_image_link(row: pd.Series, image_index: dict, flat_index: dict) -> tuple[str, str]:
    """
    Returns (url, file_id)

    Priority:
      1) image_url column (if present)
      2) image_drive_id column (if present)
      3) nested index (camera::filename)
      4) flat index (filename only)
    """
    if "image_url" in row.index and str(row.get("image_url", "")).strip():
        return str(row["image_url"]).strip(), ""

    if "image_drive_id" in row.index and str(row.get("image_drive_id", "")).strip():
        fid = str(row["image_drive_id"]).strip()
        return drive_view_url(fid), fid

    camera = str(row.get("camera", "") or "").strip()
    filename = str(row.get("filename", "") or "").strip()

    if camera and filename:
        key = f"{camera}::{filename}"
        if key in image_index:
            fid = image_index[key].get("id", "")
            url = image_index[key].get("webViewLink", "") or (drive_view_url(fid) if fid else "")
            return url, fid

    if filename and filename in flat_index:
        fid = flat_index[filename].get("id", "")
        url = flat_index[filename].get("webViewLink", "") or (drive_view_url(fid) if fid else "")
        return url, fid

    return "", ""


# ---------------------------
# Cleaning helpers
# ---------------------------
def _after_last_semicolon(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    if not s:
        return ""
    parts = [p.strip() for p in s.split(";") if p.strip()]
    return parts[-1] if parts else s


def normalize_species(raw: str) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none"):
        return ""
    low = s.lower()
    if "vehicle" in low:
        return "vehicle"
    if "human" in low or "person" in low:
        return "human"
    return _after_last_semicolon(s)


def normalize_event_type(raw: str) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().lower()
    if s in ("", "blank", "none", "nan"):
        return ""
    if s == "person":
        return "human"
    return s


def build_datetime(df: pd.DataFrame) -> pd.Series:
    date_s = df.get("date", pd.Series([""] * len(df))).astype(str).fillna("")
    time_s = df.get("time", pd.Series([""] * len(df))).astype(str).fillna("")
    return pd.to_datetime((date_s + " " + time_s).str.strip(), errors="coerce")


def clamp_temp_domain(min_v: float, max_v: float) -> tuple[float, float]:
    lo = 10.0 if pd.isna(min_v) else min(10.0, float(min_v))
    hi = 90.0 if pd.isna(max_v) else max(90.0, float(max_v))
    if hi - lo < 20:
        mid = (hi + lo) / 2
        lo = mid - 10
        hi = mid + 10
    return lo, hi


def nice_last_modified(iso: str) -> str:
    if not iso:
        return "?"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso


# ---------------------------
# Load data
# ---------------------------
with st.spinner("Loading events…"):
    df = load_events_from_drive(DRIVE_FILE_ID)

last_mod_pretty = nice_last_modified(df.attrs.get("drive_modified", ""))

# Normalize columns we rely on
for col in ["camera", "date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)
    else:
        df[col] = ""

df["temp_f"] = pd.to_numeric(df.get("temp_f", pd.Series([pd.NA] * len(df))), errors="coerce")

df["event_type"] = df["event_type"].map(normalize_event_type)
df["species"] = df["species"].map(normalize_species)
df["datetime"] = build_datetime(df)

# Derive event_type if missing (just in case)
def _derive_type(row):
    et = str(row.get("event_type", "")).strip().lower()
    if et in ("animal", "human", "vehicle"):
        return et
    sp = str(row.get("species", "")).strip().lower()
    if sp == "human":
        return "human"
    if sp == "vehicle":
        return "vehicle"
    if sp:
        return "animal"
    return ""

df["event_type"] = df.apply(_derive_type, axis=1)

valid = df.dropna(subset=["datetime"]).copy()
if valid.empty:
    st.error("No usable date/time data found in events.csv.")
    st.stop()

# Build image indexes
image_index = {}
flat_index = {}

if ROOT_FOLDER_ID:
    with st.spinner("Indexing photos (by camera)…"):
        image_index = build_image_index_from_root(ROOT_FOLDER_ID)
elif IMAGES_FOLDER_ID:
    with st.spinner("Indexing photos…"):
        flat_index = list_images_in_folder_flat(IMAGES_FOLDER_ID)

st.success(f"Loaded **{len(df):,}** sightings • Updated: **{last_mod_pretty}**")


# ---------------------------
# Sidebar filters
# ---------------------------
st.sidebar.header("Filters")

section = st.sidebar.radio("Section", options=["Wildlife", "People", "Vehicles"], index=0)

# Camera filter (works in all sections)
all_cams = sorted([c for c in valid["camera"].unique().tolist() if str(c).strip()])
camera_filter = st.sidebar.multiselect("Camera", options=all_cams, default=[])

min_dt = valid["datetime"].min()
max_dt = valid["datetime"].max()

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_dt.date(), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date(),
)

temp_series = valid["temp_f"].dropna()
temp_range = None
if not temp_series.empty:
    tmin = int(temp_series.min())
    tmax = int(temp_series.max())
    if tmin == tmax:
        tmin -= 1
        tmax += 1
    temp_range = st.sidebar.slider("Temperature (°F)", min_value=tmin, max_value=tmax, value=(tmin, tmax))

# Wildlife-only species filter
species_filter = []
if section == "Wildlife":
    wild = valid[valid["event_type"] == "animal"].copy()
    if camera_filter:
        wild = wild[wild["camera"].isin(camera_filter)]
    wild_species = sorted(
        s for s in wild["species"].dropna().astype(str).unique().tolist()
        if s and s not in ("human", "vehicle")
    )
    if wild_species:
        species_filter = st.sidebar.multiselect("Species", options=wild_species, default=[])

st.sidebar.markdown(f"<div class='small-muted'>Cache: {CACHE_TTL_SECONDS//3600}h</div>", unsafe_allow_html=True)


# ---------------------------
# Apply filters
# ---------------------------
base = df.dropna(subset=["datetime"]).copy()

# Section purity
if section == "Wildlife":
    base = base[base["event_type"] == "animal"]
elif section == "People":
    base = base[base["event_type"] == "human"]
else:
    base = base[base["event_type"] == "vehicle"]

# Camera filter
if camera_filter:
    base = base[base["camera"].isin(camera_filter)]

# Date filter
start, end = date_range
base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]

# Temp filter
if temp_range is not None:
    lo, hi = temp_range
    base = base[base["temp_f"].notna()]
    base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]
else:
    lo, hi = 10, 90

# Species filter (wildlife only)
if section == "Wildlife" and species_filter:
    base = base[base["species"].isin(species_filter)]

if base.empty:
    st.info("No sightings match your filters.")
    st.stop()

temp_min = base["temp_f"].min() if base["temp_f"].notna().any() else 10
temp_max = base["temp_f"].max() if base["temp_f"].notna().any() else 90
Y_LO, Y_HI = clamp_temp_domain(temp_min, temp_max)

DOT_SIZE = 240
OPACITY = 0.86


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
left, right = st.columns([2.15, 1])

with left:
    st.subheader("Activity Over Time")
    st.caption("Each dot is one sighting. Temperature is in °F.")

    chart_df = base.dropna(subset=["datetime", "temp_f"]).copy()
    if chart_df.empty:
        st.info("No temperature data available for charting.")
    else:
        if section == "Wildlife":
            counts = (
                chart_df[chart_df["species"] != ""]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
            )
            top_species = counts.head(10).index.tolist()
            chart_df["species_group"] = chart_df["species"].where(chart_df["species"].isin(top_species), other="Other")
            color_enc = alt.Color("species_group:N", title="Species")
            tooltip = [
                alt.Tooltip("camera:N", title="Camera"),
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("species:N", title="Species"),
                alt.Tooltip("filename:N", title="File"),
            ]
        else:
            chart_df["group"] = section
            color_enc = alt.Color("group:N", legend=None)
            tooltip = [
                alt.Tooltip("camera:N", title="Camera"),
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("filename:N", title="File"),
            ]

        scatter = (
            alt.Chart(chart_df)
            .mark_circle(size=DOT_SIZE, opacity=OPACITY)
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
    patt["hour"] = patt["datetime"].dt.hour
    patt["weekday"] = patt["datetime"].dt.day_name()

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    if section == "Wildlife":
        st.caption("Bars are split by species (stacked) so you can see what makes up each hour/day.")

        sp_counts = (
            patt[patt["species"] != ""]
            .groupby("species")
            .size()
            .sort_values(ascending=False)
        )
        top_species = sp_counts.head(8).index.tolist()
        patt["species_group"] = patt["species"].where(patt["species"].isin(top_species), other="Other")

        by_hour = (
            patt.groupby(["hour", "species_group"])
            .size()
            .reset_index(name="Sightings")
            .sort_values(["hour", "species_group"])
        )
        hour_chart = (
            alt.Chart(by_hour)
            .mark_bar()
            .encode(
                x=alt.X("hour:O", title="Hour of Day", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Sightings"),
                color=alt.Color("species_group:N", title="Species"),
                tooltip=[
                    alt.Tooltip("hour:O", title="Hour"),
                    alt.Tooltip("species_group:N", title="Species"),
                    alt.Tooltip("Sightings:Q", title="Sightings"),
                ],
            )
        )

        by_day = (
            patt.groupby(["weekday", "species_group"])
            .size()
            .reset_index(name="Sightings")
        )
        by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)
        by_day = by_day.sort_values(["weekday", "species_group"])
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
            st.markdown("**Time of Day**")
            st.altair_chart(hour_chart, width="stretch")
        with cB:
            st.markdown("**Day of Week**")
            st.altair_chart(day_chart, width="stretch")

    else:
        st.caption("Counts by hour and day of week.")

        by_hour = patt.groupby("hour").size().reset_index(name="Sightings").sort_values("hour")
        hour_chart = (
            alt.Chart(by_hour)
            .mark_bar()
            .encode(
                x=alt.X("hour:O", title="Hour of Day", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("hour:O", title="Hour"), alt.Tooltip("Sightings:Q", title="Sightings")],
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
            st.markdown("**Time of Day**")
            st.altair_chart(hour_chart, width="stretch")
        with cB:
            st.markdown("**Day of Week**")
            st.altair_chart(day_chart, width="stretch")


with right:
    st.subheader("Photo Viewer")

    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    def _row_label(r):
        when = r["datetime"].strftime("%b %d • %I:%M %p")
        t = f"{int(round(r['temp_f']))}°F" if pd.notna(r.get("temp_f")) else "—"
        cam = (r.get("camera") or "").strip()
        if section == "Wildlife":
            spec = r.get("species", "") or "Unknown"
            return f"{when} • {cam} • {spec} • {t}"
        return f"{when} • {cam} • {section} • {t}"

    view["label"] = view.apply(_row_label, axis=1)

    chosen_idx = st.selectbox(
        "Select a sighting",
        options=view.index.tolist(),
        format_func=lambda i: view.loc[i, "label"],
    )

    row = view.loc[chosen_idx]
    url, fid = resolve_image_link(row, image_index=image_index, flat_index=flat_index)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"**When:** {row.get('datetime')}")
    st.markdown(f"**Camera:** {row.get('camera') or '—'}")

    if pd.notna(row.get("temp_f")):
        st.markdown(f"**Temperature:** {int(round(float(row.get('temp_f'))))} °F")
    else:
        st.markdown("**Temperature:** —")

    if section == "Wildlife":
        st.markdown(f"**Species:** {row.get('species') or 'Unknown'}")

    st.markdown(f"**File:** `{row.get('filename','')}`")

    if url:
        st.link_button("Open photo in Google Drive", url)
    else:
        if ROOT_FOLDER_ID:
            st.warning(
                "Photo link not available.\n\n"
                "Checklist:\n"
                "• The Drive root folder is correct\n"
                "• It contains `images/<camera>/<filename>`\n"
                "• The folder is shared with the service account\n"
            )
        else:
            st.warning(
                "Photo link not available.\n\n"
                "Fix this with the new folder structure:\n"
                "• Set `gdrive.root_folder_id` in Streamlit secrets (folder that contains `images/`)\n\n"
                "Fallback options:\n"
                "• Add `image_drive_id` or `image_url` columns to events.csv\n"
                "• Or set `gdrive.images_folder_id` if images are in a single flat folder"
            )

    if fid and st.toggle("Show photo preview", value=True):
        try:
            service = _drive_client()
            img_bytes = _download_drive_file_bytes(service, fid)
            st.image(img_bytes, width="stretch")
        except Exception as e:
            st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Section Table")

    show_cols = [c for c in ["datetime", "camera", "temp_f", "species", "filename"] if c in view.columns]
    if section != "Wildlife":
        show_cols = [c for c in ["datetime", "camera", "temp_f", "filename"] if c in view.columns]

    st.dataframe(
        view.sort_values("datetime", ascending=False)[show_cols],
        width="stretch",
        hide_index=True,
    )

st.divider()
st.caption(
    f"Source: {df.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h"
)
