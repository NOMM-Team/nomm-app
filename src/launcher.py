#!/usr/bin/env python3

# global imports
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
import vdf
import gettext
import locale

# force specific gtk version before GTK is called
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Notify', '0.7')
# specific imports
from gi.repository import Gtk, Adw, GLib, Gdk, Gio, GdkPixbuf
from dashboard import GameDashboard
from utils import download_heroic_assets
from nxm_handler import handle_nexus_link
APP_NAME = 'com.nomm.Nomm'

# Localisation setup
# Initialize the translation system
translation_system = gettext.translation(APP_NAME, localedir='/app/share/locale', fallback=True)
# Install the '_' function globally so all other imported files can see it
translation_system.install(names=['ngettext'])

def slugify(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

class Nomm(Adw.Application):
    def __init__(self, **kwargs):
        # 1. Update Application ID to match your protocol registration
        super().__init__(application_id=APP_NAME, **kwargs)
        self.matches = []
        self.steam_base = self.get_steam_base_dir()

        user_data_dir = os.path.join(GLib.get_user_data_dir(), "nomm")
        self.user_config_path = os.path.join(user_data_dir, "user_config.yaml")
        self.game_config_path = os.path.join(user_data_dir, "game_configs")

        default_game_config_path_dev = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "default_game_configs")
        default_game_config_path_flat = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_game_configs")

        if os.path.exists(default_game_config_path_dev): # in dev environment (launching python file directly)
            self.default_game_config_path = default_game_config_path_dev
            self.assets_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        else: # in flatpak environment
            self.default_game_config_path = default_game_config_path_flat
            self.assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        self.win = None

        # Debug prints
        print(f"user_config_path: {self.user_config_path}")
        print(f"default_game_config_path: {self.default_game_config_path}")
        print(f"game_config_path: {self.game_config_path}")
        if self.steam_base:
            print(f"base steam path: {self.steam_base}")

    def get_steam_base_dir(self):
        paths = [
            os.path.expanduser("~/.steam/debian-installation/"),
            os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/"),
            os.path.expanduser("~/.local/share/Steam/"),
            os.path.expanduser("~/snap/steam/common/.local/share/Steam/")
        ]
        for p in paths:
            if os.path.exists(p):
                print(f"Steam path found: {p}")
                return p
                
        print(f"WARNING: Steam path could not be found!!")
        return None

    def sync_configs(self):

        src, dest = self.default_game_config_path, self.game_config_path
        if not os.path.exists(src): return
        if not os.path.exists(dest): os.makedirs(dest)
        for filename in os.listdir(src):
            if filename.lower().endswith((".yaml", ".yml")):
                try:
                    shutil.copy2(os.path.join(src, filename), os.path.join(dest, filename))
                except: pass
    
    def styles_application(self): # Ensure this is indented inside the class
        css_provider = Gtk.CssProvider()
        css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "layout.css")
        try:
            css_provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            print(f"Successfully loaded styles from {css_path}")
        except Exception as e:
            print(f"Error loading CSS: {e}")
            
    def do_activate(self):
        self.sync_configs()
        self.styles_application()
        
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
            title=_("Welcome to the Native Open Mod Manager (NOMM) app!"),
            description=_("This app is still in early development, so expect some bugs and missing features.\nI hope you can still enjoy what the app currently offers and please don't forget that you can report any bugs or request features on the Github!"),
        )
        status_page.add_css_class("setup-page")
        
        assets_dir = self.assets_path
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
            title=_("Select your mods download folder"),
            description=_("Please select the folder where mod downloads will be stored.\nMod downloads will be categorised by game name.\nI recommend you create a nomm directory at the end of your target path."),
            icon_name="folder-download-symbolic"
        )
        status_page.add_css_class("setup-page")
        
        btn = Gtk.Button(label=_("Set Mod Download Path"))
        btn.set_halign(Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.set_margin_top(24)
        btn.connect("clicked", self.on_select_downloads_folder_clicked)
        
        status_page.set_child(btn)
        self.stack.add_named(status_page, "setup")
        self.stack.set_visible_child_name("setup")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_downloads_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title=_("Select Mod Downloads Folder"))
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
            description="Please select the folder where mods will be temporarily stored.",
            icon_name="folder-git-symbolic"
        )
        status_page.add_css_class("setup-page")
        
        # 1. Create a container box for our widgets
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_halign(Gtk.Align.CENTER)

        # 2. Create the Warning Label
        warning_label = Gtk.Label()
        warning_label.set_markup(
            _("<b>Important:</b> If using Steam Flatpak, ensure it has permission to access this folder (you can do this via command line or Flatseal).")
        )
        warning_label.set_wrap(True)
        warning_label.set_max_width_chars(50)
        warning_label.set_justify(Gtk.Justification.CENTER)
        
        # 3. Style it red using Libadwaita's built-in error color
        warning_label.add_css_class("error") 
        # Alternatively, use "destructive-action" for a slightly different red
        
        btn = Gtk.Button(label=_("Set Mod Staging Path"))
        btn.add_css_class("suggested-action")
        btn.set_margin_top(12)
        btn.connect("clicked", self.on_select_staging_folder_clicked)
        
        # 4. Assemble the box and set it as the status page child
        vbox.append(warning_label)
        vbox.append(btn)
        
        status_page.set_child(vbox)
        
        self.stack.add_named(status_page, "setup")
        self.stack.set_visible_child_name("setup")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_staging_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title=_("Select Mod Staging Folder"))
        dialog.select_folder(self.win, None, self.on_staging_folder_selected_callback)

    def on_staging_folder_selected_callback(self, dialog, result):
        try:
            selected_file = dialog.select_folder_finish(result)
            if selected_file:
                path = selected_file.get_path()
                # Save path, then move to Protocol screen
                self.temp_config["staging_path"] = path
                self.show_nexus_api_key_screen()
        except Exception: pass

    def show_nexus_api_key_screen(self):
        """Step 4: Nexus API Key Entry"""
        self.remove_stack_child("api_key")
        status_page = Adw.StatusPage(
            title=_("Nexus API Key"),
            description=_("If you want to download mods from Nexus Mods, enter your API Key (Site Preferences > API Keys > scroll all the way down)"),
            icon_name="dialog-password-symbolic"
        )

        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        entry_box.set_margin_top(24)
        
        self.api_entry = Gtk.Entry(placeholder_text=_("Enter API Key..."))
        self.api_entry.set_size_request(400, -1) 
        self.api_entry.set_visibility(False) # Masks the key like a password
        
        cont_btn = Gtk.Button(label=_("Continue"), css_classes=["suggested-action"])
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
        label = Gtk.Label(label=_("NOMM: Searching for games..."))
        label.add_css_class("title-1")
        box.append(spinner)
        box.append(label)
        self.status_label = label
        self.stack.add_named(box, "loading")
        self.stack.set_visible_child_name("loading")
        threading.Thread(target=self.run_background_workflow, daemon=True).start()

    def game_title_matcher(self, game_path: str, game_config_path: str, game_config_data: dict, folder_name: str, game_title_list: str, platform: str, app_id=None):
        '''Tries to match supported game titles with folder names identified and if it does it adds them to the match list'''
        if not game_title_list:
            return

        slugged_folder_name = slugify(folder_name)
        if not isinstance(game_title_list, list):
            game_title_list = [game_title_list] # this is a workaround to ensure that games with only one title/ID will still be interpreted in following loop
        for game_title in game_title_list: # loop through all associated game titles/ID for that entry
            slugged_game_title = slugify(game_title)
            if slugged_folder_name == slugged_game_title:
                
                # --- AUTO-REGISTER PATH DURING SCAN ---
                # Update the data dictionary with the discovered platform & path
                clean_game_path = game_path.strip()
                print(f"Saved game path: {clean_game_path}")
                game_config_data["platform"] = platform
                game_config_data["game_path"] = clean_game_path
                
                # Save the updated config back to the YAML file
                with open(game_config_path, 'w') as f_out:
                    yaml.dump(game_config_data, f_out, default_flow_style=False)
                
                # add a special case if game is gog to avoid using app ID as game title
                if platform == "heroic-gog":
                    game_title = game_config_data["name"]
                    app_id = slugged_folder_name # this is to make sure that a singular app_id is sent to the find_game_art matcher

                self.matches.append({
                    "name": game_title,
                    "img": self.find_game_art(app_id, platform),
                    "path": clean_game_path,
                    "app_id": app_id,
                    "platform": platform,
                    "game_config_path": game_config_path
                })
                return True
        return False

    def game_matcher(self, yaml_path: str, yaml_data: dict, game_path: str, platform: str):
        '''Tries to match supported game titles with folder names identified and if it does it adds them to the match list'''

        library_game_name = os.path.basename(game_path)
        yaml_game_name = yaml_data.get("steam_folder_name", yaml_data.get("name"))

        if not slugify(library_game_name) == slugify(yaml_game_name):
            return False # not a match

        # it's a match - extract useful information from yaml
        game_title = yaml_data["name"]

        # --- AUTO-REGISTER PATH DURING SCAN ---
        # Update the data dictionary with the discovered platform & path
        game_path = game_path.strip()
        print(f"Saved game path: {game_path}")
        yaml_data["platform"] = platform
        yaml_data["game_path"] = game_path
        
        # Save the updated config back to the YAML file
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False)
        
        # add a special case if game is gog to avoid using app ID as game title
        if platform == "heroic-gog":
            game_title = game_config_data["name"]
            app_id = slugged_folder_name # this is to make sure that a singular app_id is sent to the find_game_art matcher
        elif platform == "steam":
            app_id = yaml_data["steam_id"]

        self.matches.append({
            "name": game_title,
            "img": self.find_game_art(app_id, platform),
            "path": game_path,
            "app_id": app_id,
            "platform": platform,
            "game_config_path": yaml_path
        })
        return True


    def get_steam_library_paths(self, vdf_path):
        libraries = []

        # attempt to open the libraryfolders.vdf file
        try:
            with open(vdf_path, 'r') as f:
                data = vdf.load(f)
        except:
            print(f"Could not find libraryfolders.vdf file at {vdf_path}")
            return
        # parse the information with the vdf parser
        try:    
            # The structure is "libraryfolders" -> "0", "1", "2", etc.
            folders = data.get("libraryfolders", {})
            
            for index in folders:
                # Each numbered block contains a "path" key
                path = folders[index].get("path")
                if path:
                    full_path = path + "/steamapps/common"
                    libraries.append(os.path.normpath(full_path))
                
        except Exception as e:
            print(f"Error parsing VDF: {e}")
        
        return libraries

    def get_heroic_library_paths(self):
        # Check for Epic (Heroic) library path
        epic_library_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary/installed.json") # flatpak
        if not os.path.exists(epic_library_path): # not flatpak
            epic_library_path = os.path.expanduser("~/.config/heroic/legendaryConfig/legendary/installed.json")
            if not os.path.exists(epic_library_path): # not found
                epic_library_path = None
                print(f"No installed.json found for Epic.")

        # Check for GOG (Heroic) library path
        gog_library_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/gog_store/installed.json") # flatpak
        if not os.path.exists(gog_library_path): # not flatpak
            gog_library_path = os.path.expanduser("~/.config/heroic/gog_store/installed.json")
            if not os.path.exists(gog_library_path): # not found
                gog_library_path = None
                print(f"No installed.json found for GOG.")

        # Save for easy access later on:
        self.epic_library_path = epic_library_path
        self.gog_library_path = gog_library_path

    def run_background_workflow(self):
        print("Background game search process started")
        config_dir = self.game_config_path
        found_libs = set()
        try:
            with open(self.user_config_path, 'r') as f:
                current_config = yaml.safe_load(f) or {}
                found_libs = set(current_config.get("library_paths", []))
        except:
            print("Could not find user config")

        # Locate Steam libraries
        if not found_libs:
            found_libs = self.get_steam_library_paths(self.steam_base + "config/libraryfolders.vdf")
            if found_libs:
                current_config["library_paths"] = sorted(list(found_libs))
                with open(self.user_config_path, 'w') as f:
                    yaml.dump(current_config, f)

        # Locate Heroic (GOG/Epic) libraries
        self.get_heroic_library_paths()

        if not os.path.exists(config_dir):
            print(f"Something went wrong, could not access the game configs directory at {config_dir}")
            exit(1)

        self.matches = []

        for filename in os.listdir(config_dir):
            if filename.lower().endswith((".yaml", ".yml")):
                yaml_path = os.path.join(config_dir, filename)
                try:
                    with open(yaml_path, 'r') as f:
                        yaml_data = yaml.safe_load(f) or {}

                    if not yaml_data.get("name"):
                        print("Malformed game YAML: missing game name")
                        continue
                    
                    print(f"Looking for game {yaml_data.get("name")}")

                    if yaml_data.get("mods_path") == None:
                        print("Malformed game YAML: missing mods_path")
                        continue
                    
                    # Search in Steam librarie(s)
                    if found_libs:
                        for lib in found_libs:
                            if not os.path.exists(lib): continue
                            for folder in os.listdir(lib):
                                game_path = os.path.join(lib, folder)
                                if self.game_matcher(yaml_path, yaml_data, game_path, platform="steam"):
                                    break
                    
                    # Search in Epic (Heroic) library
                    if self.epic_library_path:
                        self.check_heroic_games(yaml_path, yaml_data, "heroic-epic")
                    # Search in GOG (Heroic) library
                    if self.gog_library_path and yaml_data.get("gog_id"):
                        self.check_heroic_games(yaml_path, yaml_data, "heroic-gog")
                
                except Exception as e:
                    print(f"Error processing {filename} during scan: {e}")

        GLib.idle_add(self.show_library_ui)

    def check_heroic_games(self, game_config_path: str, game_config_data: dict, platform: str):
        if platform == "heroic-epic":
            json_path = self.epic_library_path
            game_title = game_config_data["name"]
        elif platform == "heroic-gog":
            json_path = self.gog_library_path
            game_title = str(game_config_data["gog_id"])
        
        try:
            with open(json_path, 'r') as f:
                installed_games = json.load(f)
        except Exception as e:
            print(f"Error when trying to access {platform} json file at {json_path}: {e}")
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

    def count_archives(self, directory):
        # Define the extensions we care about
        extensions = (".zip", ".rar", ".7z")
        
        # Count only files that end with those extensions (case-insensitive)
        return sum(1 for entry in os.scandir(directory)
                if entry.is_file() and entry.name.lower().endswith(extensions))

    def show_library_ui(self):
        self.remove_stack_child("library")

        # If user has selected launcher skip option, launch game profile directly
        user_config = self.load_config()
        if user_config.get('enable_launcher_skip') and user_config.get("last_selected_game"):

            print(user_config.get("last_selected_game"))
            game_info = None
            for match in self.matches:
                if match["name"] == user_config.get("last_selected_game"):
                    game_info = match
            if game_info:
                self.dashboard = GameDashboard(
                    game_name=game_info['name'],
                    game_path=game_info['path'],
                    application=self,
                    steam_base=self.steam_base,
                    app_id=game_info.get('app_id'),
                    user_config_path=self.user_config_path,
                    game_config_path=game_info["game_config_path"],
                )
                self.dashboard.launch()
                if self.win:
                    self.win.close()
                    self.win = None
            else:
                print("Was supposed to skip launcher, but could not find game to skip to")


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

        if self.matches:
            for game in self.matches:
                # 1. THE CARD
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                card.set_size_request(200, 300)
                card.set_halign(Gtk.Align.START)
                card.set_hexpand(False)
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
                
                assets_dir = self.assets_path

                if platform == "steam":
                    icon_path = os.path.join(assets_dir, "steam_logo.svg")
                elif platform == "heroic-epic":
                    icon_path = os.path.join(assets_dir, "epic_logo.svg")
                elif platform == "heroic-gog":
                    icon_path = os.path.join(assets_dir, "gog_logo.svg")

                if os.path.exists(icon_path):
                    try:
                        platform_badge_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            icon_path, 32, 32, True # True = Preserve aspect ratio
                        )
                        
                        # Using this for now as it's the only method I found to actually force the pictures to stay in their boxes
                        # TODO: find a non-deprecated way to do the same thing
                        platform_badge_tex = Gdk.Texture.new_for_pixbuf(platform_badge_pb)
                        platform_badge = Gtk.Picture.new_for_paintable(platform_badge_tex)
                        
                        # Styling & Placement
                        platform_badge.set_halign(Gtk.Align.END)
                        platform_badge.set_valign(Gtk.Align.END)
                        platform_badge.set_margin_end(10)
                        platform_badge.set_margin_bottom(10)
                        platform_badge.add_css_class("platform-badge")
                        
                        # Add to the image overlay created earlier
                        image_overlay.add_overlay(platform_badge)
                    except Exception as e:
                        print(f"Error rendering SVG badge: {e}")

                # Number of mods badge
                mod_total_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                
                # Styling & Placement
                mod_total_badge.set_halign(Gtk.Align.START)
                mod_total_badge.set_valign(Gtk.Align.END)
                mod_total_badge.set_margin_start(10)
                mod_total_badge.set_margin_bottom(10)
                mod_total_badge.add_css_class("platform-badge")
                    
                # If there is a mod downloads folder, count the number of archives inside
                try:
                    with open(self.user_config_path, 'r') as f:
                        user_config_data = yaml.safe_load(f)

                    game_downloads_path = user_config_data.get("download_path") + '/' + game["name"]
                    mod_total_badge_label = Gtk.Label(label=self.count_archives(game_downloads_path), css_classes=["badge-accent"])
                # If not, just set the number to 0
                except Exception as e:
                    print(f"Could not add mod total to poster: {e}")
                    print("(You probably haven't downloaded any mods yet)")
                    mod_total_badge_label = Gtk.Label(label='0', css_classes=["badge-accent"])

                # Add label
                mod_total_badge.append(mod_total_badge_label)
                image_overlay.add_overlay(mod_total_badge)

                # 4. Final Assembly
                card.append(image_overlay)
                flow.append(card)

            scroll.set_child(flow)
            overlay.set_child(scroll)

        else: # no games found
            status_page = Adw.StatusPage(
                title=_("No games detected"),
                description=_("We couldn't find any Steam or Heroic games. This could be due to\n \
- You not having any supported games installed\n \
- Your Steam/Heroic installation type not being handled\n\n \
Feel free to contact me on Discord or Github for more help!"),
                icon_name="input-gaming-symbolic"
            )
            overlay.set_child(status_page)

        

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

        #TODO: Ask user if they want to move all data from old folder to new one

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
        storage_group = Adw.PreferencesGroup(title=_("Storage"), description=_("Configure where NOMM manages your files."))
        content.append(storage_group)

        # Downloads Path Row
        path_row = Adw.ActionRow(title=_("Mod Downloads Path"))
        current_path = self.load_config().get('download_path', 'Not set')
        path_row.set_subtitle(current_path)

        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        folder_btn.connect("clicked", lambda b: self.pick_folder(settings_win, path_row, "download_path"))
        
        path_row.add_suffix(folder_btn)
        storage_group.add(path_row)

        # Staging Path Row
        staging_row = Adw.ActionRow(title=_("Mod Staging Path"))
        current_staging = self.load_config().get('staging_path', 'Not set')
        staging_row.set_subtitle(current_staging)

        staging_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        staging_btn.connect("clicked", lambda b: self.pick_folder(settings_win, staging_row, "staging_path"))
        
        staging_row.add_suffix(staging_btn)
        storage_group.add(staging_row)

        # --- NEXUS SECTION ---
        nexus_group = Adw.PreferencesGroup(title=_("Nexus Mods Integration"))
        content.append(nexus_group)

        api_entry = Gtk.PasswordEntry(hexpand=True, valign=Gtk.Align.CENTER)
        api_entry.set_property("placeholder-text", _("Paste API Key..."))
        api_entry.set_text(self.load_config().get('nexus_api_key', ''))

        check_btn = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)

        api_row = Adw.ActionRow(title=_("Nexus API Key"))
        api_row.add_suffix(api_entry)
        api_row.add_suffix(spinner)
        api_row.add_suffix(check_btn)
        nexus_group.add(api_row)

        # Validation Logic for Nexus API key
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

        # --- GENERAL SETTINGS SECTION ---
        general_group = Adw.PreferencesGroup(title=_("General Settings"))
        content.append(general_group)

        # Per-game accent colours
        accent_row = Adw.SwitchRow(title=_("Per-Game Accent Colour"))
        accent_row.set_subtitle(_("Accent colour will change for each game depending on configuration"))
        accent_row.set_active(self.load_config().get('enable_per_game_accent_colour'))
        accent_row.connect("notify::active", lambda row, pspec: self.toggle_per_game_accent_colour(row.get_active()))
        general_group.add(accent_row)

        # Skip launcher
        launcher_skip_row = Adw.SwitchRow(title=_("Skip Launcher"))
        launcher_skip_row.set_subtitle(_("App launches last used game profile instead of starting up launcher"))
        launcher_skip_row.set_active(self.load_config().get('enable_launcher_skip'))
        launcher_skip_row.connect("notify::active", lambda row, pspec: self.toggle_launcher_skip(row.get_active()))
        general_group.add(launcher_skip_row)

        # Fullscreen
        fullscreen_row = Adw.SwitchRow(title=_("Fullscreen NOMM"))
        fullscreen_row.set_subtitle(_("App launches in full screen when you select a game"))
        fullscreen_row.set_active(self.load_config().get('enable_fullscreen'))
        fullscreen_row.connect("notify::active", lambda row, pspec: self.toggle_fullscreen(row.get_active()))
        general_group.add(fullscreen_row)

        # --- COMMUNITY SECTION ---
        community_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, halign=Gtk.Align.CENTER)
        community_box.set_margin_top(10)

        assets_dir = self.assets_path

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
        community_box.append(create_social_button("matrix_logo.svg", "https://matrix.to/#/#nomm:matrix.org"))
        community_box.append(create_social_button("youtube_logo.svg", "https://www.youtube.com/channel/UCNHRyvBXItOkBZN0rWqZVrA"))

        content.append(community_box)

        # Separator and Close
        content.append(Gtk.Separator(margin_top=10))
        
        save_btn = Gtk.Button(label=_("Close"), css_classes=["suggested-action"], margin_top=12)
        save_btn.connect("clicked", lambda b: (self.update_config('nexus_api_key', api_entry.get_text()), settings_win.destroy()))
        content.append(save_btn)

        settings_win.present()

    def toggle_per_game_accent_colour(self, state):
        print(f"Per-game accent colours are now: {state}")
        self.update_config('enable_per_game_accent_colour', state)

    def toggle_launcher_skip(self, state):
        print(f"Launcher skip is now: {state}")
        self.update_config('enable_launcher_skip', state)

    def toggle_fullscreen(self, state):
        print(f"Fullscreen is now: {state}")
        self.update_config('enable_fullscreen', state)

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

        # Get the base path from user_config
        download_base = ""
        try:
            with open(self.user_config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                download_base = config.get("download_path", "")
        except: pass

        if download_base:
            # Define the game-specific path
            game_download_path = os.path.join(download_base, game_data['name'])
            print(f"Switch to game download path: {game_download_path}")
            # Create the physical folder if it doesn't exist
            os.makedirs(game_download_path, exist_ok=True)

        # Launch Dashboard
        self.dashboard = GameDashboard(
            game_name=game_data['name'],
            game_path=game_data['path'],
            application=self,
            steam_base=self.steam_base,
            app_id=game_data.get('app_id'),
            user_config_path=self.user_config_path,
            game_config_path=game_data["game_config_path"],
        )
        self.update_config("last_selected_game", game_data["name"])
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
            if isinstance(app_id, list):
                print("Something went seriously wrong, contact NOMM author")
                app_id = app_id[0]
            paths = download_heroic_assets(app_id, platform)
            return paths["art_square"]
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("nxm://"):
        nxm_link = sys.argv[1]
        print(f"nomm is processing: {nxm_link}")
        handle_nexus_link(nxm_link)
    else:
        print("Launching app")
        app = Nomm()
        app.run(None)
