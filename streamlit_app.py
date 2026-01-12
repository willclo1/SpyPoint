# streamlit_app.py
# Ranch Activity Dashboard — clean sections:
#   Wildlife shows ONLY wildlife (with species filter + species-stacked bars)
#   People shows ONLY people
#   Vehicles shows ONLY vehicles

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


def drive_view_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def resolve_image_link(row: pd.Series, image_map: dict) -> tuple[str, str]:
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
    # Always show at least 10–90 for clear scaling
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

for col in ["date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

df["temp_f"] = pd.to_numeric(df.get("temp_f", pd.Series([pd.NA] * len(df))), errors="coerce")
df["event_type"] = df.get("event_type", "").map(normalize_event_type) if "event_type" in df.columns else ""
df["species"] = df.get("species", "").map(normalize_species) if "species" in df.columns else ""
df["datetime"] = build_datetime(df)

# If event_type is missing/empty, derive it from species
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

# Image index (optional)
image_map = {}
if IMAGES_FOLDER_ID:
    with st.spinner("Indexing photos folder…"):
        image_map = list_images_in_folder(IMAGES_FOLDER_ID)

st.success(f"Loaded **{len(df):,}** sightings • Updated: **{last_mod_pretty}**")


# ---------------------------
# Sidebar (global filters)
# ---------------------------
st.sidebar.header("Filters")

section = st.sidebar.radio("Section", options=["Wildlife", "People", "Vehicles"], index=0)

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

# Wildlife-only species filter (only affects wildlife section)
species_filter = []
if section == "Wildlife":
    wild = valid[valid["event_type"] == "animal"].copy()
    wild_species = sorted(
        s for s in wild["species"].dropna().astype(str).unique().tolist()
        if s and s not in ("human", "vehicle")
    )
    if wild_species:
        species_filter = st.sidebar.multiselect("Species", options=wild_species, default=[])

st.sidebar.markdown(f"<div class='small-muted'>Cache: {CACHE_TTL_SECONDS//3600}h</div>", unsafe_allow_html=True)


# ---------------------------
# Apply filters (section-pure)
# ---------------------------
base = df.dropna(subset=["datetime"]).copy()

# Section purity
if section == "Wildlife":
    base = base[base["event_type"] == "animal"]
elif section == "People":
    base = base[base["event_type"] == "human"]
else:
    base = base[base["event_type"] == "vehicle"]

# Date filter
start, end = date_range
base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]

# Temp filter
if temp_range is not None:
    lo, hi = temp_range
    base = base[base["temp_f"].notna()]
    base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]
else:
    lo, hi = 10, 90  # fallback for chart scaling if no temp present

# Species filter (wildlife only)
if section == "Wildlife" and species_filter:
    base = base[base["species"].isin(species_filter)]

if base.empty:
    st.info("No sightings match your filters. Try expanding the date range or temperature range.")
    st.stop()

# Chart scaling: always at least 10–90
temp_min = base["temp_f"].min() if base["temp_f"].notna().any() else 10
temp_max = base["temp_f"].max() if base["temp_f"].notna().any() else 90
Y_LO, Y_HI = clamp_temp_domain(temp_min, temp_max)

DOT_SIZE = 240
OPACITY = 0.86


