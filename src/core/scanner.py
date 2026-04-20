# src/core/scanner.py

import os
import json
import yaml
import vdf
import re
from core.config import load_user_config, update_user_config, write_yaml
from core.heroic_asset import download_heroic_assets

def slugify(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

def get_steam_base_dir():
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

def get_steam_library_paths(vdf_path):
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

def get_heroic_library_paths():
    paths = {"epic": None, "gog": None}
    
    # Epic
    epic_flatpak = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary/installed.json")
    epic_native = os.path.expanduser("~/.config/heroic/legendaryConfig/legendary/installed.json")
    paths["epic"] = epic_flatpak if os.path.exists(epic_flatpak) else (epic_native if os.path.exists(epic_native) else None)

    # GOG
    gog_flatpak = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/gog_store/installed.json")
    gog_native = os.path.expanduser("~/.config/heroic/gog_store/installed.json")
    paths["gog"] = gog_flatpak if os.path.exists(gog_flatpak) else (gog_native if os.path.exists(gog_native) else None)

    return paths

def find_game_art(app_id, platform, steam_base):
    if not app_id: return None
    if platform == "steam" and steam_base:
        path = os.path.join(steam_base, "appcache/librarycache", str(app_id))
        if not os.path.exists(path): return None
        for root, _, files in os.walk(path):
            for t in ["library_capsule.jpg", "library_600x900.jpg"]:
                if t in files: return os.path.join(root, t)
    elif platform == "heroic-epic":
        paths = download_heroic_assets(app_id, platform)
        return paths.get("art_square") if paths else None
    elif platform == "heroic-gog":
        if isinstance(app_id, list):
            app_id = app_id[0]
        paths = download_heroic_assets(app_id, platform)
        return paths.get("art_square") if paths else None
    return None

# ==========================================
# SOUS-FONCTIONS DE SCAN PAR PLATEFORME
# ==========================================

def _scan_steam_game(yaml_data, yaml_path, game_title, found_libs, steam_base):
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

# ==========================================
# FONCTION PRINCIPALE
# ==========================================

def scan_all_games(game_configs_dir):
    """Fonction principale qui scanne tout et retourne une liste de dictionnaires de jeux trouvés."""
    matches = []
    steam_base = get_steam_base_dir()
    
    user_config = load_user_config()
    found_libs = set(user_config.get("library_paths", []))

    # 1. Update Steam Libraries if empty
    if not found_libs and steam_base:
        found_libs = set(get_steam_library_paths(os.path.join(steam_base, "config/libraryfolders.vdf")))
        if found_libs:
            update_user_config("library_paths", sorted(list(found_libs)))

    # 2. Pre-load Heroic Libraries (Optimisation : lu une seule fois, pas à chaque jeu)
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

    # 3. Scan each config
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