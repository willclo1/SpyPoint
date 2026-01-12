import io
from datetime import datetime, date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError


# =========================
# Page setup (simple + readable)
# =========================
st.set_page_config(page_title="Ranch Camera Dashboard", page_icon="🦌", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1200px; }
      h1 { letter-spacing: -0.02em; margin-bottom: 0.25rem; }
      h2, h3 { letter-spacing: -0.02em; }
      .small-muted { opacity: 0.78; font-size: 0.95rem; }
      .card {
        padding: 1rem 1.1rem;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.10);
        background: rgba(255,255,255,0.03);
      }
      div[data-testid="stMetricValue"] { font-size: 1.7rem; }
      div[data-testid="stMetricLabel"] { font-size: 0.95rem; opacity: 0.8; }
      .stDataFrame { border-radius: 14px; overflow: hidden; }
      .stAlert { border-radius: 14px; }
      section[data-testid="stSidebar"] { padding-top: 1rem; }
      label { font-weight: 600 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Camera Dashboard")
st.caption("Simple patterns over time (temperature + time). Pick an event to view the photo.")


# =========================
# Secrets (Google Drive)
# =========================
DRIVE_FILE_ID = st.secrets["gdrive"]["file_id"]
IMAGES_FOLDER_ID = (st.secrets.get("gdrive", {}).get("images_folder_id") or "").strip()
CACHE_TTL_SECONDS = int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60))


# =========================
# Google Drive helpers
# =========================
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


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def list_images_in_folder(folder_id: str) -> dict:
    """
    Returns dict: { filename: {id, webViewLink} }
    """
    if not folder_id:
        return {}
    service = _drive_client()
    out = {}
    page_token = None
    fields = "nextPageToken, files(id,name,webViewLink,trashed)"
    q = f"'{folder_id}' in parents and trashed=false"

    while True:
        resp = (
            service.files()
            .list(q=q, fields=fields, pageToken=page_token, pageSize=1000)
            .execute()
        )
        for f in resp.get("files", []):
            name = f.get("name", "")
            if name:
                out[name] = {"id": f.get("id", ""), "webViewLink": f.get("webViewLink", "")}
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def drive_view_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def resolve_image_link(row: pd.Series, image_map: dict) -> tuple[str, str]:
    """
    Returns (url, file_id)
    Priority:
      1) image_url column
      2) image_drive_id column
      3) filename lookup in images folder index
    """
    try:
        if "image_url" in row.index and str(row.get("image_url", "")).strip():
            return str(row["image_url"]).strip(), ""
        if "image_drive_id" in row.index and str(row.get("image_drive_id", "")).strip():
            fid = str(row["image_drive_id"]).strip()
            return drive_view_url(fid), fid

        fn = str(row.get("filename", "")).strip()
        if fn and fn in image_map:
            fid = image_map[fn].get("id", "")
            url = image_map[fn].get("webViewLink", "") or (drive_view_url(fid) if fid else "")
            return url, fid
    except Exception:
        pass

    return "", ""


# =========================
# Data cleaning (keep simple, avoid surprises)
# =========================
def _after_last_semicolon(s: str) -> str:
    if not s:
        return ""
    parts = [p.strip() for p in str(s).split(";") if p.strip()]
    return parts[-1] if parts else str(s).strip()


