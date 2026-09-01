
import os
from pathlib import Path
from nomm.core.user_config import update_user_config, PRESET_GAME_CONFIG_PATH, CUSTOM_GAME_CONFIG_PATH
from nomm.platforms import steam, heroic, switch
from nomm.core.tools import load_yaml


def get_game_configs():

    all_configs_data = []

    # Just in case the user hasn't created any custom configs
    Path(CUSTOM_GAME_CONFIG_PATH).mkdir(parents=True, exist_ok=True)

    # We load the custom game configs afterwards so they override the preset ones.
    for config_path in [PRESET_GAME_CONFIG_PATH, CUSTOM_GAME_CONFIG_PATH]:
        for filename in os.listdir(config_path):
            if not filename.lower().endswith((".yaml", ".yml")):
                continue

            yaml_path = os.path.join(config_path, filename)
            config_data = load_yaml(yaml_path)
            if not config_data:
                continue

            if "name" not in config_data or "mods_path" not in config_data:
                print("[!] Missing required information in YAML file, skipping...")
                continue

            all_configs_data.append(config_data)
    return all_configs_data


def scan_all_games():
    matches = []
    steam_base = steam.get_steam_base_dir()

    # Pre-load Libraries
    steam_libraries = steam.get_library_paths(steam_base)  # list with paths to Steam libraries
    epic_library = heroic.get_epic_library()  # dict with paths to individual games
    gog_library = heroic.get_gog_library()  # dict with paths to individual games

    heroic_game_paths = []

    # Scan each game config
    for config_data in get_game_configs():

        game_title = config_data["name"]

        # Scan Steam
        if steam_libraries:
            match = steam.find_game(config_data, game_title, steam_libraries, steam_base)
            if match:
                matches.append(match)
                continue

        # Scan Heroic Epic
        if epic_library:
            match = heroic.find_epic_game(config_data, game_title, epic_library)
            if match:
                matches.append(match)
                heroic_game_paths.append(match["path"])
                continue

        # Scan Heroic GOG
        if gog_library:
            match = heroic.find_gog_game(config_data, game_title, gog_library)
            if match:
                matches.append(match)
                heroic_game_paths.append(match["path"])
                continue

    heroic_libraries = heroic.obtain_heroic_libraries(heroic_game_paths)
    matches += switch.find_matches()
    game_libraries = steam_libraries + heroic_libraries
    print(f"Game libraries detected: {str(game_libraries)}")
    update_user_config("library_paths", sorted(game_libraries))

    return matches, game_libraries
