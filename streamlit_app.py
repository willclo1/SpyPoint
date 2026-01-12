import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# =========================
# Page setup (simple + readable)
# =========================
st.set_page_config(page_title="Ranch Camera Dashboard", page_icon="🦌", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1200px; }
      h1, h2, h3 { letter-spacing: -0.02em; }
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
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Camera Dashboard")
st.caption("Simple patterns over time (temperature + time). Click an event to see the photo.")


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
    return "", ""


# =========================
# Data cleaning (keep simple)
# =========================
def _after_last_semicolon(s: str) -> str:
    if not s:
        return ""
    parts = [p.strip() for p in str(s).split(";") if p.strip()]
    return parts[-1] if parts else str(s).strip()


def normalize_species(raw: str) -> str:
    """
    Your labels sometimes come like: "a;b;c;vehicle" etc.
    Rules:
      - if it contains vehicle => "vehicle"
      - if it contains human/person => "human"
      - else keep the last segment after semicolons
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


def build_datetime(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")


# =========================
# Load + prep
# =========================
with st.spinner("Loading events from Google Drive…"):
    df = load_events_from_drive(DRIVE_FILE_ID)

last_mod = df.attrs.get("drive_modified", "")
try:
    last_mod_pretty = datetime.fromisoformat(last_mod.replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p")
except Exception:
    last_mod_pretty = last_mod or "?"

# normalize important columns only
for col in ["date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

if "temp_f" in df.columns:
    df["temp_f"] = pd.to_numeric(df["temp_f"], errors="coerce")

if "event_type" in df.columns:
    df["event_type"] = df["event_type"].map(normalize_event_type)

if "species" in df.columns:
    df["species"] = df["species"].map(normalize_species)

if "date" in df.columns and "time" in df.columns:
    df["datetime"] = build_datetime(df)
else:
    df["datetime"] = pd.NaT

# extra columns for “pattern” views
df["hour"] = df["datetime"].dt.hour
df["day"] = df["datetime"].dt.date

# Load image index (optional)
image_map = {}
if IMAGES_FOLDER_ID:
    with st.spinner("Indexing photos folder… (cached)"):
        image_map = list_images_in_folder(IMAGES_FOLDER_ID)

st.success(f"Loaded **{len(df):,}** events • Updated: **{last_mod_pretty}**")


# =========================
# Sidebar: simple controls
# =========================
st.sidebar.header("What do you want to look at?")

mode = st.sidebar.radio(
    "Show",
    options=["Animals", "People & Vehicles"],
    index=0,
)

# Date range (big + simple)
df_dt = df.dropna(subset=["datetime"]).copy()
if df_dt.empty:
    st.sidebar.error("No valid date/time data found in events.csv.")
    st.stop()

min_dt = df_dt["datetime"].min()
max_dt = df_dt["datetime"].max()

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_dt.date(), max_dt.date()),
)

# Temperature filter
tmin = int(df_dt["temp_f"].min()) if df_dt["temp_f"].notna().any() else 0
tmax = int(df_dt["temp_f"].max()) if df_dt["temp_f"].notna().any() else 100
temp_range = st.sidebar.slider("Temperature (°F)", min_value=tmin, max_value=tmax, value=(tmin, tmax))

# Scaling control (non-tech friendly)
fixed_scale = st.sidebar.checkbox("Keep same chart scale", value=True)
st.sidebar.caption("Tip: Keep this on to compare weeks easily.")


# =========================
# Filter data
# =========================
base = df.dropna(subset=["datetime"]).copy()
start, end = date_range
base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]
lo, hi = temp_range
base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]

if mode == "Animals":
    data = base[base["event_type"] == "animal"].copy()
else:
    data = base[base["event_type"].isin(["human", "vehicle"])].copy()

# quick KPIs (only important info)
k1, k2, k3 = st.columns(3)
k1.metric("Events in range", f"{len(data):,}")
k2.metric("First day", str(start))
k3.metric("Last day", str(end))


# =========================
# Friendly empty state
# =========================
if data.empty:
    st.info("No events match your filters. Try expanding the date range or temperature range.")
    st.stop()


# =========================
# Main layout: Patterns + Photo viewer
# =========================
left, right = st.columns([2.2, 1])

with left:
    st.subheader("Patterns")

    # ---- Chart 1: timeline scatter (clear, big dots)
    st.markdown("**1) When things happen (time vs temperature)**")

    # y-axis scaling
    y_domain = None
    if fixed_scale and df_dt["temp_f"].notna().any():
        # fixed to current *filter range* so it doesn't jump around within a view
        y_domain = [lo, hi]

    # color grouping: simple + predictable
    if mode == "Animals":
        # Too many species can overwhelm; group common ones automatically
        top_species = (
            data[data["species"].notna() & (data["species"] != "")]
            .groupby("species")
            .size()
            .sort_values(ascending=False)
            .head(8)
            .index
            .tolist()
        )
        data["species_group"] = data["species"].where(data["species"].isin(top_species), other="Other")
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
        alt.Chart(data)
        .mark_circle(size=220, opacity=0.85)
        .encode(
            x=alt.X("datetime:T", title="Time"),
            y=alt.Y("temp_f:Q", title="Temp (°F)", scale=alt.Scale(domain=y_domain)),
            color=alt.Color(color_field, title=color_title),
            tooltip=tooltip,
        )
        .interactive()
    )

    st.altair_chart(scatter, use_container_width=True)

      # ---- Chart 2: Simple pattern charts (much more readable than a heatmap)
    st.markdown("**2) Simple patterns (easy to read)**")

    patt = data.dropna(subset=["datetime", "temp_f"]).copy()
    patt["hour"] = patt["datetime"].dt.hour
    patt["weekday"] = patt["datetime"].dt.day_name()

    # Order weekdays in a normal, human order
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # --- A) Events by hour (bar)
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
            x=alt.X(
                "hour:O",
                title="Hour of Day (0 = midnight, 12 = noon, 23 = 11pm)",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("events:Q", title="Number of Events"),
            tooltip=[
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("events:Q", title="Events"),
            ],
        )
    )

    # --- B) Events by weekday (bar)
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
            y=alt.Y(
                "weekday:N",
                title="Day of Week",
                sort=weekday_order,
            ),
            x=alt.X("events:Q", title="Number of Events"),
            tooltip=[
                alt.Tooltip("weekday:N", title="Day"),
                alt.Tooltip("events:Q", title="Events"),
            ],
        )
    )

    # --- C) Typical temperature by hour (line)
    # Uses median temperature (more stable than mean)
    by_hour_temp = (
        patt.groupby("hour")["temp_f"]
        .median()
        .reset_index(name="median_temp_f")
        .sort_values("hour")
    )

    # Keep y-axis stable if user has "fixed_scale" checked
    temp_domain = [lo, hi] if fixed_scale else None

    temp_chart = (
        alt.Chart(by_hour_temp)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "hour:O",
                title="Hour of Day",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "median_temp_f:Q",
                title="Typical Temperature (°F) at that Hour (median)",
                scale=alt.Scale(domain=temp_domain),
            ),
            tooltip=[
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("median_temp_f:Q", title="Median Temp (°F)", format=".1f"),
            ],
        )
    )

    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Events by hour**")
        st.altair_chart(hour_chart, use_container_width=True)

    with cB:
        st.markdown("**Events by day of week**")
        st.altair_chart(day_chart, use_container_width=True)

    st.markdown("**Typical temperature by hour**")
    st.altair_chart(temp_chart, use_container_width=True)

    st.caption("These charts answer: *When does it happen? Which days? What temps?* (without the clutter).")

    st.caption("Hover a chart point to see details. Use the picker on the right to open the photo.")

with right:
    st.subheader("Photo Viewer")

    # A big, friendly event picker
    view = data.sort_values("datetime", ascending=False).copy()
    view["label"] = (
        view["datetime"].dt.strftime("%b %d %I:%M %p")
        + " • "
        + (view["species"].where(view["species"] != "", other=view["event_type"])).fillna("")
        + " • "
        + view["temp_f"].round(0).astype("Int64").astype(str)
        + "°F"
    )

    chosen = st.selectbox("Pick an event", options=view.index.tolist(), format_func=lambda i: view.loc[i, "label"])

    row = view.loc[chosen]
    url, fid = resolve_image_link(row, image_map)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"**When:** {row.get('datetime')}")
    st.markdown(f"**Temp:** {row.get('temp_f')} °F")
    if mode == "Animals":
        st.markdown(f"**Species:** {row.get('species') or 'Unknown'}")
    else:
        st.markdown(f"**Type:** {row.get('event_type')}")
    st.markdown(f"**File:** `{row.get('filename','')}`")

    if url:
        st.link_button("Open photo in Google Drive", url)
    else:
        st.warning(
            "I can’t link this photo yet.\n\n"
            "Fix: make sure your images folder is shared with the service account "
            "and `gdrive.images_folder_id` is set in secrets."
        )

    # Simple preview toggle (no tech words)
    if fid and st.toggle("Show photo preview here", value=True):
        try:
            service = _drive_client()
            img_bytes = _download_drive_file_bytes(service, fid)
            st.image(img_bytes, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.caption("This view shows only the important details + the photo.")


st.divider()
st.caption(
    f"Source: {df.attrs.get('drive_name','events.csv')} • "
    f"Updated {last_mod_pretty} • "
    f"Cache {CACHE_TTL_SECONDS//3600}h"
)