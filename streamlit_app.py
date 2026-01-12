import io
import pandas as pd
import streamlit as st
import altair as alt

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


st.set_page_config(page_title="Ranch Camera Dashboard", layout="wide")

st.title("Ranch Camera Dashboard")
st.caption("Data source: events.csv from Google Drive")

# --- Settings ---
DRIVE_FILE_ID = st.secrets["gdrive"]["file_id"]
CACHE_TTL_SECONDS = int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60))  # default 6h


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

    # Optional: fetch modified time for display
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


# --- Load data ---
with st.spinner("Loading events.csv from Google Drive..."):
    df = load_events_from_drive(DRIVE_FILE_ID)

st.success(
    f"Loaded {len(df):,} rows • "
    f"Last modified: {df.attrs.get('drive_modified','?')}"
)

# --- Basic cleaning for your columns ---
# Expecting: date, time, temp_f, event_type, species, species_conf, etc.
for col in ["date", "time", "event_type", "species"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

if "temp_f" in df.columns:
    df["temp_f"] = pd.to_numeric(df["temp_f"], errors="coerce")

# Build datetime if possible (your date/time are strings like MM/DD/YYYY + HH:MM AM/PM)
if "date" in df.columns and "time" in df.columns:
    dt = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")
    df["datetime"] = dt

# --- Filters ---
left, right = st.columns([2, 1])

with left:
    if "datetime" in df.columns:
        min_dt = df["datetime"].min()
        max_dt = df["datetime"].max()
        date_range = st.date_input(
            "Date range",
            value=(min_dt.date(), max_dt.date()) if pd.notna(min_dt) and pd.notna(max_dt) else None,
        )
    else:
        date_range = None

with right:
    species_options = sorted([s for s in df.get("species", pd.Series(dtype=str)).unique() if s])
    species_filter = st.multiselect("Species", options=species_options)

# Apply filters
f = df.copy()

if date_range and "datetime" in f.columns and len(date_range) == 2:
    start, end = date_range
    f = f[(f["datetime"].dt.date >= start) & (f["datetime"].dt.date <= end)]

if species_filter and "species" in f.columns:
    f = f[f["species"].isin(species_filter)]

st.subheader("Charts")

c1, c2 = st.columns(2)

with c1:
    st.markdown("**Detections over time**")
    if "datetime" in f.columns:
        chart_df = f.dropna(subset=["datetime"])
        chart = (
            alt.Chart(chart_df)
            .mark_circle(size=40)
            .encode(
                x=alt.X("datetime:T", title="Time"),
                y=alt.Y("temp_f:Q", title="Temp (°F)"),
                color=alt.Color("event_type:N", title="Event"),
                tooltip=["filename", "datetime", "temp_f", "event_type", "species", "species_conf"],
            )
            .interactive()
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No datetime column available to chart.")

with c2:
    st.markdown("**Top species**")
    if "species" in f.columns:
        top = (
            f[f["species"] != ""]
            .groupby("species")
            .size()
            .sort_values(ascending=False)
            .head(15)
            .reset_index(name="count")
        )
        bar = (
            alt.Chart(top)
            .mark_bar()
            .encode(
                x=alt.X("count:Q", title="Count"),
                y=alt.Y("species:N", sort="-x", title="Species"),
                tooltip=["species", "count"],
            )
        )
        st.altair_chart(bar, use_container_width=True)

st.subheader("Events table")
show_cols = [c for c in ["datetime", "date", "time", "temp_f", "event_type", "species", "species_conf", "filename"] if c in f.columns]
st.dataframe(f[show_cols].sort_values(by="datetime", ascending=False) if "datetime" in f.columns else f[show_cols], use_container_width=True)

st.divider()
st.caption(f"Auto-refresh: cached for {CACHE_TTL_SECONDS//3600}h (change in Streamlit secrets).")