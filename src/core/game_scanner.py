
import os

import vdf
import yaml

from gi.repository import GLib

from core.user_config import update_user_config
from core.tools import  write_yaml, load_yaml, slugify
from typing import List, Dict, Optional, Any

from platforms import steam, heroic, switch


def scan_all_games(game_configs_dir):
    matches = []
    steam_base = steam.get_steam_base_dir()

    user_config_dir = os.path.join(GLib.get_user_data_dir(), 'nomm', 'user_config.yaml')
    user_config = load_yaml(user_config_dir)

    # Pre-load Libraries
    steam_libraries = steam.get_library_paths(steam_base) # list with paths to Steam libraries
    epic_library = heroic.get_epic_library() # dict with paths to individual games
    gog_library = heroic.get_gog_library() # dict with paths to individual games

    if not os.path.exists(game_configs_dir):
        print(f"Configs directory not found at {game_configs_dir}")
        return matches

    heroic_game_paths = []

    # Scan each game config
    for filename in os.listdir(game_configs_dir):
        if not filename.lower().endswith((".yaml", ".yml")):
            continue

        yaml_path = os.path.join(game_configs_dir, filename)
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[!] Error processing {filename}: {e}, skipping")
            continue

        if not yaml_data.get("name") or "mods_path" not in yaml_data:
            print("[!] Missing required information in YAML file, skipping...")
            continue

        game_title = yaml_data["name"]

        # Scan Steam
        if steam_libraries:
            match = steam.find_game(yaml_data, yaml_path, game_title, steam_libraries, steam_base)
            if match:
                matches.append(match)
                continue

        # Scan Heroic Epic
        if epic_library:
            match = heroic.find_epic_game(yaml_data, yaml_path, game_title, epic_library)
            if match:
                matches.append(match)
                heroic_game_paths.append(match["path"])
                continue

        # Scan Heroic GOG
        if gog_library:
            match = heroic.find_gog_game(yaml_data, yaml_path, game_title, gog_library)
            if match:
                matches.append(match)
                heroic_game_paths.append(match["path"])
                continue
    
    heroic_libraries = heroic.obtain_heroic_libraries(heroic_game_paths)
    matches += switch.find_matches(game_configs_dir)
    game_libraries = steam_libraries + heroic_libraries
    print(f"Game libraries detected: {str(game_libraries)}")
    update_user_config("library_paths", sorted(game_libraries))

    return matches, game_libraries
