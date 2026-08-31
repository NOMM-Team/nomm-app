import gettext
import os
import threading
import subprocess
import gi
import locale
from importlib import resources
from urllib.parse import urlparse
from dulwich import porcelain

from nomm.core.game_scanner import scan_all_games
from nomm.core.tools import translate_fuse_path, load_nomm_version, get_bundled_data_dir
from nomm.core.user_config import (load_user_config, update_user_config,
                                   write_user_config, PRESET_GAME_CONFIG_PATH)
from nomm.platforms.switch import list_emulators, get_emulator_logo
from nomm.gui.app_views.library_view import LibraryView
from nomm.gui.dashboard import GameDashboard
from nomm.platforms.nexus import handle_nexus_link
from nomm.platforms.gamebanana import handle_gamebanana_link
from nomm.platforms.steam import get_username_from_steam_id, get_steam_base_dir

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Notify', '0.7')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

APP_NAME = 'moe.nomm.Nomm'
APP_VERSION = load_nomm_version()
LOCALE_DIR = '/app/share/locale'

# Localisation setup
gettext.bindtextdomain(APP_NAME, LOCALE_DIR)
gettext.textdomain(APP_NAME)
gettext.install(APP_NAME, LOCALE_DIR, names=['ngettext'])

try:
    locale.bindtextdomain(APP_NAME, LOCALE_DIR)
    locale.textdomain(APP_NAME)
except AttributeError:
    pass

_ = gettext.gettext


