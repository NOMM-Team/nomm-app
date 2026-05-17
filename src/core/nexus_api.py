import os
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml
from gi.repository import GLib

from core.mod_manager import get_metadata_path, load_staging_metadata
from core.downloader import download_mod
from gui.notifications import send_download_notification, download_with_progress
from core.tools import load_yaml, write_yaml, download_image, process_bbcode
from typing import Optional, Callable

import requests

def endorse_nexus_mod(headers: dict, game_domain: str, mod_id: str, unendorse: bool):
    """
    Sends an endorsement (or unendorse action) to the Nexus Mods API.

    :param headers: Standard headers including the API key
    :param game_domain: The domain name of the game (e.g., 'witcher3').
    :param mod_id: The ID of the mod to endorse.
    :param unendorse: Set to True if you want to remove an endorsement.
    :return: Bool to indicate success or failure
    """
    # Determine the endpoint based on action
    action = "abstain" if unendorse else "endorse"
    url = f"https://api.nexusmods.com/v1/games/{game_domain}/mods/{mod_id}/{action}.json"
    
    try:
        # Nexus API expects a POST request for endorsements
        response = requests.post(url, headers=headers, timeout=10)
        # Handle the response
        if response.status_code == 200:
            return True
        else:
            # Handle generic API errors (e.g., Mod not found, internal server issues)
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("message", f"HTTP Error {response.status_code}")
            return False, f"Failed to process request: {error_msg}"
            
    except requests.exceptions.RequestException as e:
        # Catches connection timeouts, DNS errors, offline status, etc.
        return False, f"Network error encountered: {str(e)}"

def get_mod_info(headers: dict, game_id: str, mod_id: str, download_dir: Path, current_mod_staging_folder: str = "") -> dict:
    print(f"Obtaining mod information for mod: {mod_id}")

    try:
        mod_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}.json"
        resp = requests.get(mod_url, headers=headers, timeout=10)
        resp.raise_for_status()
    except HTTPError as e:
        print(f"Failed to obtain mod information: {e}")

    remote_data = resp.json()
    metadata = {}
    metadata["display_name"] = remote_data.get("name")
    metadata["author"] = remote_data.get("author")
    metadata["uploader"] = remote_data.get("uploaded_by")
    metadata["endorsements"] = remote_data.get("endorsement_count")
    metadata["new_version"] = remote_data.get("version")
    metadata["thumbnail"] = remote_data.get("picture_url")

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
        f.write(process_bbcode(remote_data.get("description")))
    metadata["description"] = description_path

    return metadata

def check_for_mod_updates_async(staging_metadata: dict, headers: dict, game_id: str, download_dir: Path, on_complete_callback: Optional[Callable]) -> None:
    def worker():
        print("Checking for updates in background...")

        for mod_name, mod_metadata in staging_metadata.get("mods", {}).items():
            mod_id = mod_metadata.get("mod_id")
            local_version = str(mod_metadata.get("version", ""))
            if not mod_id:
                print(f"No mod ID found for {mod_name}, skipping update check")
                continue

            print(f"Checking for update for mod: {mod_name}")
            new_metatadata = get_mod_info(headers, game_id, mod_id, download_dir, mod_metadata["folder_name"] if "folder_name" in mod_metadata else mod_metadata["name"])

            remote_version = str(new_metatadata.get("new_version", ""))

            if remote_version and remote_version != local_version:
                print("New version available!")
                try:
                    changelog_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}/changelogs.json"
                    changelog_resp = requests.get(changelog_url, headers=headers, timeout=10)
                except Exception as e:
                    print(f"Error checking {mod_name}: {e}")
                    continue
                
                if changelog_resp.status_code == 200:
                    logs = changelog_resp.json()
                    # Nexus returns a dict where keys are version numbers
                    # We grab the log for the specific remote version found
                    new_log = logs.get(remote_version)
                    if new_log:
                        # Join list of changes into a single string if necessary
                        new_changelog = "\n".join(new_log) if isinstance(new_log, list) else new_log
                        staging_metadata["mods"][mod_name]["changelog"] = new_changelog
            
            # update mod_metadata with new metadata values
            staging_metadata["mods"][mod_name] |= new_metatadata

        GLib.idle_add(on_complete_callback, staging_metadata)

    threading.Thread(target=worker, daemon=True).start()

