import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ---------------------------
# Page config + small UI polish
# ---------------------------
st.set_page_config(page_title="Ranch Camera Dashboard", page_icon="🦌", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
      h1, h2, h3 { letter-spacing: -0.02em; }
      div[data-testid="stMetricValue"] { font-size: 1.6rem; }
      div[data-testid="stMetricLabel"] { font-size: 0.9rem; opacity: 0.8; }
      .stDataFrame { border-radius: 12px; overflow: hidden; }
      .stAlert { border-radius: 12px; }
      section[data-testid="stSidebar"] { padding-top: 1rem; }
      .small-muted { opacity: 0.75; font-size: 0.9rem; }
      .card {
        padding: 0.9rem 1rem;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.08);
        background: rgba(255,255,255,0.02);
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Ranch Camera Dashboard")
st.caption("📌 events.csv pulled from Google Drive")


# ---------------------------
# Settings (secrets)
# ---------------------------
DRIVE_FILE_ID = st.secrets["gdrive"]["file_id"]
CACHE_TTL_SECONDS = int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60))

# Optional: folder that contains the original images on Drive
# If provided, the app will map filename -> Drive fileId automatically.
IMAGES_FOLDER_ID = (st.secrets.get("gdrive", {}).get("images_folder_id") or "").strip()


# ---------------------------
# Google Drive client + helpers
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
    NOTE: Works best if all images are in ONE folder on Drive.
    """
    if not folder_id:
        return {}

    service = _drive_client()
    out = {}
    page_token = None

    # Only fetch what we need
    fields = "nextPageToken, files(id,name,webViewLink,mimeType,trashed)"

    # Query for files in folder
    q = f"'{folder_id}' in parents and trashed=false"

    while True:
        resp = (
            service.files()
            .list(
                q=q,
                fields=fields,
                pageToken=page_token,
                pageSize=1000,
            )
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


# ---------------------------
# Cleaning helpers
# ---------------------------
def _after_last_semicolon(s: str) -> str:
    if not s:
        return ""
    parts = [p.strip() for p in str(s).split(";") if p.strip()]
    return parts[-1] if parts else str(s).strip()


def normalize_species(raw: str) -> str:
    """If contains vehicle/human/person anywhere -> normalize. Else keep only after last semicolon."""
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


def safe_float_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


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

for col in ["date", "time", "event_type", "species", "filename"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

if "temp_f" in df.columns:
    df["temp_f"] = safe_float_series(df["temp_f"])

if "event_type" in df.columns:
    df["event_type"] = df["event_type"].map(normalize_event_type)

if "species" in df.columns:
    df["species"] = df["species"].map(normalize_species)

for i in (1, 2, 3):
    c = f"top{i}_species"
    if c in df.columns:
        df[c] = df[c].fillna("").astype(str).map(normalize_species)

if "date" in df.columns and "time" in df.columns:
    df["datetime"] = build_datetime(df)
else:
    df["datetime"] = pd.NaT


# ---------------------------
# Image link mapping (optional)
# ---------------------------
# Preferred: events.csv has image_drive_id or image_url
# Fallback: map by filename using a Drive folder listing
image_map = {}
if IMAGES_FOLDER_ID:
    with st.spinner("Indexing image folder on Google Drive… (cached)"):
        image_map = list_images_in_folder(IMAGES_FOLDER_ID)


def resolve_image_link(row: pd.Series) -> tuple[str, str]:
    """
    Returns: (url, file_id)
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
# Sidebar filters (global)
# ---------------------------
st.sidebar.header("Filters")

df_dt = df.dropna(subset=["datetime"]).copy()
if not df_dt.empty:
    min_dt = df_dt["datetime"].min()
    max_dt = df_dt["datetime"].max()
    date_range = st.sidebar.date_input("Date range", value=(min_dt.date(), max_dt.date()))
else:
    date_range = None
    st.sidebar.info("No valid datetime values found.")

# Temp filter (°F only)
temp_minmax = None
if "temp_f" in df.columns and df["temp_f"].notna().any():
    tmin = int(df["temp_f"].min())
    tmax = int(df["temp_f"].max())
    temp_minmax = st.sidebar.slider("Temp (°F)", min_value=tmin, max_value=tmax, value=(tmin, tmax))

st.sidebar.markdown(
    f'<div class="small-muted">Cache TTL: {CACHE_TTL_SECONDS//3600}h</div>',
    unsafe_allow_html=True,
)

# Apply global filters (date/temp only)
base = df.copy()
if date_range and "datetime" in base.columns and len(date_range) == 2:
    start, end = date_range
    base = base.dropna(subset=["datetime"])
    base = base[(base["datetime"].dt.date >= start) & (base["datetime"].dt.date <= end)]

