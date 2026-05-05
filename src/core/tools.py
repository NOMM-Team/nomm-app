import os
import yaml
import vdf
import requests

from typing import List, Dict, Any
from gi.repository import GLib, Gio

def get_contrast_color(hex_code: str) -> str:
    hex_code = hex_code.lstrip('#')
    
    r, g, b = [int(hex_code[i:i+2], 16) for i in (0, 2, 4)]
    
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    
    return "#000000" if luminance > 0.5 else "#ffffff"
        
def load_yaml(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error while loading {path}: {e}")
    return {}

def write_yaml(data: dict, path: str) -> bool:
    # difference here: creates the path if needed
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False)
            return True
    except Exception as e:
        print(f"Error while writing in {path}: {e}")
        return False
    return False

def timestamp_converter(timestamp: str, timestamp_type="short") -> str:
    """Converts standard time timestamps (2026-04-28 15:52:14.249614) into localised text"""
    #TODO: review this method to produce a nicer timestamp format
    legible_timestamp = timestamp
    try:
        timestamp.strftime("%c")
    except:
        print(f"Could not translate timestamp: {timestamp}")
        return timestamp
    if timestamp_type == "long": # used for tooltips
        return timestamp.strftime("%c")
    if timestamp_type == "short": # used for the base UI
        return timestamp.strftime("%x %H:%M")
    return legible_timestamp

def load_user_config() -> dict:
    """Returns the user's NOMM configuration file data as a dictionary"""
    user_config_path = os.path.join(GLib.get_user_data_dir (), 'nomm', 'user_config.yaml')
    try:
        data = load_yaml(user_config_path)
    except:
        print("Error: could not load user config.")
        return None
    return data

def write_user_config(data: dict) -> dict:
    """Writes to the user's NOMM configuration file"""
    try: 
        user_config_path = os.path.join(GLib.get_user_data_dir (), 'nomm', 'user_config.yaml')
        write_yaml(data, user_config_path)
    except:
        print("Error: could not write to user config.")
        return False
    return True

def translate_fuse_path(folder_info) -> str:
    folder_path = folder_info.get_path()
    if "run/user" in folder_path:
        print(f"Detected sandboxed path: {folder_path}")
        try:
            # Get FileInfo for File
            file_info = folder_info.query_info("xattr::document-portal.host-path", Gio.FileQueryInfoFlags.NONE, None)

            # Query file attribute for real path
            real_path = file_info.get_attribute_string("xattr::document-portal.host-path")
            if real_path is not None: # Attribute does not exist if None
                print(f"Real path parsed: {real_path}")
                return real_path
            else:
                pass # TODO: Throw error dialog to request user to broaden sandbox permissions.
        except GLib.Error:
            print("Can not get real path. If you see this message you will need to manually give NOMM host filesystem permissions.")
    return folder_path

def get_username_from_steam_id(steam_id: str, steam_base_path) -> str:
    localconfig_path = steam_base_path + "userdata/" + steam_id + "/config/localconfig.vdf"
    if not os.path.exists(localconfig_path):
        print(f"No file found at : {localconfig_path}")
        return None
    with open(localconfig_path, 'r') as vdf_file:
        localconfig_data = vdf.load(vdf_file)
    try:
        steam_username = localconfig_data["UserLocalConfigStore"]["friends"][steam_id]["name"]
    except ValueError:
        print("Could not find the Steam username")
        return None
    return steam_username

def download_image(url: str, save_path: str) -> bool:
    # Send a GET request to the URL
    response = requests.get(url, stream=True)
    
    # Check if the request was successful (Status Code 200)
    if response.status_code == 200:
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"Thumbnail successfully downloaded: {save_path}")
        return True
    else:
        print(f"Failed to retrieve image. Status code: {response.status_code}")
        return False