# Interprets nxm links and launchs notification

def handle_nexus_link(nxm_link: str) -> bool:

    app_dir = os.path.join(GLib.get_user_data_dir(), "nomm")
    user_config_dir = os.path.join(app_dir, "user_config.yaml")
    user_config = load_yaml(user_config_dir)
    api_key = user_config.get("nexus_api_key")
    base_download_path = user_config.get("download_path")
    
    # Api_key checked here to prevent from storing useless data (compared to where it was)
    if not api_key or not base_download_path:
        print("Error: Missing API key or download path in user_config.yaml")
        return False

    headers = {
        'apikey': api_key,
        'Application-Name': 'NOMM',
        'Application-Version': '0.5.3',
        'User-Agent': 'NOMM/0.1 (Linux; Flatpak) Requests/Python'
    }
    
    splitted_nxm = urlsplit(nxm_link)
    nexus_id = splitted_nxm.netloc.lower()
    print(f"Nexus Game ID: {nexus_id}")

    game_configs_dir = os.path.join(app_dir, "game_configs")
    game_folder_name = ""
    
    if os.path.exists(game_configs_dir):
        for filename in os.listdir(game_configs_dir):
            if filename.lower().endswith((".yaml", ".yml")):
                try:
                    with open(os.path.join(game_configs_dir, filename), 'r') as f:
                        g_data = yaml.safe_load(f)
                        if g_data and g_data.get("nexus_id") == nexus_id:
                            game_folder_name = g_data.get("name", nexus_id)
                            break
                except:
                    continue

    if not game_folder_name:
        print(f"Game {nexus_id} could not be found in game_configs!")
        send_download_notification("failure-game-not-found", file_name=None, game_name=nexus_id, icon_path=None)
        return

    final_download_dir = Path(base_download_path) / game_folder_name
    final_download_dir.mkdir(parents=True, exist_ok=True)

    if "collections" in nxm_link:
        print("Downloading collection")
        _download_nexus_collection(nxm_link, headers, final_download_dir)
    else:
        print("Downloading single mod")
        _download_nexus_mod(nxm_link, headers, final_download_dir, nexus_id, game_folder_name, user_config_dir)

