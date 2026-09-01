import os
import vdf
from pathlib import Path
from typing import List, Dict, Optional, Any

from nomm.core.user_config import load_user_config, parse_mod_paths
from nomm.core.tools import launch_option_merger, slugify

import gettext
_ = gettext.gettext

TOOL_APP_IDS: list[int] = [1887720, 432054, 432053, 376798, 376797, 352053, 352052, 314648, 314647, 270084, 270083, 858280, 930400,
                           961940, 996510, 1054830, 1113280, 1161040, 1245040, 1420170, 1493710, 1580130, 1826330, 1887720, 2180100,
                           2230260, 2348590, 2805730, 3086180, 3658110, 4628710, 4628740, 4427310, 4862110, 1391110, 1070560,
                           4185400, 4183110, 3810310, 1628350]


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


def get_installed_steam_games(game_libraries):

    steam_libraries = []

    for game_library in game_libraries:
        if "steam" in game_library:
            if Path(game_library).exists():
                steam_libraries.append(Path(game_library))

    print(f"Unique Steam Libraries: {steam_libraries}")

    installed_games = []

    for steam_library in steam_libraries:
        for manifest_file in steam_library.glob("appmanifest_*.acf"):
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    data = vdf.load(f)

                app_state = data.get("AppState", {})
                appid = int(app_state.get("appid", 0))
                name = app_state.get("name")

                if appid and name and appid not in TOOL_APP_IDS:
                    installed_games.append(
                        {
                            "name": name,
                            "appid": appid,
                            "installdir": app_state.get("installdir", ""),
                        }
                    )
            except Exception as e:
                print(f"Error reading {manifest_file}: {e}")
    installed_games = sorted(installed_games, key=lambda g: g["name"].lower())
    return installed_games


def get_library_paths(steam_base) -> List[str]:
    libraries = []

    if not steam_base:
        return libraries

    vdf_path = os.path.join(steam_base, "config/libraryfolders.vdf")

    try:
        with open(vdf_path, 'r', encoding='utf-8') as f:
            data = vdf.load(f)
            folders = data.get("libraryfolders", {})
            for index in folders:
                path = folders[index].get("path")
                if path:
                    full_path = os.path.join(path, "steamapps")
                    libraries.append(os.path.normpath(full_path))
    except Exception as e:
        print(f"Error parsing VDF at {vdf_path}: {e}")
    return libraries


def add_launch_options(steam_base: str, launch_options, steam_id: str):
    print(f"Adding Steam launch options: {launch_options}")
    localconfig_path = steam_base + "userdata/" + load_user_config()["steam_user_id"] + "/config/localconfig.vdf"
    print(f"...to localconfig file located at: {localconfig_path}")
    with open(localconfig_path, 'r') as vdf_file:
        localconfig = vdf.load(vdf_file)
    game_data = localconfig["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"][str(steam_id)]
    if "LaunchOptions" not in game_data:
        localconfig["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"][str(steam_id)]["LaunchOptions"] = launch_options
    else:
        localconfig["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"][str(steam_id)]["LaunchOptions"] = \
            launch_option_merger(game_data["LaunchOptions"], launch_options)
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
    if not os.path.exists(path):
        return None
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


def find_game(yaml_data, game_title, found_libs, steam_base) -> List[Dict[str, Any]]:
    """Scans for a specific game in previously detected Steam libraries"""
    yaml_game_name = yaml_data.get("steam_folder_name", game_title)
    slug_yaml_name = slugify(yaml_game_name)

    for lib in found_libs:
        lib = lib + "/common"
        if not os.path.exists(lib):
            continue
        for folder in os.listdir(lib):
            if slugify(folder) == slug_yaml_name:
                game_path = os.path.join(lib, folder)

                # mod path parsing
                user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(yaml_data["steam_id"]) + "/pfx"
                mod_paths: list[dict[str, str]] = parse_mod_paths(yaml_data["mods_path"], game_path, user_data_path)

                return {
                    "name": game_title,
                    "img": get_art(steam_base, yaml_data.get("steam_id")),
                    "path": game_path,
                    "app_id": yaml_data.get("steam_id"),
                    "platform": "steam",
                    "mod_paths": mod_paths,
                    "utilities": yaml_data.get("essential-utilities"),
                    "accent_colour": yaml_data.get("accent_colour"),
                    "load_order_path": yaml_data.get("load_order_path"),
                    "wiki_link": yaml_data.get("wiki_link"),
                    "nexus_id": yaml_data.get("nexus_id")
                }
    return None
