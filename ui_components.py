# ui_components.py
from typing import Dict, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from data_prep import clamp_temp_domain
from drive_io import resolve_image_link


def inject_css():
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


def render_timeline(base: pd.DataFrame, section: str):
    st.subheader("Timeline")
    st.caption("Each dot is one sighting.")

    chart_df = base.dropna(subset=["datetime", "temp_f"]).copy()
    if chart_df.empty:
        st.info("No temperature data available for charting.")
        return

    if section == "Wildlife":
        counts = chart_df.groupby("wildlife_label").size().sort_values(ascending=False)
        top = counts.head(10).index.tolist()
        chart_df["wildlife_group_chart"] = chart_df["wildlife_label"].where(
            chart_df["wildlife_label"].isin(top),
            other="Other",
        )

        color_enc = alt.Color("wildlife_group_chart:N", title="Animal")
        tooltip = [
            alt.Tooltip("datetime:T", title="Time"),
            alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
            alt.Tooltip("wildlife_label:N", title="Animal"),
            alt.Tooltip("camera:N", title="Camera"),
            alt.Tooltip("filename:N", title="File"),
        ]
    else:
        chart_df["type_label"] = section.lower()
        color_enc = alt.Color("type_label:N", legend=None)
        tooltip = [
            alt.Tooltip("datetime:T", title="Time"),
            alt.Tooltip("temp_f:Q", title="Temp (°F)", format=".0f"),
            alt.Tooltip("camera:N", title="Camera"),
            alt.Tooltip("filename:N", title="File"),
        ]

    y_lo, y_hi = clamp_temp_domain(chart_df["temp_f"].min(), chart_df["temp_f"].max())

    scatter = (
        alt.Chart(chart_df)
        .mark_circle(size=240, opacity=0.86)
        .encode(
            x=alt.X("datetime:T", title="Time"),
            y=alt.Y("temp_f:Q", title="Temperature (°F)", scale=alt.Scale(domain=[y_lo, y_hi])),
            color=color_enc,
            tooltip=tooltip,
        )
        .interactive()
    )
    st.altair_chart(scatter, width="stretch")


