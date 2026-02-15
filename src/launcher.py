#!/usr/bin/env python3

import os
import yaml
import threading
import re
import shutil
import gi
import sys
import subprocess
import json
import requests

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gdk, Gio, GdkPixbuf
from dashboard import GameDashboard
from utils import download_heroic_assets
from nxm_handler import download_nexus_mod

CSS = """

.success {
    color: #2ec27e; /* GNOME Green */
}

.error {
    color: #e01b24; /* GNOME Red */
}

.game-card {
    border-radius: 12px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
}

.game-card:hover {
    filter: brightness(1.1) contrast(1.05);
    box-shadow: 0 0 15px rgba(255, 255, 255, 0.1), 0 12px 30px rgba(0,0,0,0.6);
}

.setup-page {
    opacity: 0;
}

.setup-page.visible {
    opacity: 1;
}

.refresh-fab {
    box-shadow: 0 6px 16px rgba(0,0,0,0.5);
    background-color: @accent_bg_color;
    color: @accent_fg_color;
    border: none;
    border-radius: 99px;
    opacity: 1;
}

.refresh-fab:hover {
    filter: brightness(1.2);
    box-shadow: 0 0 20px @accent_bg_color;
}

.refresh-fab image {
    -gtk-icon-size: 32px;
}

/* Dashboard Tab Styling */
togglebutton {
    font-size: 1.2rem;
    font-weight: bold;
    border-radius: 0;
}

.overlay-tab {
    /* 1. Remove Rounded Corners */
    border-radius: 0;
    border: none;
    
    /* 2. Bigger Font */
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: 2px;

    /* 3. Darker Unselected State */
    background-color: rgba(0, 0, 0, 0.85); 
    color: rgba(255, 255, 255, 0.6);
    
    transition: all 0.3s ease;
}

.overlay-tab:hover {
    background-color: rgba(0, 0, 0, 0.7);
    color: white;
}

/* 4. Selected (Checked) Tab State */
.overlay-tab:checked {
    /* Clearer background so the banner image is visible */
    background-color: rgba(0, 0, 0, 0.1); 
    color: white;
    /* Bottom accent line to show focus */
    border-bottom: 6px solid @accent_bg_color;
    text-shadow: 0 2px 10px rgba(0,0,0,0.5);
}

.version-badge { 
    background-color: rgba(255, 255, 255, 0.1); 
    border-radius: 99px; 
    padding: 4px 12px; 
    border: 1px solid rgba(255, 255, 255, 0.1);
}
        
.version-badge:hover {
    background-color: rgba(255, 255, 255, 0.2);
    border: 1px solid @accent_bg_color;
}

"""

