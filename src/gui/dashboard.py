import os
import shutil
import subprocess
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

import gi
import rarfile
import requests
import yaml
from gi.repository import Adw, Gdk, Gio, Gtk

from core.config import (get_metadata_path, load_metadata, load_yaml,
                         parse_deployment_paths, remove_mod_from_metadata,
                         write_yaml)
from core.heroic_asset import download_heroic_assets
from core.index_manager import check_index, init_index
from core.mod_manager import completely_uninstall_mod, get_mod_statistics
from core.scanner import find_game_art
from core.ui_tools import get_contrast_color
from gui.dashboard_views.downloads_tab import DownloadsTab
from gui.dashboard_views.mods_tab import ModsTab
from gui.dashboard_views.tools_tab import ToolsTab

rarfile.UNRAR_TOOL = "/app/bin/unrar"

class GameDashboard(Gtk.Box):
    def __init__(self, game_name, game_path, application, steam_base=None, app_id=None, user_config_path=None, game_config_path=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.app = application
        self.game_name = game_name
        self.game_path = game_path
        self.app_id = app_id
        self.current_filter = "all"
        self.active_tab = "mods"

        self.game_config = load_yaml(game_config_path)
        self.user_config = load_yaml(user_config_path)
        self.user_config_path = user_config_path
        self.downloads_path = str(Path(os.path.join(Path(self.user_config.get("download_path")), game_name)))
        self.staging_path = Path(os.path.join(Path(self.user_config.get("staging_path")), game_name))
        self.platform = self.game_config.get("platform")
        
        self.staging_metadata_path = get_metadata_path(self.staging_path, is_staging=True)
        self.downloads_metadata_path = get_metadata_path(self.downloads_path, is_staging=False)

        self.deployment_targets = parse_deployment_paths(self.game_config, self.platform, str(self.app_id))
        
        init_index(self.staging_path)
        check_index(self.staging_path)

        self.headers = {
            'apikey': self.user_config["nexus_api_key"],
            'Application-Name': 'NOMM',
            'Application-Version': '0.1'
        }

        # Per game accent colour theming
        if self.user_config.get("enable_per_game_accent_colour") and self.game_config.get("accent_colour"):
            print("applying cool new colour")
            fg_color = get_contrast_color(self.game_config["accent_colour"])
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

        hero_path = None

        # Assets management
        if self.platform == "steam":
            hero_path = find_game_art(app_id, self.platform, steam_base)
        elif self.platform in ["heroic-gog", "heroic-epic"]:
            image_paths = download_heroic_assets(app_id, self.platform)
            
            if image_paths is not None:
                hero_path = image_paths.get("art_hero")
            else:
                print(f"Warning: Could not retrieve Heroic assets for {self.game_name}")
                hero_path = None

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
        
        # Add the back button (change game)
        back_btn = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["flat"])
        back_btn.set_halign(Gtk.Align.START)
        back_btn.set_cursor_from_name("pointer")
        back_btn.connect("clicked", self.on_back_clicked)
        
        # Mod count box -- Need a CSS
        mods_badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mods_badge_box.set_halign(Gtk.Align.END)
        mods_badge_box.set_valign(Gtk.Align.END)
        mods_badge_box.set_margin_bottom(8); mods_badge_box.set_margin_end(8)
        
        # Active mod count box
        self.mods_inactive_label = Gtk.Label(label="0", css_classes=["badge-accent"])
        self.mods_active_label = Gtk.Label(label="0", css_classes=["badge-grey"])
        mods_badge_box.append(self.mods_inactive_label)
        mods_badge_box.append(self.mods_active_label)
        
        # Mods tab overlay append
        mods_tab_overlay.set_child(self.mods_tab_btn)
        mods_tab_overlay.add_overlay(mods_badge_box)
        mods_tab_overlay.add_overlay(back_btn)
        main_tabs_box.append(mods_tab_overlay)

        # Downloads tab overlay append
        dl_tab_overlay = Gtk.Overlay()
        self.dl_tab_btn = Gtk.ToggleButton(label=_("DOWNLOADS"), css_classes=["overlay-tab"])
        self.dl_tab_btn.set_cursor_from_name("pointer")
        
        # Mod count box
        dl_badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        dl_badge_box.set_halign(Gtk.Align.END)
        dl_badge_box.set_valign(Gtk.Align.END)
        dl_badge_box.set_margin_bottom(8); dl_badge_box.set_margin_end(8)
        
        # Active mod count box
        self.dl_avail_label = Gtk.Label(label="0", css_classes=["badge-accent"])
        self.dl_inst_label = Gtk.Label(label="0", css_classes=["badge-grey"])
        dl_badge_box.append(self.dl_avail_label)
        dl_badge_box.append(self.dl_inst_label)
        
        dl_tab_overlay.set_child(self.dl_tab_btn)
        dl_tab_overlay.add_overlay(dl_badge_box)
        main_tabs_box.append(dl_tab_overlay)

        tab_container.append(main_tabs_box)

        # Utilities tab
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
        
        # Banner
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
        self.create_tools_page()
        
        self.update_indicators()

        footer = Gtk.CenterBox(margin_start=40, margin_end=40, margin_top=10)

        main_layout.append(footer)
        self.append(main_layout)

    def update_indicators(self):
        stats = get_mod_statistics(self.staging_metadata_path, self.downloads_path)
        
        self.mods_inactive_label.set_text(str(stats["mods_inactive"]))
        self.mods_active_label.set_text(str(stats["mods_active"]))
        self.dl_avail_label.set_text(str(stats["downloads_available"]))
        self.dl_inst_label.set_text(str(stats["downloads_installed"]))

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
        staging_metadata = load_metadata(self.staging_metadata_path)
        
        dest_dir = self.deployment_targets[0]["path"]
        if mod_name in staging_metadata["mods"] and "deployment_target" in staging_metadata["mods"][mod_name]:
            for target in self.deployment_targets:
                if target["name"] == staging_metadata["mods"][mod_name]["deployment_target"]:
                    dest_dir = target["path"]
                    break

        staging_mod_dir = os.path.join(self.staging_path, mod_name)

        completely_uninstall_mod(staging_mod_dir, dest_dir, mod_files)

        remove_mod_from_metadata(self.staging_metadata_path, mod_name)

        self.create_mods_page()
        self.create_downloads_page()
        self.update_indicators()

    def show_message(self, h, b):
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