def normalize_species(raw: str) -> str:
    """
    Rules:
      - contains vehicle => "vehicle"
      - contains human/person => "human"
      - else keep last segment after semicolons
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
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


def safe_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def pretty_last_modified(iso_str: str) -> str:
    if not iso_str:
        return "?"
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso_str


def week_start(d: date) -> date:
    # Monday as start of week
    return d - timedelta(days=d.weekday())


# =========================
# Load + prep (with friendly errors)
# =========================
try:
    with st.spinner("Loading events from Google Drive…"):
        df = load_events_from_drive(DRIVE_FILE_ID)
except HttpError as e:
    st.error("Could not load events.csv from Google Drive.")
    st.code(str(e))
    st.stop()
except Exception as e:
    st.error("Something went wrong while loading events.csv.")
    st.code(str(e))
    st.stop()

last_mod_pretty = pretty_last_modified(df.attrs.get("drive_modified", ""))

# Ensure columns exist
for col in ["date", "time", "event_type", "species", "filename"]:
    if col not in df.columns:
        df[col] = ""
    df[col] = df[col].fillna("").astype(str)

# Temperature (°F)
if "temp_f" not in df.columns:
    df["temp_f"] = pd.NA
df["temp_f"] = pd.to_numeric(df["temp_f"], errors="coerce")

# Normalize
df["event_type"] = df["event_type"].map(normalize_event_type)
df["species"] = df["species"].map(normalize_species)

# Datetime
df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")

# Only keep graphable rows
df_valid = df.dropna(subset=["datetime"]).copy()
if df_valid.empty:
    st.error("No valid date/time values were found in events.csv. (The dashboard needs date + time.)")
    st.stop()

# pattern fields
df_valid["hour"] = df_valid["datetime"].dt.hour
df_valid["weekday"] = df_valid["datetime"].dt.day_name()

# Optional image folder index
image_map = {}
images_index_error = ""
if IMAGES_FOLDER_ID:
    try:
        with st.spinner("Indexing photos folder… (cached)"):
            image_map = list_images_in_folder(IMAGES_FOLDER_ID)
    except Exception:
        images_index_error = "Could not index your photos folder on Drive (permissions or API issue)."

st.success(f"Loaded **{len(df_valid):,}** events • Updated: **{last_mod_pretty}**")


# =========================
# Sidebar: simple controls
# =========================
st.sidebar.header("Filters")

mode = st.sidebar.radio(
    "Show",
    options=["Animals", "People & Vehicles"],
    index=0,
)

# Date defaults
min_dt = df_valid["datetime"].min()
max_dt = df_valid["datetime"].max()
default_start = min_dt.date()
default_end = max_dt.date()

# --- Quick buttons (non-tech friendly)


# Date range picker (still available, but quick buttons handle most use)
date_range = st.sidebar.date_input(
    "Date range",
    value=(quick_start, quick_end),
)

# Normalize date_range
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = date_range if isinstance(date_range, date) else quick_start
    end_date = start_date

if start_date > end_date:
    start_date, end_date = end_date, start_date

# Temperature slider
t_series = df_valid["temp_f"].dropna()
if t_series.empty:
    st.sidebar.warning("No temperature values found. Charts will show without temp filtering.")
    temp_range = None
else:
    tmin = safe_int(t_series.min(), 0)
    tmax = safe_int(t_series.max(), 100)
    if tmin is None or tmax is None or tmin >= tmax:
        tmin, tmax = 0, 100
    temp_range = st.sidebar.slider("Temperature (°F)", min_value=tmin, max_value=tmax, value=(tmin, tmax))

# Species filter (Animals only)
species_filter = []
if mode == "Animals":
    animal_species = sorted(
        [s for s in df_valid.loc[df_valid["event_type"] == "animal", "species"].unique()
         if s and s not in ("human", "vehicle")]
    )
    if animal_species:
        species_filter = st.sidebar.multiselect("Species (animals)", options=animal_species, default=[])
    else:
        st.sidebar.caption("No animal species labels available yet.")

st.sidebar.caption(f"Auto-refresh cache: {CACHE_TTL_SECONDS//3600}h")


# =========================
# Apply filters safely
# =========================
base = df_valid.copy()

# date filter
base = base[(base["datetime"].dt.date >= start_date) & (base["datetime"].dt.date <= end_date)]

# temp filter
if temp_range is not None:
    lo, hi = temp_range
    base = base[(base["temp_f"].notna()) & (base["temp_f"] >= lo) & (base["temp_f"] <= hi)]

# mode filter
if mode == "Animals":
    data = base[base["event_type"] == "animal"].copy()
    if species_filter:
        data = data[data["species"].isin(species_filter)]
else:
    data = base[base["event_type"].isin(["human", "vehicle"])].copy()

# KPIs
k1, k2, k3 = st.columns(3)
k1.metric("Events in range", f"{len(data):,}")
k2.metric("Start", str(start_date))
k3.metric("End", str(end_date))

if data.empty:
    st.info("No events match your filters. Try expanding the date range, temperature range, or clearing species filters.")
    st.stop()


# =========================
# Main layout: Patterns + Photo viewer
# =========================
left, right = st.columns([2.2, 1])

with left:
    st.subheader("Patterns (easy to read)")

    # ---- Chart 1: timeline scatter (clear, big dots)
    st.markdown("**1) When things happen (time vs temperature)**")

    chart_source = data.dropna(subset=["temp_f"]).copy()
    if chart_source.empty:
        st.info("No valid temperature values in this filter window. (Can’t plot temp chart.)")
    else:
        # Force readable y-axis scale: at least 10°F to 90°F
        # Expand beyond those if your data is outside that range.
        filtered_temps = chart_source["temp_f"].dropna()
        min_temp = float(filtered_temps.min()) if not filtered_temps.empty else 10.0
        max_temp = float(filtered_temps.max()) if not filtered_temps.empty else 90.0
        y_min = min(10.0, min_temp)
        y_max = max(90.0, max_temp)

        if mode == "Animals":
            top_species = (
                chart_source[chart_source["species"].notna() & (chart_source["species"] != "")]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
                .head(8)
                .index
                .tolist()
            )
            chart_source["species_group"] = chart_source["species"].where(chart_source["species"].isin(top_species), other="Other")
            color_field = "species_group:N"
            color_title = "Species"
            tooltip = [
                "filename:N",
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)"),
                alt.Tooltip("species:N", title="Species"),
            ]
        else:
            color_field = "event_type:N"
            color_title = "Type"
            tooltip = [
                "filename:N",
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)"),
                alt.Tooltip("event_type:N", title="Type"),
            ]

        scatter = (
            alt.Chart(chart_source)
            .mark_circle(size=220, opacity=0.85)
            .encode(
                x=alt.X("datetime:T", title="Time"),
                y=alt.Y("temp_f:Q", title="Temp (°F)", scale=alt.Scale(domain=[y_min, y_max])),
                color=alt.Color(color_field, title=color_title),
                tooltip=tooltip,
            )
            .interactive()
        )
        st.altair_chart(scatter, use_container_width=True)

        st.caption(f"Temperature scale is always shown from at least **10°F to 90°F** (and expands if needed).")

    # ---- Chart 2: time patterns (hour + weekday)
    st.markdown("**2) Time patterns (when most activity happens)**")

    patt = data.copy()

    # Events by hour
    by_hour = (
        patt.groupby("hour")
        .size()
        .reset_index(name="events")
        .sort_values("hour")
    )
    hour_chart = (
        alt.Chart(by_hour)
        .mark_bar()
        .encode(
            x=alt.X("hour:O", title="Hour of Day (0=midnight • 12=noon • 23=11pm)", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("events:Q", title="Number of Events"),
            tooltip=[alt.Tooltip("hour:O", title="Hour"), alt.Tooltip("events:Q", title="Events")],
        )
    )

    # Events by weekday
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day = (
        patt.groupby("weekday")
        .size()
        .reindex(weekday_order, fill_value=0)
        .reset_index(name="events")
    )
    by_day.columns = ["weekday", "events"]

    day_chart = (
        alt.Chart(by_day)
        .mark_bar()
        .encode(
            y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
            x=alt.X("events:Q", title="Number of Events"),
            tooltip=[alt.Tooltip("weekday:N", title="Day"), alt.Tooltip("events:Q", title="Events")],
        )
    )

    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Events by hour**")
        st.altair_chart(hour_chart, use_container_width=True)
    with cB:
        st.markdown("**Events by day of week**")
        st.altair_chart(day_chart, use_container_width=True)

    st.caption("Tip: Use these to spot routines (like deer at dawn, or vehicles mid-day).")

with right:
    st.subheader("Photo Viewer")

    if images_index_error:
        st.warning(images_index_error)

    view = data.sort_values("datetime", ascending=False).copy()

    def _label_for_row(r):
        when = r["datetime"].strftime("%b %d %I:%M %p") if pd.notna(r["datetime"]) else "Unknown time"
        temp = ""
        if pd.notna(r.get("temp_f", pd.NA)):
            try:
                temp = f"{int(round(float(r['temp_f'])))}°F"
            except Exception:
                temp = ""
        what = (r.get("species", "") or "Unknown animal") if mode == "Animals" else (r.get("event_type", "") or "Unknown")
        return f"{when} • {what} • {temp}".strip(" •")

    view["label"] = view.apply(_label_for_row, axis=1)

    chosen = st.selectbox(
        "Pick an event",
        options=view.index.tolist(),
        format_func=lambda i: view.loc[i, "label"] if i in view.index else "Event",
    )

    row = view.loc[chosen]
    url, fid = resolve_image_link(row, image_map)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"**When:** {row.get('datetime')}")
    if pd.notna(row.get("temp_f", pd.NA)):
        st.markdown(f"**Temp:** {row.get('temp_f')} °F")
    if mode == "Animals":
        st.markdown(f"**Species:** {row.get('species') or 'Unknown'}")
    else:
        st.markdown(f"**Type:** {row.get('event_type') or 'Unknown'}")
    st.markdown(f"**File:** `{row.get('filename','')}`")

    if url:
        st.link_button("Open photo in Google Drive", url)
    else:
        st.warning(
            "I can’t link this photo yet.\n\n"
            "Fix: share the images folder with the service account and set `gdrive.images_folder_id` in Streamlit secrets."
        )

    # Preview (safe)
    if fid:
        show_preview = st.toggle("Show photo preview here", value=True)
        if show_preview:
            try:
                service = _drive_client()
                img_bytes = _download_drive_file_bytes(service, fid)
                st.image(img_bytes, use_container_width=True)
            except HttpError as e:
                st.error("Could not load the preview from Google Drive (permission or API issue).")
                st.code(str(e))
            except Exception as e:
                st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("This view shows only the important details + the photo.")


st.divider()
st.caption(
    f"Source: {df.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h"
)