def slugify(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

class Nomm(Adw.Application):
    def __init__(self, **kwargs):
        # 1. Update Application ID to match your protocol registration
        super().__init__(application_id='com.nomm.Nomm', **kwargs)
        self.matches = []
        self.steam_base = self.get_steam_base_dir()
        self.user_config_path = os.path.expanduser("~/nomm/user_config.yaml")
        self.game_config_path = os.path.expanduser("~/nomm/game_configs")
        self.win = None

    def get_steam_base_dir(self):
        paths = [
            os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/"),
            os.path.expanduser("~/.local/share/Steam/"),
            os.path.expanduser("~/snap/steam/common/.local/share/Steam/")
        ]
        for p in paths:
            if os.path.exists(p): return p
        return None

    def sync_configs(self):

        src, dest = "./default_game_configs", self.game_config_path
        if not os.path.exists(src): return
        if not os.path.exists(dest): os.makedirs(dest)
        for filename in os.listdir(src):
            if filename.lower().endswith((".yaml", ".yml")):
                try:
                    shutil.copy2(os.path.join(src, filename), os.path.join(dest, filename))
                except: pass

    def do_activate(self):
        self.sync_configs()
        self.apply_styles()
        
        if self.win:
            self.win.present()
            return

        self.win = Adw.ApplicationWindow(application=self)
        self.win.set_title("NOMM")
        self.win.set_default_size(1230, 900)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.win.set_content(self.stack)

        if not os.path.exists(self.user_config_path):
            self.show_welcome_screen()
        else:
            self.show_loading_and_scan()

        self.win.present()

    def remove_stack_child(self, name):
        child = self.stack.get_child_by_name(name)
        if child:
            self.stack.remove(child)

    def show_welcome_screen(self):
        """Step 0: Intro page & "Let's go" button"""
        self.remove_stack_child("setup")
        status_page = Adw.StatusPage(
            title="Welcome to the Native Open Mod Manager (NOMM) app!",
            description="This app is still in early development, so expect some bugs and missing features.\nI hope you can still enjoy what the app currently offers and please don't forget that you can report any bugs or request features on the Github!",
        )
        status_page.add_css_class("setup-page")
        
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        logo_path = os.path.join(assets_dir, "nomm.png")
        if os.path.exists(logo_path):
            try:
                # Create a Pixbuf, then a Texture (which implements Gdk.Paintable)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(logo_path)
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                status_page.set_paintable(texture)
            except Exception as e:
                print(f"Error loading setup logo: {e}")
                status_page.set_icon_name("folder-download-symbolic") # Fallback

        btn = Gtk.Button(label="Let's go!")
        btn.set_halign(Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.set_margin_top(24)
        btn.connect("clicked", self.show_downloads_folder_select_screen)
        
        status_page.set_child(btn)
        self.stack.add_named(status_page, "setup")
        self.stack.set_visible_child_name("setup")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))


    def show_downloads_folder_select_screen(self, btn=None):
        """Step 1: Downloads Folder Selection"""
        self.remove_stack_child("setup")
        status_page = Adw.StatusPage(
            title="Select your mods download folder",
            description="Please select the folder where mod downloads will be stored.\nMod downloads will be categorised by game name.\nI recommend you create a nomm directory at the end of your target path.",
            icon_name="folder-download-symbolic"
        )
        status_page.add_css_class("setup-page")
        
        btn = Gtk.Button(label="Set Mod Download Path")
        btn.set_halign(Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.set_margin_top(24)
        btn.connect("clicked", self.on_select_downloads_folder_clicked)
        
        status_page.set_child(btn)
        self.stack.add_named(status_page, "setup")
        self.stack.set_visible_child_name("setup")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_downloads_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title="Select Mod Downloads Folder")
        dialog.select_folder(self.win, None, self.on_downloads_folder_selected_callback)

    def on_downloads_folder_selected_callback(self, dialog, result):
        try:
            selected_file = dialog.select_folder_finish(result)
            if selected_file:
                path = selected_file.get_path()
                # Save path, then move to Protocol screen
                self.temp_config = {"download_path": path, "library_paths": []}
                self.show_staging_select_screen()
        except Exception: pass

    def show_staging_select_screen(self):
        """Step 2: Staging Folder Selection"""
        self.remove_stack_child("setup")
        status_page = Adw.StatusPage(
            title="Select your staging folder",
            description="Please select the folder where mods will be temporarily stored after installing them (but before deployment).",
            icon_name="folder-git-symbolic"
        )
        status_page.add_css_class("setup-page")
        
        btn = Gtk.Button(label="Set Mod Staging Path")
        btn.set_halign(Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.set_margin_top(24)
        btn.connect("clicked", self.on_select_staging_folder_clicked)
        
        status_page.set_child(btn)
        self.stack.add_named(status_page, "setup")
        self.stack.set_visible_child_name("setup")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_staging_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title="Select Mod Downloads Folder")
        dialog.select_folder(self.win, None, self.on_staging_folder_selected_callback)

    def on_staging_folder_selected_callback(self, dialog, result):
        try:
            selected_file = dialog.select_folder_finish(result)
            if selected_file:
                path = selected_file.get_path()
                # Save path, then move to Protocol screen
                self.temp_config["staging_path"] = path
                self.show_protocol_choice_screen()
        except Exception: pass

    def show_protocol_choice_screen(self):
        """Step 3: NXM Protocol Choice"""
        self.remove_stack_child("protocol")
        box = Adw.StatusPage(
            title="Handle Nexus Links?",
            description="Would you like NOMM to handle 'nxm://' links from Nexus Mods?",
            icon_name="network-transmit-receive-symbolic"
        )
        
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        btn_box.set_margin_top(24)

        yes_btn = Gtk.Button(label="Yes, Register Nomm", css_classes=["suggested-action"])
        yes_btn.connect("clicked", self.on_protocol_choice, True)
        
        no_btn = Gtk.Button(label="No, Maybe Later")
        no_btn.connect("clicked", self.on_protocol_choice, False)

        btn_box.append(yes_btn)
        btn_box.append(no_btn)
        box.set_child(btn_box)

        self.stack.add_named(box, "protocol")
        self.stack.set_visible_child_name("protocol")

    def on_protocol_choice(self, btn, choice):
        if choice:
            self.register_nomm_nxm_protocol()
            self.show_api_key_screen()
        else:
            # Skip API key and just finish
            self.finalize_setup("")

    def show_api_key_screen(self):
        """Step 4: Nexus API Key Entry"""
        self.remove_stack_child("api_key")
        status_page = Adw.StatusPage(
            title="Nexus API Key",
            description="Enter your API Key from Nexus Mods (Site Preferences > API Keys)",
            icon_name="dialog-password-symbolic"
        )

        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        entry_box.set_margin_top(24)
        
        self.api_entry = Gtk.Entry(placeholder_text="Enter API Key...")
        self.api_entry.set_size_request(400, -1) 
        self.api_entry.set_visibility(False) # Masks the key like a password
        
        cont_btn = Gtk.Button(label="Continue & Scan", css_classes=["suggested-action"])
        cont_btn.connect("clicked", lambda b: self.finalize_setup(self.api_entry.get_text()))

        entry_box.append(self.api_entry)
        entry_box.append(cont_btn)
        status_page.set_child(entry_box)

        self.stack.add_named(status_page, "api_key")
        self.stack.set_visible_child_name("api_key")

    def finalize_setup(self, api_key):
        """Step 5: Save and Start Scan"""
        self.temp_config["nexus_api_key"] = api_key
        
        # Create the ~/nomm/ directory if it doesn't exist yet
        os.makedirs(os.path.dirname(self.user_config_path), exist_ok=True)
        
        with open(self.user_config_path, 'w') as f:
            yaml.dump(self.temp_config, f, default_flow_style=False)
        self.show_loading_and_scan()

    def show_loading_and_scan(self):
        self.remove_stack_child("loading")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30, valign=Gtk.Align.CENTER)
        spinner = Gtk.Spinner()
        spinner.set_size_request(128, 128)
        spinner.start()
        label = Gtk.Label(label="NOMM: Mapping Libraries...")
        label.add_css_class("title-1")
        box.append(spinner)
        box.append(label)
        self.status_label = label
        self.stack.add_named(box, "loading")
        self.stack.set_visible_child_name("loading")
        threading.Thread(target=self.run_background_workflow, daemon=True).start()

    def game_title_matcher(self, game_path: str, game_config_path: str, game_config_data: dict, folder_name: str, game_title: str, platform: str, app_id=None):
        '''Tries to match supported game titles with folder names identified and if it does it adds them to the match list'''
        slugged_game_title = slugify(game_title)
        slugged_folder_name = slugify(folder_name)
        if slugged_folder_name == slugged_game_title:
            
            # --- AUTO-REGISTER PATH DURING SCAN ---
            # Update the data dictionary with the discovered platform & path
            game_config_data["platform"] = platform
            game_config_data["game_path"] = game_path
            
            # Save the updated config back to the YAML file
            with open(game_config_path, 'w') as f_out:
                yaml.dump(game_config_data, f_out, default_flow_style=False)
            
            # add a special case if game is gog to avoid using app ID as game title
            if platform == "heroic-gog":
                game_title = game_config_data["name"]

            self.matches.append({
                "name": game_title,
                "img": self.find_game_art(app_id, platform),
                "path": game_path,
                "app_id": app_id,
                "platform": platform
            })
            return True
        return False

    def run_background_workflow(self):
        config_dir = self.game_config_path
        found_libs = set()
        try:
            with open(self.user_config_path, 'r') as f:
                current_config = yaml.safe_load(f) or {}
                found_libs = set(current_config.get("library_paths", []))
        except: pass

        if not found_libs:
            potential_mounts = {"/", os.path.expanduser("~")}
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 3 and parts[1].startswith(('/', '/run/media', '/mnt')):
                            potential_mounts.add(parts[1])
            except: pass

            targets = ["SteamLibrary/steamapps/common", "steamapps/common"]
            for m in potential_mounts:
                if not os.path.exists(m): continue
                for root, dirs, _ in os.walk(m):
                    if any(root.endswith(t) for t in targets):
                        found_libs.add(os.path.realpath(root))
                        del dirs[:]
                        break

            current_config["library_paths"] = sorted(list(found_libs))
            with open(self.user_config_path, 'w') as f:
                yaml.dump(current_config, f)

        self.matches = []
        if os.path.exists(config_dir):
            for filename in os.listdir(config_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    conf_path = os.path.join(config_dir, filename)
                    try:
                        with open(conf_path, 'r') as f:
                            data = yaml.safe_load(f) or {}
                        
                        game_title, steam_app_id, gog_store_id = data.get("name"), data.get("steamappid"), str(data.get("gogstoreid", None))
                        if not game_title: continue
                        
                        # Steam library searching:

                        for lib in found_libs:
                            if not os.path.exists(lib): continue
                            for folder in os.listdir(lib):
                                game_path = os.path.join(lib, folder)
                                if self.game_title_matcher(game_path, conf_path, data, folder, game_title, platform="steam", app_id=steam_app_id):
                                    break
                        
                        # (Heroic) Epic library searching
                        self.check_heroic_games(conf_path, data, game_title, "heroic-epic")
                        # (Heroic) GOG library searching
                        self.check_heroic_games(conf_path, data, gog_store_id, "heroic-gog")
                    
                    except Exception as e:
                        print(f"Error processing {filename} during scan: {e}")

        GLib.idle_add(self.show_library_ui)

    def check_heroic_games(self, game_config_path: str, game_config_data: dict, game_title: str, platform: str):
        if platform == "heroic-epic":
            json_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary/installed.json")
        elif platform == "heroic-gog":
            json_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/gog_store/installed.json")

        if not os.path.exists(json_path):
            print(f"No {platform} installed.json found.")
            return None
        try:
            with open(json_path, 'r') as f:
                installed_games = json.load(f)
        except Exception as e:
            print(f"Error when trying to access {platform} json file: {e}")
            return None

        # for Epic Games, installed_games is a dict where keys are IDs and values are game info
        if platform == "heroic-epic": 
            for app_id, game_info in installed_games.items():
                # Heroic GOG games have no title in the json - I use the app id instead which is stored in appName
                heroic_game_title = game_info.get("title", "")
                game_path = game_info.get("install_path", "")
                if self.game_title_matcher(game_path, game_config_path, game_config_data, heroic_game_title, game_title, platform=platform, app_id=app_id):
                    return

        elif platform == "heroic-gog":
            for game_info in installed_games["installed"]:
                heroic_game_title = game_info.get("appName", "")
                game_path = game_info.get("install_path", "")
                if self.game_title_matcher(game_path, game_config_path, game_config_data, heroic_game_title, game_title, platform=platform, app_id=game_title):
                    return
        
        return None


    def show_library_ui(self):
        self.remove_stack_child("library")
        view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        view.append(Adw.HeaderBar())
        
        overlay = Gtk.Overlay()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        
        # Homogeneous ensures the FlowBox treats every slot as a 200px block
        flow = Gtk.FlowBox(
            valign=Gtk.Align.START, 
            halign=Gtk.Align.START, # FIX 1: Keeps the grid columns from stretching
            selection_mode=Gtk.SelectionMode.NONE,
            margin_top=40, margin_bottom=40, margin_start=40, margin_end=40,
            column_spacing=30, row_spacing=30,
            homogeneous=True
        )

        for game in self.matches:
            # 1. THE CARD
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            card.set_size_request(200, 300)
            card.set_halign(Gtk.Align.START) # FIX 2: Prevents card from expanding horizontally
            card.set_hexpand(False)          # FIX 3: Explicitly refuse extra horizontal space
            card.add_css_class("game-card")
            card.set_overflow(Gtk.Overflow.HIDDEN)
            card.set_tooltip_text(f"{game['name']}\n{game['path']}")

            gesture = Gtk.GestureClick()
            gesture.connect("released", self.on_game_clicked, game)
            card.add_controller(gesture)

            # 2. THE IMAGE OVERLAY (To superimpose the badge)
            image_overlay = Gtk.Overlay()
            
            # --- Image Loading Logic ---
            img_widget = None
            if game['img'] and os.path.exists(game['img']):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(game['img'], 200, 300, False)
                    texture = Gdk.Texture.new_for_pixbuf(pb)
                    img_widget = Gtk.Picture.new_for_paintable(texture)
                    img_widget.set_can_shrink(True)
                except Exception as e:
                    print(f"Scaling error: {e}")

            poster = img_widget if img_widget else self.get_placeholder_game_poster()
            image_overlay.set_child(poster)

            # 3. THE PLATFORM BADGE
            platform = game['platform']
            
            assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

            if platform == "steam":
                icon_path = os.path.join(assets_dir, "steam_logo.svg")
            elif platform == "heroic-epic":
                icon_path = os.path.join(assets_dir, "epic_logo.svg")
            elif platform == "heroic-gog":
                icon_path = os.path.join(assets_dir, "gog_logo.svg")

            if os.path.exists(icon_path):
                try:
                    badge_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        icon_path, 32, 32, True # True = Preserve aspect ratio
                    )
                    
                    # Modern Texture conversion
                    badge_tex = Gdk.Texture.new_for_pixbuf(badge_pb)
                    badge_img = Gtk.Picture.new_for_paintable(badge_tex)
                    
                    # Styling & Placement
                    badge_img.set_halign(Gtk.Align.END)
                    badge_img.set_valign(Gtk.Align.END)
                    badge_img.set_margin_end(10)
                    badge_img.set_margin_bottom(10)
                    badge_img.add_css_class("platform-badge")
                    
                    # Add to the image overlay created earlier
                    image_overlay.add_overlay(badge_img)
                except Exception as e:
                    print(f"Error rendering SVG badge: {e}")

            # 4. Final Assembly
            card.append(image_overlay)
            flow.append(card)

        scroll.set_child(flow)
        overlay.set_child(scroll)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.add_css_class("circular")
        refresh_btn.add_css_class("accent")      
        refresh_btn.add_css_class("refresh-fab")
        refresh_btn.set_cursor_from_name("pointer")
        refresh_btn.set_size_request(64, 64)
        refresh_btn.set_valign(Gtk.Align.START)
        refresh_btn.set_halign(Gtk.Align.END)
        refresh_btn.set_margin_top(30)
        refresh_btn.set_margin_end(30)
        refresh_btn.connect("clicked", self.on_refresh_clicked)

        settings_btn = Gtk.Button(icon_name="settings-configure-symbolic")
        settings_btn.add_css_class("circular")
        settings_btn.add_css_class("accent")      
        settings_btn.add_css_class("refresh-fab")
        settings_btn.set_cursor_from_name("pointer")
        settings_btn.set_size_request(64, 64)
        settings_btn.set_valign(Gtk.Align.START)
        settings_btn.set_halign(Gtk.Align.END)
        settings_btn.set_margin_top(30)
        settings_btn.set_margin_end(120)
        settings_btn.connect("clicked", self.on_settings_clicked)

        overlay.add_overlay(settings_btn)
        overlay.add_overlay(refresh_btn)
        view.append(overlay)
        self.stack.add_named(view, "library")
        self.stack.set_visible_child_name("library")

    def load_config(self):
        if os.path.exists(self.user_config_path):
            try:
                with open(self.user_config_path, 'r') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Error loading config: {e}")
                return {}
        return {}

    def update_config(self, key, value):
        config = self.load_config()
        config[key] = value
        # Ensure directory exists before writing
        os.makedirs(os.path.dirname(self.user_config_path), exist_ok=True)
        with open(self.user_config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

    def pick_folder(self, parent_win, row, config_key):
        """Opens a folder dialog and updates the specific config key and UI row."""
        dialog = Gtk.FileDialog(title=f"Select {row.get_title()}")
        
        def callback(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
                if folder:
                    new_path = folder.get_path()
                    self.update_config(config_key, new_path)
                    row.set_subtitle(new_path)
            except Exception as e:
                print(f"Folder selection failed: {e}")

        dialog.select_folder(parent_win, None, callback)

    def on_settings_clicked(self, button):
        settings_win = Adw.Window(title="Settings", transient_for=self.win, modal=True)
        settings_win.set_default_size(500, -1)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        settings_win.set_content(content)

        # --- STORAGE SECTION ---
        storage_group = Adw.PreferencesGroup(title="Storage", description="Configure where NOMM manages your files.")
        content.append(storage_group)

        # 1. Downloads Path Row
        path_row = Adw.ActionRow(title="Mod Downloads Path")
        current_path = self.load_config().get('download_path', 'Not set')
        path_row.set_subtitle(current_path)

        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        folder_btn.connect("clicked", lambda b: self.pick_folder(settings_win, path_row, "download_path"))
        
        path_row.add_suffix(folder_btn)
        storage_group.add(path_row)

        # 2. NEW: Staging Path Row
        staging_row = Adw.ActionRow(title="Mod Staging Path")
        current_staging = self.load_config().get('staging_path', 'Not set')
        staging_row.set_subtitle(current_staging)

        staging_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        staging_btn.connect("clicked", lambda b: self.pick_folder(settings_win, staging_row, "staging_path"))
        
        staging_row.add_suffix(staging_btn)
        storage_group.add(staging_row)

        # --- NEXUS SECTION ---
        nexus_group = Adw.PreferencesGroup(title="Nexus Mods Integration")
        content.append(nexus_group)

        api_entry = Gtk.PasswordEntry(hexpand=True, valign=Gtk.Align.CENTER)
        api_entry.set_property("placeholder-text", "Paste API Key...")
        api_entry.set_text(self.load_config().get('nexus_api_key', ''))

        check_btn = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)

        api_row = Adw.ActionRow(title="Nexus API Key")
        api_row.add_suffix(api_entry)
        api_row.add_suffix(spinner)
        api_row.add_suffix(check_btn)
        nexus_group.add(api_row)

        # 3. Validation Logic
        def on_validate_clicked(btn):
            key = api_entry.get_text()
            if not key: return

            btn.set_sensitive(False)
            spinner.start()
            
            # Reset button colors
            check_btn.remove_css_class("success")
            check_btn.remove_css_class("error")

            def check_api():
                try:
                    response = requests.get(
                        "https://api.nexusmods.com/v1/users/validate.json",
                        headers={"apikey": key},
                        timeout=10
                    )
                    is_valid = response.status_code == 200
                except:
                    is_valid = False

                def update_ui():
                    spinner.stop()
                    btn.set_sensitive(True)
                    if is_valid:
                        check_btn.add_css_class("success")
                        check_btn.set_icon_name("emblem-ok-symbolic")
                    else:
                        check_btn.add_css_class("error")
                        check_btn.set_icon_name("dialog-error-symbolic")
                    return False

                GLib.idle_add(update_ui)

            threading.Thread(target=check_api, daemon=True).start()

        check_btn.connect("clicked", on_validate_clicked)

        # --- COMMUNITY SECTION ---
        community_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, halign=Gtk.Align.CENTER)
        community_box.set_margin_top(10)

        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

        def create_social_button(icon_filename, url):
            btn_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            # Load custom icon
            icon_path = os.path.join(assets_dir, icon_filename)
            if os.path.exists(icon_path):
                # We use Picture for better scaling of brand assets
                img = Gtk.Picture.new_for_filename(icon_path)
                img.set_size_request(24, 24)
                btn_content.append(img)
            else:
                # Fallback to a generic icon if file is missing
                btn_content.append(Gtk.Image(icon_name="action-unavailable-symbolic"))
            
            button = Gtk.Button(child=btn_content)
            button.add_css_class("flat")
            button.connect("clicked", lambda b: Gtk.FileLauncher.new(Gio.File.new_for_uri(url)).launch(settings_win, None, None))
            return button

        # Add the brand buttons
        community_box.append(create_social_button("github_logo.svg", "https://github.com/allexio/nomm"))
        community_box.append(create_social_button("discord_logo.svg", "https://discord.gg/WFRePSjEQY"))

        content.append(community_box)

        # Separator and Close
        content.append(Gtk.Separator(margin_top=10))
        
        save_btn = Gtk.Button(label="Close", css_classes=["suggested-action"], margin_top=12)
        save_btn.connect("clicked", lambda b: (self.update_config('nexus_api_key', api_entry.get_text()), settings_win.destroy()))
        content.append(save_btn)

        settings_win.present()

    def on_refresh_clicked(self, btn):
        try:
            with open(self.user_config_path, 'r') as f:
                config = yaml.safe_load(f)
            config["library_paths"] = []
            with open(self.user_config_path, 'w') as f:
                yaml.dump(config, f)
        except: pass
        self.show_loading_and_scan()

    def on_game_clicked(self, gesture, n_press, x, y, game_data):
        # 1. Get the base path from user_config
        download_base = ""
        try:
            with open(self.user_config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                download_base = config.get("download_path", "")
        except: pass

        if download_base:
            # 2. Define the game-specific path
            game_download_path = os.path.join(download_base, game_data['name'])
            
            # Create the physical folder if it doesn't exist
            if not os.path.exists(game_download_path):
                os.makedirs(game_download_path, exist_ok=True)

            # 3. Update the game-specific YAML config
            config_dir = self.game_config_path
            slug = slugify(game_data['name'])
            
            for filename in os.listdir(config_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    conf_path = os.path.join(config_dir, filename)
                    try:
                        with open(conf_path, 'r') as f:
                            data = yaml.safe_load(f) or {}
                        
                        # Match by name or app_id
                        if slugify(data.get("name", "")) == slug or data.get("steamappid") == game_data.get("app_id"):
                            data["downloads_path"] = game_download_path
                            
                            with open(conf_path, 'w') as f:
                                yaml.dump(data, f, default_flow_style=False)
                            break # Found and updated
                    except Exception as e:
                        print(f"Failed to update game config: {e}")

        # 4. Launch Dashboard
        self.dashboard = GameDashboard(
            game_name=game_data['name'], 
            game_path=game_data['path'],
            application=self,
            steam_base=self.steam_base,
            app_id=game_data.get('app_id'),
            user_config_path=self.user_config_path
        )
        self.dashboard.launch()
        
        if self.win:
            self.win.close()
            self.win = None

    def get_placeholder_game_poster(self):
        b = Gtk.Box(orientation=1, valign=Gtk.Align.CENTER)
        img = Gtk.Image.new_from_icon_name("input-gaming-symbolic")
        img.set_pixel_size(128)
        b.append(img)
        return b

    def apply_styles(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, 800)

    def find_game_art(self, app_id, platform):
        if not app_id: return None
        if platform == "steam":
            path = os.path.join(self.steam_base, "appcache/librarycache", str(app_id))
            if not os.path.exists(path): return None
            for root, _, files in os.walk(path):
                for t in ["library_capsule.jpg", "library_600x900.jpg"]:
                    if t in files: return os.path.join(root, t)
        elif platform == "heroic-epic":
            paths = download_heroic_assets(app_id, platform)
            return paths["art_square"]
        elif platform == "heroic-gog":
            paths = download_heroic_assets(app_id, platform)
            return paths["art_square"]
        return None

    def register_nomm_nxm_protocol(self):
        """Internalized protocol registration helper"""
        app_path = os.path.abspath(sys.argv[0])
        icon_path = os.path.join(os.path.dirname(os.path.dirname(app_path)), "assets", "nomm.png")
        desktop_file_content = f"""[Desktop Entry]
Name=Nomm
Exec=python3 {app_path} %u
Type=Application
Terminal=false
Icon={icon_path}
MimeType=x-scheme-handler/nxm;
"""
        desktop_dir = os.path.expanduser("~/.local/share/applications")
        desktop_path = os.path.join(desktop_dir, "nomm.desktop")
        os.makedirs(desktop_dir, exist_ok=True)

        try:
            with open(desktop_path, "w") as f:
                f.write(desktop_file_content)
            
            subprocess.run(["update-desktop-database", desktop_dir], check=True)
            subprocess.run(["xdg-settings", "set", "default-url-scheme-handler", "nxm", "nomm.desktop"], check=True)
            print("Protocol registered successfully!")
        except Exception as e:
            print(f"Failed to register protocol: {e}")

def create_success_file():
    # 'os.path.expanduser' handles the "~" correctly for any user
    home_path = os.path.expanduser("~/success.txt")
    
    try:
        with open(home_path, "w") as f:
            f.write("Operation completed successfully!")
        print(f"File created at: {home_path}")
    except Exception as e:
        print(f"Failed to create file: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("nxm://"):
        nxm_link = sys.argv[1]
        print(f"nomm is processing: {nxm_link}")
        create_success_file()
        download_nexus_mod(nxm_link)
    else:
        app = Nomm()
        app.run(None)
    