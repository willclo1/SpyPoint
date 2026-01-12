# streamlit_app.py
# Ranch Activity Dashboard — clean, non-technical, pattern-focused
#
# Pulls events.csv from Google Drive (service account) + optionally indexes an images folder
# so each event can open/preview the corresponding image.
#
# Requires secrets:
#   [gdrive]
#   file_id = "...."                # Drive file id for events.csv
#   images_folder_id = "...."       # OPTIONAL: Drive folder containing images
#
#   [gcp_service_account]
#   type="service_account"
#   project_id="..."
#   private_key_id="..."
#   private_key="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
#   client_email="..."
#   client_id="..."
#   token_uri="https://oauth2.googleapis.com/token"
#   ... (the rest is ok too)
#
# Optional:
#   cache_ttl_seconds = 21600  # 6 hours

import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ---------------------------
# Page config + subtle polish
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
      button[kind="secondary"] { border-radius: 10px; }
      button[kind="primary"] { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Activity")
st.caption("Patterns in wildlife, people, and vehicles over time. Select a sighting to view the photo.")


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
    # 1) direct URL in CSV
    if "image_url" in row.index and str(row.get("image_url", "")).strip():
        return str(row["image_url"]).strip(), ""

    # 2) direct fileId in CSV
    if "image_drive_id" in row.index and str(row.get("image_drive_id", "")).strip():
        fid = str(row["image_drive_id"]).strip()
        return drive_view_url(fid), fid

    # 3) fallback: lookup by filename in images folder index
    fn = str(row.get("filename", "")).strip()
    if fn and fn in image_map:
        fid = image_map[fn].get("id", "")
        url = image_map[fn].get("webViewLink", "") or (drive_view_url(fid) if fid else "")
        return url, fid

    return "", ""


# ---------------------------
# Cleaning helpers (robust)
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
    Rules:
      - if it contains 'vehicle' => 'vehicle'
      - if it contains 'human' or 'person' => 'human'
      - else keep the last segment after semicolons (taxonomy strings)
    """
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
    # Expecting MM/DD/YYYY and HH:MM AM/PM (but we handle messy cases)
    date_s = df.get("date", pd.Series([""] * len(df))).astype(str).fillna("")
    time_s = df.get("time", pd.Series([""] * len(df))).astype(str).fillna("")
    return pd.to_datetime((date_s + " " + time_s).str.strip(), errors="coerce")


def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def clamp_temp_domain(min_v: float, max_v: float) -> tuple[float, float]:
    """
    Ensure temperature axis is always readable:
      at least 10°F to 90°F, expanded if data exceeds those bounds.
    """
    lo = min(10.0, float(min_v)) if pd.notna(min_v) else 10.0
    hi = max(90.0, float(max_v)) if pd.notna(max_v) else 90.0
    if hi - lo < 20:
        # prevent squished charts
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

# Normalize columns
for col in ["date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

# Temperature (°F only)
if "temp_f" in df.columns:
    df["temp_f"] = safe_numeric(df["temp_f"])
else:
    df["temp_f"] = pd.Series([pd.NA] * len(df))

# Event type + species
if "event_type" in df.columns:
    df["event_type"] = df["event_type"].map(normalize_event_type)
else:
    df["event_type"] = ""

if "species" in df.columns:
    df["species"] = df["species"].map(normalize_species)
else:
    df["species"] = ""

# datetime
df["datetime"] = build_datetime(df)

# Fill missing temp with NA (avoid filter crashes)
df["temp_f"] = df["temp_f"].where(df["temp_f"].notna(), pd.NA)

# If event_type is missing, derive a best-effort from species
# (keeps UI usable if CSV schema drifts)
def _derive_type(row):
    et = str(row.get("event_type", "")).strip().lower()
    if et in ("animal", "human", "vehicle"):
        return et
    sp = str(row.get("species", "")).strip().lower()
    if sp in ("human", "vehicle"):
        return sp
    if sp:
        return "animal"
    return ""

df["event_type"] = df.apply(_derive_type, axis=1)

# index photos folder (optional)
image_map = {}
if IMAGES_FOLDER_ID:
    with st.spinner("Indexing photos folder…"):
        image_map = list_images_in_folder(IMAGES_FOLDER_ID)

# Basic integrity check
valid = df.dropna(subset=["datetime"]).copy()
if valid.empty:
    st.error("No usable date/time data found in events.csv. Check your OCR date/time fields.")
    st.stop()

st.success(f"Loaded **{len(df):,}** sightings • Updated: **{last_mod_pretty}**")


# ---------------------------
# Sidebar controls (simple)
# ---------------------------
st.sidebar.header("Filters")

mode = st.sidebar.radio("Show", options=["All", "Wildlife", "People", "Vehicles"], index=0)

min_dt = valid["datetime"].min()
max_dt = valid["datetime"].max()

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_dt.date(), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date(),
)

# Temp range (handle missing temps gracefully)
temp_series = valid["temp_f"].dropna()
if temp_series.empty:
    st.sidebar.warning("No temperature data found. Temperature charts will still work but may be empty.")
    temp_range = None
else:
    # Use observed min/max for slider bounds (clamped in charts separately)
    tmin = int(temp_series.min())
    tmax = int(temp_series.max())
    if tmin == tmax:
        tmin -= 1
        tmax += 1
    temp_range = st.sidebar.slider("Temperature (°F)", min_value=tmin, max_value=tmax, value=(tmin, tmax))

# Species filter (only meaningful for Wildlife; still safe in other modes)
species_filter = []
wild_species = sorted(
    s for s in valid["species"].dropna().astype(str).unique().tolist()
    if s and s not in ("human", "vehicle")
)
if mode in ("All", "Wildlife") and wild_species:
    species_filter = st.sidebar.multiselect("Species (wildlife)", options=wild_species, default=[])

st.sidebar.markdown(f"<div class='small-muted'>Cache: {CACHE_TTL_SECONDS//3600}h</div>", unsafe_allow_html=True)


# ---------------------------
# Apply filters (robust)
# ---------------------------
base = df.dropna(subset=["datetime"]).copy()

# Date filter (safe)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]

# Temp filter (safe)
if temp_range is not None:
    lo, hi = temp_range
    # Only filter rows where temp exists; keep rows with missing temp out of temp-based charts later
    base = base[base["temp_f"].notna()]
    base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]

# Mode filter
if mode == "Wildlife":
    base = base[base["event_type"] == "animal"]
elif mode == "People":
    base = base[base["event_type"] == "human"]
elif mode == "Vehicles":
    base = base[base["event_type"] == "vehicle"]

# Species filter (wildlife only)
if species_filter:
    base = base[base["species"].isin(species_filter)]

if base.empty:
    st.info("No sightings match your filters. Try expanding the date range or temperature range.")
    st.stop()


# ---------------------------
# Summary strip (simple KPIs)
# ---------------------------
total = len(base)
wildlife_count = int((base["event_type"] == "animal").sum())
people_count = int((base["event_type"] == "human").sum())
vehicle_count = int((base["event_type"] == "vehicle").sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Sightings", f"{total:,}")
m2.metric("Wildlife", f"{wildlife_count:,}")
m3.metric("People", f"{people_count:,}")
m4.metric("Vehicles", f"{vehicle_count:,}")


# ---------------------------
# Main layout: patterns + photo viewer
# ---------------------------
left, right = st.columns([2.15, 1])

# Chart defaults
DOT_SIZE = 240  # big, readable
OPACITY = 0.86

# Stable temp axis: 10–90 minimum, expanded if needed
temp_min = base["temp_f"].min() if base["temp_f"].notna().any() else 10
temp_max = base["temp_f"].max() if base["temp_f"].notna().any() else 90
Y_LO, Y_HI = clamp_temp_domain(temp_min, temp_max)


with left:
    st.subheader("Activity Over Time")
    st.caption("Each dot is a sighting. Temperature is shown in °F.")

    # --- Main scatter
    chart_df = base.dropna(subset=["datetime", "temp_f"]).copy()
    if chart_df.empty:
        st.info("No temperature data available for charting in this filter window.")
    else:
        # Keep wildlife readable without rainbow overload
        if mode in ("Wildlife",) or (mode == "All" and wildlife_count > 0):
            # Only group species for animal rows; keep people/vehicles separate labels
            cd = chart_df.copy()
            cd["kind"] = cd["event_type"].map({"animal": "Wildlife", "human": "People", "vehicle": "Vehicles"}).fillna("Other")

            # Species grouping only for wildlife rows
            top_species = (
                cd[(cd["event_type"] == "animal") & (cd["species"] != "")]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
                .head(8)
                .index
                .tolist()
            )
            cd["label"] = cd.apply(
                lambda r: (r["species"] if r["event_type"] == "animal" else r["kind"]),
                axis=1,
            )
            cd["label"] = cd.apply(
                lambda r: (r["label"] if (r["event_type"] != "animal" or r["label"] in top_species) else "Other wildlife"),
                axis=1,
            )

            color_field = "label:N"
            color_title = "Group"
            tooltip = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("kind:N", title="Type"),
                alt.Tooltip("species:N", title="Species"),
                alt.Tooltip("filename:N", title="File"),
            ]
            plot_df = cd
        else:
            # People-only or Vehicles-only
            plot_df = chart_df.copy()
            plot_df["kind"] = plot_df["event_type"].map({"animal": "Wildlife", "human": "People", "vehicle": "Vehicles"}).fillna("")
            color_field = "kind:N"
            color_title = "Type"
            tooltip = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("kind:N", title="Type"),
                alt.Tooltip("filename:N", title="File"),
            ]

        scatter = (
            alt.Chart(plot_df)
            .mark_circle(size=DOT_SIZE, opacity=OPACITY)
            .encode(
                x=alt.X("datetime:T", title="Time"),
                y=alt.Y("temp_f:Q", title="Temperature (°F)", scale=alt.Scale(domain=[Y_LO, Y_HI])),
                color=alt.Color(color_field, title=color_title),
                tooltip=tooltip,
            )
            .interactive()
        )
        st.altair_chart(scatter, use_container_width=True)

    st.markdown("---")
    st.subheader("Patterns")
    st.caption("Simple views that answer: *What time? What day? What temps?*")

    patt = base.dropna(subset=["datetime"]).copy()
    patt = patt.dropna(subset=["temp_f"])  # patterns depend on temperature/time

    patt["hour"] = patt["datetime"].dt.hour
    patt["weekday"] = patt["datetime"].dt.day_name()

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # Events by hour
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

    # Events by weekday
    by_day = (
        patt.groupby("weekday")
        .size()
        .reindex(weekday_order, fill_value=0)
        .reset_index(name="Sightings")
    )
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

    # Typical temperature by hour (median)
    by_hour_temp = patt.groupby("hour")["temp_f"].median().reset_index(name="Typical Temp (°F)").sort_values("hour")
    temp_chart = (
        alt.Chart(by_hour_temp)
        .mark_line(point=alt.OverlayMarkDef(size=70))
        .encode(
            x=alt.X("hour:O", title="Hour of Day", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Typical Temp (°F):Q", title="Typical Temperature (°F)", scale=alt.Scale(domain=[Y_LO, Y_HI])),
            tooltip=[
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("Typical Temp (°F):Q", title="Median Temp (°F)", format=".1f"),
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

    st.markdown("**Typical Temperature**")
    st.altair_chart(temp_chart, use_container_width=True)


with right:
    st.subheader("View a Sighting")
    st.caption("Pick a time → see the photo and key details.")

    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    # Friendly label for dropdown
    def _row_label(r):
        when = r["datetime"].strftime("%b %d • %I:%M %p")
        t = f"{int(round(r['temp_f']))}°F" if pd.notna(r.get("temp_f")) else "—"
        et = r.get("event_type", "")
        if et == "animal":
            kind = "Wildlife"
            spec = r.get("species", "") or "Unknown"
            return f"{when} • {spec} • {t}"
        if et == "human":
            return f"{when} • People • {t}"
        if et == "vehicle":
            return f"{when} • Vehicle • {t}"
        return f"{when} • Sighting • {t}"

    view["label"] = view.apply(_row_label, axis=1)

    chosen_idx = st.selectbox(
        "Select a sighting",
        options=view.index.tolist(),
        format_func=lambda i: view.loc[i, "label"],
    )

    row = view.loc[chosen_idx]
    url, fid = resolve_image_link(row, image_map)

    st.markdown('<div class="card">', unsafe_allow_html=True)

    st.markdown(f"**When:** {row.get('datetime')}")
    if pd.notna(row.get("temp_f")):
        st.markdown(f"**Temperature:** {int(round(float(row.get('temp_f'))))} °F")
    else:
        st.markdown("**Temperature:** —")

    et = row.get("event_type", "")
    if et == "animal":
        st.markdown(f"**Type:** Wildlife")
        st.markdown(f"**Species:** {row.get('species') or 'Unknown'}")
    elif et == "human":
        st.markdown("**Type:** People")
    elif et == "vehicle":
        st.markdown("**Type:** Vehicle")
    else:
        st.markdown("**Type:** Sighting")

    if url:
        st.link_button("Open photo in Google Drive", url)
    else:
        st.warning(
            "Photo link not available.\n\n"
            "Fix options:\n"
            "• Add `image_drive_id` or `image_url` columns to events.csv\n"
            "• Or set `gdrive.images_folder_id` in secrets and share that folder with the service account"
        )

    # Preview (simple, optional)
    show_preview = st.toggle("Show photo preview", value=True, help="Shows the photo here on the page.")
    if show_preview and fid:
        try:
            service = _drive_client()
            img_bytes = _download_drive_file_bytes(service, fid)
            st.image(img_bytes, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("All Sightings (table)", expanded=False):
        table_cols = []
        for c in ["datetime", "temp_f", "event_type", "species", "filename"]:
            if c in base.columns:
                table_cols.append(c)
        # Human-friendly values
        tdf = base.copy()
        tdf["type"] = tdf["event_type"].map({"animal": "Wildlife", "human": "People", "vehicle": "Vehicle"}).fillna("")
        if "event_type" in table_cols:
            table_cols = [c for c in table_cols if c != "event_type"]
            table_cols.insert(2, "type")
        st.dataframe(
            tdf.sort_values("datetime", ascending=False)[table_cols],
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.caption(
    f"Source: {df.attrs.get('drive_name','events.csv')} • Updated {last_mod_pretty} • Cache {CACHE_TTL_SECONDS//3600}h"
)