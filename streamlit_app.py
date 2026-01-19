# streamlit_app.py
# Ranch Activity Dashboard — camera-aware + robust image linking
#   Wildlife shows ONLY wildlife (with species filter + species-stacked bars)
#   People shows ONLY people
#   Vehicles shows ONLY vehicles
#
# New structure support:
#   - events.csv includes a "camera" column
#   - images are stored in Drive as: images/<camera>/<filename>.jpg
#   - Streamlit can open + preview the exact file (camera + filename) reliably

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
      .tight { margin-top: 0.25rem; }
      .muted { opacity: 0.8; }
      .hr { border-top: 1px solid rgba(255,255,255,0.10); margin: 1rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Activity")
st.caption("Wildlife, people, and vehicles — separated. Filter by camera. Select a sighting to view the photo.")


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
# Root folder that contains:
#   events.csv
#   images/<camera>/<filename>.jpg
GDRIVE_ROOT_FOLDER_ID = (st.secrets.get("gdrive", {}).get("root_folder_id") or "").strip()

# Back-compat (older approach): a single folder containing ALL images flat.
IMAGES_FOLDER_ID = (st.secrets.get("gdrive", {}).get("images_folder_id") or "").strip()

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


def _safe_str(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def _list_drive_files_recursive(root_folder_id: str) -> dict:
    """
    Recursively list files under root_folder_id and build a map:
      relpath (e.g. "images/gate/PICT123.jpg") -> {id, name, webViewLink}

    This is the most reliable way to support camera subfolders on Drive.
    If root_folder_id is not set, returns {}.
    """
    if not root_folder_id:
        return {}

    service = _drive_client()

    # 1) Collect all folders under root
    folders = {}  # folder_id -> relpath
    folders[root_folder_id] = ""  # root path

    # BFS across folders
    queue = [root_folder_id]
    while queue:
        parent_id = queue.pop(0)
        parent_rel = folders.get(parent_id, "")

        page_token = None
        while True:
            resp = (
                service.files()
                .list(
                    q=f"'{parent_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'",
                    fields="nextPageToken, files(id,name)",
                    pageSize=1000,
                    pageToken=page_token,
                )
                .execute()
            )
            for f in resp.get("files", []):
                fid = f.get("id")
                name = f.get("name", "")
                if not fid or not name:
                    continue
                rel = f"{parent_rel}/{name}".strip("/")
                if fid not in folders:
                    folders[fid] = rel
                    queue.append(fid)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    # 2) List files in each folder, build relpath map
    out = {}
    for folder_id, folder_rel in folders.items():
        page_token = None
        while True:
            resp = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'",
                    fields="nextPageToken, files(id,name,webViewLink,mimeType)",
                    pageSize=1000,
                    pageToken=page_token,
                )
                .execute()
            )
            for f in resp.get("files", []):
                fid = f.get("id", "")
                name = f.get("name", "")
                if not fid or not name:
                    continue
                relpath = f"{folder_rel}/{name}".strip("/")
                out[relpath] = {"id": fid, "name": name, "webViewLink": f.get("webViewLink", "")}
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return out


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def list_images_in_folder(folder_id: str) -> dict:
    """
    Back-compat: list images in a single flat folder.
    Returns { filename: {id, webViewLink} }.
    """
    if not folder_id:
        return {}
    service = _drive_client()
    out = {}
    page_token = None
    fields = "nextPageToken, files(id,name,webViewLink,trashed)"
    q = f"'{folder_id}' in parents and trashed=false"
    while True:
        resp = service.files().list(q=q, fields=fields, pageToken=page_token, pageSize=1000).execute()
        for f in resp.get("files", []):
            name = f.get("name", "")
            if name:
                out[name] = {"id": f.get("id", ""), "webViewLink": f.get("webViewLink", "")}
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def resolve_image_link(row: pd.Series, drive_index: dict, flat_image_map: dict) -> tuple[str, str]:
    """
    Returns (url, file_id)

    Priority:
      1) image_url column
      2) image_drive_id column
      3) NEW structure lookup: "images/<camera>/<filename>" under root folder index
      4) OLD structure lookup: filename in flat images folder map
    """
    # 1) Explicit URL
    if "image_url" in row.index and _safe_str(row.get("image_url", "")):
        return _safe_str(row.get("image_url", "")), ""

    # 2) Explicit Drive file id
    if "image_drive_id" in row.index and _safe_str(row.get("image_drive_id", "")):
        fid = _safe_str(row.get("image_drive_id", ""))
        return drive_view_url(fid), fid

    # 3) New structure: images/<camera>/<filename>
    cam = _safe_str(row.get("camera", ""))
    fn = _safe_str(row.get("filename", ""))
    if cam and fn and drive_index:
        key = f"images/{cam}/{fn}"
        if key in drive_index:
            fid = drive_index[key].get("id", "")
            url = drive_index[key].get("webViewLink", "") or (drive_view_url(fid) if fid else "")
            return url, fid

    # 4) Old structure: filename in flat folder
    if fn and fn in flat_image_map:
        fid = flat_image_map[fn].get("id", "")
        url = flat_image_map[fn].get("webViewLink", "") or (drive_view_url(fid) if fid else "")
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
    # your OCR can produce inconsistent formats; errors='coerce' keeps app alive
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