def render_patterns(base: pd.DataFrame, section: str, include_other: bool, bar_style: str, time_gran: str):
    st.subheader("Patterns")

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
        # People/Vehicles: simple counts
        by_time = patt.groupby("time_label").size().reset_index(name="Sightings")
        by_time["__h"] = by_time["time_label"].str.split(":").str[0].astype(int)
        by_time = by_time.sort_values("__h")

        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=by_time["time_label"].tolist(), axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Sightings"),
                tooltip=[alt.Tooltip("time_label:N", title="Time"), alt.Tooltip("Sightings:Q", title="Sightings")],
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
            st.markdown("**Time of day**")
            st.altair_chart(time_chart, width="stretch")
        with cB:
            st.markdown("**Day of week**")
            st.altair_chart(day_chart, width="stretch")
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
                y=alt.Y("Sightings:Q", title="Sightings"),
                color=alt.Color("animal_group:N", title="Animal"),
                xOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("time_label:N", title="Time"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Sightings"),
                ],
            )
        )
    else:
        time_chart = (
            alt.Chart(by_time)
            .mark_bar()
            .encode(
                x=alt.X("time_label:N", title="Time of Day", sort=time_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Sightings:Q", title="Sightings"),
                color=alt.Color("animal_group:N", title="Animal"),
                tooltip=[
                    alt.Tooltip("time_label:N", title="Time"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Sightings"),
                ],
            )
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
                x=alt.X("Sightings:Q", title="Sightings"),
                color=alt.Color("animal_group:N", title="Animal"),
                yOffset="animal_group:N",
                tooltip=[
                    alt.Tooltip("weekday:N", title="Day"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Sightings"),
                ],
            )
        )
    else:
        day_chart = (
            alt.Chart(by_day)
            .mark_bar()
            .encode(
                y=alt.Y("weekday:N", title="Day of Week", sort=weekday_order),
                x=alt.X("Sightings:Q", title="Sightings"),
                color=alt.Color("animal_group:N", title="Animal"),
                tooltip=[
                    alt.Tooltip("weekday:N", title="Day"),
                    alt.Tooltip("animal_group:N", title="Animal"),
                    alt.Tooltip("Sightings:Q", title="Sightings"),
                ],
            )
        )

    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Time of day**")
        st.altair_chart(time_chart, width="stretch")
    with cB:
        st.markdown("**Day of week**")
        st.altair_chart(day_chart, width="stretch")


def render_listing_and_viewer(
    base: pd.DataFrame,
    section: str,
    include_other: bool,
    image_index: Dict,
    drive_client_factory,
    download_bytes_func,
):
    """
    Adds your "table/listing of files" workflow:
      - show filtered events as a table
      - select one row
      - show photo + metadata
    """
    st.subheader("Browse Sightings")

    view = base.dropna(subset=["datetime"]).sort_values("datetime", ascending=False).copy()

    # Wildlife: hide Other by default (unless include_other)
    if section == "Wildlife" and not include_other:
        view = view[view["wildlife_label"] != "Other"]

    # Search
    q = st.text_input("Search (animal, camera, filename)", value="")
    if q.strip():
        ql = q.strip().lower()
        mask = (
            view["wildlife_label"].astype(str).str.lower().str.contains(ql, na=False)
            | view["camera"].astype(str).str.lower().str.contains(ql, na=False)
            | view["filename"].astype(str).str.lower().str.contains(ql, na=False)
        )
        view = view[mask]

    if view.empty:
        st.info("No sightings to show.")
        return

    # Listing table
    show = view.copy()
    if section == "Wildlife":
        label_col = "wildlife_label"
    else:
        label_col = "event_type"

    listing = show[[
        "event_id",
        "datetime",
        "camera",
        label_col,
        "temp_f",
        "filename",
        "friendly_name",
    ]].copy()

    listing.rename(columns={label_col: "label"}, inplace=True)
    listing["Select"] = False

    # Let user control how many rows to display
    limit = st.slider("Rows to show", min_value=50, max_value=500, value=150, step=50)
    listing = listing.head(limit)

    edited = st.data_editor(
        listing[["Select", "friendly_name", "datetime", "camera", "label", "temp_f", "filename"]],
        hide_index=True,
        use_container_width=True,
        disabled=["friendly_name", "datetime", "camera", "label", "temp_f", "filename"],
        column_config={
            "friendly_name": st.column_config.TextColumn("Sighting"),
            "temp_f": st.column_config.NumberColumn("Temp (°F)", format="%.0f"),
            "label": st.column_config.TextColumn("Animal/Type"),
        },
        key=f"listing_{section}",
    )

    chosen = edited[edited["Select"] == True]
    if chosen.empty:
        st.caption("Select a row above to preview it.")
        return

    chosen_name = chosen.iloc[0]["friendly_name"]
    row = show[show["friendly_name"] == chosen_name].iloc[0]

    cam = str(row.get("camera", "")).strip()
    fn = str(row.get("filename", "")).strip()
    url, fid = resolve_image_link(cam, fn, image_index)

    st.markdown("---")
    st.subheader("Selected Sighting")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"**{row.get('friendly_name','')}**")
    st.markdown(f"**Camera:** {cam or '—'}")
    st.markdown(f"**When:** {row.get('datetime')}")
    if pd.notna(row.get("temp_f")):
        st.markdown(f"**Temperature:** {int(round(float(row.get('temp_f'))))} °F")

    if section == "Wildlife":
        st.markdown(f"**Animal:** {row.get('wildlife_label') or 'Other'}")
    else:
        st.markdown(f"**Type:** {(row.get('event_type') or '').capitalize()}")

    st.markdown(f"**File:** `{fn}`")

    if url:
        st.link_button("Open in Google Drive", url)
    else:
        st.warning("Photo link not found in Drive for this row.")

    # Inline preview
    if fid and st.toggle("Show preview", value=True, key=f"preview_{section}"):
        try:
            service = drive_client_factory()
            img_bytes = download_bytes_func(service, fid)
            st.image(img_bytes, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load preview: {e}")

    st.markdown("</div>", unsafe_allow_html=True)
