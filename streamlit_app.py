# streamlit_app.py
# Ranch Activity Dashboard — Drive structure:
#   <root_folder_id>/
#       feeder/
#       gate/
#       events.csv
#
# Sections:
#   Wildlife: animals only + species filter + stacked species bars
#   People: humans only
#   Vehicles: vehicles only
#
# Photo viewer resolves images from: root/{camera}/{filename}

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


DRIVE_FILE_ID = _require_secret("gdrive.file_id")  # events.csv file id
ROOT_FOLDER_ID = (st.secrets.get("gdrive", {}).get("root_folder_id") or "").strip()  # RanchCam/Incoming folder id
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


def drive_view_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def list_camera_folders(root_folder_id: str) -> dict:
    """
    Returns {camera_name: folder_id} for subfolders under root folder.
    Your structure: root/feeder, root/gate, ...
    """
    if not root_folder_id:
        return {}

    service = _drive_client()
    out = {}
    page_token = None
    fields = "nextPageToken, files(id,name,mimeType,trashed)"

    q = (
        f"'{root_folder_id}' in parents and trashed=false "
        f"and mimeType='application/vnd.google-apps.folder'"
    )

    while True:
        resp = service.files().list(q=q, fields=fields, pageToken=page_token, pageSize=1000).execute()
        for f in resp.get("files", []):
            name = (f.get("name") or "").strip()
            fid = (f.get("id") or "").strip()
            if name and fid:
                out[name] = fid
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def find_file_in_folder(folder_id: str, filename: str) -> tuple[str, str]:
    """
    Find a file by exact name inside a folder.
    Returns (webViewLink, file_id) or ("","") if not found.
    """
    if not folder_id or not filename:
        return "", ""

    service = _drive_client()
    # Escape single quotes for Drive query
    safe_name = filename.replace("'", "\\'")
    q = f"'{folder_id}' in parents and trashed=false and name='{safe_name}'"
    fields = "files(id,name,webViewLink)"

    resp = service.files().list(q=q, fields=fields, pageSize=5).execute()
    files = resp.get("files", []) or []
    if not files:
        return "", ""

    f0 = files[0]
    fid = (f0.get("id") or "").strip()
    link = (f0.get("webViewLink") or "").strip() or (drive_view_url(fid) if fid else "")
    return link, fid


def resolve_image_link(row: pd.Series, camera_folder_map: dict) -> tuple[str, str]:
    """
    Priority:
      1) image_url column
      2) image_drive_id column
      3) root_folder_id + camera folder + filename lookup
    """
    if "image_url" in row.index and str(row.get("image_url", "")).strip():
        return str(row["image_url"]).strip(), ""

    if "image_drive_id" in row.index and str(row.get("image_drive_id", "")).strip():
        fid = str(row["image_drive_id"]).strip()
        return drive_view_url(fid), fid

    cam = str(row.get("camera", "")).strip()
    fn = str(row.get("filename", "")).strip()
    folder_id = camera_folder_map.get(cam, "")
    if folder_id and fn:
        return find_file_in_folder(folder_id, fn)

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
    """
    Normalizes SpeciesNet style labels.
    Also enforces your rules:
      - "animal" or blank -> "Other"
      - domestic dog -> "__DROP_DOG__" (we’ll remove from wildlife views)
    """
    if raw is None:
        return "Other"
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none"):
        return "Other"

    low = s.lower()

    # hard-drop dogs from wildlife analysis
    if "domestic dog" in low or low == "dog":
        return "__DROP_DOG__"

    # normalize vehicle/human labels if they leak into species column
    if "vehicle" in low:
        return "vehicle"
    if "human" in low or "person" in low:
        return "human"

    s2 = _after_last_semicolon(s).replace("_", " ").strip()
    if not s2 or s2.lower() in ("animal", "unknown"):
        return "Other"

    return s2


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
    lo = min(10.0, float(min_v)) if pd.notna(min_v) else 10.0
    hi = max(90.0, float(max_v)) if pd.notna(max_v) else 90.0
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

