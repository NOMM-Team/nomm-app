import json
import os
import re
import requests

import vdf
import yaml

from gi.repository import GLib

from core.config import update_user_config, write_yaml, load_yaml
from typing import List, Dict, Optional, Any

# Launcher.py/slugify
def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())

# launcher.py/get_steam_base_dir
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

# launcher.py/get_steam_library_paths
def get_steam_library_paths(vdf_path) -> List[str]:
    libraries = []
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

# launcher.py/get_heroic_library_paths
def get_heroic_library_paths() -> Dict[str, Optional[str]]:
    paths = {"epic": None, "gog": None}
    
    # Epic
    epic_flatpak = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary/installed.json")
    epic_native = os.path.expanduser("~/.config/heroic/legendaryConfig/legendary/installed.json")
    # Gives to "epic" key either flatpak path or native path
    paths["epic"] = epic_flatpak if os.path.exists(epic_flatpak) else (epic_native if os.path.exists(epic_native) else None)

    # GOG
    gog_flatpak = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/gog_store/installed.json")
    gog_native = os.path.expanduser("~/.config/heroic/gog_store/installed.json")
    # Gives to "gog" key either flatpak path or native path
    paths["gog"] = gog_flatpak if os.path.exists(gog_flatpak) else (gog_native if os.path.exists(gog_native) else None)

    # Returns the paths in a dictionary
    return paths

# Now returns a dictionary so you don't need two methods to get 2 images
# launcher.py/find_game_art + edition to return a dictionnary with 
# both the banner and the game poster
def find_game_art(app_id: str | int, platform: str, steam_base: Optional[str]) -> dict:
    art = {"hero": None, "poster": None}
    if not app_id: return None
    if platform == "steam" and steam_base:
        path = os.path.join(steam_base, "appcache/librarycache", str(app_id))
        if not os.path.exists(path): return None
        for root, _, files in os.walk(path):
            if "library_hero.jpg" in files:
                art["hero"] = os.path.join(root, "library_hero.jpg")
            for t in ["library_capsule.jpg", "library_600x900.jpg"]:
                if t in files:
                    art["poster"] = os.path.join(root, t)
                    break
    elif platform == "heroic-epic":
        paths = download_heroic_assets(app_id, platform)
        art["poster"] = paths.get("art_square")
        art["hero"] = paths.get("art_hero")
        return art if art else None
    elif platform == "heroic-gog":
        if isinstance(app_id, list):
            app_id = app_id[0]
        paths = download_heroic_assets(app_id, platform)
        art["poster"] = paths.get("art_square")
        art["hero"] = paths.get("art_hero")
        return art if art else None
    return art

# launcher.py/game_title_matcher (l:320)
def _scan_steam_game(yaml_data, yaml_path, game_title, found_libs, steam_base) -> List[Dict[str, Any]]:
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
                
                return {
                    "name": game_title,
                    "img": find_game_art(yaml_data.get("steam_id"), "steam", steam_base),
                    "path": game_path,
                    "app_id": yaml_data.get("steam_id"),
                    "platform": "steam",
                    "game_config_path": yaml_path
                }
    return None

# Same as previous one but for heroic epic
# launcher.py/game_title_matcher
def _scan_heroic_epic_game(yaml_data, yaml_path, game_title, installed_epic, steam_base):
    for app_id, game_info in installed_epic.items():
        if slugify(game_info.get("title", "")) == slugify(game_title):
            game_path = game_info.get("install_path", "")
            yaml_data["platform"] = "heroic-epic"
            yaml_data["game_path"] = game_path
            write_yaml(yaml_data, yaml_path)
            
            return {
                "name": game_title,
                "img": find_game_art(app_id, "heroic-epic", steam_base),
                "path": game_path,
                "app_id": app_id,
                "platform": "heroic-epic",
                "game_config_path": yaml_path
            }
    return None

# Same as previous one but for heroic epic
# launcher.py/game_title_matcher
def _scan_heroic_gog_game(yaml_data, yaml_path, game_title, installed_gog, steam_base):
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
                "img": find_game_art(yaml_data["gog_id"], "heroic-gog", steam_base),
                "path": game_path,
                "app_id": yaml_data["gog_id"],
                "platform": "heroic-gog",
                "game_config_path": yaml_path
            }
    return None

# launcher.py/run_background_workflow
def scan_all_games(game_configs_dir):
    matches = []
    steam_base = get_steam_base_dir()
    
    user_config_dir = os.path.join(GLib.get_user_data_dir(), 'nomm', 'user_config.yaml')
    user_config = load_yaml(user_config_dir)
    found_libs = set(user_config.get("library_paths", []))

    # Update Steam Libraries if empty
    if not found_libs and steam_base:
        found_libs = set(get_steam_library_paths(os.path.join(steam_base, "config/libraryfolders.vdf")))
        if found_libs:
            update_user_config("library_paths", sorted(list(found_libs)))

    # Pre-load Heroic Libraries
    heroic_paths = get_heroic_library_paths()
    installed_epic = {}
    installed_gog = {}
    
    if heroic_paths["epic"]:
        try:
            with open(heroic_paths["epic"], 'r', encoding='utf-8') as f:
                installed_epic = json.load(f)
        except Exception as e:
            print(f"Error loading Epic JSON: {e}")
            
    if heroic_paths["gog"]:
        try:
            with open(heroic_paths["gog"], 'r', encoding='utf-8') as f:
                installed_gog = json.load(f)
        except Exception as e:
            print(f"Error loading GOG JSON: {e}")

    if not os.path.exists(game_configs_dir):
        print(f"Configs directory not found at {game_configs_dir}")
        return matches

    # Scan each config
    for filename in os.listdir(game_configs_dir):
        if not filename.lower().endswith((".yaml", ".yml")):
            continue
            
        yaml_path = os.path.join(game_configs_dir, filename)
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f) or {}

            if not yaml_data.get("name") or yaml_data.get("mods_path") is None:
                continue
            
            game_title = yaml_data["name"]

            # --- SCAN STEAM ---
            if found_libs:
                match = _scan_steam_game(yaml_data, yaml_path, game_title, found_libs, steam_base)
                if match:
                    matches.append(match)
                    continue

            # --- SCAN HEROIC EPIC ---
            if installed_epic:
                match = _scan_heroic_epic_game(yaml_data, yaml_path, game_title, installed_epic, steam_base)
                if match:
                    matches.append(match)
                    continue

            # --- SCAN HEROIC GOG ---
            if installed_gog:
                match = _scan_heroic_gog_game(yaml_data, yaml_path, game_title, installed_gog, steam_base)
                if match:
                    matches.append(match)
                    continue

        except Exception as e:
            print(f"Error processing {filename} during scan: {e}")

    return matches

# Grabs the assets from heroic games launcher such as banner and game image
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