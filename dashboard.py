import os
import gi
import yaml
import shutil
import zipfile
import webbrowser
from pathlib import Path
from datetime import datetime
from PIL import Image

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib # Added GLib

class GameDashboard(Adw.Window):
    def __init__(self, game_name, game_path, application, steam_base=None, app_id=None, **kwargs):
        super().__init__(application=application, **kwargs)
        self.app = application
        self.game_name = game_name
        self.game_path = game_path
        self.app_id = app_id
        self.current_filter = "all"
        
        self.game_config = self.load_game_config()
        self.downloads_path = self.game_config.get("downloads_path")
        
        # --- SETUP FILE MONITOR ---
        if self.downloads_path and os.path.exists(self.downloads_path):
            self.setup_folder_monitor()
        
        self.set_title(f"NOMM - {game_name}")
        self.maximize()
        self.fullscreen()
        
        win_height = self.get_default_size()[1]
        if self.is_maximized():
            monitor = Gdk.Display.get_default().get_monitors().get_item(0)
            win_height = monitor.get_geometry().height
        banner_height = int(win_height * 0.15)

        hero_path = self.find_hero_image(steam_base, app_id)
        if hero_path:
            dominant_hex = self.get_dominant_color(hero_path)
            self.apply_dynamic_accent(dominant_hex)

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

        tab_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True)
        self.mods_tab_btn = Gtk.ToggleButton(label="MODS")
        self.dl_tab_btn = Gtk.ToggleButton(label="DOWNLOADS")
        
        for btn in [self.mods_tab_btn, self.dl_tab_btn]:
            btn.set_hexpand(True)
            btn.add_css_class("overlay-tab")
            btn.set_cursor_from_name("pointer")
            tab_container.append(btn)

        self.dl_tab_btn.set_group(self.mods_tab_btn)
        self.mods_tab_btn.set_active(True)
        banner_overlay.add_overlay(tab_container)
        main_layout.append(banner_overlay)

        self.view_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=400, vexpand=True)
        self.mods_tab_btn.connect("toggled", self.on_tab_changed, "mods")
        self.dl_tab_btn.connect("toggled", self.on_tab_changed, "downloads")

        main_layout.append(self.view_stack)
        self.create_mods_page()
        self.create_downloads_page()

        footer = Gtk.CenterBox(margin_start=40, margin_end=40, margin_top=20, margin_bottom=40)
        back_btn = Gtk.Button(label="Change Game")
        back_btn.add_css_class("flat")
        back_btn.set_cursor_from_name("pointer")
        back_btn.connect("clicked", self.on_back_clicked)
        footer.set_start_widget(back_btn)
        
        launch_btn = Gtk.Button(label="Launch Game")
        launch_btn.add_css_class("suggested-action")
        launch_btn.set_size_request(240, 64)
        launch_btn.set_cursor_from_name("pointer")
        launch_btn.connect("clicked", self.on_launch_clicked)
        footer.set_end_widget(launch_btn)

        main_layout.append(footer)
        self.set_content(main_layout)

    def setup_folder_monitor(self):
        """Monitors the downloads folder for any file changes."""
        file = Gio.File.new_for_path(self.downloads_path)
        # MONITOR_NONE tracks all changes; we use a flag to prevent rapid-fire updates
        self.monitor = file.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_folder_changed)

    def on_folder_changed(self, monitor, file, other_file, event_type):
        """Callback triggered when folder contents change."""
        # We focus on CREATED and DELETED events to avoid unnecessary 
        # refreshes while a file is still being written/copied.
        targets = [
            Gio.FileMonitorEvent.CREATED, 
            Gio.FileMonitorEvent.DELETED, 
            Gio.FileMonitorEvent.MOVED
        ]
        if event_type in targets:
            # Rebuild the UI to show the new file list
            self.create_downloads_page()

    def find_hero_image(self, steam_base, app_id):
        if not steam_base or not app_id: return None
        cache_dir = os.path.join(steam_base, "appcache", "librarycache")
        if not os.path.exists(cache_dir): return None

        path = os.path.join(cache_dir, "library_hero.jpg")
        if os.path.exists(path): return path

        appid_dir = os.path.join(cache_dir, str(app_id))
        if os.path.exists(appid_dir):
            for root, _, files in os.walk(appid_dir):
                for f in files:
                    if f == "library_hero.jpg":
                        return os.path.join(root, f)
        return None

    def get_target_path(self):
        game_path_obj = Path(self.game_path).resolve()
        system_prefixes = ['/usr', '/var', '/etc', '/bin', '/lib', '/opt']
        is_system_drive = any(str(game_path_obj).startswith(pref) for pref in system_prefixes) or str(game_path_obj).startswith(str(Path.home()))

        if is_system_drive:
            nomm_root = Path.home() / "nomm"
        else:
            curr = game_path_obj
            while curr.parent != curr:
                if os.path.ismount(curr): break
                curr = curr.parent
            nomm_root = curr / "nomm"
        
        return nomm_root / self.game_name

    def is_mod_installed(self, zip_filename):
        target_dir = self.get_target_path()
        if not target_dir.exists(): return False
            
        zip_path = os.path.join(self.downloads_path, zip_filename)
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                zip_files = [f for f in z.namelist() if not f.endswith('/')]
                if not zip_files: return False
                for f in zip_files:
                    if not (target_dir / f).exists(): return False
            return True
        except: return False

    def get_install_timestamp(self, zip_filename):
        target_dir = self.get_target_path()
        zip_path = os.path.join(self.downloads_path, zip_filename)
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                zip_files = [f for f in z.namelist() if not f.endswith('/')]
                if zip_files:
                    target_file = target_dir / zip_files[0]
                    if target_file.exists():
                        mtime = target_file.stat().st_mtime
                        return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        except: pass
        return "—"

    def get_download_timestamp(self, zip_filename):
        """Returns the formatted modification date of the ZIP file itself."""
        zip_path = os.path.join(self.downloads_path, zip_filename)
        try:
            if os.path.exists(zip_path):
                mtime = os.path.getmtime(zip_path)
                return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        except: pass
        return "—"

    def create_downloads_page(self):
        
        if not hasattr(self, 'view_stack'): return
        
        # Remove existing child if rebuilding
        if self.view_stack.get_child_by_name("downloads"):
            self.view_stack.remove(self.view_stack.get_child_by_name("downloads"))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        
        # --- ACTION BAR ---
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        filter_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        filter_group.add_css_class("linked")
        
        self.all_filter_btn = Gtk.ToggleButton(label="All")
        self.all_filter_btn.set_active(True)
        self.all_filter_btn.connect("toggled", self.on_filter_toggled, "all")
        filter_group.append(self.all_filter_btn)

        for name, label in [("uninstalled", "Uninstalled"), ("installed", "Installed")]:
            btn = Gtk.ToggleButton(label=label)
            btn.set_group(self.all_filter_btn)
            btn.connect("toggled", self.on_filter_toggled, name)
            filter_group.append(btn)
        
        spacer = Gtk.Box(hexpand=True)
        open_folder_btn = Gtk.Button(icon_name="folder-open-symbolic")
        open_folder_btn.add_css_class("flat")
        open_folder_btn.connect("clicked", lambda x: os.system(f'xdg-open "{self.downloads_path}"'))
        
        action_bar.append(filter_group)
        action_bar.append(spacer)
        action_bar.append(open_folder_btn)
        container.append(action_bar)

        # --- LIST AREA ---
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_filter_func(self.filter_list_rows)

        if self.downloads_path and os.path.exists(self.downloads_path):
            # --- STREAMLINED SORTING ---
            # Sort by mtime of the file directly
            files = [f for f in os.listdir(self.downloads_path) if f.lower().endswith('.zip')]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.downloads_path, f)), reverse=True)

            for f in files:
                is_installed = self.is_mod_installed(f)
                
                # We use these helpers to populate the labels
                downloaded_time = self.get_download_timestamp(f)
                installed_time = self.get_install_timestamp(f) if is_installed else "—"
                
                row = Adw.ActionRow(title=f)
                row.is_installed = is_installed
                
                # Prefix Icons
                if is_installed:
                    prefix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                    prefix_box.append(Gtk.Image.new_from_icon_name("package-x-generic-symbolic"))
                    check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                    check.add_css_class("success")
                    prefix_box.append(check)
                    row.add_prefix(prefix_box)
                else:
                    row.add_prefix(Gtk.Image.new_from_icon_name("package-x-generic-symbolic"))
                
                # Timestamps
                for text in [f"Downloaded: {downloaded_time}", f"Installed: {installed_time}"]:
                    lbl = Gtk.Label(label=text)
                    lbl.add_css_class("dim-label")
                    lbl.set_margin_end(20)
                    row.add_suffix(lbl)

                # --- REINSTALL STACK ---
                install_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                main_install_btn = Gtk.Button(label="Reinstall" if is_installed else "Install")
                if not is_installed: main_install_btn.add_css_class("suggested-action")
                main_install_btn.set_valign(Gtk.Align.CENTER)

                confirm_install_btn = Gtk.Button(label="Are you sure?")
                confirm_install_btn.add_css_class("suggested-action")
                confirm_install_btn.set_valign(Gtk.Align.CENTER)
                confirm_install_btn.connect("clicked", self.on_install_clicked, f)

                def handle_install_click(btn, stack, installed, filename):
                    if not installed:
                        self.on_install_clicked(None, filename)
                    else:
                        stack.set_visible_child_name("confirm")
                        GLib.timeout_add_seconds(3, lambda: stack.set_visible_child_name("main") or False)

                main_install_btn.connect("clicked", handle_install_click, install_stack, is_installed, f)
                install_stack.add_named(main_install_btn, "main")
                install_stack.add_named(confirm_install_btn, "confirm")
                row.add_suffix(install_stack)

                # --- DELETE STACK ---
                delete_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                bin_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
                bin_btn.add_css_class("flat")
                
                confirm_del_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER)
                confirm_del_btn.add_css_class("destructive-action")
                confirm_del_btn.connect("clicked", self.execute_inline_delete, f)

                bin_btn.connect("clicked", lambda b, ds=delete_stack: [
                    ds.set_visible_child_name("confirm"),
                    GLib.timeout_add_seconds(3, lambda: ds.set_visible_child_name("bin") or False)
                ])
                
                delete_stack.add_named(bin_btn, "bin")
                delete_stack.add_named(confirm_del_btn, "confirm")
                row.add_suffix(delete_stack)

                self.list_box.append(row)
        
        scrolled.set_child(self.list_box)
        container.append(scrolled)
        self.view_stack.add_named(container, "downloads")

    def execute_inline_delete(self, btn, filename):
        """Final deletion execution with no further popups."""
        try:
            path = os.path.join(self.downloads_path, filename)
            if os.path.exists(path):
                os.remove(path)
                self.create_downloads_page() # Refresh list
        except Exception as e:
            self.show_message("Error", f"Could not delete: {str(e)}")

    def filter_list_rows(self, row):
        """Logic to determine if a row should be shown based on current_filter."""
        if self.current_filter == "all":
            return True
        if self.current_filter == "installed":
            return getattr(row, 'is_installed', False)
        if self.current_filter == "uninstalled":
            return not getattr(row, 'is_installed', False)
        return True

    def on_filter_toggled(self, btn, filter_name):
        if btn.get_active():
            self.current_filter = filter_name
            self.list_box.invalidate_filter() # Triggers the filter_func

    # Rest of the methods (find_hero_image, on_install_clicked, etc.) remain the same...
    def on_install_clicked(self, btn, filename):
        zip_path = os.path.join(self.downloads_path, filename)
        target_dir = self.get_target_path()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
            self.create_downloads_page() # Rebuild to update row states
        except Exception as e: self.show_message("Error", str(e))

    def on_delete_file(self, btn, filename):
        dialog = Adw.MessageDialog(transient_for=self, heading="Delete File?", body=f"Delete {filename}?")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        def on_response(diag, response):
            if response == "delete":
                try:
                    os.remove(os.path.join(self.downloads_path, filename))
                    self.create_downloads_page()
                except Exception as e: print(f"Error: {e}")
            diag.close()
        dialog.connect("response", on_response)
        dialog.present()

    def get_dominant_color(self, image_path):
        try:
            with Image.open(image_path) as img:
                img = img.convert("RGB").resize((1, 1), resample=Image.Resampling.LANCZOS)
                r, g, b = img.getpixel((0, 0))
                return f"#{r:02x}{g:02x}{b:02x}"
        except: return "#3584e4"

    def apply_dynamic_accent(self, hex_color):
        css = f"@define-color accent_bg_color {hex_color}; @define-color accent_color {hex_color};"
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def show_message(self, heading, body):
        dialog = Adw.MessageDialog(transient_for=self, heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()

    def load_game_config(self):
        config_dir = "./game_configs/"
        import re
        def slug(text): return re.sub(r'[^a-z0-9]', '', text.lower())
        target = slug(self.game_name)
        if os.path.exists(config_dir):
            for filename in os.listdir(config_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    with open(os.path.join(config_dir, filename), 'r') as f:
                        data = yaml.safe_load(f) or {}
                        if slug(data.get("name", "")) == target: return data
        return {}

    def create_mods_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        lbl = Gtk.Label(label="Installed Mods")
        lbl.add_css_class("title-1")
        box.append(lbl)
        self.view_stack.add_named(box, "mods")

    def on_tab_changed(self, btn, name):
        if btn.get_active(): self.view_stack.set_visible_child_name(name)

    def on_back_clicked(self, btn):
        self.app.do_activate() 
        self.close()

    def on_launch_clicked(self, btn):
        if self.app_id: webbrowser.open(f"steam://launch/{self.app_id}")

    def launch(self): self.present()