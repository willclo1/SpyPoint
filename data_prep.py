# data_prep.py
import hashlib
from datetime import datetime
from typing import Tuple

import pandas as pd


def nice_last_modified(iso: str) -> str:
    if not iso:
        return "?"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso


def clamp_temp_domain(min_v, max_v) -> Tuple[float, float]:
    try:
        min_v = float(min_v)
    except Exception:
        min_v = 10.0
    try:
        max_v = float(max_v)
    except Exception:
        max_v = 90.0

    lo = min(10.0, min_v)
    hi = max(90.0, max_v)
    if hi - lo < 20:
        mid = (hi + lo) / 2
        lo = mid - 10
        hi = mid + 10
    return lo, hi


def build_datetime(df: pd.DataFrame) -> pd.Series:
    date_s = df.get("date", pd.Series([""] * len(df))).astype(str).fillna("").str.strip()
    time_s = df.get("time", pd.Series([""] * len(df))).astype(str).fillna("").str.strip()
    return pd.to_datetime((date_s + " " + time_s).str.strip(), errors="coerce")


def make_event_id(row) -> str:
    base = f"{row.get('camera','')}|{row.get('filename','')}|{row.get('date','')}|{row.get('time','')}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()[:10]


def make_friendly_name(row) -> str:
    dt = row.get("datetime")
    when = dt.strftime("%b %d %I:%M %p") if pd.notna(dt) else "Unknown time"
    cam = (row.get("camera") or "unknown").strip()
    et = (row.get("event_type") or "").strip().lower()

    if et in ("human", "vehicle"):
        label = et.capitalize()
    else:
        label = (row.get("wildlife_label") or row.get("species_clean") or "Other").strip()
        if not label:
            label = "Other"

    fn = (row.get("filename") or "").strip()
    suffix = fn[-8:] if len(fn) >= 8 else fn
    return f"{when} • {cam} • {label} • {suffix}"


def prep_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trust pipeline columns:
      - event_type
      - species_clean
      - species_group
    """
    out = df.copy()

    for col in ["camera", "filename", "event_type", "species_clean", "species_group", "date", "time", "temp_f"]:
        if col not in out.columns:
            out[col] = ""

    out["camera"] = out["camera"].fillna("").astype(str).str.strip()
    out["filename"] = out["filename"].fillna("").astype(str).str.strip()

    out["event_type"] = (
        out["event_type"].fillna("").astype(str).str.strip().str.lower()
        .replace({"person": "human", "people": "human"})
    )

    out["temp_f"] = pd.to_numeric(out["temp_f"], errors="coerce")
    out["datetime"] = build_datetime(out)

    out["species_clean"] = out["species_clean"].fillna("").astype(str).str.strip()
    out["species_group"] = out["species_group"].fillna("").astype(str).str.strip()

    # Wildlife label preference: group -> clean -> Other
    out["wildlife_label"] = out["species_group"]
    out.loc[out["wildlife_label"] == "", "wildlife_label"] = out["species_clean"]
    out.loc[out["wildlife_label"] == "", "wildlife_label"] = "Other"

    out["event_id"] = out.apply(make_event_id, axis=1)
    out["friendly_name"] = out.apply(make_friendly_name, axis=1)

    return out
