import os
import json

from nomm.core.user_config import parse_mod_paths, DATA_DIR
from nomm.core.tools import slugify, load_cached_assets, download_image


def get_epic_library() -> dict | None:
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


def get_gog_library() -> dict | None:
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


def find_epic_game(yaml_data, game_title, installed_epic):
    for app_id, game_info in installed_epic.items():
        if slugify(game_info.get("title", "")) == slugify(game_title):
            game_path = game_info.get("install_path", "")

            # mod path parsing
            # TODO: add support for heroic/EPIC user data path
            user_data_path = ""
            mod_paths = parse_mod_paths(yaml_data["mods_path"], game_path, user_data_path)

            return {
                "name": game_title,
                "img": get_art(game_title, app_id, "heroic-epic"),
                "path": game_path,
                "app_id": app_id,
                "platform": "heroic-epic",
                "mod_paths": mod_paths,
                "utilities": yaml_data.get("essential-utilities"),
                "accent_colour": yaml_data.get("accent_colour"),
                "load_order_path": yaml_data.get("load_order_path"),
                "wiki_link": yaml_data.get("wiki_link"),
                "nexus_id": yaml_data.get("nexus_id")
            }
    return None


def find_gog_game(yaml_data, game_title, installed_gog):
    if not yaml_data.get("gog_id"):
        return None

    for game_info in installed_gog.get("installed", []):
        if slugify(game_info.get("appName", "")) == slugify(str(yaml_data["gog_id"])):
            game_path = game_info.get("install_path", "")

            # mod path parsing
            # TODO: add support for heroic/GOG user data path
            user_data_path = ""
            mod_paths = parse_mod_paths(yaml_data["mods_path"], game_path, user_data_path)

            return {
                "name": game_title,
                "img": get_art(game_title, yaml_data["gog_id"], "heroic-gog"),
                "path": game_path,
                "app_id": yaml_data["gog_id"],
                "platform": "heroic-gog",
                "mod_paths": mod_paths,
                "utilities": yaml_data.get("essential-utilities"),
                "accent_colour": yaml_data.get("accent_colour"),
                "load_order_path": yaml_data.get("load_order_path"),
                "wiki_link": yaml_data.get("wiki_link"),
                "nexus_id": yaml_data.get("nexus_id")
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


def get_art(game_title: str, app_id: str | int, platform: str) -> dict:
    if not app_id:
        return None

    art = load_cached_assets(game_title, platform)
    if not art:
        if download_heroic_assets(game_title, app_id, platform):
            art = load_cached_assets(game_title, platform)
        else:
            print(f"Could not download heroic assets for game: {game_title}")
            return {"hero": None, "poster": None}
    return art


# Grabs the assets from heroic games launcher such as banner and game image
def download_heroic_assets(game_title: str, appName: str, platform: str):

    json_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/store/download-manager.json")  # flatpak
    if not os.path.exists(json_path):
        json_path = os.path.expanduser("~/.config/heroic/store/download-manager.json")  # not flatpak

    cache_base = os.path.join(DATA_DIR, "image-cache", f"{platform}", f"{game_title}")

    if not os.path.exists(json_path):
        print(f"Heroic config not found at {json_path}")
        return None

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to process Heroic JSON: {e}")
        return None

    finished_apps = data.get("finished", [])
    target_info = None

    for entry in finished_apps:
        params = entry.get("params", {})
        game_info = params.get("gameInfo", {})

        # Match by internal appName (e.g., 'Curry') or title (e.g., 'ABZÛ')
        if params.get("appName") == str(appName) or game_info.get("title") == appName:
            target_info = game_info
            break

    if not target_info:
        return None

    urls = {
        "art_grid": target_info.get("art_square"),
        "art_hero": target_info.get("art_background") or target_info.get("art_cover")
    }

    os.makedirs(cache_base, exist_ok=True)

    for key, url in urls.items():
        if not url:
            continue

        ext = os.path.splitext(url)[1] if "." in url.split("/")[-1] else ".jpg"

        if "?" in ext:
            ext = ext.split("?")[0]

        local_path = os.path.join(cache_base, f"{key}{ext}")

        download_image(url, local_path)

    return True
