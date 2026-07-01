import os
import yaml

from gi.repository import GLib
from core.tools import load_cached_assets, download_image

def find_matches(game_configs_dir) -> list:

    switch_config_path = os.path.join(game_configs_dir, "emulation/switch.yaml")
    if not os.path.exists(switch_config_path):
        return []

    PLATFORM = "switch"
    

    try:
        with open(switch_config_path, 'r') as f:
            supported_switch_games = yaml.safe_load(f)
    except Exception as e:
        print(f"Was not able to load switch config - is it improperly formatted? {e}")

    ryujinx_game_path = os.path.expanduser("~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/games")

    installed_games = os.listdir(ryujinx_game_path)
    matches = []

    for game in supported_switch_games:
        if game["switch_id"].lower() in installed_games:
            art = load_cached_assets(game["full_name"], PLATFORM)
            if not art:
                cache_base = os.path.join(GLib.get_user_data_dir(), "nomm", "image-cache", PLATFORM, f"{game["full_name"]}")
                grid_path = os.path.join(cache_base, "art_grid.jpg")
                download_image(game["grid_url"], grid_path)
                hero_path = os.path.join(cache_base, "art_hero.jpg")
                download_image(game["hero_url"], hero_path)
                art = {
                    "poster" : grid_path,
                    "hero" : hero_path
                }
            mod_paths = {"name": "default",
            "path": f".var/app/io.github.ryubing.Ryujinx/config/Ryujinx/sdcard/atmosphere/contents/{game["switch_id"]}/"}
            matches.append(
                {
                    "name": game["full_name"],
                    "img": art,
                    "path": os.path.join(ryujinx_game_path, game["switch_id"]),
                    "app_id": game["switch_id"],
                    "platform": PLATFORM,
                    "game_config_path": switch_config_path,
                    "mod_paths": mod_paths,
                    "utilities": None
                }
            )
    
    return matches