# Download the mods from nexus and is used in nxm_handler
def _download_nexus_mod(nxm_link: str, headers: dict, final_download_dir: Path, nexus_id: str, game_folder_name: str, user_config_dir):
    
    splitted_nxm = urlsplit(nxm_link)
    nxm_path = splitted_nxm.path.split('/')
    nxm_query = dict(item.split('=') for item in splitted_nxm.query.split('&'))

    mod_id = nxm_path[2]
    file_id = nxm_path[4]

    params = {
        'key': nxm_query.get("key"),
        'expires': nxm_query.get("expires")
    }
    
    download_api_url = f"https://api.nexusmods.com/v1/games/{nexus_id}/mods/{mod_id}/files/{file_id}/download_link.json"

    try:
        response = requests.get(download_api_url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Nexus API Error: {response.json()}")
        response.raise_for_status()
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

    download_data = response.json()
    if not download_data:
        print("No download mirrors available.")
        return False

    uri = download_data[0].get('URI')
    splitted_uri = urlsplit(uri)
    file_url = urlunsplit(splitted_uri)
    file_name = splitted_uri.path.split('/')[-1]
    
    full_file_path = final_download_dir / file_name

    print(f"Downloading {file_name} to {game_folder_name}...")
    user_meta = load_yaml(user_config_dir)
    if user_meta.get('disable_download_window'):
        download_mod(file_url, str(final_download_dir)) # silent download
    else:
        download_with_progress(file_url, final_download_dir) # windowed download
    
    try:
        info_api_url = f"https://api.nexusmods.com/v1/games/{nexus_id}/mods/{mod_id}/files/{file_id}.json"
        info_response = requests.get(info_api_url, headers=headers, timeout=(10, None))
        info_response.raise_for_status()
        file_info_data = info_response.json()

    except Exception as e:
        print(f"Warning: Could not retrieve mod metadata: {e}")

    # obtain additional metadata on the mod
    mod_metadata = get_mod_info(headers, nexus_id, mod_id, final_download_dir)
    if "display_name" in mod_metadata:
        mod_metadata["folder_name"] = mod_metadata["display_name"]
    else:
        mod_metadata["folder_name"] = file_info_data.get("name")
    mod_metadata["changelog"] = file_info_data.get("changelog_html", "")
    mod_metadata["mod_id"] = mod_id
    mod_metadata["file_id"] = file_id
    mod_metadata["mod_link"] = f"https://www.nexusmods.com/{nexus_id}/mods/{mod_id}" 
    mod_metadata["version"] = file_info_data.get("version", "")

    # Handle saving all of this data
    downloads_metadata_path = get_metadata_path(str(final_download_dir), is_staging=False)
    downloads_metadata = load_yaml(downloads_metadata_path)

    if "mods" not in downloads_metadata:
        downloads_metadata["mods"] = {}
    downloads_metadata["info"] = {}
    downloads_metadata["info"]["game"] = game_folder_name
    downloads_metadata["info"]["nexus_id"] = nexus_id
    downloads_metadata["mods"][file_name] = mod_metadata

    write_yaml(downloads_metadata, downloads_metadata_path)

    send_download_notification("success", file_name=file_name, game_name=game_folder_name, icon_path=None)

    print(f"Done! Saved to {full_file_path}")
    return True

def _download_nexus_collection(nxm_link: str, headers: dict, final_download_dir: Path):
    parts = nxm_link.replace("nxm://", "").split("/")
    game_domain = parts[0]
    collection_id = parts[2]
    revision_id = parts[4] if len(parts) > 4 else "1"
    
    # Fetch Collection Metadata via GraphQL
    print(f"Fetching collection revision {revision_id}...")
    
    # retrieve a list of {mod_id, file_id} from the collection metadata.
    mod_files_to_download = _get_files_from_collection(game_domain, collection_id, revision_id, headers)

    if not mod_files_to_download:
        print("Could not retrieve collection files.")
        return False

    success_count = 0
    for mod in mod_files_to_download:
        mod_id = mod['mod_id']
        file_id = mod['file_id']
        download_api_url = f"https://api.nexusmods.com/v1/games/{game_domain}/mods/{mod_id}/files/{file_id}/download_link.json"
        
        try:
            res = requests.get(download_api_url, headers=headers)
            res.raise_for_status()
            links = res.json()
            
            if links:
                direct_url = links[0]['URI']
                if download_mod(direct_url, str(final_download_dir)):
                    success_count += 1
        except Exception as e:
            print(f"Failed to download mod {mod_id}: {e}")

    print(f"Collection download complete: {success_count}/{len(mod_files_to_download)} files.")
    return True

# Get files from collexion and returns a dict if it manages to get the list
def _get_files_from_collection(game_domain: str, collection_id: str, revision_id: str, headers: dict):
    # API Endpoint
    graphql_url = "https://api.nexusmods.com/v2/graphql"
    
    current_dir = pathlib.Path(__file__).parent.parent.resolve()
    query_path = os.path.join(current_dir, 'queries', 'get_collections.graphql')
    
    with open(query_path, 'r') as f:
        query = f.read()
    
    variables = {
        "slug": collection_id,
        "revision": int(revision_id),
        'viewAdultContent': True,
        "domainName": game_domain
    }

    headers["Content-Type"] = "application/json"

    try:
        response = requests.post(
            graphql_url,
            json={'query': query, 'variables': variables}, 
            headers=headers,
            timeout=15,
            allow_redirects=True
        )

        if not response.raise_for_status:
            print(f"Failed API Call: {response.status_code}")
            print(f"Response: {response.text}")

        response.raise_for_status()

        data = response.json()
        
        if "errors" in data:
            print(f"GraphQL Errors: {data['errors']}")
            return []

        # Extract the list of modFiles
        revision_data = data["data"]["collectionRevision"]
        if not revision_data:
            print(f"Error: Collection {collection_id} Revision {revision_id} not found.")
            return []
            
        mod_files = revision_data.get("modFiles", [])
        
        # Transform into a cleaner list of dicts
        # The GraphQL returns camelCase: {'modId': 123, 'fileId': 456}
        # We'll normalize them to snake_case for a loop: {'mod_id': 123, 'file_id': 456}
        return [{"mod_id": m["file"]['modId'], "file_id": m["fileId"]} for m in mod_files]

    except Exception as e:
        print(f"GraphQL Query Failed: {e}")
        return []
