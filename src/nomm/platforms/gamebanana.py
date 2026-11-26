import os
import threading


from pathlib import Path
from urllib.parse import urlsplit, urlparse, parse_qs, unquote, quote
from urllib.error import HTTPError

import requests
from gi.repository import GLib

from nomm.core.user_config import load_user_config, get_game_config, SWITCH_GAME_CONFIG_PATH
from nomm.core.mod_manager import get_metadata_path, meta_lock
from nomm.core.downloader import Downloader
from nomm.gui.notifications import download_popup, send_download_notification
from nomm.core.tools import load_yaml, write_yaml, download_image, sanitize_for_pango

GAMEBANANA_API_V13 = "https://gamebanana.com/apiv13"
GB_SORT_MAPPING = {
    "Most Downloaded first": "Generic_MostDownloaded",
    "Highest Rated first": "Generic_MostLiked",
    "Newest first": "Generic_Newest",
    "Oldest first": "Generic_Oldest",
}


def get_mod_info(headers: dict, mod_id: str, download_dir: Path, current_mod_staging_folder: str = "") -> dict:
    print(f"Obtaining mod information for mod: {mod_id}")

    try:
        mod_url = f"{GAMEBANANA_API_V13}/Mod/{mod_id}/ProfilePage"
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
    metadata["uploader_url"] = remote_data.get("_aSubmitter").get("_sProfileUrl")
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
    thumbnail_folder = download_dir.resolve() / "thumbnails/"
    thumbnail_folder.mkdir(parents=True, exist_ok=True)
    thumbnail_path = str(thumbnail_folder / (f"{dest_folder}.png"))
    download_image(metadata["thumbnail"], thumbnail_path)
    metadata["thumbnail"] = thumbnail_path

    # Save description separately to not pollute metadata file
    description_folder = download_dir.resolve() / "descriptions/"
    description_folder.mkdir(parents=True, exist_ok=True)
    description_path = str(description_folder / (f"{dest_folder}.html"))
    with open(description_path, 'w') as f:
        f.write(sanitize_for_pango(remote_data.get("_sText")))
    metadata["description"] = description_path
    return metadata


# Interprets nxm links and launchs notification
def handle_gamebanana_link(link: str, downloader: Downloader, headers: dict) -> bool:
    # link example: nomm://gb/switch/0100152000022000/708958?url=https://gamebanana.com/mmdl/1795390
    user_config = load_user_config()
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

    if not os.path.exists(SWITCH_GAME_CONFIG_PATH):
        return
    switch_config = load_yaml(SWITCH_GAME_CONFIG_PATH)

    game_folder_name = ""
    for game in switch_config:
        if game["switch_id"] == mod_switch_id:
            game_folder_name = game["full_name"]
            break

    if not game_folder_name:
        print(f"Game {mod_switch_id} could not be found in game_configs!")
        GLib.idle_add(send_download_notification, "failure-game-not-found", file_name=None, game_name=game["full_name"], icon_path=None)
        return False

    download_dir = Path(base_download_path) / game_folder_name
    download_dir.mkdir(parents=True, exist_ok=True)

    # Get the download url
    parsed = urlparse(link)
    download_url = parse_qs(parsed.query).get("url", [None])[0]

    # Download mod
    return _download_gb_mod(download_url, headers, download_dir, mod_id, game_folder_name, user_config, downloader)


def _extract_gamebanana_game_id(mod_id: str, headers: dict | None = None) -> str:
    if not mod_id:
        return ""
    try:
        data = _gb_get_json(f"{GAMEBANANA_API_V13}/Mod/{mod_id}/ProfilePage", headers=headers)
        if isinstance(data, dict):
            game_obj = data.get("_aGame")
            if isinstance(game_obj, dict):
                gid = game_obj.get("_idRow") or game_obj.get("_id")
                if gid:
                    return str(gid).strip()
            gid = data.get("_idGameRow") or data.get("_idGame")
            if gid:
                return str(gid).strip()
    except Exception as e:
        print(f"Failed to resolve GameBanana game ID for mod {mod_id}: {e}")
    return ""


def _resolve_game_folder_from_gb_id(gb_game_id: str | int) -> str:
    target_id = str(gb_game_id or "").strip()
    if not target_id:
        return ""

    # Check generic game YAML files (custom & preset)
    potential_match = get_game_config(gamebanana_id=target_id)
    if potential_match:
        return potential_match.get("name")

    # Check Switch configuration file
    if SWITCH_GAME_CONFIG_PATH and os.path.exists(SWITCH_GAME_CONFIG_PATH):
        switch_config = load_yaml(SWITCH_GAME_CONFIG_PATH) or []
        for game in switch_config:
            if isinstance(game, dict) and str(game.get("gamebanana_id") or "").strip() == target_id:
                folder = game.get("full_name").strip()
                if folder:
                    return folder

    return ""


