# src/gui/settings.py

import os
import requests
import threading
import gettext
from gi.repository import Gtk, Adw, GLib, Gio

from core.config import load_user_config, update_user_config

_ = gettext.gettext

class SettingsWindow(Adw.Window):
    def __init__(self, parent_window, assets_path, **kwargs):
        super().__init__(title=_("Settings"), transient_for=parent_window, modal=True, **kwargs)
        self.set_default_size(500, -1)
        self.assets_path = assets_path

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self.set_content(content)

        # --- STORAGE SECTION ---
        storage_group = Adw.PreferencesGroup(title=_("Storage"), description=_("Configure where NOMM manages your files."))
        content.append(storage_group)

        # Downloads Path Row
        self.path_row = Adw.ActionRow(title=_("Mod Downloads Path"))
        current_path = load_user_config().get('download_path', 'Not set')
        self.path_row.set_subtitle(current_path)

        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        folder_btn.connect("clicked", lambda b: self.pick_folder(self.path_row, "download_path"))
        self.path_row.add_suffix(folder_btn)
        storage_group.add(self.path_row)

        # Staging Path Row
        self.staging_row = Adw.ActionRow(title=_("Mod Staging Path"))
        current_staging = load_user_config().get('staging_path', 'Not set')
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
        self.api_entry.set_text(load_user_config().get('nexus_api_key', ''))

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
        accent_row.set_active(load_user_config().get('enable_per_game_accent_colour', False))
        accent_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_per_game_accent_colour', row.get_active()))
        general_group.add(accent_row)

        # Skip launcher
        launcher_skip_row = Adw.SwitchRow(title=_("Skip Launcher"))
        launcher_skip_row.set_subtitle(_("App launches last used game profile instead of starting up launcher"))
        launcher_skip_row.set_active(load_user_config().get('enable_launcher_skip', False))
        launcher_skip_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_launcher_skip', row.get_active()))
        general_group.add(launcher_skip_row)

        # Fullscreen
        fullscreen_row = Adw.SwitchRow(title=_("Fullscreen NOMM"))
        fullscreen_row.set_subtitle(_("App launches in full screen when you select a game"))
        fullscreen_row.set_active(load_user_config().get('enable_fullscreen', False))
        fullscreen_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_fullscreen', row.get_active()))
        general_group.add(fullscreen_row)

        # --- COMMUNITY SECTION ---
        community_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, halign=Gtk.Align.CENTER)
        community_box.set_margin_top(10)

        community_box.append(self.create_social_button("github_logo.svg", "https://github.com/allexio/nomm"))
        community_box.append(self.create_social_button("discord_logo.svg", "https://discord.gg/WFRePSjEQY"))
        community_box.append(self.create_social_button("matrix_logo.svg", "https://matrix.to/#/#nomm:matrix.org"))
        community_box.append(self.create_social_button("youtube_logo.svg", "https://www.youtube.com/channel/UCNHRyvBXItOkBZN0rWqZVrA"))

        content.append(community_box)

        # Separator and Close
        content.append(Gtk.Separator(margin_top=10))
        
        save_btn = Gtk.Button(label=_("Close"), css_classes=["suggested-action"], margin_top=12)
        save_btn.connect("clicked", lambda b: self.close_settings())
        content.append(save_btn)

    def pick_folder(self, row, config_key):
        """Ouvre un dialogue de sélection de dossier et met à jour la configuration."""
        dialog = Gtk.FileDialog(title=f"Select {row.get_title()}")

        def callback(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
                if folder:
                    new_path = folder.get_path()
                    update_user_config(config_key, new_path)
                    row.set_subtitle(new_path)
            except Exception as e:
                print(f"Folder selection failed: {e}")

        dialog.select_folder(self, None, callback)

    def on_validate_clicked(self, btn):
        """Vérifie la validité de l'API Key Nexus."""
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
        """Met à jour un paramètre booléen dans la configuration."""
        print(f"{key} is now: {state}")
        update_user_config(key, state)

    def create_social_button(self, icon_filename, url):
        """Crée un bouton social avec icône."""
        btn_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon_path = os.path.join(self.assets_path, icon_filename)
        
        if os.path.exists(icon_path):
            img = Gtk.Picture.new_for_filename(icon_path)
            img.set_size_request(24, 24)
            btn_content.append(img)
        else:
            btn_content.append(Gtk.Image(icon_name="action-unavailable-symbolic"))
        
        button = Gtk.Button(child=btn_content)
        button.add_css_class("flat")
        button.connect("clicked", lambda b: Gtk.FileLauncher.new(Gio.File.new_for_uri(url)).launch(self, None, None))
        return button

    def close_settings(self):
        """Sauvegarde l'API Key en cours avant de fermer."""
        update_user_config('nexus_api_key', self.api_entry.get_text())
        self.destroy()