import os
import yaml
import requests
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path

def download_nexus_mod(nxm_link):
    """
    Downloads a mod into a game-specific subfolder found by matching nexus_game_id.
    """
    user_config_path = os.path.expanduser("~/nomm/user_config.yaml")
    game_configs_dir = os.path.expanduser("~/nomm/game_configs")
    
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
        game_folder_name = nexus_game_id # Fallback to the raw ID
        
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

        # 4. Get the Download URI from Nexus API
        headers = {
            'apikey': api_key,
            'Application-Name': 'Nomm',
            'Application-Version': '1.0.0'
        }
        params = {
            'key': nxm_query.get("key"),
            'expires': nxm_query.get("expires")
        }
        
        download_api_url = f"https://api.nexusmods.com/v1/games/{nexus_game_id}/mods/{mod_id}/files/{file_id}/download_link.json"

        response = requests.get(download_api_url, headers=headers, params=params)
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
        mod_data = requests.get(file_url, stream=True)
        mod_data.raise_for_status()
        
        with open(full_file_path, "wb") as f:
            for chunk in mod_data.iter_content(chunk_size=8192):
                f.write(chunk)

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
                "mod_id": mod_id,
                "file_id": file_id,
                "nexus_game_id": nexus_game_id
            }

            # Define metadata file path: filename.zip.nomm.yaml
            metadata_filename = f"{file_name}.nomm.yaml"
            metadata_path = final_download_dir / metadata_filename

            with open(metadata_path, "w") as f:
                yaml.dump(mod_metadata, f, default_flow_style=False)
            
            print(f"Metadata saved to {metadata_filename}")

        except Exception as e:
            print(f"Warning: Could not retrieve mod metadata: {e}")
            # We don't return False here because the actual mod download succeeded

        print(f"Done! Saved to {full_file_path}")
        return True

    except Exception as e:
        print(f"An error occurred: {e}")
        return False