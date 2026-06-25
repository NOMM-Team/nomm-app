import gettext
import os
import threading
import subprocess

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Notify', '0.7')

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from core.game_scanner import scan_all_games
from core.tools import (load_yaml,
                        translate_fuse_path, write_yaml)
from core.user_config import (load_user_config, update_user_config,
                              write_user_config)
from gui.app_views.library_view import LibraryView
from gui.dashboard import GameDashboard
from platforms.nexus import handle_nexus_link
from platforms.steam import get_username_from_steam_id, get_steam_base_dir

APP_NAME = 'com.nomm.Nomm'

translation_system = gettext.translation(APP_NAME, localedir='/app/share/locale', fallback=True)
translation_system.install(names=['ngettext'])

class Nomm(Adw.Application):
    def __init__(self, **kwargs):
        
        self.downloader = kwargs.pop('downloader', None)
        
        super().__init__(application_id=APP_NAME, flags=Gio.ApplicationFlags.HANDLES_OPEN, **kwargs)
        self.matches = []
        self.user_defined_paths = []
        self.steam_base = get_steam_base_dir()

        user_data_dir = os.path.join(GLib.get_user_data_dir(), 'nomm')
        self.user_config_path = os.path.join(user_data_dir, "user_config.yaml")
        self.game_config_path = os.path.join(user_data_dir, "game_configs")
        
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.initialize_custom_icons(base_path)

        if os.path.exists(os.path.join(os.path.dirname(base_path), "assets")):
            self.assets_path = os.path.join(os.path.dirname(base_path), "assets")
            self.default_game_config_path = os.path.join(os.path.dirname(base_path), "default_game_configs")
        else:
            self.assets_path = os.path.join(base_path, "assets")
            self.default_game_config_path = os.path.join(base_path, "default_game_configs")

        self.initialize_custom_icons(self.assets_path)            
        self.win = None

    def initialize_custom_icons(self, assets_path):
        # 1. Compile the XML into a .gresource bundle dynamically (if running in dev mode)
        # In a production flatpak, this compilation step is handled automatically by Meson/Blueprint
        xml_path = os.path.join(assets_path, "resources.gresource.xml")
        gresource_path = "resources.gresource"

        if os.path.exists(xml_path):
            # Tell the compiler that files inside the XML are found inside assets/icons/
            icons_dir = os.path.join(assets_path, "icons")
            
            subprocess.run([
                "glib-compile-resources", 
                xml_path, 
                f"--sourcedir={icons_dir}", 
                "--target", gresource_path
            ])

        # 2. Load and register the compiled resource file into memory
        if os.path.exists(gresource_path):
            resource = Gio.Resource.load(gresource_path)
            Gio.resources_register(resource)
            
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            icon_theme.add_resource_path("/com/nomm/Nomm/icons")
            print("[+] Custom icon theme registered successfully!")

    # Choose either to launch the popup_download, the app or both 
    def do_open(self, files, n_files, hint):
        for f in files:
            uri = f.get_uri()
            if not uri.startswith("nxm://"):
                continue
            self.hold()
            threading.Thread(target=self._process_nxm_link, args=(uri,), daemon=True).start()

    def _process_nxm_link(self, uri):
        started = False
        try:
            started = handle_nexus_link(uri, self.downloader)
        except Exception as e:
            print(f"Error while treating nxm link {uri}: {e}")
        GLib.idle_add(self._connect_release_on_finish if started else self.release)
    
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
    
    # Cancels downloads when shutting down the app by switching 
    # the download thread event with cancel_all empty event
    def do_shutdown(self):
        self.downloader.cancel_all()
        Adw.Application.do_shutdown(self)
                  
    def sync_configs(self):
        """Synchronises game configs from bundled YAMLs to user YAMLs"""
        # This should only be run if it's the app's first run OR it's a manual refresh
        print("Synchronising YAML game_configs")
        src, dest = self.default_game_config_path, self.game_config_path
        if not os.path.exists(src): return
        if not os.path.exists(dest): os.makedirs(dest)
        for filename in os.listdir(src):
            if filename.lower().endswith((".yaml", ".yml")):
                try:
                    import shutil
                    shutil.copy2(os.path.join(src, filename), os.path.join(dest, filename))
                except: pass
    
    def styles_application(self):
        css_provider = Gtk.CssProvider()
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        css_path = os.path.join(base_dir, "styles", "layout.css")
            
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
            self.sync_configs()
            self.show_welcome_screen()
        else:
            self.show_loading_and_scan()

        self.win.present()

    def remove_stack_child(self, name):
        child = self.stack.get_child_by_name(name)
        if child: self.stack.remove(child)

    def show_welcome_screen(self):
        self.remove_stack_child("setup")
        status_page = Adw.StatusPage(
            title=_("Welcome to the Native Open Mod Manager (NOMM) app!"),
            description=_("This app is still in early development, so expect some bugs and missing features.\nI hope you can still enjoy what the app currently offers and please don't forget that you can report any bugs or request features on the Github!"),
            icon_name="nomm-logo"
        )
        status_page.add_css_class("setup-page")

        btn = Gtk.Button(label="Let's go!")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(24)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", self.show_downloads_folder_select_screen)
        
        status_page.set_child(btn)
        self.stack.add_named(status_page, "setup")
        self.stack.set_visible_child_name("setup")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def show_downloads_folder_select_screen(self, btn=None):
        self.remove_stack_child("setup")
        status_page = Adw.StatusPage(
            title=_("Select your mods download folder"),
            description=_("Please select the folder where mod archives will be downloaded.\nMod downloads will be categorised by game name.\nI recommend you create a nomm directory at the end of your target path"),
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
        selected_folder_path = translate_fuse_path(dialog.select_folder_finish(result))
        self.temp_config = {"download_path": selected_folder_path, "library_paths": []}
        self.user_defined_paths = [selected_folder_path]
        self.show_staging_select_screen()

    def show_staging_select_screen(self):
        self.remove_stack_child("setup")
        status_page = Adw.StatusPage(
            title="Select your staging folder",
            description="Please select the folder where mods will be temporarily stored.",
            icon_name="folder-git-symbolic"
        )
        status_page.add_css_class("setup-page")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        warning_label = Gtk.Label(wrap=True, max_width_chars=50, justify=Gtk.Justification.CENTER)
        warning_label.set_markup(_("<b>Important:</b> If using Flatpaks for your platforms (Steam, Heroic, etc.), ensure they have permission to access this folder (you can do this via command line or Flatseal)."))
        warning_label.add_css_class("error")
        btn = Gtk.Button(label=_("Set Mod Staging Path"), margin_top=12)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", self.on_select_staging_folder_clicked)
        vbox.append(warning_label); vbox.append(btn)
        status_page.set_child(vbox)
        self.stack.add_named(status_page, "setup"); self.stack.set_visible_child_name("setup")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_staging_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title=_("Select Mod Staging Folder"))
        dialog.select_folder(self.win, None, self.on_staging_folder_selected_callback)

    def on_staging_folder_selected_callback(self, dialog, result):
        selected_folder_path = translate_fuse_path(dialog.select_folder_finish(result))
        self.temp_config["staging_path"] = selected_folder_path
        self.user_defined_paths.append(selected_folder_path)
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
        entry_box.append(self.api_entry); entry_box.append(cont_btn)
        status_page.set_child(entry_box)
        self.stack.add_named(status_page, "api_key"); self.stack.set_visible_child_name("api_key")

    def store_api_key(self, api_key):
        self.temp_config["nexus_api_key"] = api_key
        self.steam_user_id_handler()

    def steam_user_id_handler(self):
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
            icon_name="steam-logo-symbolic"
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
        write_yaml(self.temp_config, self.user_config_path)
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
        box.append(spinner); box.append(label)
        self.stack.add_named(box, "loading"); self.stack.set_visible_child_name("loading")
        import threading
        threading.Thread(target=self.run_background_workflow, daemon=True).start()

    def run_background_workflow(self):
        self.matches, game_libraries = scan_all_games(self.game_config_path)

        # Check if there are essential paths that are locked (staging & downloads folders)
        user_config = load_user_config()
        essential_paths = [user_config["download_path"], user_config["staging_path"]]
        print(f"Checking for access rights to essential paths: {essential_paths}")
        self.locked_essential_paths = [path for path in essential_paths if not os.access(path, os.W_OK)]
        
        # Check which game libraries are locked (No Write Access)
        print(f"Checking for access rights to library paths: {game_libraries}")
        self.locked_libraries = [lib for lib in game_libraries if not os.access(lib, os.W_OK)]

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
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR) # Essential for wrapping long paths
        text_view.set_monospace(True)
        text_view.add_css_class("card") # Adds a nice background/border in Libadwaita
        
        # Insert the command into the TextView buffer
        buffer = text_view.get_buffer()
        buffer.set_text(full_command)
        
        # Set a minimum size so it looks like a "block"
        text_view.set_size_request(450, 100) 
        # Add some internal padding
        text_view.set_left_margin(10); text_view.set_right_margin(10)
        text_view.set_top_margin(10); text_view.set_bottom_margin(10)

        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy to Clipboard"))
        copy_btn.set_valign(Gtk.Align.START) # Keep button at the top of the multi-line block
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
        quit_btn.add_css_class("suggested-action") # This provides the accent color
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
        user_config = load_yaml(self.user_config_path)
        if user_config.get('enable_launcher_skip') and user_config.get("last_selected_game"):
            game_info = next((m for m in self.matches if m["name"] == user_config.get("last_selected_game")), None)
            if game_info:
                self.open_dashboard(game_info)
                return

        library_view = LibraryView(self, self.matches)
        
        self.stack.add_named(library_view, "library")
        self.stack.set_visible_child_name("library")

    def on_game_clicked(self, game_data):
        config = load_yaml(self.user_config_path)
        if config.get('enable_fullscreen'): self.win.fullscreen()
        
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

    def return_to_library(self):
        if load_yaml(self.user_config_path).get('enable_fullscreen'): self.win.unfullscreen()
        
        # Creates the library_view if it has not been set before
        if not self.stack.get_child_by_name("library"):
            library_view = LibraryView(self, self.matches)
            self.stack.add_named(library_view, "library")
        
        self.stack.set_visible_child_name("library")

    def on_settings_clicked(self, button):
        from gui.app_views.settings import SettingsWindow
        settings_win = SettingsWindow(self, parent_window=self.win)
        settings_win.present()

    def manual_library_refresh(self):
        """Resets some logic when the user does a manual refresh"""
        # Reset ignored libraries
        update_user_config("ignored_libraries",[])
        self.sync_configs()
        self.show_loading_and_scan()