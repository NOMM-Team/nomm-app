import os
from datetime import datetime

from gi.repository import GLib
from core.tools import load_yaml, write_yaml
from typing import List, Dict, Any

# changes user setting by changing/writing the value for an associated key string
# new useful method for the future if we need to add another setting
def update_user_config(key: str, value: Any) -> None:
    user_config_path = os.path.join(GLib.get_user_data_dir (), 'nomm', 'user_config.yaml') 
    config = load_yaml(user_config_path)
    config[key] = value
    write_yaml(config, user_config_path)

# Returns both game path and steam/heroic(WIP) user data path
# dashboard.py/parse_deployment_paths
def parse_deployment_paths(game_config: dict, platform: str, app_id: str) -> List[Dict[str, str]]:
    game_path = game_config.get("game_path")
    deployment_dicts = game_config.get("mods_path", "")

    if not game_path:
        return {}

    user_data_path = ""
    if platform == "steam":
        user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(app_id) + "/pfx"
    elif platform in ["heroic-gog", "heroic-epic"]:
        user_data_path = os.path.dirname(os.path.dirname(game_path))
        #TODO: implement support for heroic user data files
        print("WARNING: User data folder not supported yet for heroic installations")
    else:
            print("unrecognised platform")
            return {}
    
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