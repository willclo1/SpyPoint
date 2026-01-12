# streamlit_app.py
import io
from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# =========================
# Page setup (clean + readable)
# =========================
st.set_page_config(page_title="Ranch Camera Dashboard", page_icon="🦌", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1250px; }
      h1, h2, h3 { letter-spacing: -0.02em; }
      .small-muted { opacity: 0.78; font-size: 0.95rem; }
      .card {
        padding: 1rem 1.1rem;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.10);
        background: rgba(255,255,255,0.03);
      }
      .stDataFrame { border-radius: 14px; overflow: hidden; }
      .stAlert { border-radius: 14px; }
      section[data-testid="stSidebar"] { padding-top: 1rem; }
      div[data-testid="stMetricValue"] { font-size: 1.7rem; }
      div[data-testid="stMetricLabel"] { font-size: 0.95rem; opacity: 0.82; }
      .tight { margin-top: 0.25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Camera Dashboard")
st.caption("Patterns over time (temperature + time). Pick an event to view the photo.")


# =========================
# Secrets (Google Drive)
# =========================
# Required:
#   st.secrets["gdrive"]["file_id"]
#   st.secrets["gcp_service_account"]  (service account JSON as dict)
#
# Optional (recommended for linking images):
#   st.secrets["gdrive"]["images_folder_id"]
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
# Data cleaning (simple rules, defensive)
# =========================
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
    Your labels sometimes come like: "a;b;c;vehicle".
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
    # Expecting date like MM/DD/YYYY and time like HH:MM AM/PM
    return pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")


def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def week_start(dt: pd.Timestamp) -> pd.Timestamp:
    # Monday as start of week
    if pd.isna(dt):
        return pd.NaT
    return (dt - pd.Timedelta(days=dt.weekday())).normalize()


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

# Normalize key columns defensively
for col in ["date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)
    else:
        # Create missing columns so UI doesn't blow up
        df[col] = ""

if "temp_f" in df.columns:
    df["temp_f"] = safe_numeric(df["temp_f"])
else:
    df["temp_f"] = pd.NA

df["event_type"] = df["event_type"].map(normalize_event_type)
df["species"] = df["species"].map(normalize_species)

# Optional: normalize top species columns if present
for i in (1, 2, 3):
    c = f"top{i}_species"
    if c in df.columns:
        df[c] = df[c].fillna("").astype(str).map(normalize_species)

# Build datetime
df["datetime"] = build_datetime(df)

# Drop rows with no datetime (can't chart trends without it)
df_dt = df.dropna(subset=["datetime"]).copy()
if df_dt.empty:
    st.error("No valid date/time data found in events.csv. Check your OCR date/time columns.")
    st.stop()

# Optional image map (for linking by filename)
image_map = {}
if IMAGES_FOLDER_ID:
    with st.spinner("Indexing photos folder… (cached)"):
        image_map = list_images_in_folder(IMAGES_FOLDER_ID)

st.success(f"Loaded **{len(df_dt):,}** events • Updated: **{last_mod_pretty}**")


# =========================
# Sidebar: section + filters
# =========================
st.sidebar.header("View")

section = st.sidebar.radio(
    "Section",
    options=["Wildlife", "People", "Vehicles"],
    index=0,
)

min_dt = df_dt["datetime"].min()
max_dt = df_dt["datetime"].max()

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_dt.date(), max_dt.date()),
)

# Temperature filter (°F)
temp_series = df_dt["temp_f"].dropna()
if temp_series.empty:
    # Still allow viewing without temp (but charts will warn)
    tmin, tmax = 10, 90
else:
    # UI-friendly default bounds, but keep real limits available
    tmin = int(min(temp_series.min(), 10))
    tmax = int(max(temp_series.max(), 90))

temp_range = st.sidebar.slider(
    "Temperature (°F)",
    min_value=int(tmin),
    max_value=int(tmax),
    value=(max(10, int(tmin)), max(90, int(tmax))),
)

# Species filter ONLY for wildlife
species_filter = []
if section == "Wildlife":
    species_options = sorted([s for s in df_dt["species"].unique().tolist() if s and s not in ("human", "vehicle")])
    species_filter = st.sidebar.multiselect("Species", options=species_options, default=[])

