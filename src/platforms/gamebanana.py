import os
import threading

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml
from gi.repository import GLib

from core.mod_manager import get_metadata_path, load_staging_metadata, meta_lock
from core.downloader import Downloader
from gui.notifications import download_popup, send_download_notification
from core.tools import load_yaml, write_yaml, download_image, sanitize_for_pango

import requests

def get_mod_info(headers: dict, mod_id: str, download_dir: Path, current_mod_staging_folder: str = "") -> dict:
    print(f"Obtaining mod information for mod: {mod_id}")

    try:
        mod_url = f"https://gamebanana.com/apiv13/Mod/{mod_id}/ProfilePage"
        resp = requests.get(mod_url, headers=clean_headers(headers), timeout=10)
        resp.raise_for_status()
    except HTTPError as e:
        print(f"Failed to obtain mod information: {e}")

    remote_data = resp.json()
    metadata = {}
    metadata["display_name"] = remote_data.get("_sName")
    contributors = remote_data.get("_aCredits")
    contributor_list = []
    for category in contributors:
        for contributor in category["_aAuthors"]:
            contributor_list.append(contributor["_sName"])
    metadata["author"] = ", ".join(contributor_list)
    metadata["uploader"] = remote_data.get("_aSubmitter").get("_sName")
    metadata["endorsements"] = remote_data.get("_nLikeCount")
    metadata["new_version"] = remote_data.get("_sVersion")
    thumbnail_info = remote_data.get("_aPreviewContent").get("screenshots")[0]
    metadata["thumbnail"] = thumbnail_info.get("_sBaseUrl") + "/" + thumbnail_info.get("_sFile")
    metadata["summary"] = remote_data.get("_sDescription", "No description summary provided. Click the + button to see the full description.")
    metadata["platform"] = "GameBanana"
    metadata["mod_link"] = f"https://gamebanana.com/mods/{mod_id}"

    if current_mod_staging_folder:
        # If this is called as part of a metadata update, use the current folder
        dest_folder = current_mod_staging_folder
    else:
        # If this is called as part of a mod download, use the name of the mod
        dest_folder = metadata["display_name"]

    # Download thumbnail to have a local copy
    thumbnail_folder = download_dir.resolve() / f"thumbnails/"
    thumbnail_folder.mkdir(parents=True, exist_ok=True)
    thumbnail_path = str(thumbnail_folder / (f"{dest_folder}.png"))
    download_image(metadata["thumbnail"], thumbnail_path)
    metadata["thumbnail"] = thumbnail_path

    # Save description separately to not pollute metadata file
    description_folder = download_dir.resolve() / f"descriptions/"
    description_folder.mkdir(parents=True, exist_ok=True)
    description_path = str(description_folder / (f"{dest_folder}.html"))
    with open(description_path, 'w') as f:
        f.write(sanitize_for_pango(remote_data.get("_sText")))
    metadata["description"] = description_path
    return metadata

def clean_headers(headers: dict):
    """Removes API key from request headers"""
    clean_headers = headers.copy()
    clean_headers.pop("apikey", None)
    return clean_headers