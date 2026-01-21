# drive_io.py
import io
from typing import Dict, Tuple

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def drive_view_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


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


@st.cache_data(ttl=lambda: int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60)))
def load_events_from_drive(file_id: str):
    service = _drive_client()
    meta = service.files().get(fileId=file_id, fields="name,modifiedTime,size").execute()
    raw = _download_drive_file_bytes(service, file_id)

    import pandas as pd

    df = pd.read_csv(io.BytesIO(raw))
    df.attrs["drive_name"] = meta.get("name", "events.csv")
    df.attrs["drive_modified"] = meta.get("modifiedTime", "")
    df.attrs["drive_size"] = meta.get("size", "")
    return df


@st.cache_data(ttl=lambda: int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60)))
def list_camera_folders(root_folder_id: str) -> Dict[str, str]:
    service = _drive_client()
    q = f"'{root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    fields = "files(id,name)"
    resp = service.files().list(q=q, fields=fields, pageSize=1000).execute()
    out = {}
    for f in resp.get("files", []):
        name = (f.get("name") or "").strip()
        fid = (f.get("id") or "").strip()
        if name and fid:
            out[name] = fid
    return out


@st.cache_data(ttl=lambda: int(st.secrets.get("cache_ttl_seconds", 6 * 60 * 60)))
def index_images_by_camera(root_folder_id: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    image_index[camera][filename] = {"id": file_id, "webViewLink": link}
    """
    service = _drive_client()
    cam_folders = list_camera_folders(root_folder_id)

    image_index: Dict[str, Dict[str, Dict[str, str]]] = {}
    for cam_name, cam_folder_id in cam_folders.items():
        image_index[cam_name] = {}
        page_token = None
        fields = "nextPageToken, files(id,name,webViewLink,trashed,mimeType)"
        q = f"'{cam_folder_id}' in parents and trashed=false"

        while True:
            resp = (
                service.files()
                .list(q=q, fields=fields, pageToken=page_token, pageSize=1000)
                .execute()
            )
            for f in resp.get("files", []):
                name = (f.get("name") or "").strip()
                fid = (f.get("id") or "").strip()
                link = (f.get("webViewLink") or "").strip()
                if not name or not fid:
                    continue

                mt = (f.get("mimeType") or "")
                if mt.startswith("image/") or name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    image_index[cam_name][name] = {
                        "id": fid,
                        "webViewLink": link or drive_view_url(fid),
                    }

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return image_index


def resolve_image_link(camera: str, filename: str, image_index: dict) -> Tuple[str, str]:
    camera = (camera or "").strip()
    filename = (filename or "").strip()
    if not camera or not filename:
        return "", ""
    hit = image_index.get(camera, {}).get(filename)
    if not hit:
        return "", ""
    return hit.get("webViewLink", ""), hit.get("id", "")
