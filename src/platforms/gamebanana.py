import os
import threading

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit, urlunsplit, urlparse, parse_qs, unquote

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

# Interprets nxm links and launchs notification
def handle_gamebanana_link(link: str, downloader: Downloader, headers: dict) -> bool:

    app_dir = os.path.join(GLib.get_user_data_dir(), "nomm")
    user_config_dir = os.path.join(app_dir, "user_config.yaml")
    user_config = load_yaml(user_config_dir)
    base_download_path = user_config.get("download_path")

    # Api_key checked here to prevent from storing useless data (compared to where it was)
    if not base_download_path:
        print("Error: Missing API key or download path in user_config.yaml")
        return False
    
    split_url = urlsplit(link).path.split("/")
    if split_url[1] != "switch" or len(split_url) < 4:
        print(f"Malformed nomm protocol url: {split_url}")
        return

    mod_switch_id = split_url[2]
    mod_id = split_url[3]
    print(f"Switch Title ID: {mod_switch_id}")
    print(f"Mod ID: {mod_id}")

    switch_config_path = os.path.join(app_dir, "game_configs", "emulation", "switch.yaml")
    if not os.path.exists(switch_config_path):
        return
    switch_config = load_yaml(switch_config_path)

    game_folder_name = ""
    for game in switch_config:
        if game["switch_id"] == mod_switch_id:
            game_folder_name = game["full_name"]
            break

    if not game_folder_name:
        print(f"Game {mod_switch_id} could not be found in game_configs!")
        GLib.idle_add(send_download_notification, "failure-game-not-found", file_name=None, game_name=nexus_id, icon_path=None)
        return False

    download_dir = Path(base_download_path) / game_folder_name
    download_dir.mkdir(parents=True, exist_ok=True)

    # Get the download url
    parsed = urlparse(link)
    download_url = parse_qs(parsed.query).get("url", [None])[0]

    # Download mod
    return _download_gb_mod(download_url, headers, download_dir, mod_id, game_folder_name, user_config_dir, downloader)


def _download_gb_mod(mod_url: str, headers: dict, download_dir: Path, mod_id: str, game_folder_name: str, user_config_dir, downloader: Downloader) -> bool:

    response = requests.head(mod_url, allow_redirects=True, headers=headers, timeout=10)
    download_url = response.url
    
    parsed_path = urlparse(download_url).path
    file_name = unquote(os.path.basename(parsed_path))

    def on_download_complete(download_inst, downloaded_filename):
        if unquote(downloaded_filename) != file_name:
            return
        download_inst.disconnect_by_func(on_download_complete)
        download_inst.disconnect_by_func(on_download_error)
        with download_inst._downloads_lock:
            download_inst._active_downloads.add(file_name)
        threading.Thread(
            target=_fetch_and_write_mod_metadata, 
            args=(headers, download_dir, mod_id, game_folder_name, file_name, downloader), 
            daemon=True
        ).start()

    def on_download_error(download_inst, error_data):
        if unquote(error_data.get('filename', '')) != file_name:
            return
        download_inst.disconnect_by_func(on_download_complete)
        download_inst.disconnect_by_func(on_download_error)

    downloader.connect('download-complete', on_download_complete)
    downloader.connect('download-error', on_download_error)

    print(f"Downloading {file_name} to {game_folder_name}...")
    user_meta = load_yaml(user_config_dir)
    
    if user_meta.get('disable_download_window'):
        threading.Thread(
            target=downloader.download_mod, 
            args=(download_url, str(download_dir)), 
            daemon=True
        ).start()
    else:
        download_popup(file_name, download_url, download_dir, downloader)

    return True

def _fetch_and_write_mod_metadata(headers: dict, download_dir: Path, mod_id: str, game_folder_name: str, file_name: str, downloader: Downloader):
    
    print("Writing metadata")
    # Get mod metadata
    mod_metadata = get_mod_info(headers, mod_id, download_dir)

    downloads_metadata_path = get_metadata_path(str(download_dir), is_staging=False)
    mod_metadata["folder_name"] = mod_metadata["display_name"]
    mod_metadata["mod_id"] = mod_id

    with meta_lock:
        downloads_metadata = load_yaml(downloads_metadata_path)

        if "mods" not in downloads_metadata:
            downloads_metadata["mods"] = {}
        downloads_metadata["info"] = {}
        downloads_metadata["info"]["game"] = game_folder_name
        downloads_metadata["mods"][file_name] = mod_metadata

        write_yaml(downloads_metadata, downloads_metadata_path)
    GLib.idle_add(downloader.emit, 'download-metadata-ready', file_name)

    send_download_notification("success", file_name=file_name, game_name=game_folder_name, icon_path=None)
    
    downloader._active_downloads.discard(file_name)
    
    return True

def get_file_url(url: str, headers: dict = None) -> str:
    # Use HEAD request (or stream=True GET) so we only download HTTP headers
    response = requests.head(
        url, allow_redirects=True, headers=headers, timeout=10
    )

    final_path = urlparse(response.url).path
    filename = os.path.basename(final_path)

    if filename and "." in filename:
        return unquote(filename)
    else:
        print("Filename could not be determined!")
        return None

def clean_headers(headers: dict):
    """Removes API key from request headers"""
    clean_headers = headers.copy()
    clean_headers.pop("apikey", None)
    return clean_headers