# ensure columns exist
for col in ["camera", "date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)
    else:
        if col == "camera":
            df["camera"] = "unknown"
        elif col == "filename":
            df["filename"] = ""
        else:
            df[col] = ""

df["temp_f"] = pd.to_numeric(df.get("temp_f", pd.Series([pd.NA] * len(df))), errors="coerce")

df["event_type"] = df["event_type"].map(normalize_event_type)
df["species"] = df["species"].map(normalize_species)
df["datetime"] = build_datetime(df)

# derive event_type if missing/empty
def _derive_type(row):
    et = str(row.get("event_type", "")).strip().lower()
    if et in ("animal", "human", "vehicle"):
        return et
    sp = str(row.get("species", "")).strip().lower()
    if sp == "human":
        return "human"
    if sp == "vehicle":
        return "vehicle"
    if sp and sp not in ("other", "__drop_dog__"):
        return "animal"
    # if it’s “Other” but still in wildlife context, treat as animal
    if sp == "other":
        return "animal"
    return ""

df["event_type"] = df.apply(_derive_type, axis=1)

valid = df.dropna(subset=["datetime"]).copy()
if valid.empty:
    st.error("No usable date/time data found in events.csv.")
    st.stop()

# Drive folder map (camera folders)
camera_folder_map = {}
if ROOT_FOLDER_ID:
    with st.spinner("Loading camera folders…"):
        camera_folder_map = list_camera_folders(ROOT_FOLDER_ID)

st.success(f"Loaded **{len(df):,}** sightings • Updated: **{last_mod_pretty}**")


# ---------------------------
# Sidebar filters
# ---------------------------
st.sidebar.header("Filters")

section = st.sidebar.radio("Section", options=["Wildlife", "People", "Vehicles"], index=0)

# camera filter (always visible)
camera_options = sorted([c for c in df["camera"].astype(str).unique().tolist() if c.strip()]) or ["unknown"]
default_cams = camera_options  # default to all
selected_cameras = st.sidebar.multiselect("Camera", options=camera_options, default=default_cams)

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

# wildlife-only species filter
species_filter = []
if section == "Wildlife":
    wild = valid[(valid["event_type"] == "animal") & (valid["species"] != "__DROP_DOG__")].copy()
    wild = wild[wild["species"].astype(str).str.strip() != ""]
    # species list: exclude human/vehicle labels if they leak in
    wild_species = sorted(
        s for s in wild["species"].dropna().astype(str).unique().tolist()
        if s and s not in ("human", "vehicle", "__DROP_DOG__")
    )
    if wild_species:
        species_filter = st.sidebar.multiselect("Species", options=wild_species, default=[])

if not ROOT_FOLDER_ID:
    st.sidebar.warning(
        "Photo links need `gdrive.root_folder_id` in Streamlit secrets "
        "(the folder that contains `feeder/`, `gate/`, and `events.csv`)."
    )

st.sidebar.markdown(f"<div class='small-muted'>Cache: {CACHE_TTL_SECONDS//3600}h</div>", unsafe_allow_html=True)


# ---------------------------
# Apply filters
# ---------------------------
base = df.dropna(subset=["datetime"]).copy()

# cameras
if selected_cameras:
    base = base[base["camera"].isin(selected_cameras)]
else:
    base = base.iloc[0:0]

# section purity
if section == "Wildlife":
    base = base[(base["event_type"] == "animal") & (base["species"] != "__DROP_DOG__")]
elif section == "People":
    base = base[base["event_type"] == "human"]
else:
    base = base[base["event_type"] == "vehicle"]

# date range
start, end = date_range
base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]

# temp
if temp_range is not None:
    lo, hi = temp_range
    base = base[base["temp_f"].notna()]
    base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]
else:
    lo, hi = 10, 90

# species filter (wildlife only)
if section == "Wildlife" and species_filter:
    base = base[base["species"].isin(species_filter)]

if base.empty:
    st.info("No sightings match your filters. Try expanding the date range, temperature range, or camera selection.")
    st.stop()

# chart scaling
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
            # Top species + Other (and your rule: "animal"/blank already normalized -> Other)
            counts = (
                chart_df[chart_df["species"].notna()]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
            )
            top_species = [s for s in counts.head(10).index.tolist() if s not in ("__DROP_DOG__",)]
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
        st.caption("Bars are split by species so you can see what makes up each hour/day.")

        sp_counts = (
            patt[patt["species"].notna()]
            .groupby("species")
            .size()
            .sort_values(ascending=False)
        )
        top_species = [s for s in sp_counts.head(8).index.tolist() if s not in ("__DROP_DOG__",)]
        patt["species_group"] = patt["species"].where(patt["species"].isin(top_species), other="Other")

        by_hour = (
            patt.groupby(["hour", "species_group"], dropna=False)
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
            patt.groupby(["weekday", "species_group"], dropna=False)
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
        cam = (r.get("camera") or "").strip() or "unknown"
        if section == "Wildlife":
            spec = r.get("species", "") or "Other"
            if spec == "__DROP_DOG__":
                spec = "Other"
            return f"{when} • {cam} • {spec} • {t}"
        return f"{when} • {cam} • {section} • {t}"

    view["label"] = view.apply(_row_label, axis=1)

    chosen_idx = st.selectbox(
        "Select a sighting",
        options=view.index.tolist(),
        format_func=lambda i: view.loc[i, "label"],
    )

    row = view.loc[chosen_idx]
    url, fid = resolve_image_link(row, camera_folder_map)

    st.markdown('<div class="card">', unsafe_allow_html=True)

    st.markdown(f"**Camera:** {row.get('camera') or 'unknown'}")
    st.markdown(f"**When:** {row.get('datetime')}")

    if pd.notna(row.get("temp_f")):
        st.markdown(f"**Temperature:** {int(round(float(row.get('temp_f'))))} °F")
    else:
        st.markdown("**Temperature:** —")

    if section == "Wildlife":
        sp = row.get("species") or "Other"
        if sp == "__DROP_DOG__":
            sp = "Other"
        st.markdown(f"**Species:** {sp}")

    st.markdown(f"**File:** `{row.get('filename','')}`")

    if url:
        st.link_button("Open photo in Google Drive", url)
    else:
        st.warning(
            "Photo link not available.\n\n"
            "To fix this with your folder structure:\n"
            "• Set `gdrive.root_folder_id` in Streamlit secrets (the folder that contains `feeder/`, `gate/`, and `events.csv`).\n"
            "• Make sure that folder (and its subfolders) are shared with your service account.\n\n"
            "Fallback options:\n"
            "• Add `image_drive_id` or `image_url` columns to events.csv"
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

    show_cols = [c for c in ["camera", "datetime", "temp_f", "species", "filename"] if c in view.columns]
    if section != "Wildlife":
        show_cols = [c for c in ["camera", "datetime", "temp_f", "filename"] if c in view.columns]

    st.dataframe(view.sort_values("datetime", ascending=False)[show_cols], width="stretch", hide_index=True)

st.divider()
st.caption(
    f"Source: {df.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h"
)
