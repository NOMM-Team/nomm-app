import os
from datetime import datetime

import yaml
from gi.repository import GLib
from typing import List, Dict, Any

# Grabs the required yaml, load it and return a dictionary
def load_yaml(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error while loading {path}: {e}")
    return {}

# Useful: Pushs a dictionary into the yaml
def write_yaml(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False)
    except Exception as e:
        print(f"Error while writing in {path}: {e}")

# Useful: changes user setting by changing/writing the value for an associated key string
def update_user_config(key: str, value: Any) -> None:
    user_config_path = os.path.join(GLib.get_user_data_dir (), 'nomm', 'user_config.yaml') 
    config = load_yaml(user_config_path)
    config[key] = value
    write_yaml(config, user_config_path)

#
def parse_deployment_paths(game_config: dict, platform: str, app_id: str) -> List[Dict[str, str]]:
    game_path = game_config.get("game_path")
    deployment_dicts = game_config.get("mods_path", "")

    if not game_path:
        return []

    user_data_path = ""
    if platform == "steam":
        user_data_path = os.path.dirname(os.path.dirname(game_path)) + f"/compatdata/{app_id}/pfx"
    elif platform in ["heroic-gog", "heroic-epic"]:
        user_data_path = os.path.dirname(os.path.dirname(game_path))

    if not isinstance(deployment_dicts, list):
        deployment_dicts = [{"name": "default", "path": deployment_dicts}]
    
    for deployment_dict in deployment_dicts:
        deployment_path = deployment_dict["path"]
        if "}" not in deployment_path: # Format NOMM 0.5
            deployment_path = os.path.join(game_path, deployment_path)
        else: # Format NOMM 0.6
            deployment_path = deployment_path.replace("{game_path}", game_path)
            deployment_path = deployment_path.replace("{user_data_path}", user_data_path)
        deployment_dict["path"] = deployment_path
    
    return deployment_dicts

# Games YAML are handled here
def get_metadata_path(base_folder: str, is_staging: bool = True) -> str:
    filename = ".staging.nomm.yaml" if is_staging else ".downloads.nomm.yaml"
    return os.path.join(base_folder, filename)

def load_metadata(path: str) -> dict:
    data = load_yaml(path)
    
    if not isinstance(data, dict):
        data = {}
    if "mods" not in data:
        data["mods"] = {}
    if "info" not in data:
        data["info"] = {}
    #WIP putting index here
    if "index" not in data:
        data["index"] = []
        
    return data

# Removes the mod from the staging metadata -- metadata allows to list mods that are installed
def remove_mod_from_metadata(path: str, mod_name: str) -> bool:
    data = load_metadata(path)
    if mod_name in data["mods"]:
        del data["mods"][mod_name]

        if mod_name in data["index"]:
            data["index"].remove(mod_name)
        
        write_yaml(data, path)
        
        staging_path = os.path.dirname(path)
        
        return True
    return False

def finalize_mod_metadata(filename: str, extracted_roots: list, deployment_target_name: str, staging_meta_path: str, downloads_meta_path: str):
    from datetime import datetime
    
    current_staging_metadata = load_metadata(staging_meta_path)
    
    current_download_metadata = {}
    if os.path.exists(downloads_meta_path):
        with open(downloads_meta_path, 'r') as f:
            current_download_metadata = yaml.safe_load(f) or {}

    if "info" not in current_staging_metadata and "info" in current_download_metadata:
        current_staging_metadata["info"] = current_download_metadata["info"]
    
    mod_name = filename.replace(".zip", "").replace(".rar", "").replace(".7z", "")
    
    if filename in current_download_metadata.get("mods", {}):
        mod_data = current_download_metadata["mods"][filename]
        mod_name = mod_data.get("name", mod_name)
        current_staging_metadata["mods"][mod_name] = mod_data
    else:
        current_staging_metadata["mods"][mod_name] = {}

    current_staging_metadata["mods"][mod_name]["mod_files"] = extracted_roots
    current_staging_metadata["mods"][mod_name]["status"] = "disabled"
    current_staging_metadata["mods"][mod_name]["archive_name"] = filename
    current_staging_metadata["mods"][mod_name]["install_timestamp"] = datetime.now().strftime("%c")
    current_staging_metadata["mods"][mod_name]["deployment_target"] = deployment_target_name
   
   #Adding index for load order
    if "index" not in current_staging_metadata:
        current_staging_metadata["index"] = []

    if mod_name not in current_staging_metadata["index"]:
        current_staging_metadata["index"].append(mod_name)
    
    staging_path = os.path.dirname(staging_meta_path)

    write_yaml(current_staging_metadata, staging_meta_path)

def read_index(staging_path: str) -> bool:
    current_staging_metadata = load_metadata(staging_path)
    return current_staging_metadata["index"]

# Change the mod index from the index list
def change_mod_index(staging_meta_path: str, mod_name: str, index: int):
    current_staging_metadata=load_metadata(staging_meta_path)
    
    if mod_name in current_staging_metadata["index"]:
        pos = current_staging_metadata["index"].index(mod_name)
        mod = current_staging_metadata["index"].pop(pos)
        current_staging_metadata["index"].insert(index, mod)
        
        try:
            write_yaml(current_staging_metadata, staging_meta_path)
            return True
        except Exception as e:
            print(f"Error while changing mod index: {e}")
            return False
    return False

# Check if the mod_index mods are also present from the mod folder and vice versa
# This method has to be changed so it changes ALL the metadata and loads everygame to make sure the display is never broken
##def check_index(staging_path: str):
##    if not os.path.exists(staging_path):
##        return []
##        
##    physical_folders = [
##        f for f in os.listdir(staging_path) 
##        if os.path.isdir(os.path.join(staging_path, f)) and not f.startswith('.')
##    ]
##
##    test_path = os.path.join(staging_path, ".staging.nomm.yaml")
##    current_index = read_index(test_path)
##    new_index = [mod for mod in current_index if mod in physical_folders]
##    
##    changed = False
##    for folder in physical_folders:
##        if folder not in new_index:
##            new_index.append(folder)
##            changed = True
##            
##    if len(new_index) != len(current_index):
##        changed = True
##
##    if changed:
##        try:
##            write_yaml(new_index, test_path)
##        except Exception as e:
##            print(f"Error while syncing index : {e}")
##
##    return new_index