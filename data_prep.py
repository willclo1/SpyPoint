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


def get_moon_emoji(phase: str) -> str:
    """Return emoji for moon phase"""
    if pd.isna(phase):
        return ""
    
    phase = str(phase).strip().lower()
    
    moon_map = {
        "new moon": "🌑",
        "new": "🌑",
        "waxing crescent": "🌒",
        "first quarter": "🌓",
        "waxing gibbous": "🌔",
        "full moon": "🌕",
        "full": "🌕",
        "waning gibbous": "🌖",
        "last quarter": "🌗",
        "third quarter": "🌗",
        "waning crescent": "🌘",
    }
    
    return moon_map.get(phase, "🌙")


def standardize_moon_phase(phase: str) -> str:
    """Standardize moon phase naming for consistency"""
    if pd.isna(phase):
        return ""
    
    phase_lower = str(phase).strip().lower()
    
    # Map common variations to standard names
    phase_map = {
        "new moon": "New Moon",
        "new": "New Moon",
        "waxing crescent": "Waxing Crescent",
        "first quarter": "First Quarter",
        "waxing gibbous": "Waxing Gibbous",
        "full moon": "Full Moon",
        "full": "Full Moon",
        "waning gibbous": "Waning Gibbous",
        "last quarter": "Last Quarter",
        "third quarter": "Last Quarter",
        "waning crescent": "Waning Crescent",
    }
    
    return phase_map.get(phase_lower, str(phase).strip().title())


def prep_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize event data with vectorized pandas operations."""
    out = df.copy()

    required = [
        "camera", "filename", "event_type", "species_clean", "species_group",
        "date", "time", "temp_f", "moon_phase", "moon_illumination", "moon_age_days",
    ]
    for col in required:
        if col not in out.columns:
            out[col] = ""

    text_cols = [
        "camera", "filename", "event_type", "species_clean", "species_group",
        "date", "time", "moon_phase",
    ]
    for col in text_cols:
        out[col] = out[col].fillna("").astype(str).str.strip()

    out["event_type"] = out["event_type"].str.lower().replace({"person": "human", "people": "human"})
    out["temp_f"] = pd.to_numeric(out["temp_f"], errors="coerce")
    out["moon_illumination"] = pd.to_numeric(out["moon_illumination"], errors="coerce")
    out["moon_age_days"] = pd.to_numeric(out["moon_age_days"], errors="coerce")
    out["datetime"] = build_datetime(out)

    out["wildlife_label"] = out["species_group"].where(out["species_group"].ne(""), out["species_clean"])
    out["wildlife_label"] = out["wildlife_label"].replace("", "Other")

    phase_map = {
        "new moon": "New Moon", "new": "New Moon",
        "waxing crescent": "Waxing Crescent", "first quarter": "First Quarter",
        "waxing gibbous": "Waxing Gibbous", "full moon": "Full Moon", "full": "Full Moon",
        "waning gibbous": "Waning Gibbous", "last quarter": "Last Quarter",
        "third quarter": "Last Quarter", "waning crescent": "Waning Crescent",
    }
    emoji_map = {
        "new moon": "🌑", "new": "🌑", "waxing crescent": "🌒",
        "first quarter": "🌓", "waxing gibbous": "🌔", "full moon": "🌕",
        "full": "🌕", "waning gibbous": "🌖", "last quarter": "🌗",
        "third quarter": "🌗", "waning crescent": "🌘",
    }
    phase_key = out["moon_phase"].str.lower()
    out["moon_phase_clean"] = phase_key.map(phase_map).fillna(out["moon_phase"].str.title())
    out["moon_emoji"] = phase_key.map(emoji_map).fillna("🌙")
    out.loc[out["moon_phase"].eq(""), ["moon_phase_clean", "moon_emoji"]] = ""

    identity = (
        out["camera"] + "|" + out["filename"] + "|" + out["date"] + "|" + out["time"]
    )
    out["event_id"] = identity.map(lambda value: hashlib.md5(value.encode("utf-8")).hexdigest()[:10])

    when = out["datetime"].dt.strftime("%b %d %I:%M %p").fillna("Unknown time")
    label = out["wildlife_label"].copy()
    human_vehicle = out["event_type"].isin(["human", "vehicle"])
    label.loc[human_vehicle] = out.loc[human_vehicle, "event_type"].str.capitalize()
    suffix = out["filename"].str[-8:]
    out["friendly_name"] = when + " • " + out["camera"].replace("", "unknown") + " • " + label + " • " + suffix

    return out
