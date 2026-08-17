import os
import yaml
import requests
import re
import html

from pathlib import Path
from typing import Callable, Optional
from gi.repository import GLib, Gio, Gtk


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
        except GLib.Error:
            print("Can not get real path. If you see this message you will need to manually give NOMM host filesystem permissions.")
    return folder_path



def retrieve_casesensitive_paths(path:str):
    parts = path.split('/')
    part_list = ['/']
    for part in parts[1:]:
        try:
            new_path = os.path.join(*part_list) if part_list else '/'
        except Exception as e:
            return None    
        found_item = next((f for f in os.listdir(new_path) if f.lower() == part.lower()), None)
        if found_item:
            part_list.append(found_item)
    path = os.path.join(*part_list)
    return path

def download_image(url: str, save_path: str) -> bool:
    # Send a GET request to the URL
    response = requests.get(url, stream=True)
    
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    # Check if the request was successful (Status Code 200)
    if response.status_code == 200:
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"Image successfully downloaded and stored in cache: {save_path}")
        return True
    else:
        print(f"Failed to download image. Status code: {response.status_code}")
        return False

def process_bbcode(raw_desc: str) -> str:

    # 1. Convert BBCode/HTML-ish to Pango Markup
    pango_text = raw_desc.replace("<br />", "\n")
    pango_text = pango_text.replace("[b]", "<b>").replace("[/b]", "</b>")
    pango_text = pango_text.replace("[u]", "<u>").replace("[/u]", "</u>")
    pango_text = pango_text.replace("[i]", "<i>").replace("[/i]", "</i>")
    
    # Handle centering
    pango_text = pango_text.replace("[center]", "").replace("[/center]", "")
    
    # Handle fonts
    pango_text = re.sub(r'\[font=([^\]]+)\]', r'<span font_family="\1">', pango_text)
    pango_text = pango_text.replace("[/font]", "</span>")

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

def sanitize_for_pango(raw_html: str) -> str:
    """Class-free HTML sanitizer that auto-closes unclosed tags for GTK Pango. Mainly used for GameBanana descriptions."""
    if not raw_html:
        return ""

    text = raw_html
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(p|div)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>', r'___A_HREF___\1___', text, flags=re.IGNORECASE)
    text = re.sub(r'</a>', '___A_END___', text, flags=re.IGNORECASE)
    text = re.sub(r'<(b|strong)[^>]*>', '___B_START___', text, flags=re.IGNORECASE)
    text = re.sub(r'</(b|strong)>', '___B_END___', text, flags=re.IGNORECASE)
    text = re.sub(r'<(i|em)[^>]*>', '___I_START___', text, flags=re.IGNORECASE)
    text = re.sub(r'</(i|em)>', '___I_END___', text, flags=re.IGNORECASE)
    text = re.sub(r'<u[^>]*>', '___U_START___', text, flags=re.IGNORECASE)
    text = re.sub(r'</u>', '___U_END___', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.escape(text)
    text = text.replace('___B_START___', '<b>').replace('___B_END___', '</b>')
    text = text.replace('___I_START___', '<i>').replace('___I_END___', '</i>')
    text = text.replace('___U_START___', '<u>').replace('___U_END___', '</u>')
    text = re.sub(r'___A_HREF___(.*?)___', r'<a href="\1">', text)
    text = text.replace('___A_END___', '</a>')
    for tag in ['b', 'i', 'u', 'a']:
        open_count = len(re.findall(f'<{tag}[^>]*>', text))
        close_count = len(re.findall(f'</{tag}>', text))
        if open_count > close_count:
            text += f"</{tag}>" * (open_count - close_count)

    return text.strip()

def list_archives(archives_directory: str):

    ARCHIVE_MIME_TYPES = {
                "application/zip",
                "application/x-zip-compressed",
                "application/x-rar",
                "application/vnd.rar",
                "application/x-rar-compressed",
                "application/x-7z-compressed"
            }

    archive_list = []

    for file in os.listdir(archives_directory):
        full_path = os.path.join(archives_directory, file)
        
        if not os.path.isfile(full_path):
            continue
            
        try:
            gio_file = Gio.File.new_for_path(full_path)
            file_info = gio_file.query_info("standard::content-type", Gio.FileQueryInfoFlags.NONE, None)
            mime_type = file_info.get_content_type()
            
            
            # If the OS identifies it as a known archive file type, pull it in
            if mime_type in ARCHIVE_MIME_TYPES:
                archive_list.append(file)
            else:
                if "yaml" not in mime_type:
                    print(f"[!] Could not identify mime type in download folder: {mime_type}")
        except Exception as e:
            print(f"Error reading file metadata for {file}: {e}")
    
    return archive_list

def launch_option_merger(current_launch_options: str, new_option: str) -> str:
    # TODO: add some proprer logic here - notably to check if the new option being added doesn't already exist.
    merged_launch_option = current_launch_options + " " + new_option
    return merged_launch_option

def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())

def load_cached_assets(game_name: str, platform: str) -> dict[str, str]:
    """Attempts to load game poster and hero from cache, or downloads them"""
    cache_base = os.path.join(GLib.get_user_data_dir(), "nomm", "image-cache", f"{platform}", f"{game_name}")
    
    if os.path.exists(cache_base):
        existing_files = {}
        for entry in os.listdir(cache_base):
            if entry.startswith("art_grid"):
                existing_files["poster"] = os.path.join(cache_base, entry)
            elif entry.startswith("art_hero"):
                existing_files["hero"] = os.path.join(cache_base, entry)
        
        if "poster" in existing_files:
            print(f"Using cached assets for {game_name}")
            return existing_files

    return None

def get_nomm_tags(headers: dict):

    url = f"https://api.github.com/repos/allexio/nomm/tags?per_page=100"

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        tags = response.json()
        tag_names = [tag["name"] for tag in tags]
        return tag_names
    else:
        return None

def create_icon_button(
    *,
    icon_name: str,
    tooltip: str,
    icon_size: int = 24,
    icon_margin: int = 2,
    valign: Gtk.Align = Gtk.Align.CENTER,
    halign: Gtk.Align = Gtk.Align.END,
    css_classes: Optional[list[str]] = None,
    on_click: Optional[Callable] = None,
) -> Gtk.Button:

    button = Gtk.Button(valign=valign, halign=halign)
    button.add_css_class("image-button")

    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_pixel_size(icon_size)
    img.set_valign(Gtk.Align.CENTER)
    img.set_halign(Gtk.Align.CENTER)
    img.set_margin_start(icon_margin)
    img.set_margin_end(icon_margin)
    img.set_margin_top(icon_margin)
    img.set_margin_bottom(icon_margin)
    button.set_child(img)

    button.set_tooltip_text(tooltip)
    button.set_cursor_from_name("pointer")

    classes_to_add = css_classes if css_classes is not None else ["flat"]
    for css_class in classes_to_add:
        button.add_css_class(css_class)

    if on_click:
        button.connect("clicked", on_click)

    return button