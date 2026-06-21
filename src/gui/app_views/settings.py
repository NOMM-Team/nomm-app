import gettext
import os
import threading

import requests
from gi.repository import Adw, Gio, GLib, Gtk

from core.user_config import update_user_config
from core.tools import load_yaml, translate_fuse_path

_ = gettext.gettext

class SettingsWindow(Adw.Window):
    def __init__(self, app, parent_window, assets_path, **kwargs):
        super().__init__(title=_("Settings"), transient_for=parent_window, modal=True, **kwargs)
        self.app = app
        self.set_default_size(500, -1)
        self.assets_path = assets_path        

        self.user_config_dir = os.path.join(GLib.get_user_data_dir(), "nomm", "user_config.yaml")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self.set_content(content)

        # --- STORAGE SECTION ---
        storage_group = Adw.PreferencesGroup(title=_("Storage"), description=_("Configure where NOMM manages your files."))
        content.append(storage_group)

        # Downloads Path Row
        self.path_row = Adw.ActionRow(title=_("Mod Downloads Path"))
        current_path = load_yaml(self.user_config_dir).get('download_path', 'Not set')
        self.path_row.set_subtitle(current_path)

        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        folder_btn.connect("clicked", lambda b: self.pick_folder(self.path_row, "download_path"))
        self.path_row.add_suffix(folder_btn)
        storage_group.add(self.path_row)

        # Staging Path Row
        self.staging_row = Adw.ActionRow(title=_("Mod Staging Path"))
        current_staging = load_yaml(self.user_config_dir).get('staging_path', 'Not set')
        self.staging_row.set_subtitle(current_staging)

        staging_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        staging_btn.connect("clicked", lambda b: self.pick_folder(self.staging_row, "staging_path"))
        self.staging_row.add_suffix(staging_btn)
        storage_group.add(self.staging_row)

        # --- NEXUS SECTION ---
        nexus_group = Adw.PreferencesGroup(title=_("Nexus Mods Integration"))
        content.append(nexus_group)

        self.api_entry = Gtk.PasswordEntry(hexpand=True, valign=Gtk.Align.CENTER)
        self.api_entry.set_property("placeholder-text", _("Paste API Key..."))
        self.api_entry.set_text(load_yaml(self.user_config_dir).get('nexus_api_key', ''))

        self.check_btn = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)

        api_row = Adw.ActionRow(title=_("Nexus API Key"))
        api_row.add_suffix(self.api_entry)
        api_row.add_suffix(self.spinner)
        api_row.add_suffix(self.check_btn)
        nexus_group.add(api_row)

        self.check_btn.connect("clicked", self.on_validate_clicked)

        # --- GENERAL SETTINGS SECTION ---
        general_group = Adw.PreferencesGroup(title=_("General Settings"))
        content.append(general_group)

        # Per-game accent colours
        accent_row = Adw.SwitchRow(title=_("Per-Game Accent Colour"))
        accent_row.set_subtitle(_("Accent colour will change for each game depending on configuration"))
        accent_row.set_active(load_yaml(self.user_config_dir).get('enable_per_game_accent_colour', False))
        accent_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_per_game_accent_colour', row.get_active()))
        general_group.add(accent_row)

        # Skip launcher
        launcher_skip_row = Adw.SwitchRow(title=_("Skip Launcher"))
        launcher_skip_row.set_subtitle(_("App launches last used game profile instead of starting up launcher"))
        launcher_skip_row.set_active(load_yaml(self.user_config_dir).get('enable_launcher_skip', False))
        launcher_skip_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_launcher_skip', row.get_active()))
        general_group.add(launcher_skip_row)
        
        # Skip launcher
        download_popup = Adw.SwitchRow(title=_("Disable Download Window"))
        download_popup.set_subtitle(_("Disables mod downloads spawning a separate window"))
        download_popup.set_active(load_yaml(self.user_config_dir).get('disable_download_window', False))
        download_popup.connect("notify::active", lambda row, pspec: self.toggle_setting('disable_download_window', row.get_active()))
        general_group.add(download_popup)

        # Fullscreen
        fullscreen_row = Adw.SwitchRow(title=_("Fullscreen NOMM"))
        fullscreen_row.set_subtitle(_("App launches in full screen when you select a game"))
        fullscreen_row.set_active(load_yaml(self.user_config_dir).get('enable_fullscreen', False))
        fullscreen_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_fullscreen', row.get_active()))
        general_group.add(fullscreen_row)

        # --- COMMUNITY SECTION ---
        community_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, halign=Gtk.Align.CENTER)
        community_box.set_margin_top(10)

        community_box.append(self.create_social_button("github-logo-symbolic", "https://github.com/allexio/nomm"))
        community_box.append(self.create_social_button("discord-logo-symbolic", "https://discord.gg/WFRePSjEQY"))
        community_box.append(self.create_social_button("matrix-logo-symbolic", "https://matrix.to/#/#nomm:matrix.org"))
        community_box.append(self.create_social_button("youtube-logo-symbolic", "https://www.youtube.com/channel/UCNHRyvBXItOkBZN0rWqZVrA"))

        content.append(community_box)

        # Separator and Close
        content.append(Gtk.Separator(margin_top=10))
        
        save_btn = Gtk.Button(label=_("Close"), css_classes=["suggested-action"], margin_top=12)
        save_btn.connect("clicked", lambda b: self.close_settings())
        content.append(save_btn)

    def pick_folder(self, row, config_key):
        dialog = Gtk.FileDialog(title=f"Select {row.get_title()}")

        def callback(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
                if folder:
                    print("new folder selected")
                    folder_path = translate_fuse_path(folder)
                    update_user_config(config_key, folder_path)
                    row.set_subtitle(folder_path)
            except Exception as e:
                print(f"Folder selection failed: {e}")

        dialog.select_folder(self, None, callback)

    def on_validate_clicked(self, btn):
        key = self.api_entry.get_text()
        if not key: return

        self.check_btn.set_sensitive(False)
        self.spinner.start()
        
        self.check_btn.remove_css_class("success")
        self.check_btn.remove_css_class("error")

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
                self.spinner.stop()
                self.check_btn.set_sensitive(True)
                if is_valid:
                    self.check_btn.add_css_class("success")
                    self.check_btn.set_icon_name("emblem-ok-symbolic")
                else:
                    self.check_btn.add_css_class("error")
                    self.check_btn.set_icon_name("dialog-error-symbolic")
                return False

            GLib.idle_add(update_ui)

        threading.Thread(target=check_api, daemon=True).start()

    def toggle_setting(self, key, state):
        update_user_config(key, state)

    def create_social_button(self, icon_name, url):
        btn_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(48)
        btn_content.append(img)
        
        button = Gtk.Button(child=btn_content)
        button.add_css_class("flat")
        button.connect("clicked", lambda b: Gtk.FileLauncher.new(Gio.File.new_for_uri(url)).launch(self, None, None))
        return button

    def close_settings(self):
        update_user_config('nexus_api_key', self.api_entry.get_text())
        self.destroy()
        self.app.show_loading_and_scan()