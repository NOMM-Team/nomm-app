import os
import requests
import json

import vdf

from gi.repository import GLib
from core.user_config import load_user_config
from core.tools import slugify, write_yaml

def get_epic_library() -> dict or None:
    epic_flatpak = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary/installed.json")
    epic_native = os.path.expanduser("~/.config/heroic/legendaryConfig/legendary/installed.json")
    if os.path.exists(epic_flatpak):
        path = epic_flatpak
    elif os.path.exists(epic_native):
        path = epic_native
    else:
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading Epic JSON: {e}")

def get_gog_library() -> dict or None:
    gog_flatpak = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/gog_store/installed.json")
    gog_native = os.path.expanduser("~/.config/heroic/gog_store/installed.json")
    if os.path.exists(gog_flatpak):
        path = gog_flatpak
    elif os.path.exists(gog_native):
        path = gog_native
    else:
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading GOG JSON: {e}")

def find_epic_game(yaml_data, yaml_path, game_title, installed_epic):
    for app_id, game_info in installed_epic.items():
        if slugify(game_info.get("title", "")) == slugify(game_title):
            game_path = game_info.get("install_path", "")
            yaml_data["platform"] = "heroic-epic"
            yaml_data["game_path"] = game_path
            write_yaml(yaml_data, yaml_path)
            
            return {
                "name": game_title,
                "img": get_art(app_id, "heroic-epic"),
                "path": game_path,
                "app_id": app_id,
                "platform": "heroic-epic",
                "game_config_path": yaml_path
            }
    return None

def find_gog_game(yaml_data, yaml_path, game_title, installed_gog):
    if not yaml_data.get("gog_id"):
        return None
        
    for game_info in installed_gog.get("installed", []):
        if slugify(game_info.get("appName", "")) == slugify(str(yaml_data["gog_id"])):
            game_path = game_info.get("install_path", "")
            yaml_data["platform"] = "heroic-gog"
            yaml_data["game_path"] = game_path
            write_yaml(yaml_data, yaml_path)
            
            return {
                "name": game_title,
                "img": get_art(yaml_data["gog_id"], "heroic-gog"),
                "path": game_path,
                "app_id": yaml_data["gog_id"],
                "platform": "heroic-gog",
                "game_config_path": yaml_path
            }
    return None

def obtain_heroic_libraries(game_paths: list) -> list:
    """Takes a list of unique game paths and attempts to extrapolate a list of library directories.
    This is used to request access to whole libraries and not just each game individually."""
    directory_paths = []
    for path in game_paths:
        if os.path.dirname(path) not in directory_paths:
            directory_paths.append(os.path.dirname(path))
    return directory_paths

def get_art(app_id: str | int, platform: str) -> dict:
    art = {"hero": None, "poster": None}
    if not app_id: return None

    paths = download_heroic_assets(app_id, platform)
    art["poster"] = paths.get("art_square")
    art["hero"] = paths.get("art_hero")
    return art

# Grabs the assets from heroic games launcher such as banner and game image
# TODO: Needs to be cleaned
def download_heroic_assets(appName: str, platform: str):
    if isinstance(appName, list):
        appName = str(appName[0])
    else:
        appName = str(appName)

    json_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/store/download-manager.json") # flatpak
    if not os.path.exists(json_path):
        json_path = os.path.expanduser("~/.config/heroic/store/download-manager.json") # not flatpak

    if isinstance(appName, list):
        appName = appName[0]
    
    cache_base = os.path.join(GLib.get_user_data_dir(), "nomm", "image-cache", f"{platform}", f"{appName}")
    
    if os.path.exists(cache_base):
        existing_files = {}
        for entry in os.listdir(cache_base):
            if entry.startswith("art_square"):
                existing_files["art_square"] = os.path.join(cache_base, entry)
            elif entry.startswith("art_hero"):
                existing_files["art_hero"] = os.path.join(cache_base, entry)
        
        if "art_square" in existing_files:
            print(f"Using cached assets for {appName}")
            return existing_files

    if not os.path.exists(json_path):
        print(f"Heroic config not found at {json_path}")
        return None

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        finished_apps = data.get("finished", [])
        target_info = None

        for entry in finished_apps:
            params = entry.get("params", {})
            game_info = params.get("gameInfo", {})
            
            # Match by internal appName (e.g., 'Curry') or title (e.g., 'ABZÛ')
            if params.get("appName") == appName or game_info.get("title") == appName:
                target_info = game_info
                break
        
        if not target_info:
            return None

        urls = {
            "art_square": target_info.get("art_square"),
            "art_hero": target_info.get("art_background") or target_info.get("art_cover")
        }

        os.makedirs(cache_base, exist_ok=True)
        downloaded_paths = {}

        for key, url in urls.items():
            if not url:
                continue
                
            ext = os.path.splitext(url)[1] if "." in url.split("/")[-1] else ".jpg"
            # Ensure extensions like .jpg?foo=bar are cleaned
            if "?" in ext: ext = ext.split("?")[0]
            
            local_path = os.path.join(cache_base, f"{key}{ext}")

            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(r.content)
                    downloaded_paths[key] = local_path
                    print(f"Downloaded: {local_path}")
            except Exception as e:
                print(f"Error downloading {key}: {e}")

        return downloaded_paths
    except Exception as e:
        print(f"Failed to process Heroic JSON: {e}")
        return None

