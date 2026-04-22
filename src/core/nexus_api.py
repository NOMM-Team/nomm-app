import os
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml
from gi.repository import GLib

from core.config import get_metadata_path, load_metadata
from core.downloader import download_mod
from gui.notifications import send_download_notification
from typing import Optional, Callable


def check_for_mod_updates_async(staging_metadata: dict, headers: dict, game_id: str, on_complete_callback: Optional[Callable]) -> None:
    def worker():
        print("Checking for updates in background...")
        mods_updated = False

        for mod_name, details in staging_metadata.get("mods", {}).items():
            mod_id = details.get("mod_id")
            local_version = str(details.get("version", ""))
            if not mod_id:
                print(f"No mod ID found for {mod_name}, skipping update check")
                continue

            print(f"Checking for update for mod: {mod_name}")
            try:
                mod_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}.json"
                resp = requests.get(mod_url, headers=headers, timeout=10)
                
                if resp.status_code == 200:
                    remote_data = resp.json()
                    remote_version = str(remote_data.get("version", ""))

                    if remote_version and remote_version != local_version:
                        details["new_version"] = remote_version
                        mods_updated = True

                        changelog_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}/changelogs.json"
                        changelog_resp = requests.get(changelog_url, headers=headers, timeout=10)
                        
                        if changelog_resp.status_code == 200:
                            logs = changelog_resp.json()
                            new_log = logs.get(remote_version)
                            if new_log:
                                details["changelog"] = "\n".join(new_log) if isinstance(new_log, list) else new_log
                else:
                    print(f"Error getting update info for {mod_name}: {resp.status_code}")

            except Exception as e:
                print(f"Error checking {mod_name}: {e}")

        GLib.idle_add(on_complete_callback, mods_updated, staging_metadata)

    threading.Thread(target=worker, daemon=True).start()

def handle_nexus_link(nxm_link: str) -> bool:

    app_dir = os.path.join(GLib.get_user_data_dir(), "nomm")
    user_config_dir = os.path.join(app_dir, "user_config.yaml")
    user_config = load_yaml(user_config_dir)
    api_key = user_config.get("nexus_api_key")
    base_download_path = user_config.get("download_path")
    
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
    nexus_game_id = splitted_nxm.netloc.lower()
    print(f"Nexus Game ID: {nexus_game_id}")

    game_configs_dir = os.path.join(app_dir, "game_configs")
    game_folder_name = ""
    
    if os.path.exists(game_configs_dir):
        for filename in os.listdir(game_configs_dir):
            if filename.lower().endswith((".yaml", ".yml")):
                try:
                    with open(os.path.join(game_configs_dir, filename), 'r') as f:
                        g_data = yaml.safe_load(f)
                        if g_data and g_data.get("nexus_id") == nexus_game_id:
                            game_folder_name = g_data.get("name", nexus_game_id)
                            break
                except:
                    continue

    if not game_folder_name:
        print(f"Game {nexus_game_id} could not be found in game_configs!")
        send_download_notification("failure-game-not-found", file_name=None, game_name=nexus_game_id, icon_path=None)
        return

    final_download_dir = Path(base_download_path) / game_folder_name
    final_download_dir.mkdir(parents=True, exist_ok=True)

    if "collections" in nxm_link:
        print("Downloading collection")
        _download_nexus_collection(nxm_link, headers, final_download_dir)
    else:
        print("Downloading single mod")
        _download_nexus_mod(nxm_link, headers, final_download_dir, nexus_game_id, game_folder_name)


def _download_nexus_mod(nxm_link: str, headers: dict, final_download_dir: Path, nexus_game_id: str, game_folder_name: str):
    try:
        splitted_nxm = urlsplit(nxm_link)
        nxm_path = splitted_nxm.path.split('/')
        nxm_query = dict(item.split('=') for item in splitted_nxm.query.split('&'))

        mod_id = nxm_path[2]
        file_id = nxm_path[4] 

        params = {
            'key': nxm_query.get("key"),
            'expires': nxm_query.get("expires")
        }
        
        download_api_url = f"https://api.nexusmods.com/v1/games/{nexus_game_id}/mods/{mod_id}/files/{file_id}/download_link.json"

        response = requests.get(download_api_url, headers=headers, params=params)
        if response.status_code == 403:
            print(f"Nexus API Error: {response.json()}")
        response.raise_for_status()

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
        download_mod(file_url, str(final_download_dir))

        try:
            info_api_url = f"https://api.nexusmods.com/v1/games/{nexus_game_id}/mods/{mod_id}/files/{file_id}.json"
            info_response = requests.get(info_api_url, headers=headers)
            info_response.raise_for_status()
            file_info_data = info_response.json()

            mod_metadata = {
                "name": file_info_data.get("name", "Unknown Mod"),
                "version": file_info_data.get("version", "1.0"),
                "changelog": file_info_data.get("changelog_html", ""),
                "mod_id": mod_id,
                "file_id": file_id,
                "mod_link": f"https://www.nexusmods.com/{nexus_game_id}/mods/{mod_id}"  
            }

            downloads_metadata_path = get_metadata_path(str(final_download_dir), is_staging=False)
            downloads_metadata = load_metadata(downloads_metadata_path)

            downloads_metadata["info"]["game"] = game_folder_name
            downloads_metadata["info"]["nexus_id"] = nexus_game_id
            downloads_metadata["mods"][file_name] = mod_metadata

            write_yaml(downloads_metadata, downloads_metadata_path)
            
            send_download_notification("success", file_name=file_name, game_name=game_folder_name, icon_path=None)
        except Exception as e:
            print(f"Warning: Could not retrieve mod metadata: {e}")

        print(f"Done! Saved to {full_file_path}")
        return True

    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def _download_nexus_collection(nxm_link: str, headers: dict, final_download_dir: Path):
    parts = nxm_link.replace("nxm://", "").split("/")
    game_domain = parts[0]
    collection_id = parts[2]
    revision_id = parts[4] if len(parts) > 4 else "1"

    print(f"Fetching collection revision {revision_id}...")
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


def _get_files_from_collection(game_domain: str, collection_id: str, revision_id: str, headers: dict):
    graphql_url = "https://graphql.nexusmods.com"
    query = """
    query collectionRevision($slug: String!, $revision: Int!, $domainName: String!) {
        collectionRevision(slug: $slug, revision: $revision, domainName: $domainName) {
            modFiles {
              modId
              fileId
            }
        }
    }
    """
    
    variables = {
        "slug": collection_id,
        "revision": int(revision_id),
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

        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            print(f"GraphQL Errors: {data['errors']}")
            return []

        revision_data = data.get("data", {}).get("collectionRevision")
        if not revision_data:
            print(f"Error: Collection {collection_id} Revision {revision_id} not found.")
            return []
            
        mod_files = revision_data.get("modFiles", [])
        return [{"mod_id": str(m["modId"]), "file_id": str(m["fileId"])} for m in mod_files]

    except Exception as e:
        print(f"GraphQL Query Failed: {e}")
        return []