def _download_gb_mod(mod_url: str, headers: dict, download_dir: Path, mod_id: str,
                     game_folder_name: str, user_config: dict, downloader: Downloader) -> bool:

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

    if user_config.get('disable_download_window'):
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
        if os.path.exists(downloads_metadata_path):
            downloads_metadata = load_yaml(downloads_metadata_path)
        else:
            downloads_metadata = {}

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


def _build_gamebanana_protocol_url(
    mod_id: str | int,
    download_url: str = "",
    headers: dict | None = None,
) -> str:
    clean_id = str(mod_id or "").strip()
    if not clean_id:
        return ""

    dl_url = (download_url or "").strip()
    if not dl_url or "/mods/" in dl_url:
        resolved = get_gamebanana_mod_download_url(clean_id, headers=headers)
        if resolved:
            dl_url = resolved

    if not dl_url:
        return ""

    return f"nomm://gb/{clean_id}?url={quote(dl_url, safe='')}"


def _gb_get_json(url: str, headers: dict | None = None, params: dict | list | None = None, timeout: int = 12):
    req_headers = {"User-Agent": "nomm-mod-browser/1.0", "Accept": "application/json"}
    if headers:
        req_headers.update(clean_headers(headers))
    resp = requests.get(url, headers=req_headers, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _gb_extract_thumbnail(record: dict) -> str:
    content = record.get("_aPreviewContent")
    if isinstance(content, dict):
        # apiv13 list records use singular "screenshot" (dict)
        shot = content.get("screenshot")
        if not isinstance(shot, dict):
            shots = content.get("screenshots")
            if isinstance(shots, list) and shots and isinstance(shots[0], dict):
                shot = shots[0]

        if isinstance(shot, dict):
            base = str(shot.get("_sBaseUrl") or "").rstrip("/")
            for key in ("_sFile530", "_sFile220", "_sFile"):
                fname = shot.get(key)
                if fname:
                    fname_str = str(fname).strip()
                    if fname_str.startswith("http://") or fname_str.startswith("https://"):
                        return fname_str
                    return f"{base}/{fname_str.lstrip('/')}" if base else fname_str

    preview_media = record.get("_aPreviewMedia")
    if isinstance(preview_media, dict):
        images = preview_media.get("_aImages")
        if isinstance(images, list) and images and isinstance(images[0], dict):
            img = images[0]
            base = str(img.get("_sBaseUrl") or "").rstrip("/")
            for key in ("_sFile530", "_sFile220", "_sFile100", "_sFile"):
                fname = img.get(key)
                if fname:
                    fname_str = str(fname).strip()
                    if fname_str.startswith("http://") or fname_str.startswith("https://"):
                        return fname_str
                    return f"{base}/{fname_str.lstrip('/')}" if base else fname_str

    return ""


def _gb_extract_author(record: dict) -> str:
    submitter = record.get("_aSubmitter")
    if isinstance(submitter, dict):
        return str(submitter.get("_sName") or submitter.get("_sUserTitle") or "").strip()
    if isinstance(submitter, str):
        return submitter.strip()
    return ""


def _gb_extract_download_url(files_list: list | None) -> str:
    if not isinstance(files_list, list):
        return ""
    for f in files_list:
        if isinstance(f, dict):
            url = f.get("_sDownloadUrl") or f.get("_sUrl")
            if url:
                return str(url)
    return ""


def get_gamebanana_first_mod_date(headers: dict | None = None, game_id: str | int = "") -> float:
    if not game_id:
        return 1420070400.0
    try:
        data = _gb_get_json(
            f"{GAMEBANANA_API_V13}/Mod/Index",
            headers=headers,
            params={
                "_nPage": 1,
                "_nPerpage": 1,
                "_sSort": "Generic_Oldest",
                "_aFilters[Generic_Game]": str(game_id),
            },
        )
        records = data.get("_aRecords") if isinstance(data, dict) else []
        if records and isinstance(records[0], dict):
            ts = records[0].get("_tsDateAdded")
            if isinstance(ts, (int, float)) and ts > 0:
                return float(ts)
    except Exception as e:
        print(f"Failed to fetch first GameBanana mod date: {e}")
    return 1420070400.0


def get_gamebanana_mod_download_url(mod_id: str | int, headers: dict | None = None) -> str:
    if not mod_id:
        return ""
    try:
        data = _gb_get_json(f"{GAMEBANANA_API_V13}/Mod/{mod_id}/ProfilePage", headers=headers)
        if isinstance(data, dict):
            return _gb_extract_download_url(data.get("_aFiles"))
    except Exception as e:
        print(f"Failed to resolve GameBanana download URL for mod {mod_id}: {e}")
    return ""


def handle_gamebanana_mod_link(link: str, downloader: Downloader, headers: dict) -> bool:
    """Handles platform-agnostic GameBanana links: nomm://gb/{mod_id}?url={download_url}"""
    user_config = load_user_config()
    base_download_path = user_config.get("download_path")
    if not base_download_path:
        print("Error: Missing download path in user_config.yaml")
        return False

    parsed = urlparse(link)
    path_parts = [p for p in (parsed.path or "").split("/") if p]

    if parsed.netloc == "gb":
        mod_id = path_parts[0] if len(path_parts) >= 1 else ""
    else:
        mod_id = path_parts[1] if len(path_parts) >= 2 and path_parts[0] == "gb" else ""

    if not mod_id:
        print(f"Malformed nomm GameBanana mod url: {link}")
        return False

    download_url = parse_qs(parsed.query).get("url", [None])[0]
    if not download_url:
        print(f"Missing download url query parameter in: {link}")
        return False

    gb_game_id = _extract_gamebanana_game_id(mod_id, headers=headers)
    game_folder_name = _resolve_game_folder_from_gb_id(gb_game_id)

    if not game_folder_name:
        print(f"Could not determine target game folder for GameBanana mod {mod_id} (game_id={gb_game_id})")
        return False

    download_dir = Path(base_download_path) / game_folder_name
    download_dir.mkdir(parents=True, exist_ok=True)

    return _download_gb_mod(
        download_url,
        headers,
        download_dir,
        mod_id,
        game_folder_name,
        user_config,
        downloader,
    )


def search_gamebanana_mods(
    headers: dict | None = None,
    game_id: str | int = "",
    query: str = "",
    category: str = "All Categories",
    sort_by: str = "Most Downloaded first",
    date_range: tuple = (),
    updated_range: tuple = (),
    include_adult: bool = False,
    author: str = "",
    count: int = 20,
    offset: int = 0,
) -> list[dict]:
    if not game_id:
        return []

    page_size = max(1, int(count or 20))
    page = (max(0, int(offset or 0)) // page_size) + 1
    sort_param = GB_SORT_MAPPING.get(sort_by, "Generic_MostDownloaded")
    cleaned_query = (query or "").strip()
    cleaned_author = (author or "").strip()

    try:
        if cleaned_query:
            data = _gb_get_json(
                f"{GAMEBANANA_API_V13}/Util/Search/Results",
                headers=headers,
                params={
                    "_sModelName": "Mod",
                    "_sSearchString": cleaned_query,
                    "_idGameRow": str(game_id),
                    "_nPage": page,
                    "_nPerpage": page_size,
                },
            )
        else:
            data = _gb_get_json(
                f"{GAMEBANANA_API_V13}/Mod/Index",
                headers=headers,
                params={
                    "_aFilters[Generic_Game]": str(game_id),
                    "_nPage": page,
                    "_nPerpage": page_size,
                    "_sSort": sort_param,
                },
            )
        records = data.get("_aRecords") if isinstance(data, dict) else []
    except Exception as e:
        print(f"GameBanana mod search failed: {e}")
        return []

    if not isinstance(records, list):
        return []

    created_min, created_max = (
        (float(date_range[0]), float(date_range[1]))
        if isinstance(date_range, (tuple, list)) and len(date_range) == 2
        else (None, None)
    )
    updated_min, updated_max = (
        (float(updated_range[0]), float(updated_range[1]))
        if isinstance(updated_range, (tuple, list)) and len(updated_range) == 2
        else (None, None)
    )

    results: list[dict] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue

        if not include_adult and bool(rec.get("_bHasContentRatings")):
            continue

        mod_id = rec.get("_idRow") or rec.get("_idRecord") or ""
        name = str(rec.get("_sName") or "").strip()
        mod_author = _gb_extract_author(rec)

        if cleaned_author and cleaned_author.lower() not in mod_author.lower():
            continue

        is_nsfw = bool(rec.get("_bIsNsfw") or rec.get("_bHasNsfwContent"))
        if not include_adult and is_nsfw:
            continue

        created_ts = float(rec.get("_tsDateAdded") or 0.0)
        updated_ts = float(rec.get("_tsDateModified") or created_ts or 0.0)

        if created_min is not None and created_ts > 0 and created_ts < created_min:
            continue
        if created_max is not None and created_ts > 0 and created_ts > created_max:
            continue
        if updated_min is not None and updated_ts > 0 and updated_ts < updated_min:
            continue
        if updated_max is not None and updated_ts > 0 and updated_ts > updated_max:
            continue

        views = int(rec.get("_nViewCount", 0))
        endorsements = int(rec.get("_nLikeCount", 0))
        short_desc = str(rec.get("_sDescription") or "").strip()
        page_url = str(
            rec.get("_sProfileUrl")
            or (f"https://gamebanana.com/mods/{mod_id}" if mod_id else "")
        )
        download_url = _gb_extract_download_url(rec.get("_aFiles")) or page_url

        results.append({
            "name": name,
            "author": mod_author,
            "thumbnail_url": _gb_extract_thumbnail(rec),
            "views": views,
            "endorsements": endorsements,
            "short_description": short_desc,
            "page_url": page_url,
            "download_url": download_url,
            "mod_id": str(mod_id),
            "created_at": created_ts,
            "updated_at": updated_ts
        })

    return results