if temp_minmax and "temp_f" in base.columns:
    lo, hi = temp_minmax
    base = base[(base["temp_f"] >= lo) & (base["temp_f"] <= hi)]

animals_df = base[base.get("event_type", "") == "animal"].copy() if "event_type" in base.columns else base.iloc[0:0].copy()
hv_df = base[base.get("event_type", "").isin(["human", "vehicle"])].copy() if "event_type" in base.columns else base.iloc[0:0].copy()


# ---------------------------
# KPI row (global)
# ---------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Filtered events", f"{len(base):,}")
k2.metric("Animals", f"{len(animals_df):,}")
k3.metric("Humans", f"{int((hv_df.get('event_type', pd.Series(dtype=str)) == 'human').sum()):,}")
k4.metric("Vehicles", f"{int((hv_df.get('event_type', pd.Series(dtype=str)) == 'vehicle').sum()):,}")


# ---------------------------
# Tabs: Animals / Humans+Vehicles / Table
# ---------------------------
tab_animals, tab_hv, tab_table = st.tabs(["🦌 Animals", "🚙 Humans & Vehicles", "🗂️ All Events"])

DOT_SIZE = 160  # bigger dots


with tab_animals:
    st.subheader("Animals — Temp (°F) vs Time")

    # Animal-only species filter
    species_options = sorted([s for s in animals_df.get("species", pd.Series(dtype=str)).unique() if s and s not in ("human", "vehicle")])
    chosen_species = st.multiselect("Filter animal species", options=species_options, default=[])

    a = animals_df.copy()
    if chosen_species:
        a = a[a["species"].isin(chosen_species)]

    c1, c2 = st.columns([2, 1])

    with c1:
        if not a.empty and a["datetime"].notna().any():
            chart_df = a.dropna(subset=["datetime"]).copy()

            # Nice scatter: color by species (limited cardinality)
            # If too many species, fallback to a single color by leaving color unset
            use_color = chart_df["species"].nunique() <= 20

            enc = {
                "x": alt.X("datetime:T", title="Time"),
                "y": alt.Y("temp_f:Q", title="Temp (°F)"),
                "tooltip": [
                    "filename:N",
                    alt.Tooltip("datetime:T", title="Time"),
                    alt.Tooltip("temp_f:Q", title="Temp (°F)"),
                    "species:N",
                    "species_conf:N",
                ],
            }
            if use_color:
                enc["color"] = alt.Color("species:N", title="Species")

            chart = (
                alt.Chart(chart_df)
                .mark_circle(size=DOT_SIZE, opacity=0.80)
                .encode(**enc)
                .interactive()
            )

            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No animal data in the current filter window.")

    with c2:
        st.subheader("Top animal species")
        if not a.empty and "species" in a.columns:
            top = (
                a[(a["species"] != "") & (~a["species"].isin(["human", "vehicle"]))]
                .groupby("species")
                .size()
                .sort_values(ascending=False)
                .head(15)
                .reset_index(name="count")
            )
            if top.empty:
                st.info("No animal species to show.")
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

    st.markdown("---")
    st.subheader("Pick an animal event → open image in Drive")

    # Table with row selection (best way to “click → open image” reliably)
    cols = [c for c in ["datetime", "temp_f", "species", "species_conf", "filename"] if c in a.columns]
    a_table = a.sort_values(by="datetime", ascending=False) if "datetime" in a.columns else a

    selection = None
    try:
        selection = st.dataframe(
            a_table[cols],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
    except TypeError:
        # Older Streamlit fallback: use selectbox
        st.info("Your Streamlit version doesn’t support row selection here — using a dropdown fallback.")
        label_series = (
            a_table["datetime"].astype(str) + " • " + a_table.get("species", "").astype(str) + " • " + a_table.get("filename", "").astype(str)
            if "datetime" in a_table.columns
            else a_table.get("filename", pd.Series(dtype=str)).astype(str)
        )
        idx = st.selectbox("Select an event", options=list(range(len(a_table))), format_func=lambda i: label_series.iloc[i] if i < len(label_series) else str(i))
        selection = {"selection": {"rows": [idx]}}

    sel_rows = (selection or {}).get("selection", {}).get("rows", [])
    if sel_rows:
        idx = sel_rows[0]
        row = a_table.iloc[idx]
        url, fid = resolve_image_link(row)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f"**Selected:** `{row.get('filename','')}`")
        st.markdown(f"- **Time:** {row.get('datetime','')}")
        st.markdown(f"- **Temp (°F):** {row.get('temp_f','')}")
        st.markdown(f"- **Species:** {row.get('species','')}  ({row.get('species_conf','')})")

        if url:
            st.markdown(f"🔗 **Open image in Drive:** {url}")
        else:
            st.warning(
                "No Drive link available for this image.\n\n"
                "Best fix: add `image_drive_id` (or `image_url`) to events.csv, "
                "or set `gdrive.images_folder_id` in Streamlit secrets so the app can map filenames."
            )

        # Optional quick preview if we have a fileId
        if fid:
            if st.checkbox("Show image preview (downloads image from Drive)"):
                try:
                    service = _drive_client()
                    img_bytes = _download_drive_file_bytes(service, fid)
                    st.image(img_bytes, use_container_width=True)
                except Exception as e:
                    st.error(f"Could not preview image: {e}")

        st.markdown("</div>", unsafe_allow_html=True)