# normalize columns safely
for col in ["camera", "date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)
    else:
        # Ensure missing columns don't crash filters later
        if col == "camera":
            df["camera"] = ""
        if col == "filename":
            df["filename"] = ""
        if col == "event_type":
            df["event_type"] = ""
        if col == "species":
            df["species"] = ""

# temp_f
df["temp_f"] = pd.to_numeric(df.get("temp_f", pd.Series([pd.NA] * len(df))), errors="coerce")

# normalize event/species
df["event_type"] = df["event_type"].map(normalize_event_type)
df["species"] = df["species"].map(normalize_species)

# datetime
df["datetime"] = build_datetime(df)

# derive event_type if blank
def _derive_type(row):
    et = _safe_str(row.get("event_type", "")).lower()
    if et in ("animal", "human", "vehicle"):
        return et
    sp = _safe_str(row.get("species", "")).lower()
    if sp == "human":
        return "human"
    if sp == "vehicle":
        return "vehicle"
    if sp:
        return "animal"
    return ""

df["event_type"] = df.apply(_derive_type, axis=1)

# camera cleanup: ensure non-empty when possible
df["camera"] = df["camera"].map(lambda x: _safe_str(x).lower())
df.loc[df["camera"] == "", "camera"] = "unknown"

valid = df.dropna(subset=["datetime"]).copy()
if valid.empty:
    st.error("No usable date/time data found in events.csv.")
    st.stop()

# Drive indexes for images
drive_index = {}
if GDRIVE_ROOT_FOLDER_ID:
    with st.spinner("Indexing Drive folders…"):
        drive_index = _list_drive_files_recursive(GDRIVE_ROOT_FOLDER_ID)

flat_image_map = {}
if IMAGES_FOLDER_ID:
    with st.spinner("Indexing legacy images folder…"):
        flat_image_map = list_images_in_folder(IMAGES_FOLDER_ID)

st.success(f"Loaded **{len(df):,}** sightings • Updated: **{last_mod_pretty}**")


# ---------------------------
# Sidebar (filters)
# ---------------------------
st.sidebar.header("Filters")

section = st.sidebar.radio("Section", options=["Wildlife", "People", "Vehicles"], index=0)

# Camera filter (NEW)
camera_options = sorted(valid["camera"].dropna().astype(str).unique().tolist())
camera_default = [c for c in camera_options if c != "unknown"] or camera_options
camera_filter = st.sidebar.multiselect(
    "Camera",
    options=camera_options,
    default=camera_default,
)

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
    wild = wild[wild["species"].astype(str).str.strip() != ""]
    wild = wild[~wild["species"].isin(["human", "vehicle"])]
    wild_species = sorted(wild["species"].dropna().astype(str).unique().tolist())
    if wild_species:
        species_filter = st.sidebar.multiselect("Species", options=wild_species, default=[])

st.sidebar.markdown(f"<div class='small-muted'>Cache: {CACHE_TTL_SECONDS//3600}h</div>", unsafe_allow_html=True)


# ---------------------------
# Apply filters (section-pure)
# ---------------------------
base = df.dropna(subset=["datetime"]).copy()

# camera filter first
if camera_filter:
    base = base[base["camera"].isin([c.lower() for c in camera_filter])]
else:
    # If user unselects all, show nothing instead of everything
    base = base.iloc[0:0]

# section purity
if section == "Wildlife":
    base = base[base["event_type"] == "animal"]
elif section == "People":
    base = base[base["event_type"] == "human"]
else:
    base = base[base["event_type"] == "vehicle"]

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

# species filter
if section == "Wildlife" and species_filter:
    base = base[base["species"].isin(species_filter)]

if base.empty:
    st.info("No sightings match your filters. Try expanding the date range, temperature range, or camera selection.")
    st.stop()

# chart scaling: always at least 10–90
temp_min = base["temp_f"].min() if base["temp_f"].notna().any() else 10
temp_max = base["temp_f"].max() if base["temp_f"].notna().any() else 90
Y_LO, Y_HI = clamp_temp_domain(temp_min, temp_max)

DOT_SIZE = 240
OPACITY = 0.86


# ---------------------------
# Header KPIs
# ---------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Sightings", f"{len(base):,}")
k2.metric("Cameras", f"{base['camera'].nunique():,}")
k3.metric("First day", str(start))
k4.metric("Last day", str(end))


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
                chart_df[chart_df["species"].astype(str).str.strip() != ""]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
            )
            top_species = counts.head(10).index.tolist()
            chart_df["species_group"] = chart_df["species"].where(chart_df["species"].isin(top_species), other="Other")

            color_enc = alt.Color("species_group:N", title="Species")
            tooltip = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("species:N", title="Species"),
                alt.Tooltip("camera:N", title="Camera"),
                alt.Tooltip("filename:N", title="File"),
            ]
        else:
            chart_df["group"] = section
            color_enc = alt.Color("group:N", legend=None)
            tooltip = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("camera:N", title="Camera"),
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
        st.altair_chart(scatter, use_container_width=True)

    st.markdown("---")
    st.subheader("Patterns")

    patt = base.dropna(subset=["datetime"]).copy()
    patt["hour"] = patt["datetime"].dt.hour
    patt["weekday"] = patt["datetime"].dt.day_name()

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    if section == "Wildlife":
        st.caption("Bars are split by species (stacked) so you can see what makes up each hour/day.")

        sp_counts = (
            patt[patt["species"].astype(str).str.strip() != ""]
            .groupby("species")
            .size()
            .sort_values(ascending=False)
        )
        top_species = sp_counts.head(8).index.tolist()
        patt["species_group"] = patt["species"].where(patt["species"].isin(top_species), other="Other")

        by_hour = (
            patt.groupby(["hour", "species_group"], observed=True)
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
            patt.groupby(["weekday", "species_group"], observed=True)
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
            st.altair_chart(hour_chart, use_container_width=True)
        with cB:
            st.markdown("**Day of Week**")
            st.altair_chart(day_chart, use_container_width=True)

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
            st.altair_chart(hour_chart, use_container_width=True)
        with cB:
            st.markdown("**Day of Week**")
            st.altair_chart(day_chart, use_container_width=True)


with right:
    st.subheader("Photo Viewer")

    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    def _row_label(r):
        when = r["datetime"].strftime("%b %d • %I:%M %p")
        t = f"{int(round(r['temp_f']))}°F" if pd.notna(r.get("temp_f")) else "—"
        cam = _safe_str(r.get("camera", "")).title()
        if section == "Wildlife":
            spec = _safe_str(r.get("species", "")) or "Unknown"
            return f"{when} • {spec} • {t} • {cam}"
        return f"{when} • {section} • {t} • {cam}"

    view["label"] = view.apply(_row_label, axis=1)

    chosen_idx = st.selectbox(
        "Select a sighting",
        options=view.index.tolist(),
        format_func=lambda i: view.loc[i, "label"],
    )

    row = view.loc[chosen_idx]

    url, fid = resolve_image_link(row, drive_index, flat_image_map)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"**When:** {row.get('datetime')}")
    st.markdown(f"**Camera:** {str(row.get('camera','unknown')).title()}")

    if pd.notna(row.get("temp_f")):
        st.markdown(f"**Temperature:** {int(round(float(row.get('temp_f'))))} °F")
    else:
        st.markdown("**Temperature:** —")

    if section == "Wildlife":
        st.markdown(f"**Species:** {_safe_str(row.get('species')) or 'Unknown'}")

    st.markdown(f"**File:** `{_safe_str(row.get('filename'))}`")

    if url:
        st.link_button("Open photo in Google Drive", url)
    else:
        st.warning(
            "Photo link not available.\n\n"
            "To fix this with the new folder structure, set **gdrive.root_folder_id** in Streamlit secrets "
            "(the Drive folder that contains `images/` and `events.csv`).\n\n"
            "Fallback options:\n"
            "• Add `image_drive_id` or `image_url` columns to events.csv\n"
            "• Or set `gdrive.images_folder_id` if your images are in a single flat folder"
        )

    # Preview (best-effort)
    if fid and st.toggle("Show photo preview", value=True):
        try:
            service = _drive_client()
            img_bytes = _download_drive_file_bytes(service, fid)
            st.image(img_bytes, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Section Table")

    # Section-pure table
    show_cols = [c for c in ["datetime", "camera", "temp_f", "species", "filename"] if c in view.columns]
    if section != "Wildlife":
        show_cols = [c for c in ["datetime", "camera", "temp_f", "filename"] if c in view.columns]

    st.dataframe(
        view.sort_values("datetime", ascending=False)[show_cols],
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.caption(
    f"Source: {df.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h"
)