class Nomm(Adw.Application):
    def __init__(self, **kwargs):

        self.downloader = kwargs.pop('downloader', None)

        super().__init__(application_id=APP_NAME, flags=Gio.ApplicationFlags.HANDLES_OPEN, **kwargs)
        self.matches: list[dict] = []
        self.steam_base = get_steam_base_dir()

        user_data_dir: str = GLib.get_user_data_dir()
        print(f"NOMM data path is: {user_data_dir}")
        self.update_game_configurations()

        base_path: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        base_path = get_bundled_data_dir()
        self.initialize_custom_icons(os.path.join(base_path, "assets"))
        self.apply_styles()

        self.win = None

        self.headers = {
            'Application-Name': APP_NAME,
            'Application-Version': APP_VERSION,
            'User-Agent': f'{APP_NAME}/{APP_VERSION} (Linux; Flatpak) Requests/Python'
        }

    def update_game_configurations(self):
        repo_url = "https://github.com/NOMM-Team/nomm-configurations.git"
        try:
            if os.path.exists(os.path.join(PRESET_GAME_CONFIG_PATH, ".git")):
                # If the repo already exists, pull updates
                print("[+] Updating default game configurations to latest version...")
                porcelain.pull(PRESET_GAME_CONFIG_PATH)
            else:
                # If it doesn't exist yet, clone it
                print("[+] Initialising default game configurations...")
                print(f"[+] Cloning {repo_url} into {PRESET_GAME_CONFIG_PATH}...")
                porcelain.clone(repo_url, PRESET_GAME_CONFIG_PATH)
        except Exception as e:
            print(f"[!] Git operation failed: {e}")

    def initialize_custom_icons(self, assets_path):
        system_gresource = "/app/share/nomm/resources.gresource"
        gresource_path = None

        if os.path.exists(system_gresource):
            gresource_path = system_gresource
        else:
            xml_path = os.path.join(assets_path, "resources.gresource.xml")
            if os.path.exists(xml_path):
                icons_dir = os.path.join(assets_path, "icons")
                cache_dir = os.path.join(GLib.get_user_cache_dir(), "nomm")
                os.makedirs(cache_dir, exist_ok=True)

                target_path = os.path.join(cache_dir, "resources.gresource")

                try:
                    subprocess.run(
                        [
                            "glib-compile-resources",
                            xml_path,
                            f"--sourcedir={icons_dir}",
                            "--target",
                            target_path,
                        ],
                        check=True,
                    )
                    gresource_path = target_path
                except (subprocess.SubprocessError, FileNotFoundError) as e:
                    print(f"[!] Error compiling resources: {e}")
                    return

        if gresource_path and os.path.exists(gresource_path):
            resource = Gio.Resource.load(gresource_path)
            Gio.resources_register(resource)

            display = Gdk.Display.get_default()
            if display:
                icon_theme = Gtk.IconTheme.get_for_display(display)
                icon_theme.add_resource_path("/com/nomm/Nomm/icons")
                print(f"[+] Custom icon theme registered successfully from {gresource_path}")

    # Choose either to launch the popup_download, the app or both
    def do_open(self, files, n_files, hint):
        for f in files:
            uri = f.get_uri()

            if uri.startswith("nxm://"):
                target_fn = handle_nexus_link
            elif uri.startswith("nomm://"):
                target_fn = self.handle_nomm_link
            else:
                print("Could not recognise protocol ident - ignoring command")
                continue

            self.hold()
            threading.Thread(
                target=self._process_link,
                args=(uri, target_fn),
                daemon=True,
            ).start()

    def _process_link(self, uri, handler_fn):
        started = False
        try:
            started = handler_fn(uri, self.downloader, self.headers)
        except Exception as e:
            print(f"Error handling URI {uri}: {e}")

        callback = (
            self._connect_release_on_finish if started else self.release
        )
        GLib.idle_add(callback)

    def handle_nomm_link(self, url: str, downloader, headers: dict) -> bool:
        """Looks at nomm protocol scheme urls and redirects to the right bit of code"""
        target = urlparse(url).netloc
        print(f"Detected link to {target}")
        if target == "gb":
            return handle_gamebanana_link(url, downloader, self.headers)
        else:
            print(f"NOMM does not handle mod platform {target}")
            return False

    # Release application.py from self.hold so the download stops happening as background task allowing you to
    # close the downloader while keeping the download active in the mod manager and disconnect the event once
    # download is done
    def _connect_release_on_finish(self, *_args):
        state = {"released": False}
        handler_ids = []

        def on_finished(downloader, _payload):
            if state["released"] or downloader.active_count() > 0:
                return
            state["released"] = True
            self.release()
            for hid in handler_ids:
                downloader.disconnect(hid)
        handler_ids.append(self.downloader.connect("download-complete", on_finished))
        handler_ids.append(self.downloader.connect("download-error", on_finished))
        handler_ids.append(self.downloader.connect("download-metadata-ready", on_finished))

    # Cancels downloads when shutting down the app by switching
    # the download thread event with cancel_all empty event
    def do_shutdown(self):
        self.downloader.cancel_all()
        Adw.Application.do_shutdown(self)

    def apply_styles(self):
        css_provider = Gtk.CssProvider()

        try:
            css_file = resources.files("nomm.styles").joinpath("layout.css")

            css_provider.load_from_path(str(css_file))

            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                print(f"[+] Successfully loaded styles from {css_file}")
        except Exception as e:
            print(f"[!] Error loading CSS: {e}")

    def do_activate(self):

        if self.win:
            self.win.present()
            return

        self.win = Adw.ApplicationWindow(application=self)
        self.win.set_title("NOMM")
        self.win.set_default_size(1230, 900)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.win.set_content(self.stack)

        if load_user_config():
            self.show_loading_and_scan()
        else:
            self.show_welcome_screen()

        self.win.present()

    def remove_stack_child(self, name):
        child = self.stack.get_child_by_name(name)
        if child:
            self.stack.remove(child)

    def show_welcome_screen(self):
        self.remove_stack_child("welcome")
        status_page = Adw.StatusPage(
            title=_("Welcome to the Native Open Mod Manager (NOMM) app!"),
            description=_("This app is still in early development, so expect some bugs and missing features.\n\
                           I hope you can still enjoy what the app currently offers and please don't forget that\
                           you can report any bugs or request features on the Github!"),
            icon_name="nomm-logo"
        )
        status_page.add_css_class("setup-page")

        btn = Gtk.Button(label="Let's go!")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(24)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", self.show_downloads_folder_select_screen)

        status_page.set_child(btn)
        self.stack.add_named(status_page, "welcome")
        self.stack.set_visible_child_name("welcome")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def show_downloads_folder_select_screen(self, btn=None):
        self.remove_stack_child("download-select")
        status_page = Adw.StatusPage(
            title=_("Select your mods download folder"),
            description=_("Please select the folder where mod archives will be downloaded.\n\
                           Mod downloads will be categorised by game name.\nI recommend you create\
                           a nomm directory at the end of your target path"),
            icon_name="downloaded-symbolic"
        )
        status_page.add_css_class("setup-page")

        btn = Gtk.Button(label=_("Set Mod Download Path"))
        btn.set_halign(Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.set_margin_top(24)
        btn.connect("clicked", self.on_select_downloads_folder_clicked)

        status_page.set_child(btn)
        self.stack.add_named(status_page, "download-select")
        self.stack.set_visible_child_name("download-select")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_downloads_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title=_("Select Mod Downloads Folder"))
        dialog.select_folder(self.win, None, self.on_downloads_folder_selected_callback)

    def on_downloads_folder_selected_callback(self, dialog, result):
        selected_folder_path, translated_folder_path = translate_fuse_path(dialog.select_folder_finish(result))
        self.temp_config = {"download_path": selected_folder_path, "translated_download_path": translated_folder_path, "library_paths": []}
        self.show_staging_select_screen()

    def show_staging_select_screen(self):
        self.remove_stack_child("staging-select")
        status_page = Adw.StatusPage(
            title="Select your staging folder",
            description="Please select the folder where mods will be temporarily stored.",
            icon_name="folder-staging-symbolic"
        )
        status_page.add_css_class("setup-page")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        warning_label = Gtk.Label(wrap=True, max_width_chars=50, justify=Gtk.Justification.CENTER)
        warning_label.set_markup(_("<b>Important:</b> If using Flatpaks for your platforms (Steam, Heroic, etc.),\
                                    ensure they have permission to access this folder (you can do this via command line or Flatseal)."))
        warning_label.add_css_class("error")
        btn = Gtk.Button(label=_("Set Mod Staging Path"), margin_top=12, halign=Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", self.on_select_staging_folder_clicked)
        vbox.append(warning_label)
        vbox.append(btn)
        status_page.set_child(vbox)
        self.stack.add_named(status_page, "staging-select")
        self.stack.set_visible_child_name("staging-select")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_staging_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title=_("Select Mod Staging Folder"))
        dialog.select_folder(self.win, None, self.on_staging_folder_selected_callback)

    def on_staging_folder_selected_callback(self, dialog, result):
        selected_folder_path, translated_folder_path = translate_fuse_path(dialog.select_folder_finish(result))
        self.temp_config["staging_path"] = selected_folder_path
        self.temp_config["translated_staging_path"] = translated_folder_path
        self.show_nexus_api_key_screen()

    def show_nexus_api_key_screen(self):
        self.remove_stack_child("api_key")
        status_page = Adw.StatusPage(
            title=_("Nexus API Key"),
            description=_("If you want to download mods from Nexus Mods, enter your API Key (Site Preferences > API Keys > scroll all the way down)"),
            icon_name="dialog-password-symbolic"
        )
        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        entry_box.set_margin_top(24)

        self.api_entry = Gtk.Entry(placeholder_text=_("Enter API Key..."), width_request=400, visibility=False)

        cont_btn = Gtk.Button(label=_("Continue"))
        cont_btn.add_css_class("suggested-action")
        cont_btn.connect("clicked", lambda b: self.store_api_key(self.api_entry.get_text()))
        entry_box.append(self.api_entry)
        entry_box.append(cont_btn)
        status_page.set_child(entry_box)
        self.stack.add_named(status_page, "api_key")
        self.stack.set_visible_child_name("api_key")

    def store_api_key(self, api_key):
        self.temp_config["nexus_api_key"] = api_key
        self.preferred_switch_emulator_handler()

    def preferred_switch_emulator_handler(self):
        emulators = list_emulators()
        if len(emulators) == 1:
            self.temp_config["preferred_switch_emulator"] = emulators[0]
            self.steam_user_id_handler()
        elif len(emulators) > 1:
            self.show_preferred_emulator_screen(emulators)
        else:  # 0 emulators found
            self.steam_user_id_handler()

    def show_preferred_emulator_screen(self, emulators):
        self.remove_stack_child("preferred_emu")

        status_page = Adw.StatusPage(
            title=_("Select Your Preferred Switch Emulator"),
            description=_("Multiple Switch emulators were detected on your system.\n"
                          "Please select the one that you want to configure when using NOMM.\n"
                          "This choice can be changed later on in the settings."),
            icon_name="switch-logo"
        )

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24, halign=Gtk.Align.CENTER)
        content_box.set_margin_top(12)

        # Horizontal row to hold the selectable emulator buttons
        cards_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16, halign=Gtk.Align.CENTER)

        selected_emulator = {"name": emulators[0]}  # Store currently highlighted choice

        # Group buttons together so selecting one unchecks the others (Radio functionality)
        group_button = None

        for emu_name in emulators:

            # Container for each emulator option card
            emu_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER)
            emu_card.set_margin_start(12)
            emu_card.set_margin_end(12)
            emu_card.set_margin_top(12)
            emu_card.set_margin_bottom(12)

            emu_logo = Gtk.Image.new_from_icon_name(get_emulator_logo(emu_name))
            emu_logo.set_pixel_size(100)
            emu_label = Gtk.Label(label=emu_name, css_classes=["title-4"])

            emu_card.append(emu_logo)
            emu_card.append(emu_label)

            # Toggle Button wrapper to make the card clickable
            btn = Gtk.ToggleButton()
            btn.set_child(emu_card)
            btn.add_css_class("card")  # Gives it a nice Libadwaita rounded card border

            # Radio-button behavior setup
            if group_button is None:
                group_button = btn
                btn.set_active(True)  # Select the first one by default
            else:
                btn.set_group(group_button)

            # Update selection state when clicked
            def on_toggled(button, name=emu_name):
                if button.get_active():
                    selected_emulator["name"] = name

            btn.connect("toggled", on_toggled)
            cards_box.append(btn)

        content_box.append(cards_box)

        # Continue Button
        cont_btn = Gtk.Button(label=_("Continue"), halign=Gtk.Align.CENTER, width_request=160)
        cont_btn.add_css_class("suggested-action")

        def on_continue_clicked(b):
            self.temp_config["preferred_switch_emulator"] = selected_emulator["name"]
            self.steam_user_id_handler()

        cont_btn.connect("clicked", on_continue_clicked)
        content_box.append(cont_btn)

        status_page.set_child(content_box)

        self.stack.add_named(status_page, "preferred_emu")
        self.stack.set_visible_child_name("preferred_emu")

    def steam_user_id_handler(self):
        if not self.steam_base:
            self.finalize_setup()
        steam_userdata_path = self.steam_base + "userdata/"
        steam_user_ids = [f for f in os.listdir(steam_userdata_path) if os.path.isdir(os.path.join(steam_userdata_path, f))]
        if "0" in steam_user_ids:
            steam_user_ids.remove("0")
        print(f"Steam user IDs detected: {steam_user_ids}")
        if len(steam_user_ids) > 1:
            self.show_steam_user_id_selection_screen(steam_user_ids)
        else:
            steam_user_id = steam_user_ids[0]
            self.temp_config["steam_user_id"] = steam_user_id
            self.finalize_setup()

    def show_steam_user_id_selection_screen(self, steam_user_ids):
        status_page = Adw.StatusPage(
            title=_("Select Your Steam user ID"),
            description=_("Multiple Steam user IDs were detected in your Steam installation.\n"
                          "Please select the one that you want to configure when using NOMM."),
            icon_name="steam-logo"
        )

        # Create a boxed list for the options
        list_box = Gtk.ListBox()
        list_box.add_css_class("boxed-list")
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.set_valign(Gtk.Align.START)

        options = []
        for steam_user_id in steam_user_ids:
            options.append({
                "id": steam_user_id,
                "username": get_username_from_steam_id(steam_user_id, self.steam_base)})

        for opt in options:
            row = Adw.ActionRow(title=opt["id"], subtitle=opt["username"])
            row.set_activatable(True)
            # Connect the row to a callback
            row.connect("activated", self.on_option_selected, opt["id"])
            list_box.append(row)

        # Wrap the list in a box for padding/alignment
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        container.set_halign(Gtk.Align.CENTER)
        container.set_margin_top(24)
        container.append(list_box)

        status_page.set_child(container)
        self.stack.add_titled(status_page, "option_select", _("Select Option"))
        self.stack.set_visible_child_name("option_select")

    def on_option_selected(self, row, steam_user_id):
        print(f"User's Steam user ID set to: {steam_user_id}")
        self.temp_config["steam_user_id"] = steam_user_id
        # Continue to next part of setup
        self.finalize_setup()

    def finalize_setup(self):
        write_user_config(self.temp_config)
        self.show_loading_and_scan()

    # Scan logic
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
        self.stack.add_named(box, "loading")
        self.stack.set_visible_child_name("loading")
        import threading
        threading.Thread(target=self.run_background_workflow, daemon=True).start()

    def run_background_workflow(self):
        self.matches, self.game_libraries = scan_all_games()

        # Check if there are essential paths that are locked (staging & downloads folders)
        user_config = load_user_config()
        essential_paths = [user_config["download_path"], user_config["staging_path"]]
        print(f"Checking for access rights to essential paths: {essential_paths}")
        self.locked_essential_paths = [path for path in essential_paths if not os.access(path, os.W_OK)]

        # Check which game libraries are locked (No Write Access)
        print(f"Checking for access rights to library paths: {self.game_libraries}")
        self.locked_libraries = [lib for lib in self.game_libraries if not os.access(lib, os.W_OK)]

        user_config = load_user_config()
        if "ignored_libraries" in user_config:
            ignored_libraries = user_config["ignored_libraries"]
            print(f"Libraries ignored and not checked: {ignored_libraries}")
            self.locked_libraries = [path for path in self.locked_libraries if path not in ignored_libraries]

        # If there are some missing paths, should display permission request window
        if self.locked_libraries or self.locked_essential_paths:
            print(f"Missing read/write access to some paths: {str(self.locked_libraries + self.locked_essential_paths)}")
            GLib.idle_add(self.show_permission_request)
        else:
            GLib.idle_add(self.show_library_ui)

    def copy_to_clipboard(self, btn, text):
        # Get the default display directly from Gdk
        display = Gdk.Display.get_default()
        clipboard = display.get_clipboard()

        # In GTK4, use .set_content() or .set() depending on your version
        # .set(text) is a convenience method added in later GTK4 updates
        clipboard.set(text)

        # Visual feedback
        btn.set_icon_name("object-select-symbolic")
        GLib.timeout_add(1000, lambda: btn.set_icon_name("edit-copy-symbolic"))

    def show_permission_request(self):
        status_page = Adw.StatusPage(
            icon_name="system-lock-screen-symbolic",
            title=_("Permissions Missing"),
            description=_("NOMM needs some extra permissions to read/write to specific folders.\n"
                          "This is used so that NOMM can find your games and install &amp; deploy mods properly.\n"
                          "Please copy the command below and run it in your terminal.")
        )

        # Generate the command
        paths_str = " ".join([f"--filesystem='{p}'" for p in (self.locked_libraries + self.locked_essential_paths)])
        full_command = f"flatpak override --user {paths_str} {APP_NAME}"

        # Build the Multi-line Block
        action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        action_box.set_halign(Gtk.Align.CENTER)

        # We use a horizontal box to keep the TextView and Copy button together
        cmd_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # TextView setup
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)  # Essential for wrapping long paths
        text_view.set_monospace(True)
        text_view.add_css_class("card")  # Adds a nice background/border in Libadwaita

        # Insert the command into the TextView buffer
        buffer = text_view.get_buffer()
        buffer.set_text(full_command)

        # Set a minimum size so it looks like a "block"
        text_view.set_size_request(450, 100)
        # Add some internal padding
        text_view.set_left_margin(10)
        text_view.set_right_margin(10)
        text_view.set_top_margin(10)
        text_view.set_bottom_margin(10)

        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy to Clipboard"))
        copy_btn.set_valign(Gtk.Align.START)  # Keep button at the top of the multi-line block
        copy_btn.add_css_class("suggested-action")
        copy_btn.connect("clicked", self.copy_to_clipboard, full_command)

        cmd_container.append(text_view)
        cmd_container.append(copy_btn)
        action_box.append(cmd_container)

        # Footer
        restart_hint = Gtk.Label(label=_("Restart NOMM after running the command."))
        restart_hint.add_css_class("dim-label")
        action_box.append(restart_hint)

        status_page.set_child(action_box)

        # Container for buttons
        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_row.set_halign(Gtk.Align.CENTER)
        button_row.set_margin_top(24)

        # Button: Quit (Accented/Blue)
        quit_btn = Gtk.Button(label=_("Quit"))
        quit_btn.add_css_class("pill")
        quit_btn.add_css_class("suggested-action")  # This provides the accent color
        quit_btn.connect("clicked", lambda x: self.quit())
        button_row.append(quit_btn)

        # Continue buttons will NOT be displayed if missing an essential path
        if not self.locked_essential_paths:
            # Button: Continue anyway
            continue_btn = Gtk.Button(label=_("Continue"))
            continue_btn.add_css_class("pill")
            continue_btn.connect("clicked", lambda x: self.show_library_ui())
            button_row.append(continue_btn)

            # Button: Continue and ignore
            continue_ignore_btn = Gtk.Button(label=_("Continue & Ignore"))
            continue_ignore_btn.add_css_class("pill")
            continue_ignore_btn.connect("clicked", lambda x: self.ignore_libraries())
            button_row.append(continue_ignore_btn)

        action_box.append(button_row)

        self.remove_stack_child("permissions")
        self.stack.add_named(status_page, "permissions")
        self.stack.set_visible_child_name("permissions")

    def ignore_libraries(self):
        """lets user ignore checking for r/w access to some libraries during startup check"""
        user_config = load_user_config()
        if "ignored_libraries" not in user_config:
            user_config["ignored_libraries"] = []
        for path in self.locked_libraries:
            if path not in user_config["ignored_libraries"]:
                user_config["ignored_libraries"].append(path)
                print(f"Added path: {path} to ignored libraries")
        write_user_config(user_config)

        # Once ignored paths are added to config, show library
        self.show_library_ui()

    def show_library_ui(self):
        self.remove_stack_child("library")

        # If user has selected launcher skip option, launch game profile directly
        user_config = load_user_config()
        if user_config.get('enable_launcher_skip') and user_config.get("last_selected_game"):
            game_info = next((m for m in self.matches if m["name"] == user_config.get("last_selected_game")), None)
            if game_info:
                self.open_dashboard(game_info)
                return

        library_view = LibraryView(self, self.matches)

        self.stack.add_named(library_view, "library")
        self.stack.set_visible_child_name("library")

    def on_game_clicked(self, game_data):
        config = load_user_config()
        if config.get('enable_fullscreen'):
            self.win.fullscreen()

        if config.get("download_path"):
            os.makedirs(os.path.join(config.get("download_path"), game_data['name']), exist_ok=True)

        self.open_dashboard(game_data)

    def open_dashboard(self, game_info):
        self.dashboard = GameDashboard(
            application=self,
            game_info=game_info
        )
        update_user_config("last_selected_game", game_info["name"])
        self.remove_stack_child("dashboard")
        self.stack.add_named(self.dashboard, "dashboard")
        self.stack.set_visible_child_name("dashboard")
        self.win.set_title(f"NOMM: {game_info["name"]}")

    def return_to_library(self):
        self.win.set_title("NOMM")
        if load_user_config().get('enable_fullscreen'):
            self.win.unfullscreen()

        # Creates the library_view if it has not been set before
        if not self.stack.get_child_by_name("library"):
            library_view = LibraryView(self, self.matches)
            self.stack.add_named(library_view, "library")

        self.stack.set_visible_child_name("library")

    def on_configuration_builder_clicked(self, button):
        from nomm.gui.app_views.configuration_builder import (
            ConfigurationBuilderWindow,
            PlatformChoiceDialog,
        )

        parent = (
            self.get_active_window()
            if hasattr(self, "get_active_window")
            else self
        )

        def on_dialog_completed(data):
            # Launch the main configuration form window with pre-filled dictionary
            config_window = ConfigurationBuilderWindow(
                parent_window=parent,
                app=self,
                initial_data=data
            )
            config_window.present()

        dialog = PlatformChoiceDialog(
            parent_window=parent, app=self, callback=on_dialog_completed
        )
        dialog.present()

    def on_settings_clicked(self, button):
        from nomm.gui.app_views.settings import SettingsWindow
        settings_win = SettingsWindow(self, parent_window=self.win)
        settings_win.present()

    def manual_library_refresh(self, button):
        """Resets some logic when the user does a manual refresh"""
        # Reset ignored libraries
        update_user_config("ignored_libraries", [])
        self.update_game_configurations()
        self.show_loading_and_scan()
