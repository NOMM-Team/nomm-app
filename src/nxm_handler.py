#nxm_handler.py

#Global imports
import os, yaml, requests

#Specific imports
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from utils import download_with_progress, send_download_notification
from gi.repository import GLib

def handle_nexus_link(nxm_link):
    user_data_dir = os.path.join(GLib.get_user_data_dir(), "nomm")
    user_config_path = os.path.join(user_data_dir, "user_config.yaml")
    game_configs_dir = os.path.join(user_data_dir, "game_configs")

    # Load User Config
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

    headers = {
        'apikey': api_key,
        'Application-Name': 'Nomm',
        'Application-Version': '0.5.3',
        'User-Agent': 'Nomm/0.5.3 (Linux; Flatpak) Requests/Python'
    }
    
    splitted_nxm = urlsplit(nxm_link)
 
    nexus_game_id = splitted_nxm.netloc.lower() # e.g., 'skyrimspecialedition'
    print(nexus_game_id)

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

    final_download_dir = Path(base_download_path) / game_folder_name
    final_download_dir.mkdir(parents=True, exist_ok=True)

    if "collections" in nxm_link:
        print("Downloading collection")
        download_nexus_collection(nxm_link, headers, final_download_dir)
    else:
        print("Downloading single mod")
        download_nexus_mod(nxm_link, headers, final_download_dir, nexus_game_id, game_folder_name)


def download_nexus_collection(nxm_link: str, headers: dict, final_download_dir: str):
    """
    Handles nxm://collection links for Premium users.
    Example link: nxm://skyrim/collections/123/revisions/1
    """
    # Parse the collection link
    # Typically: nxm://{game}/collections/{collection_id}/revisions/{revision_id}
    parts = nxm_link.replace("nxm://", "").split("/")
    game_domain = parts[0]
    collection_id = parts[2]
    revision_id = parts[4] if len(parts) > 4 else "1"

    # Fetch Collection Metadata via GraphQL
    print(f"Fetching collection revision {revision_id}...")
    
    # retrieve a list of {mod_id, file_id} from the collection metadata.
    mod_files_to_download = get_files_from_collection(game_domain, collection_id, revision_id, headers)

    if not mod_files_to_download:
        print("Could not retrieve collection files.")
        return False

    # Loop and download
    success_count = 0
    for mod in mod_files_to_download:
        mod_id = mod['mod_id']
        file_id = mod['file_id']
        
        # Get the Premium Direct Link
        download_api_url = f"https://api.nexusmods.com/v1/games/{game_domain}/mods/{mod_id}/files/{file_id}/download_link.json"
        
        try:
            # Premium users don't need 'key' or 'expires' in params if the API Key is Premium
            res = requests.get(download_api_url, headers=headers)
            res.raise_for_status()
            links = res.json()
            
            if links:
                direct_url = links[0]['URI']
                # Use your existing method!
                # Ensure final_download_dir is set per game as in your previous logic
                if download_with_progress(direct_url, final_download_dir):
                    success_count += 1
        except Exception as e:
            print(f"Failed to download mod {mod_id}: {e}")

    print(f"Collection download complete: {success_count}/{len(mod_files_to_download)} files.")
    return True

def get_files_from_collection(game_domain: str, collection_id: str, revision_id: str, headers: dict):
    """
    Queries the Nexus GraphQL API to get all mod/file IDs for a collection revision.
    """
    graphql_url = "https://graphql.nexusmods.com"
    
    # GraphQL Query to get mod IDs and file IDs from a revision
    query = """
    query collectionRevision(slug: $slug, revision: $revision, domainName: $domainName) {
        modFiles {
          modId
          fileId
        }
      }
    """

    queryold = """
    query GetCollectionFiles($slug: String, $revision: Int, $domainName: String) {
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

        if response.status_code != 200:
            print(f"Failed API Call: {response.status_code}")
            print(f"Response: {response.text}")

        response.raise_for_status()

        data = response.json()
        
        if "errors" in data:
            print(f"GraphQL Errors: {data['errors']}")
            return []

        # Extract the list of modFiles
        revision_data = data.get("data", {}).get("collectionRevision")
        if not revision_data:
            print(f"Error: Collection {collection_id} Revision {revision_id} not found.")
            return []
            
        mod_files = revision_data.get("modFiles", [])
        
        # Transform into a cleaner list of dicts
        # The GraphQL returns camelCase: {'modId': 123, 'fileId': 456}
        # We'll normalize them to snake_case for your loop: {'mod_id': 123, 'file_id': 456}
        return [{"mod_id": m["modId"], "file_id": m["fileId"]} for m in mod_files]

    except Exception as e:
        print(f"GraphQL Query Failed: {e}")
        return []

def download_nexus_mod(nxm_link: str, headers: dict, final_download_dir: str, nexus_game_id: str, game_folder_name: str):
    """
    Downloads a mod into a game-specific subfolder found by matching nexus_game_id.
    """
    try:
        # 2. Parse the NXM link
        splitted_nxm = urlsplit(nxm_link)
        nxm_path = splitted_nxm.path.split('/')
        nxm_query = dict(item.split('=') for item in splitted_nxm.query.split('&'))

        mod_id = nxm_path[2]
        file_id = nxm_path[4] 

        # 4. Get the Download URI from Nexus API

        params = {
            'key': nxm_query.get("key"),
            'expires': nxm_query.get("expires")
        }
        
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

#handle_nexus_link("nxm://cyberpunk2077/collections/jiwwyn/revisions/70")