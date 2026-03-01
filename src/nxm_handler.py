#nxm_handler.py

#Global imports
import os, yaml, requests

#Specific imports
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from utils import download_with_progress, send_download_notification
from gi.repository import GLib

def download_nexus_mod(nxm_link):
    """
    Downloads a mod into a game-specific subfolder found by matching nexus_game_id.
    """

    user_data_dir = os.path.join(GLib.get_user_data_dir(), "nomm")
    user_config_path = os.path.join(user_data_dir, "user_config.yaml")
    game_configs_dir = os.path.join(user_data_dir, "game_configs")

    # 1. Load User Config
    try:
        with open(user_config_path, 'r') as f:
            user_config = yaml.safe_load(f)
            api_key = user_config.get("nexus_api_key")
            base_download_path = user_config.get("download_path")
            
        if not api_key or not base_download_path:
            print("Error: Missing API key or download path in user_config.yaml")
            return False
    except Exception as e:
        print(f"Failed to load user_config: {e}")
        return False

    try:
        # 2. Parse the NXM link
        splitted_nxm = urlsplit(nxm_link)
        nxm_path = splitted_nxm.path.split('/')
        nxm_query = dict(item.split('=') for item in splitted_nxm.query.split('&'))
        
        nexus_game_id = splitted_nxm.netloc.lower() # e.g., 'skyrimspecialedition'
        mod_id = nxm_path[2]
        file_id = nxm_path[4]

        # 3. Determine Game-Specific Subfolder
        game_folder_name = ""
        
        if os.path.exists(game_configs_dir):
            for filename in os.listdir(game_configs_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    try:
                        with open(os.path.join(game_configs_dir, filename), 'r') as f:
                            g_data = yaml.safe_load(f)
                            # Check if this config matches the nexus game ID
                            if g_data and g_data.get("nexus_game_id") == nexus_game_id:
                                game_folder_name = g_data.get("name", nexus_game_id)
                                break
                    except:
                        continue
        if game_folder_name == "":
            print(f"game {nexus_game_id} could not be found in game_configs!")
            send_download_notification("failure-game-not-found", file_name=None, game_name=nexus_game_id, icon_path=None)
            return

        # 4. Get the Download URI from Nexus API
        headers = {
            'apikey': api_key,
            'Application-Name': 'Nomm',
            'Application-Version': '0.5.0',
            'User-Agent': 'Nomm/0.5.0 (Linux; Flatpak) Requests/Python'
        }
        params = {
            'key': nxm_query.get("key"),
            'expires': nxm_query.get("expires")
        }
        # debug
        print(f"key: {nxm_query.get('key')}")
        print(f"expires: {nxm_query.get('expires')}")
        
        download_api_url = f"https://api.nexusmods.com/v1/games/{nexus_game_id}/mods/{mod_id}/files/{file_id}/download_link.json"

        response = requests.get(download_api_url, headers=headers, params=params)
        if response.status_code == 403:
            print(f"Nexus API Error: {response.json()}") # This will tell you if it's 'Key Expired' or 'Forbidden'
        response.raise_for_status()
        
        download_data = response.json()
        if not download_data:
            print("No download mirrors available.")
            return False
            
        uri = download_data[0].get('URI')
        splitted_uri = urlsplit(uri)
        file_url = urlunsplit(splitted_uri)
        file_name = splitted_uri.path.split('/')[-1]

        # 5. Prepare final directory
        # Final Path: /base/path/Game Name/
        final_download_dir = Path(base_download_path) / game_folder_name
        final_download_dir.mkdir(parents=True, exist_ok=True)
        
        full_file_path = final_download_dir / file_name

        # 6. Download the actual mod file
        print(f"Downloading {file_name} to {game_folder_name}...")
        download_with_progress(file_url, final_download_dir)

        # 7. Obtain mod file info and save metadata
        try:
            info_api_url = f"https://api.nexusmods.com/v1/games/{nexus_game_id}/mods/{mod_id}/files/{file_id}.json"
            info_response = requests.get(info_api_url, headers=headers)
            info_response.raise_for_status()
            file_info_data = info_response.json()

            # Extract name and version
            mod_metadata = {
                "name": file_info_data.get("name", "Unknown Mod"),
                "version": file_info_data.get("version", "1.0"),
                "changelog": file_info_data.get("changelog_html", ""),
                "mod_id": mod_id,
                "file_id": file_id,
                "mod_link": f"https://www.nexusmods.com/{nexus_game_id}/mods/{mod_id}"  
            }

            # Define unique metadata file path .downloads.nomm.yaml:
            downloads_metadata_filename = f".downloads.nomm.yaml"
            downloads_metadata_path = final_download_dir / downloads_metadata_filename
            downloads_metadata = {}
            if os.path.exists(downloads_metadata_path):
                with open(downloads_metadata_path, "r") as f:
                    downloads_metadata = yaml.safe_load(f)
            else:
                # initialise file with important game info
                downloads_metadata["info"] = {}
                downloads_metadata["info"]["game"] = game_folder_name
                downloads_metadata["info"]["nexus_game_id"] = nexus_game_id
                downloads_metadata["mods"] = {}
            downloads_metadata["mods"][file_name] = mod_metadata
            with open(downloads_metadata_path, "w") as f:
                yaml.safe_dump(downloads_metadata, f, default_flow_style=False)
            
            send_download_notification("success", file_name=file_name, game_name=game_folder_name, icon_path=None)
        except Exception as e:
            print(f"Warning: Could not retrieve mod metadata: {e}")
            # We don't return False here because the actual mod download succeeded

        print(f"Done! Saved to {full_file_path}")
        return True

    except Exception as e:
        print(f"An error occurred: {e}")
        return False