# ---------------------------
# Header KPIs (section only)
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
        # Simple, readable color rules
        if section == "Wildlife":
            # keep legend readable: top species + "Other"
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
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("species:N", title="Species"),
                alt.Tooltip("filename:N", title="File"),
            ]
        else:
            # People / Vehicles: single legend item, keep clean
            chart_df["group"] = section
            color_enc = alt.Color("group:N", legend=None)
            tooltip = [
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
        st.altair_chart(scatter, use_container_width=True)

    st.markdown("---")
        st.markdown("---")
    st.subheader("Patterns")

    patt = base.dropna(subset=["datetime"]).copy()

    # Always show full week
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    patt["weekday"] = patt["datetime"].dt.day_name()
    patt["weekday"] = pd.Categorical(patt["weekday"], categories=weekday_order, ordered=True)

    # More detailed time-of-day bins (30 minutes)
    # If you want 15-min bins, set BIN_MINUTES = 15
    BIN_MINUTES = 30
    minutes_since_midnight = patt["datetime"].dt.hour * 60 + patt["datetime"].dt.minute
    patt["time_bin"] = (minutes_since_midnight // BIN_MINUTES) * BIN_MINUTES

    # Label like "06:00", "06:30", ...
    patt["time_label"] = patt["time_bin"].apply(lambda m: f"{int(m//60):02d}:{int(m%60):02d}")

    # Ensure we show ALL time bins even if empty, for consistent comparisons
    full_bins = list(range(0, 24 * 60, BIN_MINUTES))
    full_time_labels = [f"{b//60:02d}:{b%60:02d}" for b in full_bins]

    # Toggle for Wildlife charts: stacked vs clustered
    if section == "Wildlife":
        chart_style = st.radio(
            "Bar style",
            options=["Stacked", "Clustered"],
            horizontal=True,
            index=0,
        )

        # Limit legend noise: top species + Other (still allows filtering in sidebar)
        sp_counts = (
            patt[patt["species"] != ""]
            .groupby("species")
            .size()
            .sort_values(ascending=False)
        )
        top_species = sp_counts.head(10).index.tolist()
        patt["species_group"] = patt["species"].where(patt["species"].isin(top_species), other="Other")

        # --- Time of day (species split)
        by_time = (
            patt.groupby(["time_label", "species_group"])
            .size()
            .reset_index(name="Sightings")
        )

        # Add missing time bins for each species_group (so the x-axis always fully shows)
        # Build a complete grid then left-join counts
        all_species_groups = sorted(by_time["species_group"].unique().tolist())
        grid = pd.MultiIndex.from_product(
            [full_time_labels, all_species_groups],
            names=["time_label", "species_group"]
        ).to_frame(index=False)

        by_time = grid.merge(by_time, on=["time_label", "species_group"], how="left").fillna({"Sightings": 0})

        # For consistent order on x-axis
        by_time["time_label"] = pd.Categorical(by_time["time_label"], categories=full_time_labels, ordered=True)

        # --- Day of week (species split)
        by_day = (
            patt.groupby(["weekday", "species_group"])
            .size()
            .reset_index(name="Sightings")
        )

        # Add missing weekdays for each species_group (so Mon–Sun always shows)
        grid2 = pd.MultiIndex.from_product(
            [weekday_order, all_species_groups],
            names=["weekday", "species_group"]
        ).to_frame(index=False)

        by_day = grid2.merge(by_day, on=["weekday", "species_group"], how="left").fillna({"Sightings": 0})
        by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)

        # Encoding for stacked vs clustered
        stack_param = alt.Stack("zero") if chart_style == "Stacked" else None
        xoffset_param = "species_group:N" if chart_style == "Clustered" else None

        st.caption("Counts are split by species (top 10 + Other). Use the Species filter to focus.")

        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title=f"Time of Day (every {BIN_MINUTES} minutes)", sort=full_time_labels),
                y=alt.Y("Sightings:Q", title="Sightings", stack=stack_param),
                color=alt.Color("species_group:N", title="Species"),
                xOffset=xoffset_param,
                tooltip=[
                    alt.Tooltip("time_label:N", title="Time"),
                    alt.Tooltip("species_group:N", title="Species"),
                    alt.Tooltip("Sightings:Q", title="Sightings"),
                ],
            )
            .properties(height=320)
        )

        day_chart = (
            alt.Chart(by_day)
            .mark_bar()
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Sightings", stack=stack_param),
                color=alt.Color("species_group:N", title="Species"),
                xOffset=xoffset_param,
                tooltip=[
                    alt.Tooltip("weekday:N", title="Day"),
                    alt.Tooltip("species_group:N", title="Species"),
                    alt.Tooltip("Sightings:Q", title="Sightings"),
                ],
            )
            .properties(height=260)
        )

        st.markdown("**Time of day**")
        st.altair_chart(time_chart, use_container_width=True)

        st.markdown("**Day of week**")
        st.altair_chart(day_chart, use_container_width=True)

    else:
        # People / Vehicles: simple, consistent bins + full week
        by_time = (
            patt.groupby("time_label")
            .size()
            .reset_index(name="Sightings")
        )

        grid = pd.DataFrame({"time_label": full_time_labels})
        by_time = grid.merge(by_time, on="time_label", how="left").fillna({"Sightings": 0})
        by_time["time_label"] = pd.Categorical(by_time["time_label"], categories=full_time_labels, ordered=True)

        by_day = (
            patt.groupby("weekday")
            .size()
            .reset_index(name="Sightings")
        )

        grid2 = pd.DataFrame({"weekday": weekday_order})
        by_day = grid2.merge(by_day, on="weekday", how="left").fillna({"Sightings": 0})
        by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)

        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title=f"Time of Day (every {BIN_MINUTES} minutes)", sort=full_time_labels),
                y=alt.Y("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("time_label:N", title="Time"), alt.Tooltip("Sightings:Q", title="Sightings")],
            )
            .properties(height=320)
        )

        day_chart = (
            alt.Chart(by_day)
            .mark_bar()
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("weekday:N", title="Day"), alt.Tooltip("Sightings:Q", title="Sightings")],
            )
            .properties(height=260)
        )

        st.markdown("**Time of day**")
        st.altair_chart(time_chart, use_container_width=True)

        st.markdown("**Day of week**")
        st.altair_chart(day_chart, use_container_width=True)