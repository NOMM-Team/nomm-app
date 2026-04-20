# Ce fichier fait partie de Yamm (Yet Another Mod Manager).
# Yamm est un fork de Nomm, développé initialement par Allexio.
#
# Copyright (C) 2026 Emetros
# Copyright (C) 2024 Allexio
#
# Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier
# selon les termes de la Licence Publique Générale GNU telle que publiée par la
# Free Software Foundation, soit la version 3 de la Licence, soit (à votre
# discrétion) toute version ultérieure.
#
# Ce programme est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE
# GARANTIE ; sans même la garantie implicite de COMMERCIALISATION ou
# d'ADÉQUATION À UN USAGE PARTICULIER. Voir la Licence Publique Générale GNU
# pour plus de détails.
#
# Vous devriez avoir reçu une copie de la Licence Publique Générale GNU
# avec ce programme. Sinon, voir <https://www.gnu.org/licenses/>.

# Global imports
import os # a shitton of stuff
import yaml # yaml is how all my config files are stored
import shutil # I use this sparingly to copy / delete folders
import zipfile # for zip extraction
import webbrowser # to launch web browser as needed
import requests # various API calls
import gi # interface framework
import rarfile # for rar extraction
import subprocess # for bundled 7z

# Specific imports
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, Pango
from pathlib import Path
from datetime import datetime

# Core imports, these are functions used by the process
from core.heroic_asset import download_heroic_assets
from core.archive_manager import extract_archive, get_all_relative_files
from core.mod_manager import deploy_mod_files, remove_mod_files, completely_uninstall_mod
from core.nexus_api import check_for_mod_updates_async
from core.ui_tools import get_contrast_color
from core.config import (
    load_yaml, write_yaml, 
    get_metadata_path, load_metadata, save_metadata, remove_mod_from_metadata
)

# Import tabs that are used for the view
from gui.dashboard_views.mods_tab import ModsTab
from gui.dashboard_views.downloads_tab import DownloadsTab
from gui.dashboard_views.tools_tab import ToolsTab

# Point rarfile to the bundled binary
rarfile.UNRAR_TOOL = "/app/bin/unrar"

