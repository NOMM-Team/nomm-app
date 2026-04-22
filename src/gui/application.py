import gettext
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Notify', '0.7')

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk

from core.config import update_user_config, load_yaml
from core.scanner import get_steam_base_dir, scan_all_games
from gui.app_views.library_view import LibraryView
from gui.dashboard import GameDashboard

APP_NAME = 'com.nomm.Nomm'

translation_system = gettext.translation(APP_NAME, localedir='/app/share/locale', fallback=True)
translation_system.install(names=['ngettext'])

class Nomm(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(application_id=APP_NAME, **kwargs)
        self.matches = []
        self.steam_base = get_steam_base_dir()

        user_data_dir = os.path.join(GLib.get_user_data_dir(), 'nomm')
        #TODO: reduce the use of these functions
        self.user_config_path = os.path.join(user_data_dir, "user_config.yaml")
        self.game_config_path = os.path.join(user_data_dir, "game_configs")
        
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if os.path.exists(os.path.join(os.path.dirname(base_path), "assets")):
            self.assets_path = os.path.join(os.path.dirname(base_path), "assets")
            self.default_game_config_path = os.path.join(os.path.dirname(base_path), "default_game_configs")
        else:
            self.assets_path = os.path.join(base_path, "assets")
            self.default_game_config_path = os.path.join(base_path, "default_game_configs")
            
        self.win = None

    def sync_configs(self):
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
        self.sync_configs()
        self.styles_application()
        
        if self.win:
            self.win.present()
            return

        self.win = Adw.ApplicationWindow(application=self)
        self.win.set_title("Nomm")
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
        if child: self.stack.remove(child)

    def show_welcome_screen(self):
        self.remove_stack_child("setup")
        status_page = Adw.StatusPage(
            title=_("Welcome to the Native Open Mod Manager (NOMM) app!"),
            description=_("This app is still in early development..."),
        )
        status_page.add_css_class("setup-page")
        
        logo_path = os.path.join(self.assets_path, "nomm.png")
        if os.path.exists(logo_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(logo_path)
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            status_page.set_paintable(texture)

        btn = Gtk.Button(label="Let's go!", halign=Gtk.Align.CENTER, margin_top=24)
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
            description=_("Please select the folder where mod downloads will be stored..."),
            icon_name="folder-download-symbolic"
        )
        status_page.add_css_class("setup-page")
        btn = Gtk.Button(label=_("Set Mod Download Path"), halign=Gtk.Align.CENTER, margin_top=24)
        btn.add_css_class("suggested-action")
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
                self.temp_config = {"download_path": selected_file.get_path(), "library_paths": []}
                self.show_staging_select_screen()
        except: pass

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
        warning_label.set_markup(_("<b>Important:</b> If using Steam Flatpak, ensure it has permission..."))
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
        try:
            selected_file = dialog.select_folder_finish(result)
            if selected_file:
                self.temp_config["staging_path"] = selected_file.get_path()
                self.show_nexus_api_key_screen()
        except: pass

    def show_nexus_api_key_screen(self):
        self.remove_stack_child("api_key")
        status_page = Adw.StatusPage(
            title=_("Nexus API Key"),
            description=_("If you want to download mods from Nexus Mods..."),
            icon_name="dialog-password-symbolic"
        )
        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER, margin_top=24)
        self.api_entry = Gtk.Entry(placeholder_text=_("Enter API Key..."), width_request=400, visibility=False)
        cont_btn = Gtk.Button(label=_("Continue"))
        cont_btn.add_css_class("suggested-action")
        cont_btn.connect("clicked", lambda b: self.finalize_setup(self.api_entry.get_text()))
        entry_box.append(self.api_entry); entry_box.append(cont_btn)
        status_page.set_child(entry_box)
        self.stack.add_named(status_page, "api_key"); self.stack.set_visible_child_name("api_key")

    def finalize_setup(self, api_key):
        self.temp_config["nexus_api_key"] = api_key
        from core.config import write_yaml
        write_yaml(self.temp_config, self.user_config_path)
        self.show_loading_and_scan()

    # --- LOGIQUE DE SCAN ---
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
        self.matches = scan_all_games(self.game_config_path)
        GLib.idle_add(self.show_library_ui)

    def show_library_ui(self):
        self.remove_stack_child("library")
        
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
            game_name=game_info['name'],
            game_path=game_info['path'],
            application=self,
            steam_base=self.steam_base,
            app_id=game_info.get('app_id'),
            user_config_path=self.user_config_path,
            game_config_path=game_info["game_config_path"],
        )
        update_user_config("last_selected_game", game_info["name"])
        self.remove_stack_child("dashboard")
        self.stack.add_named(self.dashboard, "dashboard")
        self.stack.set_visible_child_name("dashboard")

    def return_to_library(self):
        if load_yaml(self.user_config_path).get('enable_fullscreen'): self.win.unfullscreen()
        self.stack.set_visible_child_name("library")

    def on_settings_clicked(self, button):
        from gui.app_views.settings import SettingsWindow
        settings_win = SettingsWindow(parent_window=self.win, assets_path=self.assets_path)
        settings_win.present()