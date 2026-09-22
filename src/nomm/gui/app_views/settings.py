from gettext import ngettext
import gettext
import threading
import webbrowser

import requests
from gi.repository import Adw, Gio, GLib, Gtk

from nomm.core.user_config import update_user_config, LibrarySort, DATA_DIR, load_user_config
from nomm.core.tools import translate_fuse_path, get_nomm_tags, format_gb_size, get_dir_size_bytes
from nomm.gui.ui_builders import create_code_box, create_icon_button
from nomm.platforms.switch import list_emulators
from nomm.gui.application import APP_VERSION
from nomm.core.wine_manager import get_wine, remove_wine, get_latest_wine_version, WINE_PREFIX_DIR, \
                                   get_unused_wine_prefixes, clean_wine_prefixes, WINE_INSTALL_DIR

_ = gettext.gettext


class SettingsWindow(Adw.Window):
    def __init__(self, app, parent_window, **kwargs):
        super().__init__(title=_("Settings"), transient_for=parent_window, modal=True, **kwargs)
        self.app = app
        self.set_default_size(500, 670)

        user_config = load_user_config()

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self.set_content(content)

        # --- Custom Title Box ---
        title_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            valign=Gtk.Align.CENTER,
        )
        title_label = Gtk.Label(
            label="Native Open Mod Manager (NOMM)",
            hexpand=True,
            halign=Gtk.Align.START
        )
        title_label.add_css_class("title-1")

        # Version Button
        version_btn = Gtk.Button()
        version_btn.set_cursor_from_name("pointer")
        button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_content.set_halign(Gtk.Align.CENTER)
        version_btn_label = Gtk.Label(label=_(f"v{APP_VERSION}"))
        version_btn.set_tooltip_text(_("Open changelog on Github"))
        button_content.append(version_btn_label)
        version_btn.set_child(button_content)
        version_btn.add_css_class("badge-action-row")
        version_btn.connect("clicked", lambda b: webbrowser.open(f"https://github.com/Allexio/nomm/releases/tag/{APP_VERSION}"))
        title_box.append(title_label)
        title_box.append(version_btn)

        # Tag check logic:
        tags = get_nomm_tags(app.headers)
        if not tags:
            pass
        elif APP_VERSION not in tags:
            version_badge = Gtk.Label(label=_("dev"))
            version_badge.set_tooltip_text(_("This version is meant for testing/development only and is not publicly available"))
            version_badge.add_css_class("badge-warning")
            version_badge.set_valign(Gtk.Align.CENTER)
            title_box.append(version_badge)
        elif APP_VERSION == tags[0]:
            version_badge = Gtk.Label(label=_("latest"))
            version_badge.set_tooltip_text(_("This version is the latest publicly available version"))
            version_badge.add_css_class("badge-grey")
            version_badge.set_valign(Gtk.Align.CENTER)
            title_box.append(version_badge)
        else:
            version_upgrade_button = Gtk.Button(icon_name="upgrade-symbolic")
            version_upgrade_button.set_tooltip_text(_(f"New version available: {tags[0]}"))
            version_upgrade_button.connect("clicked", lambda b: webbrowser.open(f"https://github.com/Allexio/nomm/releases/tag/{tags[0]}"))
            version_upgrade_button.add_css_class("badge-action-row-accent")
            version_upgrade_button.add_css_class("large-icon-btn")
            version_upgrade_button.set_cursor_from_name("pointer")
            title_box.append(version_upgrade_button)

        content.append(title_box)
        content.append(Gtk.Separator(margin_top=4))

        # Everything else is in a scrollbox!
        settings_scrollwindow = Gtk.ScrolledWindow(vexpand=True)
        settings_scrollbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20,
                                     margin_top=12, margin_bottom=12,
                                     margin_start=12, margin_end=12)
        settings_scrollwindow.set_child(settings_scrollbox)

        # --- STORAGE SECTION ---
        storage_group = Adw.PreferencesGroup(title=_("NOMM Paths"))
        settings_scrollbox.append(storage_group)

        # Downloads Path Row
        self.path_row = Adw.ActionRow(title=_("Mod Downloads Path"))
        current_download_path = user_config.get('download_path', 'Not set')
        if "/run/user" in current_download_path:
            current_download_path = user_config.get('translated_download_path', 'Not set')
        self.path_row.set_subtitle(current_download_path)

        folder_btn = create_icon_button(
            icon_name="mat-folder-managed-symbolic",
            tooltip=_("Change your downloads folder location. This will NOT move all your current files to the new directory."),
            on_click=lambda b: self.pick_folder(self.path_row, "download_path"),
        )
        self.path_row.add_suffix(folder_btn)
        storage_group.add(self.path_row)

        # Staging Path Row
        self.staging_row = Adw.ActionRow(title=_("Mod Staging Path"))
        current_staging_path = user_config.get('staging_path', 'Not set')
        if "/run/user" in current_staging_path:
            current_staging_path = user_config.get('translated_staging_path', 'Not set')
        self.staging_row.set_subtitle(current_staging_path)

        staging_btn = create_icon_button(
            icon_name="mat-folder-managed-symbolic",
            tooltip=_("Change your staging folder location. This will NOT move all your current files to the new directory. "),
            on_click=lambda b: self.pick_folder(self.staging_row, "staging_path"),
        )
        self.staging_row.add_suffix(staging_btn)
        storage_group.add(self.staging_row)

        # Config Path Row
        self.config_path_row = Adw.ActionRow(title=_("NOMM Configuration Path"))
        self.config_path_row.set_subtitle(DATA_DIR)

        config_path_btn = create_icon_button(
            icon_name="mat-folder-symbolic",
            tooltip=_("Go to your NOMM configuration folder location. This path is not modifiable and depends on your NOMM installation type."),
            on_click=lambda b: webbrowser.open(f"file://{DATA_DIR}"),
        )
        self.config_path_row.add_suffix(config_path_btn)
        storage_group.add(self.config_path_row)

        # --- NEXUS SECTION ---
        nexus_group = Adw.PreferencesGroup(title=_("Nexus Mods Integration"))
        settings_scrollbox.append(nexus_group)

        self.api_entry = Gtk.PasswordEntry(hexpand=True, valign=Gtk.Align.CENTER)
        self.api_entry.set_property("placeholder-text", _("Paste API Key..."))
        self.api_entry.set_text(user_config.get('nexus_api_key', ''))

        self.check_btn = Gtk.Button(icon_name="mat-experiment-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat", "large-icon-btn"])
        self.check_btn.set_tooltip_text(_("Check API key validity"))
        self.check_btn.set_cursor_from_name("pointer")
        self.spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)

        api_row = Adw.ActionRow(title=_("Nexus API Key"))
        api_row.add_suffix(self.api_entry)
        api_row.add_suffix(self.spinner)
        api_row.add_suffix(self.check_btn)
        nexus_group.add(api_row)

        self.check_btn.connect("clicked", self.on_validate_clicked)

        # --- GENERAL SETTINGS SECTION ---
        general_group = Adw.PreferencesGroup(title=_("General Settings"))
        settings_scrollbox.append(general_group)

        # Preferred Switch emulator
        installed_emulators = list_emulators()
        if installed_emulators:
            options_model = Gtk.StringList.new(installed_emulators)
            current_emulator = user_config.get('preferred_switch_emulator')
            selected_index = installed_emulators.index(current_emulator) if current_emulator in installed_emulators else 0

            switch_emulator_row = Adw.ComboRow(
                title=_("Preferred Switch Emulator"),
                subtitle=_("Switch emulator used by NOMM when multiple are installed"),
                model=options_model,
                selected=selected_index
            )
            switch_emulator_row.connect("notify::selected", self.on_switch_emulator_changed, installed_emulators)
            general_group.add(switch_emulator_row)

        # Library sort
        sorting_options = [sort.display_name for sort in LibrarySort]
        options_model = Gtk.StringList.new(sorting_options)
        current_sort_str = user_config.get("library_sort", "Number of Mods")
        current_sort = LibrarySort.from_string(current_sort_str)
        selected_index = list(LibrarySort).index(current_sort)

        library_sort_row = Adw.ComboRow(
            title=_("Sort Library Tiles by"),
            subtitle=_("How library tiles will be sorted"),
            model=options_model,
            selected=selected_index
        )
        library_sort_row.connect("notify::selected", self.on_sort_changed)
        general_group.add(library_sort_row)

        # Per-game accent colours
        accent_row = Adw.SwitchRow(title=_("Per-Game Accent Colour"))
        accent_row.set_subtitle(_("Accent colour will change for each game depending on configuration"))
        accent_row.set_active(user_config.get('enable_per_game_accent_colour', False))
        accent_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_per_game_accent_colour', row.get_active()))
        general_group.add(accent_row)

        # Skip launcher
        launcher_skip_row = Adw.SwitchRow(title=_("Skip Launcher"))
        launcher_skip_row.set_subtitle(_("App launches last used game profile instead of starting up launcher"))
        launcher_skip_row.set_active(user_config.get('enable_launcher_skip', False))
        launcher_skip_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_launcher_skip', row.get_active()))
        general_group.add(launcher_skip_row)

        # Skip launcher
        download_popup = Adw.SwitchRow(title=_("Disable Download Window"))
        download_popup.set_subtitle(_("Disables mod downloads spawning a separate window"))
        download_popup.set_active(user_config.get('disable_download_window', False))
        download_popup.connect("notify::active", lambda row, pspec: self.toggle_setting('disable_download_window', row.get_active()))
        general_group.add(download_popup)

        # Fullscreen
        fullscreen_row = Adw.SwitchRow(title=_("Fullscreen NOMM"))
        fullscreen_row.set_subtitle(_("App launches in full screen when you select a game"))
        fullscreen_row.set_active(user_config.get('enable_fullscreen', False))
        fullscreen_row.connect("notify::active", lambda row, pspec: self.toggle_setting('enable_fullscreen', row.get_active()))
        general_group.add(fullscreen_row)

        wine_group = Adw.PreferencesGroup(title=_("Wine Settings"))
        settings_scrollbox.append(wine_group)

        wine_version = user_config.get("wine_version")
        if wine_version:
            self.wine_row = Adw.ActionRow(
                title=_("Wine"),
                subtitle=_("Installed version: {}").format(wine_version)
            )

            # Open Wine Folder Button
            self.wine_row.add_suffix(create_icon_button(
                icon_name="mat-folder-symbolic",
                tooltip=_("Open Wine folder"),
                on_click=lambda b: webbrowser.open(f"file://{WINE_INSTALL_DIR}")
            ))

            # Update Button
            if wine_version != get_latest_wine_version(self.app.headers):
                self.wine_row.add_suffix(create_icon_button(
                    icon_name="upgrade-symbolic",
                    css_classes=["flat", "suggested-action"],
                    tooltip=_("Update Wine instance"),
                    on_click=lambda btn: self.on_update_wine_clicked()
                ))

            # Delete Button
            self.wine_row.add_suffix(create_icon_button(
                icon_name="mat-delete-symbolic",
                tooltip=_("Delete Wine instance"),
                css_classes=["flat", "destructive-action"],
                on_click=lambda btn: remove_wine()
            ))
            wine_group.add(self.wine_row)

            # Wine prefixes row
            prefix_count = sum(1 for item in WINE_PREFIX_DIR.iterdir() if item.is_dir())
            prefix_size = format_gb_size(get_dir_size_bytes(WINE_PREFIX_DIR))
            subtitle = ngettext(
                "%(count)d installed prefix, taking up %(size)s",
                "%(count)d installed prefixes, taking up %(size)s",
                prefix_count,
            ) % {"count": prefix_count, "size": prefix_size}
            wine_prefix_row = Adw.ActionRow(
                title=_("Wine Prefixes"),
                subtitle=subtitle
            )
            # Open prefix folder button
            wine_prefix_row.add_suffix(create_icon_button(
                icon_name="mat-folder-symbolic",
                css_classes=["flat", "suggested-action"],
                tooltip=_("Open Wineprefix folder"),
                on_click=lambda b: webbrowser.open(f"file://{WINE_PREFIX_DIR}")
            ))
            unused_wine_prefixes = get_unused_wine_prefixes()
            if unused_wine_prefixes:
                # Clean Prefixes Button
                wine_prefix_row.add_suffix(create_icon_button(
                    icon_name="mat-clean-symbolic",
                    tooltip=_("Clean unused prefixes"),
                    css_classes=["flat", "destructive-action"],
                    on_click=lambda btn: self.show_prefix_clean_confirmation_window(unused_wine_prefixes)
                ))
            wine_group.add(wine_prefix_row)

            # Wine prefix autocleaner row
            wine_prefix_auto_cleaner = Adw.SwitchRow(
                title=_("Wine Prefix Auto-Clean"),
                subtitle=_("Automatically cleans unused prefixes after one month of inactivity")
            )
            wine_prefix_auto_cleaner.set_active(user_config.get('autoclean_prefixes', False))
            wine_prefix_auto_cleaner.connect("notify::active", lambda row, pspec: self.toggle_wineprefix_autocleaner(unused_wine_prefixes,
                                                                                                                     row.get_active()))
            wine_group.add(wine_prefix_auto_cleaner)

        # --- COMMUNITY SECTION ---
        community_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, halign=Gtk.Align.CENTER)
        community_box.set_margin_top(10)

        community_box.append(self.create_social_button("github-logo-symbolic", "https://github.com/allexio/nomm"))
        community_box.append(self.create_social_button("discord-logo-symbolic", "https://discord.gg/WFRePSjEQY"))
        community_box.append(self.create_social_button("matrix-logo-symbolic", "https://matrix.to/#/#nomm:matrix.org"))
        community_box.append(self.create_social_button("youtube-logo-symbolic", "https://www.youtube.com/channel/UCNHRyvBXItOkBZN0rWqZVrA"))

        settings_scrollbox.append(community_box)
        content.append(settings_scrollwindow)

        # Close Button
        save_btn = Gtk.Button(label=_("Close"), css_classes=["suggested-action"], margin_top=12)
        save_btn.connect("clicked", lambda b: self.close_settings())
        save_btn.set_cursor_from_name("pointer")
        content.append(save_btn)

    def pick_folder(self, row, config_key):
        dialog = Gtk.FileDialog(title=f"Select {row.get_title()}")

        def callback(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
                if folder:
                    print("new folder selected")
                    folder_path, translated_folder_path = translate_fuse_path(folder)
                    update_user_config(config_key, folder_path)
                    update_user_config("translated_"+config_key, translated_folder_path)
                    if translated_folder_path:
                        row.set_subtitle(translated_folder_path)
                    else:
                        row.set_subtitle(folder_path)
            except Exception as e:
                print(f"Folder selection failed: {e}")

        dialog.select_folder(self, None, callback)

    def on_validate_clicked(self, btn):
        key = self.api_entry.get_text()
        if not key:
            return

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
            except Exception as e:
                print(f"[!] Error while trying to check API key status: {e}")
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

    def on_switch_emulator_changed(self, combo_row, gparam, installed_emulators):
        selected_index = combo_row.get_selected()
        if 0 <= selected_index < len(installed_emulators):
            selected_emulator = installed_emulators[selected_index]
            update_user_config('preferred_switch_emulator', selected_emulator)

    def on_sort_changed(self, combo_row, gparam):
        selected_index = combo_row.get_selected()
        sort_values = list(LibrarySort)
        if 0 <= selected_index < len(sort_values):
            selected_sort = sort_values[selected_index]
            update_user_config('library_sort', selected_sort.value)

    def create_social_button(self, icon_name, url):
        btn_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(48)
        btn_content.append(img)

        social_button = Gtk.Button(child=btn_content)
        social_button.add_css_class("flat")
        social_button.set_cursor_from_name("pointer")
        social_button.connect("clicked", lambda b: Gtk.FileLauncher.new(Gio.File.new_for_uri(url)).launch(self, None, None))
        return social_button

    def close_settings(self):
        update_user_config('nexus_api_key', self.api_entry.get_text())
        self.destroy()
        self.app.show_loading_and_scan()

    def show_prefix_clean_confirmation_window(self, unused_prefixes: list, auto_clean=True):
        dialog = Adw.MessageDialog(transient_for=self, heading=_("Wineprefix Cleaner"))

        status_page = Adw.StatusPage(icon_name="wine-logo")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        warning_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, halign=Gtk.Align.CENTER)
        warning_box.add_css_class("warning-card")

        warning_label = Gtk.Label(
            wrap=True, max_width_chars=50, justify=Gtk.Justification.CENTER
        )
        warning_label.set_text(_("This is a destructive operation that may delete essential configuration / data that "
                                 "impacted tools had saved."))
        warning_box.append(warning_label)
        content_box.append(warning_box)

        if auto_clean:
            wineprefix_clean_explanation = _("All prefixes older than 1 month will be deleted right now,\n"
                                             "and automatically every time you launch NOMM.\n")
        else:
            wineprefix_clean_explanation = _("All prefixes older than 1 month will be deleted.\nThese are the impacted prefixes:")
        content_box.append(Gtk.Label(label=wineprefix_clean_explanation))

        if not auto_clean:
            content_box.append(create_code_box(", ".join(unused_prefixes)))

        status_page.set_child(content_box)
        dialog.set_extra_child(status_page)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("confirm", _("Confirm"))
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response_id):
            if response_id == "confirm":
                if auto_clean:
                    update_user_config("autoclean_prefixes", True)
                clean_wine_prefixes(unused_prefixes)
        dialog.connect("response", on_response)
        dialog.present()

    def on_update_wine_clicked(self):
        get_wine()
        self.wine_row.set_subtitle("Wine updated, you can close this window")

    def toggle_wineprefix_autocleaner(self, unused_prefixes, state: bool):
        if state:
            self.show_prefix_clean_confirmation_window(unused_prefixes, True)
        else:
            update_user_config("autoclean_prefixes", False)