class GameDashboard(Gtk.Box):
    def __init__(self, game_name, game_path, application, steam_base=None, app_id=None, user_config_path=None, game_config_path=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.app = application
        self.game_name = game_name
        self.game_path = game_path
        self.app_id = app_id
        self.current_filter = "all" # default filter is all
        self.active_tab = "mods" # default tab is mods

        self.game_config = load_yaml(game_config_path)
        self.user_config = load_yaml(user_config_path)
        self.user_config_path = user_config_path
        self.downloads_path = str(Path(os.path.join(Path(self.user_config.get("download_path")), game_name)))
        self.staging_path = Path(os.path.join(Path(self.user_config.get("staging_path")), game_name))
        self.platform = self.game_config.get("platform")
        
        self.staging_metadata_path = get_metadata_path(self.staging_path, is_staging=True)
        self.downloads_metadata_path = get_metadata_path(self.downloads_path, is_staging=False)

        self.parse_deployment_paths() # parse the deployment paths

        self.headers = {
            'apikey': self.user_config["nexus_api_key"],
            'Application-Name': 'Yamm',
            'Application-Version': '0.1'
        }

        # Per game accent colour theming
        if self.user_config.get("enable_per_game_accent_colour") and self.game_config.get("accent_colour"):
            print("applying cool new colour")
            fg_color = self.get_contrast_color(self.game_config["accent_colour"])
            css = f"""
            window {{
                --accent-bg-color: {self.game_config["accent_colour"]};
                --accent-color: {self.game_config["accent_colour"]};
                --accent-fg-color: {fg_color};
            }}
            """
            style_provider = Gtk.CssProvider()
            style_provider.load_from_data(css.encode())
            
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                style_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        monitor = Gdk.Display.get_default().get_monitors().get_item(0)
        win_height = monitor.get_geometry().height
        banner_height = int(win_height * 0.15)

        # Initialise hero_path à None par sécurité
        hero_path = None

        # Récupération des images selon la plateforme
        if self.platform == "steam":
            hero_path = self.find_hero_image(steam_base, app_id)
        elif self.platform in ["heroic-gog", "heroic-epic"]:
            image_paths = download_heroic_assets(app_id, self.platform)
            # Ajoute cette vérification de sécurité
            if image_paths is not None:
                hero_path = image_paths.get("art_hero")
            else:
                print(f"Warning: Could not retrieve Heroic assets for {self.game_name}")
                hero_path = None # Repli sur aucune image au lieu de crash

        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        main_layout.append(header)

        banner_overlay = Gtk.Overlay()
        
        if hero_path:
            banner_mask = Gtk.ScrolledWindow(propagate_natural_height=False, vexpand=False)
            banner_mask.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            banner_mask.set_size_request(-1, banner_height)
            
            try:
                hero_tex = Gdk.Texture.new_from_file(Gio.File.new_for_path(hero_path))
                hero_img = Gtk.Picture(paintable=hero_tex, content_fit=Gtk.ContentFit.COVER, can_shrink=True)
                hero_img.set_valign(Gtk.Align.START)
                banner_mask.set_child(hero_img)
                banner_mask.get_vadjustment().set_value(0)
                banner_overlay.set_child(banner_mask)
            except Exception as e:
                print(f"Error loading hero: {e}")

        # --- TAB BUTTONS WITH INTEGRATED BADGES ---
        tab_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=False)
        main_tabs_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True, hexpand=True)

        # MODS TAB OVERLAY
        mods_tab_overlay = Gtk.Overlay()
        self.mods_tab_btn = Gtk.ToggleButton(label=_("MODS"), css_classes=["overlay-tab"])
        self.mods_tab_btn.set_cursor_from_name("pointer")
        
        # add the back button (change game)
        back_btn = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["flat"])
        back_btn.set_halign(Gtk.Align.START)
        back_btn.set_cursor_from_name("pointer")
        back_btn.connect("clicked", self.on_back_clicked)

        mods_badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mods_badge_box.set_halign(Gtk.Align.END)
        mods_badge_box.set_valign(Gtk.Align.END)
        mods_badge_box.set_margin_bottom(8); mods_badge_box.set_margin_end(8)
        
        self.mods_inactive_label = Gtk.Label(label="0", css_classes=["badge-accent"])
        self.mods_active_label = Gtk.Label(label="0", css_classes=["badge-grey"])
        mods_badge_box.append(self.mods_inactive_label)
        mods_badge_box.append(self.mods_active_label)
        
        
        mods_tab_overlay.set_child(self.mods_tab_btn)
        mods_tab_overlay.add_overlay(mods_badge_box)
        mods_tab_overlay.add_overlay(back_btn)
        main_tabs_box.append(mods_tab_overlay)

        # 2. DOWNLOADS TAB OVERLAY
        dl_tab_overlay = Gtk.Overlay()
        self.dl_tab_btn = Gtk.ToggleButton(label=_("DOWNLOADS"), css_classes=["overlay-tab"])
        self.dl_tab_btn.set_cursor_from_name("pointer")
        
        dl_badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        dl_badge_box.set_halign(Gtk.Align.END)
        dl_badge_box.set_valign(Gtk.Align.END)
        dl_badge_box.set_margin_bottom(8); dl_badge_box.set_margin_end(8)
        
        self.dl_avail_label = Gtk.Label(label="0", css_classes=["badge-accent"])
        self.dl_inst_label = Gtk.Label(label="0", css_classes=["badge-grey"])
        dl_badge_box.append(self.dl_avail_label)
        dl_badge_box.append(self.dl_inst_label)
        
        dl_tab_overlay.set_child(self.dl_tab_btn)
        dl_tab_overlay.add_overlay(dl_badge_box)
        main_tabs_box.append(dl_tab_overlay)

        tab_container.append(main_tabs_box)

        # 3. TOOLS TAB
        self.tools_tab_btn = Gtk.ToggleButton(css_classes=["overlay-tab"])
        wrench_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        wrench_icon.set_pixel_size(48) 
        self.tools_tab_btn.set_child(wrench_icon)
        self.tools_tab_btn.set_size_request(banner_height, banner_height)
        self.tools_tab_btn.set_cursor_from_name("pointer")
        tab_container.append(self.tools_tab_btn)

        # Grouping
        self.dl_tab_btn.set_group(self.mods_tab_btn)
        self.tools_tab_btn.set_group(self.mods_tab_btn)
        self.mods_tab_btn.set_active(True)
        
        banner_overlay.add_overlay(tab_container)
        main_layout.append(banner_overlay)

        self.view_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=400, vexpand=True)
        self.mods_tab_btn.connect("toggled", self.on_tab_changed, "mods")
        self.dl_tab_btn.connect("toggled", self.on_tab_changed, "downloads")
        self.tools_tab_btn.connect("toggled", self.on_tab_changed, "tools")
        main_layout.append(self.view_stack)
        
        # Initializing the three views
        self.create_mods_page()
        self.create_downloads_page()
        self.create_tools_page()  # Fixed: Calling the method to populate the tab
        
        self.update_indicators()

        footer = Gtk.CenterBox(margin_start=40, margin_end=40, margin_top=10)

        main_layout.append(footer)
        self.append(main_layout)

    def get_contrast_color(self, hex_code):
        # Remove # if present
        hex_code = hex_code.lstrip('#')
        
        # Convert hex to RGB
        r, g, b = [int(hex_code[i:i+2], 16) for i in (0, 2, 4)]
        
        # Calculate relative luminance
        # Formula: 0.299*R + 0.587*G + 0.114*B
        # We normalize 0-255 to 0-1
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        
        # If luminance is > 0.5, the color is "bright", use black text
        # Otherwise, use white text
        return "#000000" if luminance > 0.5 else "#ffffff"

    def check_for_conflicts(self):
        '''Check staging folder for any conflicts with staged files'''
        path_registry = {}
        staging_metadata = load_metadata(self.staging_metadata_path)

        if not staging_metadata:
            return []

        for mod in staging_metadata["mods"]:
            for file_path in staging_metadata["mods"][mod]["mod_files"]:
                if file_path not in path_registry:
                    path_registry[file_path] = []
                
                path_registry[file_path].append(mod)

        # Extract only the lists where multiple mods claim the same file
        conflicts = []
        for mod_list in path_registry.values():
            if len(mod_list) > 1:
                # We use set() then list() to ensure we don't 
                # list the same mod twice if it has weird internal duplicates
                unique_mods = sorted(list(set(mod_list)))
                if unique_mods not in conflicts:
                    conflicts.append(unique_mods)

        return conflicts

    def get_mod_deployment_paths(self):
        game_path = self.game_config.get("game_path")
        mod_install_path_dicts = self.game_config.get("mods_path", "")
        if not game_path:
            return None
        if self.platform == "steam":
            user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(self.app_id) + "/pfx"
        elif self.platform == "heroic-gog" or self.platform == "heroic-gog":
            #TODO: implement support for heroic user data files
            print("user data folder not supported yet for heroic installations")

        if not isinstance(mod_install_path_dicts, list):
            mod_install_path_dicts = [{
                "name": "Default",
                "path": mod_install_paths}]
        
        for mod_install_path_dict in mod_install_path_dicts:
            deployment_path = mod_install_path_dict["path"]
            if "}" not in deployment_path: # if this is the yamm 0.5 format
                deployment_path = Path(game_path) / deployment_path
            else: # if this is in the yamm 0.6 format
                deployment_path = deployment_path.replace("{game_path}", game_path)
                deployment_path = deployment_path.replace("{user_data_path}", user_data_path)
            mod_install_path_dict["path"] = deployment_path
            Path(deployment_path).mkdir(parents=True, exist_ok=True)
        
        return mod_install_path_dicts

    def parse_deployment_paths(self):
        '''Parse game paths from {xxx} to proper paths'''
        game_path = self.game_config.get("game_path")
        deployment_dicts = self.game_config.get("mods_path", "")

        if not game_path:
            return

        if self.platform == "steam":
            user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(self.app_id) + "/pfx"
        elif self.platform == "heroic-gog" or self.platform == "heroic-epic":
            user_data_path = os.path.dirname(os.path.dirname(game_path))
            #TODO: implement support for heroic user data files
            print("WARNING: User data folder not supported yet for heroic installations")
        else:
            print("unrecognised platform")
            return

        # handle case where there is only one path provided, and it's not a list of dicts
        if not isinstance(deployment_dicts, list):
            deployment_dicts = [{
                "name": "default",
                "path": deployment_dicts}]
        
        # parse the paths
        for deployment_dict in deployment_dicts:
            deployment_path = deployment_dict["path"]
            if "}" not in deployment_path: # if this is the yamm 0.5 format
                deployment_path = game_path + "/" + deployment_path
            else: # if this is in the yamm 0.6 format
                deployment_path = deployment_path.replace("{game_path}", game_path)
                deployment_path = deployment_path.replace("{user_data_path}", user_data_path)
            deployment_dict["path"] = deployment_path
        
        self.deployment_targets = deployment_dicts


    def update_indicators(self):
        # 1. Update Mods Stats
        mods_inactive, mods_active = 0, 0
        staging_metadata = load_metadata(self.staging_metadata_path)
        
        if staging_metadata:
            for mod_val in staging_metadata.get("mods", {}).values():
                if mod_val.get("status") == "enabled":
                    mods_active += 1
                elif mod_val.get("status") == "disabled":
                    mods_inactive += 1
        
        self.mods_inactive_label.set_text(str(mods_inactive))
        self.mods_active_label.set_text(str(mods_active))

        # 2. Update Downloads Stats
        d_avail, d_inst = 0, 0
        if self.downloads_path and os.path.exists(self.downloads_path):
            archives = [f for f in os.listdir(self.downloads_path) if f.lower().endswith(('.zip', '.rar', '.7z'))]
            
            # On crée un "set" (liste très rapide) des noms d'archives déjà installées
            installed_archives = set()
            if staging_metadata:
                for mod_val in staging_metadata.get("mods", {}).values():
                    arch = mod_val.get("archive_name")
                    if arch:
                        installed_archives.add(arch)
            
            # On compare chaque archive avec notre set
            for f in archives:
                if f in installed_archives:
                    d_inst += 1
                else:
                    d_avail += 1
                    
        self.dl_avail_label.set_text(str(d_avail))
        self.dl_inst_label.set_text(str(d_inst))

    def create_mods_page(self):
        if self.view_stack.get_child_by_name("mods"): 
            self.view_stack.remove(self.view_stack.get_child_by_name("mods"))
            
        self.mods_tab = ModsTab(self)
        self.view_stack.add_named(self.mods_tab, "mods")

    def create_downloads_page(self):
        if self.view_stack.get_child_by_name("downloads"):
            self.view_stack.remove(self.view_stack.get_child_by_name("downloads"))

        self.downloads_tab = DownloadsTab(self)
        self.view_stack.add_named(self.downloads_tab, "downloads")

    def create_tools_page(self):
        if self.view_stack.get_child_by_name("tools"):
            self.view_stack.remove(self.view_stack.get_child_by_name("tools"))

        self.tools_tab = ToolsTab(self)
        self.view_stack.add_named(self.tools_tab, "tools")

    def load_text_file(self, btn, path):        
        if path.exists():
            # file:// protocol usually triggers the default text editor for text files
            webbrowser.open(f"file://{path.resolve()}")
        else:
            self.show_message(
                _("Error when attempting to load text file"), 
                _("File not found at:\n {}").format(path)
            )

    def on_uninstall_item(self, btn, mod_files: list, mod_name: str):
        '''Uninstall a mod from the downloads page'''
        staging_metadata = load_metadata(self.staging_metadata_path)
        
        # Trouver le dossier de destination
        dest_dir = self.deployment_targets[0]["path"]
        if mod_name in staging_metadata["mods"] and "deployment_target" in staging_metadata["mods"][mod_name]:
            for target in self.deployment_targets:
                if target["name"] == staging_metadata["mods"][mod_name]["deployment_target"]:
                    dest_dir = target["path"]
                    break

        staging_mod_dir = os.path.join(self.staging_path, mod_name)

        # 1. Utiliser notre Core Manager pour tout nettoyer (symlinks + staging)
        completely_uninstall_mod(staging_mod_dir, dest_dir, mod_files)

        # 2. Nettoyer les métadonnées
        remove_mod_from_metadata(self.staging_metadata_path, mod_name)

        self.create_mods_page()
        self.create_downloads_page()
        self.update_indicators()

    def find_hero_image(self, steam_base, app_id):
        if not steam_base or not app_id: return None
        cache_dir = os.path.join(steam_base, "appcache", "librarycache")
        print(f"Fetching hero images in {cache_dir}")
        targets = [f"{app_id}_library_hero.jpg", "library_hero.jpg"]
        for name in targets:
            path = os.path.join(cache_dir, name)
            if os.path.exists(path):
                print(f"Found image at {path}")
                return path
        appid_dir = os.path.join(cache_dir, str(app_id))
        if os.path.exists(appid_dir):
            for root, _, files in os.walk(appid_dir):
                if "library_hero.jpg" in files:
                    print(f"Found image at {root}" + "/library_hero.jpg")
                    return os.path.join(root, "library_hero.jpg")
        return None

    def show_message(self, h, b):
        # Utilise le titre (h) pour différencier le log
        print(f"[{h}] Message displayed to user: {b}") 
        d = Adw.MessageDialog(transient_for=self.app.win, heading=h, body=b)
        d.add_response("ok", "OK")
        d.connect("response", lambda d, r: d.close())
        d.present()

    def on_tab_changed(self, btn, name):
        if btn.get_active(): 
            self.active_tab = name
            self.view_stack.set_visible_child_name(name)
            self.update_indicators()

    def on_back_clicked(self, btn):
        user_config = load_yaml(self.user_config_path)
        user_config["last_selected_game"] = "dashboard"
        write_yaml(user_config, self.user_config_path)
        
        # Nouvelle méthode que nous allons créer dans launcher.py
        self.app.return_to_library()

    def on_launch_clicked(self, btn):
        if self.app_id:
            if self.platform == "steam":
                webbrowser.open(f"steam://launch/{self.app_id}")
            elif self.platform == "heroic-gog":
                webbrowser.open(f"heroic://launch/gog/{self.app_id}")
            elif self.platform == "heroic-epic":
                webbrowser.open(f"heroic://launch/epic/{self.app_id}")

    def launch(self): self.present()
