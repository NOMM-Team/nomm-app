import os
import yaml
from enum import Enum

from nomm.core.tools import load_cached_assets, download_image
from nomm.core.user_config import load_user_config, SWITCH_GAME_CONFIG_PATH, DATA_DIR

# Ryubing paths
RYUBING_GAME_PATH = os.path.expanduser("~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/games")
RYUBING_MOD_PATH = os.path.expanduser("~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/sdcard/atmosphere/contents")
# Eden paths
EDEN_GAME_PATH = os.path.expanduser("~/.local/share/eden/load")
EDEN_MOD_PATH = os.path.expanduser("~/.local/share/eden/load")
# Citron paths
CITRON_GAME_PATH = os.path.expanduser("~/.local/share/citron/load")
CITRON_MOD_PATH = os.path.expanduser("~/.local/share/citron/load")


# Supported config values
class EmulatorName(Enum):
    RYUBING = "Ryubing"
    EDEN = "Eden"
    CITRON = "Citron"


def find_matches() -> list:

    if not os.path.exists(SWITCH_GAME_CONFIG_PATH) or list_emulators() == []:
        return []

    PLATFORM = "switch"

    emulator_name_str = load_user_config().get("preferred_switch_emulator", list_emulators()[0])

    try:
        preferred_emulator = EmulatorName(emulator_name_str)
    except ValueError as e:
        print(f"Preferred emulator value is not supported: {e}")
        return []

    try:
        with open(SWITCH_GAME_CONFIG_PATH, 'r') as f:
            supported_switch_games = yaml.safe_load(f)
    except Exception as e:
        print(f"Was not able to load switch config - is it improperly formatted? {e}")

    if preferred_emulator == EmulatorName.CITRON:
        game_path = CITRON_GAME_PATH
        mods_path = CITRON_MOD_PATH
    elif preferred_emulator == EmulatorName.EDEN:
        game_path = EDEN_GAME_PATH
        mods_path = EDEN_MOD_PATH
    elif preferred_emulator == EmulatorName.RYUBING:
        game_path = RYUBING_GAME_PATH
        mods_path = RYUBING_MOD_PATH

    installed_games = os.listdir(game_path)
    matches = []

    for game in supported_switch_games:
        # Ryujinx has game IDs in lowercase, and Eden has them in uppercase :')
        if preferred_emulator == EmulatorName.RYUBING:
            game_id = game["switch_id"].lower()
        elif preferred_emulator in [EmulatorName.CITRON, EmulatorName.EDEN]:
            game_id = game["switch_id"].upper()
        if game_id in installed_games:
            art = load_cached_assets(game["full_name"], PLATFORM)
            if not art:
                cache_base = os.path.join(DATA_DIR, "image-cache", PLATFORM, f"{game["full_name"]}")
                grid_path = os.path.join(cache_base, "art_grid.jpg")
                download_image(game["grid_url"], grid_path)
                hero_path = os.path.join(cache_base, "art_hero.jpg")
                download_image(game["hero_url"], hero_path)
                art = {
                    "poster": grid_path,
                    "hero": hero_path
                }
            mod_paths = [{"name": "default", "path": f"{mods_path}/{game_id}/"}]
            matches.append(
                {
                    "name": game["full_name"],
                    "img": art,
                    "path": os.path.join(game_path, game_id),
                    "app_id": game_id,
                    "platform": PLATFORM,
                    "mod_paths": mod_paths,
                    "utilities": None,
                    "accent_colour": None
                }
            )

    return matches


def list_emulators():
    """Lists Switch emulators installed on user's system"""
    installed_emulator_list = []
    if os.path.exists(CITRON_GAME_PATH):
        installed_emulator_list.append(EmulatorName.CITRON.value)
    if os.path.exists(EDEN_GAME_PATH):
        installed_emulator_list.append(EmulatorName.EDEN.value)
    if os.path.exists(RYUBING_GAME_PATH):
        installed_emulator_list.append(EmulatorName.RYUBING.value)

    return installed_emulator_list


def get_emulator_logo(emulator):
    try:
        emulator = EmulatorName(emulator)
    except ValueError as e:
        print(f"[!] Preferred emulator value is not supported: {e}")
    if emulator == EmulatorName.CITRON:
        return "citron-logo"
    elif emulator == EmulatorName.EDEN:
        return "eden-logo"
    elif emulator == EmulatorName.RYUBING:
        return "ryubing-logo"
