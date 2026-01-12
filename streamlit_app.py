import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ---------------------------
# Page config + theme helpers
# ---------------------------
st.set_page_config(
    page_title="Ranch Camera Dashboard",
    page_icon="🦌",
    layout="wide",
)

st.markdown(
    """
    <style>
      /* Make the app feel less “default Streamlit” */
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
      h1, h2, h3 { letter-spacing: -0.02em; }
      div[data-testid="stMetricValue"] { font-size: 1.5rem; }
      div[data-testid="stMetricLabel"] { font-size: 0.9rem; opacity: 0.8; }
      .stDataFrame { border-radius: 12px; overflow: hidden; }
      .stAlert { border-radius: 12px; }
      section[data-testid="stSidebar"] { padding-top: 1rem; }
      .small-muted { opacity: 0.75; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Camera Dashboard")
st.caption("📌 Data source: events.csv pulled from Google Drive")


# ---------------------------
# Settings (secrets)
# ---------------------------
DRIVE_FILE_ID = st.secrets["gdrive"]["file_id"]
CACHE_TTL_SECONDS = int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60))  # default 6h


# ---------------------------
# Google Drive fetch
# ---------------------------
def _drive_client():
    creds_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_events_from_drive(file_id: str) -> pd.DataFrame:
    service = _drive_client()

    meta = service.files().get(fileId=file_id, fields="name,modifiedTime,size").execute()

    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)
    df = pd.read_csv(fh)

    df.attrs["drive_name"] = meta.get("name", "events.csv")
    df.attrs["drive_modified"] = meta.get("modifiedTime", "")
    df.attrs["drive_size"] = meta.get("size", "")

    return df


# ---------------------------
# Cleaning helpers
# ---------------------------
def _after_last_semicolon(s: str) -> str:
    """If taxonomy strings look like 'a;b;c;whitetail deer', keep 'whitetail deer'."""
    if not s:
        return ""
    parts = [p.strip() for p in str(s).split(";") if p.strip()]
    return parts[-1] if parts else str(s).strip()


def normalize_species(raw: str) -> str:
    """
    - If species string contains 'vehicle' anywhere => 'vehicle'
    - If contains 'human' or 'person' anywhere => 'human'
    - Otherwise keep only after last semicolon for readability.
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


def make_datetime(df: pd.DataFrame) -> pd.Series:
    # date: MM/DD/YYYY, time: HH:MM AM/PM (from your OCR)
    dt = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")
    return dt


# ---------------------------
# Load data
# ---------------------------
with st.spinner("Loading events.csv from Google Drive…"):
    df = load_events_from_drive(DRIVE_FILE_ID)

last_mod = df.attrs.get("drive_modified", "")
try:
    last_mod_pretty = datetime.fromisoformat(last_mod.replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p")
except Exception:
    last_mod_pretty = last_mod or "?"

st.success(f"Loaded **{len(df):,}** rows • Last modified: **{last_mod_pretty}**")

# basic cleanup
for col in ["date", "time", "event_type", "species"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

if "temp_f" in df.columns:
    df["temp_f"] = pd.to_numeric(df["temp_f"], errors="coerce")

if "event_type" in df.columns:
    df["event_type"] = df["event_type"].map(normalize_event_type)

if "species" in df.columns:
    df["species"] = df["species"].map(normalize_species)

# clean top1/2/3 if present
for i in (1, 2, 3):
    c = f"top{i}_species"
    if c in df.columns:
        df[c] = df[c].fillna("").astype(str).map(normalize_species)

# datetime
if "date" in df.columns and "time" in df.columns:
    df["datetime"] = make_datetime(df)
else:
    df["datetime"] = pd.NaT


# ---------------------------
# Sidebar filters
# ---------------------------
st.sidebar.header("Filters")

# date range
df_dt = df.dropna(subset=["datetime"]).copy()
if not df_dt.empty:
    min_dt = df_dt["datetime"].min()
    max_dt = df_dt["datetime"].max()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_dt.date(), max_dt.date()),
    )
else:
    date_range = None
    st.sidebar.info("No valid datetime values found.")

# event type filter
event_options = ["animal", "human", "vehicle"]
if "event_type" in df.columns:
    selected_events = st.sidebar.multiselect("Event type", options=event_options, default=event_options)
else:
    selected_events = event_options

# species filter
species_options = []
if "species" in df.columns:
    species_options = sorted([s for s in df["species"].unique() if s and s not in ("human", "vehicle")])
selected_species = st.sidebar.multiselect("Species (animals)", options=species_options)

# temperature filter
temp_min, temp_max = None, None
if "temp_f" in df.columns and df["temp_f"].notna().any():
    tmin = float(df["temp_f"].min())
    tmax = float(df["temp_f"].max())
    temp_min, temp_max = st.sidebar.slider("Temp (°F)", min_value=int(tmin), max_value=int(tmax), value=(int(tmin), int(tmax)))

st.sidebar.markdown(
    f'<div class="small-muted">Cache TTL: {CACHE_TTL_SECONDS//3600}h (set in secrets)</div>',
    unsafe_allow_html=True,
)

# apply filters
f = df.copy()
if date_range and "datetime" in f.columns and len(date_range) == 2:
    start, end = date_range
    f = f.dropna(subset=["datetime"])
    f = f[(f["datetime"].dt.date >= start) & (f["datetime"].dt.date <= end)]

if "event_type" in f.columns and selected_events:
    f = f[f["event_type"].isin(selected_events)]

if selected_species and "species" in f.columns:
    # only filter animal species list; human/vehicle are already handled
    f = f[f["species"].isin(selected_species)]

if temp_min is not None and "temp_f" in f.columns:
    f = f[(f["temp_f"] >= temp_min) & (f["temp_f"] <= temp_max)]


# ---------------------------
# KPI row
# ---------------------------
k1, k2, k3, k4 = st.columns(4)

total = len(f)
animals = int((f.get("event_type", pd.Series(dtype=str)) == "animal").sum()) if "event_type" in f.columns else 0
humans = int((f.get("event_type", pd.Series(dtype=str)) == "human").sum()) if "event_type" in f.columns else 0
vehicles = int((f.get("event_type", pd.Series(dtype=str)) == "vehicle").sum()) if "event_type" in f.columns else 0

k1.metric("Events", f"{total:,}")
k2.metric("Animals", f"{animals:,}")
k3.metric("Humans", f"{humans:,}")
k4.metric("Vehicles", f"{vehicles:,}")


# ---------------------------
# Tabs: Charts / Table
# ---------------------------
tab1, tab2 = st.tabs(["📈 Charts", "🗂️ Events"])

with tab1:
    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("Detections over time (Temp °F)")
        if "datetime" in f.columns and f["datetime"].notna().any():
            chart_df = f.dropna(subset=["datetime"]).copy()

            base = (
                alt.Chart(chart_df)
                .mark_circle(size=55, opacity=0.75)
                .encode(
                    x=alt.X("datetime:T", title="Time"),
                    y=alt.Y("temp_f:Q", title="Temp (°F)"),
                    color=alt.Color("event_type:N", title="Event"),
                    tooltip=[
                        "filename:N",
                        alt.Tooltip("datetime:T", title="Time"),
                        alt.Tooltip("temp_f:Q", title="Temp (°F)"),
                        "event_type:N",
                        "species:N",
                        "species_conf:N",
                    ],
                )
            )

            st.altair_chart(base.interactive(), use_container_width=True)
        else:
            st.info("No datetime values available to chart.")

    with c2:
        st.subheader("Top animal species")
        if "species" in f.columns:
            top = (
                f[(f["species"] != "") & (~f["species"].isin(["human", "vehicle"]))]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
                .head(15)
                .reset_index(name="count")
            )

            if top.empty:
                st.info("No animal species in the current filter window.")
            else:
                bar = (
                    alt.Chart(top)
                    .mark_bar()
                    .encode(
                        x=alt.X("count:Q", title="Count"),
                        y=alt.Y("species:N", sort="-x", title="Species"),
                        tooltip=["species:N", "count:Q"],
                    )
                )
                st.altair_chart(bar, use_container_width=True)

with tab2:
    st.subheader("Events table")
    if "datetime" in f.columns:
        f_sorted = f.sort_values(by="datetime", ascending=False)
    else:
        f_sorted = f

    # nicer columns
    preferred_cols = [
        "datetime",
        "temp_f",
        "event_type",
        "species",
        "species_conf",
        "top1_species",
        "top1_conf",
        "top2_species",
        "top2_conf",
        "top3_species",
        "top3_conf",
        "filename",
    ]
    show_cols = [c for c in preferred_cols if c in f_sorted.columns]

    st.dataframe(
        f_sorted[show_cols],
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.caption(
    f"✅ Pulls from Google Drive • Cached for {CACHE_TTL_SECONDS//3600}h • "
    f"File: {df.attrs.get('drive_name', 'events.csv')}"
)