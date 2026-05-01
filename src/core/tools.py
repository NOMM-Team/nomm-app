import os
import yaml
import vdf
import requests
import re

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
    
    if isinstance(timestamp, str):
        return timestamp
    
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

def retrieve_casesensitive_paths(path:str):
    parts = path.split('/')
    part_list = []
    for part in parts:
        try:
            if not part:
                part_list.append('/')
                continue
            new_path = os.path.join(*part_list) if part_list else '/'
            found_item = next((f for f in os.listdir(new_path) if f.lower() == part.lower()), None)
            if found_item:
                part_list.append(found_item)
        except Exception as e:
            return None
    path = os.path.join(*part_list)
    return path

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

def process_bbcode(raw_desc: str) -> str:

    # 1. Convert BBCode/HTML-ish to Pango Markup
    pango_text = raw_desc.replace("<br />", "\n")
    pango_text = pango_text.replace("[b]", "<b>").replace("[/b]", "</b>")
    pango_text = pango_text.replace("[u]", "<u>").replace("[/u]", "</u>")
    pango_text = pango_text.replace("[i]", "<i>").replace("[/i]", "</i>")
    
    # Handle lists
    pango_text = pango_text.replace("[*]", "  • ").replace("[list]", "").replace("[/list]", "").replace("[/*]", "")

    # Handle colors: [color=#hex] -> <span foreground="#hex">
    pango_text = re.sub(r'\[color=([^\]]+)\]', r'<span foreground="\1">', pango_text)
    pango_text = pango_text.replace("[/color]", "</span>")
    
    # Handle sizes: [size=4] -> <span size="large">
    pango_text = re.sub(r'\[size=[^\]]+\]', r'<span size="large">', pango_text)
    pango_text = pango_text.replace("[/size]", "</span>")
    
    # Handle urls
    pango_text = re.sub(
        r'\[url=([^\]]+)\](.*?)\[/url\]', 
        r'<a href="\1">\2</a>', 
        pango_text, 
        flags=re.DOTALL
    )

    # Handle youtube links
    pango_text = re.sub(
        r'\[youtube\](.*?)\[/youtube\]', 
        r'<a href="https://youtu.be/\1">YouTube Video (\1)</a>', 
        pango_text, 
        flags=re.DOTALL
    )

    # Remove image tags
    pango_text = re.sub(r'\[img\].*?\[/img\]', '', pango_text)

    # Handle line tags
    divider = '<span foreground="gray">' + ("─" * 40) + '</span>'
    pango_text = pango_text.replace("[line]", f"\n{divider}\n")

    # Handle spoiler tags
    pango_text = pango_text.replace("[spoiler]", "\n--- SPOILER ---\n").replace("[/spoiler]", "\n----------------\n")

    pango_text = re.sub(r'\n\s*\n', '\n', pango_text) # Collapse excessive newlines

    print("BBCode successfuly parsed into HTML")
    return pango_text

def retrieve_casesensitive_paths(path:str):
    parts = path.split('/')
    part_list = []
    for part in parts:
        try:
            if not part:
                part_list.append('/')
                continue
            new_path = os.path.join(*part_list) if part_list else '/'
            found_item = next((f for f in os.listdir(new_path) if f.lower() == part.lower()), None)
            if found_item:
                part_list.append(found_item)
        except Exception as e:
            return None
    path = os.path.join(*part_list)
    return path
