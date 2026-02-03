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
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

class GameDashboard(Adw.Window):
    def __init__(self, game_name, game_path, application, steam_base=None, app_id=None, **kwargs):
        super().__init__(application=application, **kwargs)
        self.app = application
        self.game_name = game_name
        self.game_path = game_path
        self.app_id = app_id
        self.current_filter = "all"
        
        self.setup_custom_styles()

        self.game_config = self.load_game_config()
        self.downloads_path = self.game_config.get("downloads_path")
        
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

    # --- PATH HELPERS ---

    def get_staging_path(self):
        """The 'nomm' staging folder (Source for symlinks)."""
        game_path_obj = Path(self.game_path).resolve()
        system_prefixes = ['/usr', '/var', '/etc', '/bin', '/lib', '/opt']
        is_system_drive = any(str(game_path_obj).startswith(pref) for pref in system_prefixes) or str(game_path_obj).startswith(str(Path.home()))

        if is_system_drive:
            nomm_root = Path.home() / "nomm"
        else:
            curr = game_path_obj
            while curr.parent != curr:
                if os.path.ismount(curr): break # Fixed: os.path.ismount
                curr = curr.parent
            nomm_root = curr / "nomm"
        
        path = nomm_root / self.game_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_game_destination_path(self):
        """The actual folder inside the game directory (Target for symlinks)."""
        game_path = self.game_config.get("game_path")
        mods_subfolder = self.game_config.get("mods_path", "")
        if not game_path: return None
        dest = Path(game_path) / mods_subfolder
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    # --- MODS PAGE (SYMLINKS) ---

    def on_switch_toggled(self, switch, state, item_name):
        staging_item = self.get_staging_path() / item_name
        dest_dir = self.get_game_destination_path()
        
        if not dest_dir:
            self.show_message("Error", "Game destination path not found in config.")
            switch.set_active(False)
            return False

        link_path = dest_dir / item_name

        if state:
            if not link_path.exists():
                try:
                    os.symlink(staging_item, link_path)
                except Exception as e:
                    self.show_message("Error", f"Link failed: {e}")
                    switch.set_active(False)
        else:
            if link_path.is_symlink():
                try:
                    link_path.unlink()
                except Exception as e:
                    self.show_message("Error", f"Unlink failed: {e}")
                    switch.set_active(True)
        return False

    def create_mods_page(self):
        if self.view_stack.get_child_by_name("mods"):
            self.view_stack.remove(self.view_stack.get_child_by_name("mods"))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        spacer = Gtk.Box(hexpand=True)
        action_bar.append(spacer)

        staging_dir = self.get_staging_path()
        dest_dir = self.get_game_destination_path()
        items = os.listdir(staging_dir) if staging_dir.exists() else []

        if items:
            open_btn = Gtk.Button(icon_name="folder-open-symbolic")
            open_btn.add_css_class("flat")
            open_btn.connect("clicked", lambda x: os.system(f'xdg-open "{staging_dir}"'))
            action_bar.append(open_btn)
        
        container.append(action_bar)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.mods_list_box = Gtk.ListBox()
        self.mods_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.mods_list_box.add_css_class("boxed-list")

        if items:
            items.sort(key=lambda x: os.path.getmtime(staging_dir / x), reverse=True)
            for item in items:
                row = Adw.ActionRow(title=item)
                
                is_enabled = (dest_dir / item).is_symlink() if dest_dir else False
                
                enable_switch = Gtk.Switch(active=is_enabled, valign=Gtk.Align.CENTER)
                enable_switch.add_css_class("green-switch")
                enable_switch.set_margin_end(8)
                enable_switch.connect("state-set", self.on_switch_toggled, item)
                row.add_prefix(enable_switch)

                mtime = os.path.getmtime(staging_dir / item)
                ts = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                ts_lbl = Gtk.Label(label=f"Installed: {ts}")
                ts_lbl.add_css_class("dim-label")
                ts_lbl.set_margin_end(20)
                row.add_suffix(ts_lbl)

                stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                bin_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
                bin_btn.add_css_class("flat")
                conf_btn = Gtk.Button(label="Confirm Uninstall?")
                conf_btn.add_css_class("destructive-action")
                conf_btn.set_valign(Gtk.Align.CENTER)
                conf_btn.connect("clicked", self.on_uninstall_item, item)
                
                bin_btn.connect("clicked", lambda b, s=stack: [s.set_visible_child_name("c"), GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)])
                stack.add_named(bin_btn, "b")
                stack.add_named(conf_btn, "c")
                row.add_suffix(stack)
                self.mods_list_box.append(row)
        else:
            empty_box = Gtk.CenterBox(margin_top=40)
            lbl = Gtk.Label(label="No mods currently installed.")
            lbl.add_css_class("dim-label")
            empty_box.set_center_widget(lbl)
            container.append(empty_box)

        scrolled.set_child(self.mods_list_box)
        container.append(scrolled)
        self.view_stack.add_named(container, "mods")

    # --- DOWNLOADS PAGE ---

    def create_downloads_page(self):
        if not hasattr(self, 'view_stack'): return
        if self.view_stack.get_child_by_name("downloads"):
            self.view_stack.remove(self.view_stack.get_child_by_name("downloads"))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        filter_group = Gtk.Box()
        filter_group.add_css_class("linked")
        self.all_filter_btn = Gtk.ToggleButton(label="All", active=True)
        self.all_filter_btn.connect("toggled", self.on_filter_toggled, "all")
        filter_group.append(self.all_filter_btn)

        for n, l in [("uninstalled", "Uninstalled"), ("installed", "Installed")]:
            b = Gtk.ToggleButton(label=l, group=self.all_filter_btn)
            b.connect("toggled", self.on_filter_toggled, n)
            filter_group.append(b)
        
        spacer = Gtk.Box(hexpand=True)
        open_btn = Gtk.Button(icon_name="folder-open-symbolic")
        open_btn.add_css_class("flat")
        open_btn.connect("clicked", lambda x: os.system(f'xdg-open "{self.downloads_path}"'))
        
        action_bar.append(filter_group); action_bar.append(spacer); action_bar.append(open_btn)
        container.append(action_bar)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_filter_func(self.filter_list_rows)

        if self.downloads_path and os.path.exists(self.downloads_path):
            files = [f for f in os.listdir(self.downloads_path) if f.lower().endswith('.zip')]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.downloads_path, f)), reverse=True)

            for f in files:
                installed = self.is_mod_installed(f)
                row = Adw.ActionRow(title=f)
                row.is_installed = installed
                
                p_box = Gtk.Box(spacing=6)
                img = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
                p_box.append(img)
                if installed:
                    chk = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                    chk.add_css_class("success")
                    p_box.append(chk)
                row.add_prefix(p_box)
                
                dl_time = self.get_download_timestamp(f)
                inst_time = self.get_install_timestamp_from_zip(f) if installed else "—"
                
                row.add_suffix(Gtk.Label(label=f"Downloaded: {dl_time}", css_classes=["dim-label"], margin_end=20))
                row.add_suffix(Gtk.Label(label=f"Installed: {inst_time}", css_classes=["dim-label"], margin_end=20))
                
                i_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                main_i_btn = Gtk.Button(label="Reinstall" if installed else "Install", valign=Gtk.Align.CENTER)
                if not installed: main_i_btn.add_css_class("suggested-action")
                conf_i_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER)
                conf_i_btn.add_css_class("suggested-action")
                conf_i_btn.connect("clicked", self.on_install_clicked, f)

                def handle_i(btn, s, inst, fname):
                    if not inst: self.on_install_clicked(None, fname)
                    else:
                        s.set_visible_child_name("c")
                        GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("m") or False)

                main_i_btn.connect("clicked", handle_i, i_stack, installed, f)
                i_stack.add_named(main_i_btn, "m"); i_stack.add_named(conf_i_btn, "c")
                row.add_suffix(i_stack)

                d_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                b_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
                b_btn.add_css_class("flat")
                c_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER)
                c_btn.add_css_class("destructive-action")
                c_btn.connect("clicked", self.execute_inline_delete, f)
                
                b_btn.connect("clicked", lambda b, s=d_stack: [s.set_visible_child_name("c"), GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)])
                d_stack.add_named(b_btn, "b"); d_stack.add_named(c_btn, "c")
                row.add_suffix(d_stack)

                self.list_box.append(row)
        
        scrolled.set_child(self.list_box)
        container.append(scrolled)
        self.view_stack.add_named(container, "downloads")

    # --- SHARED SYSTEM ---

    def setup_custom_styles(self):
        css = """
        switch.green-switch:checked > slider { background-color: white; }
        switch.green-switch:checked { background-color: #26a269; border-color: #1a774b; }
        switch.green-switch { transition: all 200ms ease-in-out; scale: 0.8; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, 800)

    def setup_folder_monitor(self):
        f = Gio.File.new_for_path(self.downloads_path)
        self.monitor = f.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_folder_changed)

    def on_folder_changed(self, m, f, of, et):
        if et in [Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED, Gio.FileMonitorEvent.MOVED]:
            self.create_downloads_page()

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

    def get_install_timestamp_from_zip(self, zip_filename):
        staging_dir = self.get_staging_path()
        zip_path = os.path.join(self.downloads_path, zip_filename)
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                files = [x for x in z.namelist() if not x.endswith('/')]
                if files:
                    target_file = staging_dir / files[0]
                    if target_file.exists():
                        mtime = target_file.stat().st_mtime
                        return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        except: pass
        return "—"

    def is_mod_installed(self, zip_filename):
        staging_dir = self.get_staging_path()
        zip_path = os.path.join(self.downloads_path, zip_filename)
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                for f in [x for x in z.namelist() if not x.endswith('/')]:
                    if not (staging_dir / f).exists(): return False
            return True
        except: return False

    def on_install_clicked(self, btn, filename):
        zip_path = os.path.join(self.downloads_path, filename)
        staging_dir = self.get_staging_path()
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(staging_dir)
            self.create_downloads_page(); self.create_mods_page()
        except Exception as e: self.show_message("Error", str(e))

    def on_uninstall_item(self, btn, item_name):
        staging_path = self.get_staging_path() / item_name
        dest_dir = self.get_game_destination_path()
        try:
            if dest_dir:
                link_path = dest_dir / item_name
                if link_path.is_symlink(): link_path.unlink()
            if staging_path.is_dir(): shutil.rmtree(staging_path)
            else: staging_path.unlink()
            self.create_mods_page(); self.create_downloads_page()
        except Exception as e: self.show_message("Error", str(e))

    def execute_inline_delete(self, btn, f):
        try:
            p = os.path.join(self.downloads_path, f)
            if os.path.exists(p): os.remove(p); self.create_downloads_page()
        except Exception as e: self.show_message("Error", str(e))

    def on_filter_toggled(self, btn, f_name):
        if btn.get_active():
            self.current_filter = f_name
            self.list_box.invalidate_filter()

    def filter_list_rows(self, row):
        if self.current_filter == "all": return True
        return row.is_installed if self.current_filter == "installed" else not row.is_installed

    def get_download_timestamp(self, f):
        try: return datetime.fromtimestamp(os.path.getmtime(os.path.join(self.downloads_path, f))).strftime('%Y-%m-%d %H:%M')
        except: return "—"

    def find_hero_image(self, steam_base, app_id):
        if not steam_base or not app_id: return None
        cache = os.path.join(steam_base, "appcache", "librarycache")
        targets = [f"{app_id}_library_hero.jpg", "library_hero.jpg"]
        for name in targets:
            path = os.path.join(cache, name)
            if os.path.exists(path): return path
        appid_dir = os.path.join(cache, str(app_id))
        if os.path.exists(appid_dir):
            for root, _, files in os.walk(appid_dir):
                for f in files:
                    if f == "library_hero.jpg": return os.path.join(root, f)
        return None

    def get_dominant_color(self, path):
        try:
            with Image.open(path) as img:
                img = img.convert("RGB").resize((1, 1))
                r, g, b = img.getpixel((0, 0))
                return f"#{r:02x}{g:02x}{b:02x}"
        except: return "#3584e4"

    def apply_dynamic_accent(self, hex):
        css = f"@define-color accent_bg_color {hex}; @define-color accent_color {hex};"
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, 800)

    def show_message(self, h, b):
        d = Adw.MessageDialog(transient_for=self, heading=h, body=b)
        d.add_response("ok", "OK"); d.connect("response", lambda d, r: d.close()); d.present()

    def on_tab_changed(self, btn, name):
        if btn.get_active(): self.view_stack.set_visible_child_name(name)

    def on_back_clicked(self, btn):
        self.app.do_activate(); self.close()

    def on_launch_clicked(self, btn):
        if self.app_id: webbrowser.open(f"steam://launch/{self.app_id}")

    def launch(self): self.present()