import os
from datetime import datetime

import yaml
from gi.repository import GLib
from typing import List, Dict, Any

# Grabs the required yaml, load it and return a dictionary -- no changes
def load_yaml(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error while loading {path}: {e}")
    return {}

# Pushs a dictionary into the yaml --- same as finalize setup, safe_dump is standard security measure but it would work with dump
def write_yaml(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False)
    except Exception as e:
        print(f"Error while writing in {path}: {e}")

# changes user setting by changing/writing the value for an associated key string
def update_user_config(key: str, value: Any) -> None:
    user_config_path = os.path.join(GLib.get_user_data_dir (), 'nomm', 'user_config.yaml') 
    config = load_yaml(user_config_path)
    config[key] = value
    write_yaml(config, user_config_path)

# Returns both game path and steam/heroic(WIP) user data path
def parse_deployment_paths(game_config: dict, platform: str, app_id: str) -> List[Dict[str, str]]:
    game_path = game_config.get("game_path")
    deployment_dicts = game_config.get("mods_path", "")

    if not game_path:
        return []

    user_data_path = ""
    if platform == "steam":
        user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(app_id) + "/pfx"
    elif platform in ["heroic-gog", "heroic-epic"]:
        user_data_path = os.path.dirname(os.path.dirname(game_path))
        #TODO: implement support for heroic user data files
        print("WARNING: User data folder not supported yet for heroic installations")
    else:
            print("unrecognised platform")
            return []
    
    # Handle case where there is only one path provided, and it's not a list of dicts
    if not isinstance(deployment_dicts, list):
        deployment_dicts = [{"name": "default",
        "path": deployment_dicts}]
    
    # Parse the paths
    for deployment_dict in deployment_dicts:
        deployment_path = deployment_dict["path"]
        if "}" not in deployment_path: # NOMM 0.5 Format
            deployment_path = os.path.join(game_path, deployment_path)
        else: # NOMM 0.6 Format
            deployment_path = deployment_path.replace("{game_path}", game_path)
            deployment_path = deployment_path.replace("{user_data_path}", user_data_path)
        deployment_dict["path"] = deployment_path
    
    return deployment_dicts