st.sidebar.markdown(
    f'<div class="small-muted">Source: {df.attrs.get("drive_name","events.csv")}<br/>Cache: {CACHE_TTL_SECONDS//3600}h</div>',
    unsafe_allow_html=True,
)


# =========================
# Apply filters
# =========================
base = df_dt.copy()

# Date filter
try:
    start, end = date_range
    base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]
except Exception:
    st.sidebar.error("Date range is invalid. Please pick a start and end date.")
    st.stop()

# Temp filter
lo, hi = temp_range
if "temp_f" in base.columns:
    # Keep rows even if temp is missing? For patterns, we prefer temp present.
    # We'll keep them here, but charts that need temp will dropna.
    base = base[(base["temp_f"].isna()) | ((base["temp_f"] >= lo) & (base["temp_f"] <= hi))]

# Section filter
if section == "Wildlife":
    data = base[base["event_type"] == "animal"].copy()
elif section == "People":
    data = base[base["event_type"] == "human"].copy()
else:  # Vehicles
    data = base[base["event_type"] == "vehicle"].copy()

# Species filter (wildlife only)
if section == "Wildlife" and species_filter:
    data = data[data["species"].isin(species_filter)].copy()

# Friendly empty state
if data.empty:
    st.info("No events match your filters. Try expanding the date range or temperature range.")
    st.stop()


# =========================
# KPIs (simple, useful)
# =========================
k1, k2, k3 = st.columns(3)
k1.metric("Events in range", f"{len(data):,}")
k2.metric("First day", str(start))
k3.metric("Last day", str(end))


# =========================
# Main layout: Patterns + Photo viewer
# =========================
left, right = st.columns([2.2, 1])

# Consistent chart temperature scale:
# Always show at least 10–90. If your filter is wider, expand.
y_min = 10
y_max = max(90, int(hi))


