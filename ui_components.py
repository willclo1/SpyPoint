# ui_components.py
from typing import Dict, Tuple
import base64
import io
import hashlib

import altair as alt
import pandas as pd
import streamlit as st

from data_prep import clamp_temp_domain
from drive_io import resolve_image_link


@st.cache_data(ttl=3600)
def load_thumbnail_cached(file_id: str, _drive_client_factory, _download_bytes_func):
    """Cache thumbnail downloads to avoid repeated API calls."""
    try:
        service = _drive_client_factory()
        img_bytes = _download_bytes_func(service, file_id)
        return img_bytes
    except Exception as e:
        return None


def inject_css():
    st.markdown(
        """
        <style>
          /* Fix tabs being covered by header */
          .stTabs [data-baseweb="tab-list"] {
            margin-top: 1rem;
          }
          
          /* Base Layout */
          .block-container { 
            padding-top: 3rem; 
            padding-bottom: 2.5rem; 
            max-width: 1400px; 
          }
          
          /* Typography */
          h1, h2, h3 { 
            letter-spacing: -0.02em; 
            font-weight: 600;
          }
          h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
          h2 { font-size: 1.75rem; margin-bottom: 1rem; }
          h3 { font-size: 1.35rem; margin-bottom: 0.75rem; }
          
          .small-muted { 
            opacity: 0.6; 
            font-size: 0.9rem; 
          }
          
          /* Metrics Cards */
          div[data-testid="stMetricValue"] { 
            font-size: 2rem; 
            font-weight: 600;
          }
          div[data-testid="stMetricLabel"] { 
            font-size: 0.9rem; 
            opacity: 0.7;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 500;
          }
          
          /* Sidebar */
          section[data-testid="stSidebar"] { 
            padding-top: 1rem;
            background: rgba(0,0,0,0.02);
          }
          section[data-testid="stSidebar"] > div {
            padding-top: 2rem;
          }
          
          /* Buttons */
          button[kind="secondary"], 
          button[kind="primary"] { 
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.2s ease;
          }
          
          /* Alert Boxes */
          .stAlert { 
            border-radius: 10px;
            border-left: 4px solid;
          }
          
          /* Data Frames */
          .stDataFrame { 
            border-radius: 10px; 
            overflow: hidden;
          }
          
          /* ============================================
             SIGHTING CARD GALLERY
             ============================================ */
          
          .card-gallery {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin-top: 1rem;
          }
          
          .sighting-card {
            background: rgba(255,255,255,0.03);
            border: 1.5px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 0;
            transition: all 0.2s ease;
            position: relative;
            overflow: hidden;
          }
          
          .sighting-card:hover {
            background: rgba(255,255,255,0.06);
            border-color: rgba(255,255,255,0.25);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
          }
          
          .card-thumbnail {
            width: 100%;
            height: 160px;
            background: rgba(0,0,0,0.3);
            border-radius: 0;
            margin-bottom: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
          }
          
          .card-content {
            padding: 0.85rem;
          }
          
          .card-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
          }
          
          .card-thumbnail-placeholder {
            font-size: 2.5rem;
            opacity: 0.3;
          }
          
          .card-title {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.4rem;
            line-height: 1.3;
          }
          
          .card-meta {
            font-size: 0.85rem;
            opacity: 0.7;
            margin-bottom: 0.25rem;
          }
          
          .card-temp {
            font-size: 0.85rem;
            opacity: 0.6;
          }
          
          /* ============================================
             PHOTO DETAIL VIEWER
             ============================================ */
          
          .photo-viewer-container {
            background: linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.02) 100%);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 12px;
            padding: 1.5rem;
            margin-top: 1.5rem;
          }
          
          .photo-main {
            width: 100%;
            border-radius: 8px;
            overflow: hidden;
            background: #000;
            margin-bottom: 1.5rem;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
          }
          
          .photo-main img {
            width: 100%;
            height: auto;
            display: block;
          }
          
          .photo-loading {
            width: 100%;
            height: 400px;
            background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);
            background-size: 200% 100%;
            animation: loading 1.5s ease-in-out infinite;
            border-radius: 8px;
          }
          
          @keyframes loading {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
          }
          
          .metadata-section {
            margin-bottom: 1.5rem;
          }
          
          .metadata-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
          }
          
          .metadata-item {
            background: rgba(255,255,255,0.02);
            padding: 0.75rem;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.06);
          }
          
          .metadata-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            opacity: 0.5;
            margin-bottom: 0.35rem;
            font-weight: 600;
          }
          
          .metadata-value {
            font-size: 1rem;
            font-weight: 500;
          }
          
          .insights-box {
            background: rgba(76,175,80,0.08);
            border: 1px solid rgba(76,175,80,0.2);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1.5rem;
          }
          
          .insights-box.people {
            background: rgba(33,150,243,0.08);
            border-color: rgba(33,150,243,0.2);
          }
          
          .insights-box.vehicle {
            background: rgba(255,152,0,0.08);
            border-color: rgba(255,152,0,0.2);
          }
          
          .insights-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            opacity: 0.7;
            margin-bottom: 0.5rem;
            font-weight: 600;
          }
          
          .insight-item {
            font-size: 0.9rem;
            margin-bottom: 0.25rem;
            opacity: 0.85;
          }
          
          .file-info {
            font-size: 0.8rem;
            opacity: 0.5;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255,255,255,0.08);
          }
          
          .load-more-btn {
            text-align: center;
            margin-top: 1rem;
          }
          
          /* Chart styling */
          .vega-embed { 
            padding: 0 !important; 
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_timeline(base: pd.DataFrame, section: str):
    st.subheader("Timeline")
    st.caption("Each dot represents one sighting")

    chart_df = base.dropna(subset=["datetime", "temp_f"]).copy()
    if chart_df.empty:
        st.info("No temperature data available for timeline visualization")
        return

    if section == "Wildlife":
        counts = chart_df.groupby("wildlife_label").size().sort_values(ascending=False)
        top = counts.head(10).index.tolist()
        chart_df["wildlife_group_chart"] = chart_df["wildlife_label"].where(
            chart_df["wildlife_label"].isin(top),
            other="Other",
        )

        color_enc = alt.Color(
            "wildlife_group_chart:N", 
            title="Animal",
            scale=alt.Scale(scheme='category20')
        )
        tooltip = [
            alt.Tooltip("datetime:T", title="Time"),
            alt.Tooltip("temp_f:Q", title="Temperature", format=".0f"),
            alt.Tooltip("wildlife_label:N", title="Animal"),
            alt.Tooltip("camera:N", title="Camera"),
        ]
    else:
        chart_df["type_label"] = section.lower()
        color_map = {"wildlife": "#4CAF50", "people": "#2196F3", "vehicle": "#FF9800"}
        color = color_map.get(section.lower(), "#4CAF50")
        color_enc = alt.Color("type_label:N", legend=None, scale=alt.Scale(range=[color]))
        tooltip = [
            alt.Tooltip("datetime:T", title="Time"),
            alt.Tooltip("temp_f:Q", title="Temperature", format=".0f"),
            alt.Tooltip("camera:N", title="Camera"),
        ]

    y_lo, y_hi = clamp_temp_domain(chart_df["temp_f"].min(), chart_df["temp_f"].max())

    scatter = (
        alt.Chart(chart_df)
        .mark_circle(size=200, opacity=0.7)
        .encode(
            x=alt.X("datetime:T", title="Date & Time"),
            y=alt.Y("temp_f:Q", title="Temperature (°F)", scale=alt.Scale(domain=[y_lo, y_hi])),
            color=color_enc,
            tooltip=tooltip,
        )
        .properties(height=300)
        .interactive()
    )
    st.altair_chart(scatter, use_container_width=True)


def render_patterns(base: pd.DataFrame, section: str, include_other: bool, bar_style: str, time_gran: str):
    st.subheader("Activity Patterns")

    patt = base.dropna(subset=["datetime"]).copy()
    patt["weekday"] = patt["datetime"].dt.day_name()
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    patt["hour"] = patt["datetime"].dt.hour
    if time_gran == "2-hour":
        patt["time_bin"] = (patt["hour"] // 2) * 2
        patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
    elif time_gran == "4-hour":
        patt["time_bin"] = (patt["hour"] // 4) * 4
        patt["time_label"] = patt["time_bin"].astype(int).astype(str) + ":00"
    else:
        patt["time_label"] = patt["hour"].astype(int).astype(str) + ":00"

    if section != "Wildlife":
        color_map = {"People": "#2196F3", "Vehicles": "#FF9800"}
        chart_color = color_map.get(section, "#4CAF50")
        
        by_time = patt.groupby("time_label").size().reset_index(name="Sightings")
        by_time["__h"] = by_time["time_label"].str.split(":").str[0].astype(int)
        by_time = by_time.sort_values("__h")

        time_chart = (
            alt.Chart(by_time)
            .mark_bar(color=chart_color, opacity=0.8)
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=by_time["time_label"].tolist(), axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                tooltip=[alt.Tooltip("time_label:N", title="Time"), alt.Tooltip("Sightings:Q", title="Count")],
            )
            .properties(height=250)
        )

        by_day = patt.groupby("weekday").size().reindex(weekday_order, fill_value=0).reset_index(name="Sightings")
        by_day.columns = ["weekday", "Sightings"]

        day_chart = (
            alt.Chart(by_day)
            .mark_bar(color=chart_color, opacity=0.8)
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Count"),
                tooltip=[alt.Tooltip("weekday:N", title="Day"), alt.Tooltip("Sightings:Q", title="Count")],
            )
            .properties(height=250)
        )

        cA, cB = st.columns(2)
        with cA:
            st.markdown("**By Time of Day**")
            st.altair_chart(time_chart, use_container_width=True)
        with cB:
            st.markdown("**By Day of Week**")
            st.altair_chart(day_chart, use_container_width=True)
        return

    # Wildlife
    if not include_other:
        patt = patt[patt["wildlife_label"] != "Other"]

    sp_counts = patt.groupby("wildlife_label").size().sort_values(ascending=False)
    top_species = sp_counts.head(8).index.tolist()
    patt["animal_group"] = patt["wildlife_label"].where(patt["wildlife_label"].isin(top_species), other="Other")

    by_time = patt.groupby(["time_label", "animal_group"]).size().reset_index(name="Sightings")

    def _time_sort_key(x: str) -> int:
        try:
            return int(x.split(":")[0])
        except Exception:
            return 0

    time_order = sorted(by_time["time_label"].unique().tolist(), key=_time_sort_key)

    if bar_style == "Grouped":
        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=alt.Color("animal_group:N", title="Animal", scale=alt.Scale(scheme='category20')),
                xOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("time_label:N", title="Time"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )
    else:
        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Count"),
                color=alt.Color("animal_group:N", title="Animal", scale=alt.Scale(scheme='category20')),
                tooltip=[
                    alt.Tooltip("time_label:N", title="Time"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )

    by_day = patt.groupby(["weekday", "animal_group"]).size().reset_index(name="Sightings")
    by_day["weekday"] = pd.Categorical(by_day["weekday"], categories=weekday_order, ordered=True)
    by_day = by_day.sort_values(["weekday", "animal_group"])

    if bar_style == "Grouped":
        day_chart = (
            alt.Chart(by_day)
            .mark_bar()
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Count"),
                color=alt.Color("animal_group:N", title="Animal", scale=alt.Scale(scheme='category20')),
                yOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("weekday:N", title="Day"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )
    else:
        day_chart = (
            alt.Chart(by_day)
            .mark_bar()
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Count"),
                color=alt.Color("animal_group:N", title="Animal", scale=alt.Scale(scheme='category20')),
                tooltip=[
                    alt.Tooltip("weekday:N", title="Day"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Count"),
                ],
            )
            .properties(height=250)
        )

    cA, cB = st.columns(2)
    with cA:
        st.markdown("**By Time of Day**")
        st.altair_chart(time_chart, use_container_width=True)
    with cB:
        st.markdown("**By Day of Week**")
        st.altair_chart(day_chart, use_container_width=True)


def _calculate_insights(row, base: pd.DataFrame, section: str):
    """Generate contextual insights for selected sighting."""
    insights = []
    
    cam = row.get("camera", "").strip()
    dt = row.get("datetime")
    
    if pd.isna(dt):
        return insights
    
    # Same camera, same day
    same_day = base[
        (base["camera"] == cam) & 
        (base["datetime"].dt.date == dt.date())
    ]
    
    if len(same_day) > 1:
        if section == "Wildlife":
            animal = row.get("wildlife_label", "")
            same_animal_count = len(same_day[same_day["wildlife_label"] == animal])
            if same_animal_count > 1:
                insights.append(f"{same_animal_count} {animal} sightings at {cam} today")
            else:
                insights.append(f"{len(same_day)} total sightings at {cam} today")
        else:
            insights.append(f"{len(same_day)} sightings at {cam} today")
    
    # Temperature context
    temp = row.get("temp_f")
    if pd.notna(temp):
        yesterday = dt - pd.Timedelta(days=1)
        yesterday_data = base[
            (base["datetime"] >= yesterday) & 
            (base["datetime"] < dt - pd.Timedelta(hours=12))
        ]
        if not yesterday_data.empty and yesterday_data["temp_f"].notna().any():
            avg_yesterday = yesterday_data["temp_f"].mean()
            diff = temp - avg_yesterday
            if abs(diff) > 5:
                direction = "warmer" if diff > 0 else "cooler"
                insights.append(f"{abs(int(diff))}°F {direction} than previous day")
    
    # Peak activity time
    if section == "Wildlife":
        animal = row.get("wildlife_label", "")
        animal_data = base[base["wildlife_label"] == animal]
        if len(animal_data) > 5:
            hour_counts = animal_data["datetime"].dt.hour.value_counts()
            peak_hour = hour_counts.idxmax()
            insights.append(f"Peak activity: {peak_hour}:00-{peak_hour+1}:00")
    
    return insights


def render_listing_and_viewer(
    base: pd.DataFrame,
    section: str,
    include_other: bool,
    image_index: Dict,
    drive_client_factory,
    download_bytes_func,
):
    """
    Photo gallery - no selection, just browsing
    """
    
    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    if section == "Wildlife" and not include_other:
        view = view[view["wildlife_label"] != "Other"]

    # Search
    q = st.text_input("Search by animal, camera, or filename", value="", key="search_input")
    if q.strip():
        ql = q.strip().lower()
        mask = (
            view["wildlife_label"].astype(str).str.lower().str.contains(ql, na=False)
            | view["camera"].astype(str).str.lower().str.contains(ql, na=False)
            | view["filename"].astype(str).str.lower().str.contains(ql, na=False)
        )
        view = view[mask]

    if view.empty:
        st.info("No sightings match your search")
        return

    # Pagination
    if "gallery_limit" not in st.session_state:
        st.session_state.gallery_limit = 8
    
    display_view = view.head(st.session_state.gallery_limit)
    
    # Photo Gallery - simple display, no selection
    cols_per_row = 2
    rows = (len(display_view) + cols_per_row - 1) // cols_per_row
    
    for row_idx in range(rows):
        cols = st.columns(cols_per_row)
        
        for col_idx in range(cols_per_row):
            item_idx = row_idx * cols_per_row + col_idx
            if item_idx >= len(display_view):
                break
            
            row = display_view.iloc[item_idx]
            event_id = row.get("event_id", "")
            cam = str(row.get("camera", "")).strip()
            fn = str(row.get("filename", "")).strip()
            dt = row.get("datetime")
            temp = row.get("temp_f")
            
            if section == "Wildlife":
                label = row.get("wildlife_label", "Other")
            else:
                label = (row.get("event_type", "")).capitalize()
            
            time_str = dt.strftime("%b %d, %I:%M %p") if pd.notna(dt) else "Unknown time"
            temp_str = f"{int(temp)}°F" if pd.notna(temp) else ""
            
            with cols[col_idx]:
                # Try to load thumbnail
                url, fid = resolve_image_link(cam, fn, image_index)
                
                # Card container (no selection)
                st.markdown('<div class="sighting-card">', unsafe_allow_html=True)
                
                # Thumbnail
                if fid:
                    img_bytes = load_thumbnail_cached(fid, drive_client_factory, download_bytes_func)
                    if img_bytes:
                        st.markdown('<div class="card-thumbnail">', unsafe_allow_html=True)
                        st.image(img_bytes, use_container_width=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="card-thumbnail"><div class="card-thumbnail-placeholder">📷</div></div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="card-thumbnail"><div class="card-thumbnail-placeholder">📷</div></div>', unsafe_allow_html=True)
                
                # Card content
                st.markdown('<div class="card-content">', unsafe_allow_html=True)
                st.markdown(f'<div class="card-title">{label} • {cam}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card-meta">{time_str}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card-temp">{temp_str}</div>', unsafe_allow_html=True)
                
                # Add Drive link
                if url:
                    st.markdown(f'<a href="{url}" target="_blank" style="font-size: 0.8rem; opacity: 0.7;">View in Drive</a>', unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
    
    # Load More button
    if len(view) > st.session_state.gallery_limit:
        st.markdown('<div class="load-more-btn">', unsafe_allow_html=True)
        if st.button(f"Load More ({len(view) - st.session_state.gallery_limit} remaining)", key=f"load_more_{section}"):
            st.session_state.gallery_limit += 8
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Load More button
    if len(view) > st.session_state.gallery_limit:
        st.markdown('<div class="load-more-btn">', unsafe_allow_html=True)
        if st.button(f"Load More ({len(view) - st.session_state.gallery_limit} remaining)", key="load_more"):
            st.session_state.gallery_limit += 8
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