with tab_hv:
    st.subheader("Humans & Vehicles — completely separated from animals")

    if hv_df.empty:
        st.info("No human/vehicle events in the current filter window.")
    else:
        # Split explicitly
        humans = hv_df[hv_df["event_type"] == "human"].copy()
        vehicles = hv_df[hv_df["event_type"] == "vehicle"].copy()

        st.markdown("### Temp (°F) vs Time")
        chart_df = hv_df.dropna(subset=["datetime"]).copy()
        if chart_df.empty:
            st.info("No valid datetime values to chart.")
        else:
            chart = (
                alt.Chart(chart_df)
                .mark_circle(size=DOT_SIZE, opacity=0.85)
                .encode(
                    x=alt.X("datetime:T", title="Time"),
                    y=alt.Y("temp_f:Q", title="Temp (°F)"),
                    color=alt.Color("event_type:N", title="Type"),
                    tooltip=[
                        "filename:N",
                        alt.Tooltip("datetime:T", title="Time"),
                        alt.Tooltip("temp_f:Q", title="Temp (°F)"),
                        "event_type:N",
                    ],
                )
                .interactive()
            )
            st.altair_chart(chart, use_container_width=True)

        st.markdown("---")
        st.markdown("### Counts")
        c1, c2 = st.columns(2)
        c1.metric("Humans", f"{len(humans):,}")
        c2.metric("Vehicles", f"{len(vehicles):,}")

        st.markdown("---")
        st.subheader("Pick a human/vehicle event → open image in Drive")

        cols = [c for c in ["datetime", "temp_f", "event_type", "filename"] if c in hv_df.columns]
        hv_table = hv_df.sort_values(by="datetime", ascending=False)

        selection = None
        try:
            selection = st.dataframe(
                hv_table[cols],
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )
        except TypeError:
            st.info("Your Streamlit version doesn’t support row selection here — using a dropdown fallback.")
            label_series = hv_table["datetime"].astype(str) + " • " + hv_table["event_type"].astype(str) + " • " + hv_table["filename"].astype(str)
            idx = st.selectbox("Select an event", options=list(range(len(hv_table))), format_func=lambda i: label_series.iloc[i] if i < len(label_series) else str(i))
            selection = {"selection": {"rows": [idx]}}

        sel_rows = (selection or {}).get("selection", {}).get("rows", [])
        if sel_rows:
            idx = sel_rows[0]
            row = hv_table.iloc[idx]
            url, fid = resolve_image_link(row)

            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(f"**Selected:** `{row.get('filename','')}`")
            st.markdown(f"- **Time:** {row.get('datetime','')}")
            st.markdown(f"- **Temp (°F):** {row.get('temp_f','')}")
            st.markdown(f"- **Type:** {row.get('event_type','')}")

            if url:
                st.markdown(f"🔗 **Open image in Drive:** {url}")
            else:
                st.warning(
                    "No Drive link available for this image.\n\n"
                    "Best fix: add `image_drive_id` (or `image_url`) to events.csv, "
                    "or set `gdrive.images_folder_id` in Streamlit secrets so the app can map filenames."
                )

            if fid:
                if st.checkbox("Show image preview (downloads image from Drive)", key="hv_preview"):
                    try:
                        service = _drive_client()
                        img_bytes = _download_drive_file_bytes(service, fid)
                        st.image(img_bytes, use_container_width=True)
                    except Exception as e:
                        st.error(f"Could not preview image: {e}")

            st.markdown("</div>", unsafe_allow_html=True)


with tab_table:
    st.subheader("All Events (for searching / auditing)")

    show_cols = [c for c in [
        "datetime", "temp_f", "event_type", "species", "species_conf",
        "top1_species", "top1_conf", "top2_species", "top2_conf", "top3_species", "top3_conf",
        "filename"
    ] if c in base.columns]

    st.dataframe(
        base.sort_values(by="datetime", ascending=False) if "datetime" in base.columns else base,
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.caption(
    f"✅ Google Drive source: {df.attrs.get('drive_name','events.csv')} • "
    f"cached {CACHE_TTL_SECONDS//3600}h • "
    f"last modified {last_mod_pretty}"
)