with left:
    st.subheader("Patterns")

    # 1) Scatter: when it happens (time vs temp)
    st.markdown("**Timeline**")

    scatter_df = data.dropna(subset=["datetime", "temp_f"]).copy()
    if scatter_df.empty:
        st.info("No temperature values found for these events (temp_f is missing).")
    else:
        # Wildlife: color by top species groups (keeps legend readable)
        if section == "Wildlife":
            sp_counts = (
                scatter_df[scatter_df["species"] != ""]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
            )
            top_species = sp_counts.head(10).index.tolist()
            scatter_df["species_group"] = scatter_df["species"].where(scatter_df["species"].isin(top_species), other="Other")

            color_field = alt.Color("species_group:N", title="Species")
            tooltips = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("species:N", title="Species"),
                alt.Tooltip("filename:N", title="File"),
            ]
        else:
            color_field = alt.value(None)
            tooltips = [
                alt.Tooltip("datetime:T", title="Time"),
                alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
                alt.Tooltip("filename:N", title="File"),
            ]

        scatter = (
            alt.Chart(scatter_df)
            .mark_circle(size=220, opacity=0.85)
            .encode(
                x=alt.X("datetime:T", title="Time"),
                y=alt.Y("temp_f:Q", title="Temp (°F)", scale=alt.Scale(domain=[y_min, y_max])),
                color=color_field if section == "Wildlife" else alt.Color("event_type:N", title=""),
                tooltip=tooltips,
            )
            .interactive()
            .properties(height=320)
        )
        st.altair_chart(scatter, use_container_width=True)

    st.markdown("---")

    # 2) Pattern bars: time-of-day + day-of-week (wildlife supports stacked/clustered by species)
    patt = data.dropna(subset=["datetime"]).copy()

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    patt["weekday"] = patt["datetime"].dt.day_name()
    patt["weekday"] = pd.Categorical(patt["weekday"], categories=weekday_order, ordered=True)

    # More detailed bins (30 min)
    BIN_MINUTES = 30
    mins = patt["datetime"].dt.hour * 60 + patt["datetime"].dt.minute
    patt["time_bin"] = (mins // BIN_MINUTES) * BIN_MINUTES
    patt["time_label"] = patt["time_bin"].apply(lambda m: f"{int(m//60):02d}:{int(m%60):02d}")

    full_bins = list(range(0, 24 * 60, BIN_MINUTES))
    full_time_labels = [f"{b//60:02d}:{b%60:02d}" for b in full_bins]

    st.markdown("**Time patterns**")

    if section == "Wildlife":
        chart_style = st.radio(
            "Bar style",
            options=["Stacked", "Clustered"],
            horizontal=True,
            index=0,
        )

        # Keep legend readable (top 10 + Other)
        sp_counts = (
            patt[patt["species"] != ""]
            .groupby("species")
            .size()
            .sort_values(ascending=False)
        )
        top_species = sp_counts.head(10).index.tolist()
        patt["species_group"] = patt["species"].where(patt["species"].isin(top_species), other="Other")

        # --- Events by time bin, split by species_group (complete grid)
        by_time = (
            patt.groupby(["time_label", "species_group"])
            .size()
            .reset_index(name="Sightings")
        )
        all_species_groups = sorted(by_time["species_group"].unique().tolist()) if not by_time.empty else ["Other"]

        grid = pd.MultiIndex.from_product(
            [full_time_labels, all_species_groups],
            names=["time_label", "species_group"]
        ).to_frame(index=False)

        by_time = grid.merge(by_time, on=["time_label", "species_group"], how="left").fillna({"Sightings": 0})
        by_time["time_label"] = pd.Categorical(by_time["time_label"], categories=full_time_labels, ordered=True)

        # --- Events by weekday, split by species_group (complete grid)
        by_day = (
            patt.groupby(["weekday", "species_group"])
            .size()
            .reset_index(name="Sightings")
        )

        grid2 = pd.MultiIndex.from_product(
            [weekday_order, all_species_groups],
            names=["weekday", "species_group"]
        ).to_frame(index=False)

        by_day = grid2.merge(by_day, on=["weekday", "species_group"], how="left").fillna({"Sightings": 0})
        by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)

        stack_param = alt.Stack("zero") if chart_style == "Stacked" else None
        xoffset_param = "species_group:N" if chart_style == "Clustered" else None

        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title=f"Time of day (every {BIN_MINUTES} minutes)", sort=full_time_labels),
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
                y=alt.Y("weekday:N", title="Day of week", sort=weekday_order),
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
        # People/Vehicles: simple bars (always show full bins)
        by_time = patt.groupby("time_label").size().reset_index(name="Sightings")
        grid = pd.DataFrame({"time_label": full_time_labels})
        by_time = grid.merge(by_time, on="time_label", how="left").fillna({"Sightings": 0})
        by_time["time_label"] = pd.Categorical(by_time["time_label"], categories=full_time_labels, ordered=True)

        by_day = patt.groupby("weekday").size().reset_index(name="Sightings")
        grid2 = pd.DataFrame({"weekday": weekday_order})
        by_day = grid2.merge(by_day, on="weekday", how="left").fillna({"Sightings": 0})
        by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)

        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title=f"Time of day (every {BIN_MINUTES} minutes)", sort=full_time_labels),
                y=alt.Y("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("time_label:N", title="Time"), alt.Tooltip("Sightings:Q", title="Sightings")],
            )
            .properties(height=320)
        )

        day_chart = (
            alt.Chart(by_day)
            .mark_bar()
            .encode(
                y=alt.Y("weekday:N", title="Day of week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("weekday:N", title="Day"), alt.Tooltip("Sightings:Q", title="Sightings")],
            )
            .properties(height=260)
        )

        st.markdown("**Time of day**")
        st.altair_chart(time_chart, use_container_width=True)

        st.markdown("**Day of week**")
        st.altair_chart(day_chart, use_container_width=True)

    st.markdown("---")

    # 3) Weekly trend chart (great for months/weeks comparisons)
    st.markdown("**Weekly trend**")

    trend = data.dropna(subset=["datetime"]).copy()
    trend["week_start"] = trend["datetime"].apply(week_start)
    trend = trend.dropna(subset=["week_start"])

    if trend.empty:
        st.info("Not enough data to build the weekly trend.")
    else:
        if section == "Wildlife":
            # Top 8 species + Other for readability
            sp_counts = (
                trend[trend["species"] != ""]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
            )
            top_species = sp_counts.head(8).index.tolist()
            trend["species_group"] = trend["species"].where(trend["species"].isin(top_species), other="Other")

            weekly = (
                trend.groupby(["week_start", "species_group"])
                .size()
                .reset_index(name="Sightings")
                .sort_values("week_start")
            )

            line = (
                alt.Chart(weekly)
                .mark_line(point=True)
                .encode(
                    x=alt.X("week_start:T", title="Week (starts Monday)"),
                    y=alt.Y("Sightings:Q", title="Sightings per week"),
                    color=alt.Color("species_group:N", title="Species"),
                    tooltip=[
                        alt.Tooltip("week_start:T", title="Week"),
                        alt.Tooltip("species_group:N", title="Species"),
                        alt.Tooltip("Sightings:Q", title="Sightings"),
                    ],
                )
                .properties(height=280)
                .interactive()
            )
        else:
            weekly = (
                trend.groupby("week_start")
                .size()
                .reset_index(name="Sightings")
                .sort_values("week_start")
            )

            line = (
                alt.Chart(weekly)
                .mark_line(point=True)
                .encode(
                    x=alt.X("week_start:T", title="Week (starts Monday)"),
                    y=alt.Y("Sightings:Q", title="Sightings per week"),
                    tooltip=[
                        alt.Tooltip("week_start:T", title="Week"),
                        alt.Tooltip("Sightings:Q", title="Sightings"),
                    ],
                )
                .properties(height=280)
                .interactive()
            )

        st.altair_chart(line, use_container_width=True)

    st.caption("Tip: Use the date range to compare different months. Charts keep consistent bins so trends are easier to spot.")


with right:
    st.subheader("Photo Viewer")

    view = data.sort_values("datetime", ascending=False).copy()

    # Build friendly labels
    def _label_row(r: pd.Series) -> str:
        dt = r.get("datetime")
        temp = r.get("temp_f")
        name = r.get("species") if section == "Wildlife" else section[:-1].lower()  # people/vehicles -> person/vehicle-ish
        if section == "People":
            name = "human"
        if section == "Vehicles":
            name = "vehicle"
        if section == "Wildlife":
            name = r.get("species") or "wildlife"

        dt_str = dt.strftime("%b %d %I:%M %p") if isinstance(dt, pd.Timestamp) and pd.notna(dt) else "Unknown time"
        if pd.isna(temp):
            temp_str = "Temp ?"
        else:
            try:
                temp_str = f"{int(round(float(temp)))}°F"
            except Exception:
                temp_str = "Temp ?"
        return f"{dt_str} • {name} • {temp_str}"

    view["label"] = view.apply(_label_row, axis=1)

    chosen_idx = st.selectbox(
        "Pick an event",
        options=view.index.tolist(),
        format_func=lambda i: view.at[i, "label"],
    )

    row = view.loc[chosen_idx]
    url, fid = resolve_image_link(row, image_map)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    dt_val = row.get("datetime")
    st.markdown(f"**When:** {dt_val if pd.notna(dt_val) else 'Unknown'}")

    temp_val = row.get("temp_f")
    if pd.isna(temp_val):
        st.markdown("**Temp:** Unknown")
    else:
        try:
            st.markdown(f"**Temp:** {int(round(float(temp_val)))} °F")
        except Exception:
            st.markdown("**Temp:** Unknown")

    if section == "Wildlife":
        st.markdown(f"**Species:** {row.get('species') or 'Unknown'}")
    else:
        st.markdown(f"**Type:** {section[:-1]}")  # People -> Peopl (not great)
        # Fix label nicely:
        st.markdown(f"**Type:** {'Human' if section == 'People' else 'Vehicle'}")

    st.markdown(f"**File:** `{row.get('filename','')}`")

    if url:
        st.link_button("Open photo in Google Drive", url)
    else:
        st.warning(
            "No Drive link found for this photo.\n\n"
            "Recommended: set `gdrive.images_folder_id` in Streamlit secrets and share that folder "
            "with the service account."
        )

    if fid and st.toggle("Show photo preview here", value=True):
        try:
            service = _drive_client()
            img_bytes = _download_drive_file_bytes(service, fid)
            st.image(img_bytes, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    with st.expander("See the data for this event"):
        cols = [c for c in [
            "date", "time", "temp_f", "event_type", "species", "species_conf",
            "top1_species", "top1_conf", "top2_species", "top2_conf", "top3_species", "top3_conf",
            "filename"
        ] if c in row.index]
        st.dataframe(pd.DataFrame([row[cols].to_dict()]), use_container_width=True, hide_index=True)


st.divider()
st.caption(
    f"Source: {df.attrs.get('drive_name','events.csv')} • "
    f"Updated {last_mod_pretty} • "
    f"Cache {CACHE_TTL_SECONDS//3600}h"
)