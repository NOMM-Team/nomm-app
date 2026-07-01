import os

import vdf

from typing import List, Dict, Optional, Any

from core.user_config import load_user_config, parse_mod_paths
from core.tools import launch_option_merger, slugify, write_yaml

def get_steam_base_dir() -> Optional[str]:
    paths = [
        os.path.expanduser("~/.steam/debian-installation/"),
        os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/"),
        os.path.expanduser("~/.local/share/Steam/"),
        os.path.expanduser("~/snap/steam/common/.local/share/Steam/")
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def get_library_paths(steam_base) -> List[str]:
    libraries = []

    vdf_path = os.path.join(steam_base, "config/libraryfolders.vdf")

    try:
        with open(vdf_path, 'r', encoding='utf-8') as f:
            data = vdf.load(f)
            folders = data.get("libraryfolders", {})
            for index in folders:
                path = folders[index].get("path")
                if path:
                    full_path = os.path.join(path, "steamapps/common")
                    libraries.append(os.path.normpath(full_path))
    except Exception as e:
        print(f"Error parsing VDF at {vdf_path}: {e}")
    return libraries

def add_launch_options(steam_base, launch_options):
    print(f"Adding Steam launch options: {launch_options}")
    localconfig_path = steam_base + "userdata/" + load_user_config()["steam_user_id"] + "/config/localconfig.vdf"
    print(f"...to localconfig file located at: {localconfig_path}")
    with open(localconfig_path, 'r') as vdf_file:
        localconfig = vdf.load(vdf_file)
    game_data = localconfig["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"][str(steam_id)]
    if "LaunchOptions" not in game_data:
        localconfig["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"][str(steam_id)]["LaunchOptions"] = launch_options
    else:
        localconfig["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"][str(steam_id)]["LaunchOptions"] = launch_option_merger(game_data["LaunchOptions"], launch_options)
    with open(localconfig_path, 'w') as vdf_file:
        vdf.dump(localconfig, vdf_file)

def get_username_from_steam_id(steam_id: str, steam_base_path) -> str:
    localconfig_path = steam_base_path + "userdata/" + steam_id + "/config/localconfig.vdf"
    if not os.path.exists(localconfig_path):
        print(f"No file found at : {localconfig_path}")
        return None
    with open(localconfig_path, 'r') as vdf_file:
        localconfig_data = vdf.load(vdf_file)
    try:
        steam_username = localconfig_data["UserLocalConfigStore"]["friends"][steam_id]["name"]
    except KeyError:
        print(f"[!] Could not find the Steam username for steam ID: {steam_id}")
        return None
    return steam_username

def get_art(steam_base: str, app_id: str):
    """Obtains art for Steam games by retrieving the paths from the local Steam cache"""
    path = os.path.join(steam_base, "appcache/librarycache", str(app_id))
    if not os.path.exists(path): return None
    art = {}
    for root, _, files in os.walk(path):
        if "library_hero.jpg" in files:
            art["hero"] = os.path.join(root, "library_hero.jpg")
        for target in ["library_capsule.jpg", "library_600x900.jpg"]:
            if target in files:
                art["poster"] = os.path.join(root, target)
                break
        if "hero" in art and "poster" in art:
            return art
    print(f"Could not find hero and poster for game: {app_id}")
    return None

def find_game(yaml_data, yaml_path, game_title, found_libs, steam_base) -> List[Dict[str, Any]]:
    """Scans for a specific game in previously detected Steam libraries"""
    yaml_game_name = yaml_data.get("steam_folder_name", game_title)
    slug_yaml_name = slugify(yaml_game_name)
    
    for lib in found_libs:
        if not os.path.exists(lib): continue
        for folder in os.listdir(lib):
            if slugify(folder) == slug_yaml_name:
                game_path = os.path.join(lib, folder)
                yaml_data["platform"] = "steam"
                yaml_data["game_path"] = game_path
                write_yaml(yaml_data, yaml_path)

                # mod path parsing
                user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(yaml_data["steam_id"]) + "/pfx"
                mod_paths = parse_mod_paths(yaml_data["mods_path"], game_path, user_data_path)
                
                return {
                    "name": game_title,
                    "img": get_art(steam_base, yaml_data.get("steam_id")),
                    "path": game_path,
                    "app_id": yaml_data.get("steam_id"),
                    "platform": "steam",
                    "game_config_path": yaml_path,
                    "mod_paths": mod_paths,
                    "utilities": yaml_data.get("essential-utilities")
                }
    return None