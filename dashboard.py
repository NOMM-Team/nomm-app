import os
import gi
import yaml
import shutil
import zipfile
import webbrowser
import re
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
        self.active_tab = "mods"
        
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

        # --- TAB BUTTONS WITH INTEGRATED BADGES ---
        tab_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=False)
        main_tabs_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True, hexpand=True)

        # 1. MODS TAB OVERLAY
        mods_tab_overlay = Gtk.Overlay()
        self.mods_tab_btn = Gtk.ToggleButton(label="MODS", css_classes=["overlay-tab"])
        self.mods_tab_btn.set_cursor_from_name("pointer")
        
        mods_badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mods_badge_box.set_halign(Gtk.Align.END)
        mods_badge_box.set_valign(Gtk.Align.END)
        mods_badge_box.set_margin_bottom(8); mods_badge_box.set_margin_end(8)
        
        self.mods_inactive_label = Gtk.Label(label="0", css_classes=["badge-green"])
        self.mods_active_label = Gtk.Label(label="0", css_classes=["badge-grey"])
        mods_badge_box.append(self.mods_inactive_label)
        mods_badge_box.append(self.mods_active_label)
        
        mods_tab_overlay.set_child(self.mods_tab_btn)
        mods_tab_overlay.add_overlay(mods_badge_box)
        main_tabs_box.append(mods_tab_overlay)

        # 2. DOWNLOADS TAB OVERLAY
        dl_tab_overlay = Gtk.Overlay()
        self.dl_tab_btn = Gtk.ToggleButton(label="DOWNLOADS", css_classes=["overlay-tab"])
        self.dl_tab_btn.set_cursor_from_name("pointer")
        
        dl_badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        dl_badge_box.set_halign(Gtk.Align.END)
        dl_badge_box.set_valign(Gtk.Align.END)
        dl_badge_box.set_margin_bottom(8); dl_badge_box.set_margin_end(8)
        
        self.dl_avail_label = Gtk.Label(label="0", css_classes=["badge-green"])
        self.dl_inst_label = Gtk.Label(label="0", css_classes=["badge-grey"])
        dl_badge_box.append(self.dl_avail_label)
        dl_badge_box.append(self.dl_inst_label)
        
        dl_tab_overlay.set_child(self.dl_tab_btn)
        dl_tab_overlay.add_overlay(dl_badge_box)
        main_tabs_box.append(dl_tab_overlay)

        tab_container.append(main_tabs_box)

        # 3. TOOLS TAB (Square wrench tab with large icon)
        self.tools_tab_btn = Gtk.ToggleButton(css_classes=["overlay-tab"])
        # Creating a dedicated Image widget to control icon size (48px)
        wrench_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        wrench_icon.set_pixel_size(48) 
        self.tools_tab_btn.set_child(wrench_icon)
        
        self.tools_tab_btn.set_size_request(banner_height, banner_height)
        self.tools_tab_btn.set_cursor_from_name("pointer")
        tab_container.append(self.tools_tab_btn)

        # Grouping toggles
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
        
        self.create_mods_page()
        self.create_downloads_page()
        
        self.tools_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.view_stack.add_named(self.tools_page, "tools")
        
        self.update_indicators()

        footer = Gtk.CenterBox(margin_start=40, margin_end=40, margin_top=20, margin_bottom=40)
        back_btn = Gtk.Button(label="Change Game", css_classes=["flat"])
        back_btn.set_cursor_from_name("pointer")
        back_btn.connect("clicked", self.on_back_clicked)
        footer.set_start_widget(back_btn)
        
        launch_btn = Gtk.Button(label="Launch Game", css_classes=["suggested-action"])
        launch_btn.set_size_request(240, 64)
        launch_btn.set_cursor_from_name("pointer")
        launch_btn.connect("clicked", self.on_launch_clicked)
        footer.set_end_widget(launch_btn)

        main_layout.append(footer)
        self.set_content(main_layout)

    def load_game_config(self):
        config_dir = "./game_configs/"
        def slug(text): return re.sub(r'[^a-z0-9]', '', text.lower())
        target = slug(self.game_name)
        if os.path.exists(config_dir):
            for filename in os.listdir(config_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    with open(os.path.join(config_dir, filename), 'r') as f:
                        data = yaml.safe_load(f) or {}
                        if slug(data.get("name", "")) == target: return data
        return {}

    def get_staging_path(self):
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
        
        path = nomm_root / self.game_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_game_destination_path(self):
        game_path = self.game_config.get("game_path")
        mods_subfolder = self.game_config.get("mods_path", "")
        if not game_path: return None
        dest = Path(game_path) / mods_subfolder
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def update_indicators(self):
        # 1. Update Mods Stats
        m_inactive, m_active = 0, 0
        staging_dir = self.get_staging_path()
        dest_dir = self.get_game_destination_path()
        m_items = os.listdir(staging_dir) if staging_dir.exists() else []
        for item in m_items:
            if dest_dir and (dest_dir / item).is_symlink():
                m_active += 1
            else:
                m_inactive += 1
        self.mods_inactive_label.set_text(str(m_inactive))
        self.mods_active_label.set_text(str(m_active))

        # 2. Update Downloads Stats
        d_avail, d_inst = 0, 0
        if self.downloads_path and os.path.exists(self.downloads_path):
            zips = [f for f in os.listdir(self.downloads_path) if f.lower().endswith('.zip')]
            for f in zips:
                if self.is_mod_installed(f):
                    d_inst += 1
                else:
                    d_avail += 1
        self.dl_avail_label.set_text(str(d_avail))
        self.dl_inst_label.set_text(str(d_inst))

    def filter_list_rows(self, row):
        if self.current_filter == "all": return True
        if hasattr(row, 'is_installed'):
            if self.current_filter == "installed": return row.is_installed
            if self.current_filter == "uninstalled": return not row.is_installed
        return True

    def create_mods_page(self):
        if self.view_stack.get_child_by_name("mods"):
            self.view_stack.remove(self.view_stack.get_child_by_name("mods"))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        staging_dir = self.get_staging_path()
        dest_dir = self.get_game_destination_path()
        items = os.listdir(staging_dir) if staging_dir.exists() else []

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.mods_list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.mods_list_box.set_selection_mode(Gtk.SelectionMode.NONE)

        if items:
            items.sort(key=lambda x: os.path.getmtime(staging_dir / x), reverse=True)
            for item in items:
                row = Adw.ActionRow(title=item)
                is_enabled = (dest_dir / item).is_symlink() if dest_dir else False
                sw = Gtk.Switch(active=is_enabled, valign=Gtk.Align.CENTER, css_classes=["green-switch"])
                sw.connect("state-set", self.on_switch_toggled, item)
                row.add_prefix(sw)

                ts = datetime.fromtimestamp(os.path.getmtime(staging_dir / item)).strftime('%Y-%m-%d %H:%M')
                row.add_suffix(Gtk.Label(label=f"Installed: {ts}", margin_end=20))

                stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                b_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
                c_btn = Gtk.Button(label="Confirm Uninstall?", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
                c_btn.connect("clicked", self.on_uninstall_item, item)
                b_btn.connect("clicked", lambda b, s=stack: [s.set_visible_child_name("c"), GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)])
                stack.add_named(b_btn, "b"); stack.add_named(c_btn, "c")
                row.add_suffix(stack)
                self.mods_list_box.append(row)

        scrolled.set_child(self.mods_list_box)
        container.append(scrolled)
        self.view_stack.add_named(container, "mods")

    def create_downloads_page(self):
        if not hasattr(self, 'view_stack'): return
        if self.view_stack.get_child_by_name("downloads"):
            self.view_stack.remove(self.view_stack.get_child_by_name("downloads"))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        filter_group = Gtk.Box(css_classes=["linked"])
        self.all_filter_btn = Gtk.ToggleButton(label="All", active=True)
        self.all_filter_btn.connect("toggled", self.on_filter_toggled, "all")
        filter_group.append(self.all_filter_btn)
        for n, l in [("uninstalled", "Uninstalled"), ("installed", "Installed")]:
            b = Gtk.ToggleButton(label=l, group=self.all_filter_btn)
            b.connect("toggled", self.on_filter_toggled, n)
            filter_group.append(b)
        action_bar.append(filter_group)
        container.append(action_bar)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.list_box.set_filter_func(self.filter_list_rows)

        if self.downloads_path and os.path.exists(self.downloads_path):
            files = [f for f in os.listdir(self.downloads_path) if f.lower().endswith('.zip')]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.downloads_path, f)), reverse=True)

            for f in files:
                installed = self.is_mod_installed(f)
                row = Adw.ActionRow(title=f)
                row.is_installed = installed
                row.add_suffix(Gtk.Label(label=f"Downloaded: {self.get_download_timestamp(f)}", margin_end=20))
                row.add_suffix(Gtk.Label(label=f"Installed: {self.get_install_timestamp_from_zip(f) if installed else '—'}", margin_end=20))
                
                i_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                main_i_btn = Gtk.Button(label="Reinstall" if installed else "Install", valign=Gtk.Align.CENTER)
                if not installed: main_i_btn.add_css_class("suggested-action")
                conf_i_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
                conf_i_btn.connect("clicked", self.on_install_clicked, f)
                main_i_btn.connect("clicked", lambda b, s=i_stack: [s.set_visible_child_name("c"), GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("m") or False)])
                i_stack.add_named(main_i_btn, "m"); i_stack.add_named(conf_i_btn, "c")
                row.add_suffix(i_stack)

                d_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                b_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
                c_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
                c_btn.connect("clicked", self.execute_inline_delete, f)
                b_btn.connect("clicked", lambda b, s=d_stack: [s.set_visible_child_name("c"), GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)])
                d_stack.add_named(b_btn, "b"); d_stack.add_named(c_btn, "c")
                row.add_suffix(d_stack)
                self.list_box.append(row)

        scrolled.set_child(self.list_box)
        container.append(scrolled)
        self.view_stack.add_named(container, "downloads")

    def setup_custom_styles(self):
        css = """
        .badge-green { background-color: #26a269; color: white; border-radius: 6px; padding: 2px 10px; font-weight: bold; }
        .badge-grey { background-color: #333333; color: white; border-radius: 6px; padding: 2px 10px; font-weight: bold; }
        switch.green-switch:checked { background-color: #26a269; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, 800)

    def on_switch_toggled(self, switch, state, item_name):
        staging_item = self.get_staging_path() / item_name
        dest_dir = self.get_game_destination_path()
        if not dest_dir: return False
        link_path = dest_dir / item_name
        if state:
            if not link_path.exists():
                try: os.symlink(staging_item, link_path)
                except: switch.set_active(False)
        else:
            if link_path.is_symlink():
                try: link_path.unlink()
                except: switch.set_active(True)
        self.update_indicators()
        return False

    def on_install_clicked(self, btn, filename):
        try:
            with zipfile.ZipFile(os.path.join(self.downloads_path, filename), 'r') as z:
                z.extractall(self.get_staging_path())
            self.create_downloads_page(); self.create_mods_page(); self.update_indicators()
        except Exception as e: self.show_message("Error", str(e))

    def on_uninstall_item(self, btn, item_name):
        try:
            dest = self.get_game_destination_path()
            if dest and (dest / item_name).is_symlink(): (dest / item_name).unlink()
            path = self.get_staging_path() / item_name
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
            self.create_mods_page(); self.create_downloads_page(); self.update_indicators()
        except Exception as e: self.show_message("Error", str(e))

    def execute_inline_delete(self, btn, f):
        try:
            os.remove(os.path.join(self.downloads_path, f))
            self.create_downloads_page(); self.update_indicators()
        except: pass

    def is_mod_installed(self, zip_filename):
        staging = self.get_staging_path()
        try:
            with zipfile.ZipFile(os.path.join(self.downloads_path, zip_filename), 'r') as z:
                return all((staging / x).exists() for x in z.namelist() if not x.endswith('/'))
        except: return False

    def get_download_timestamp(self, f):
        return datetime.fromtimestamp(os.path.getmtime(os.path.join(self.downloads_path, f))).strftime('%Y-%m-%d %H:%M')

    def get_install_timestamp_from_zip(self, zip_filename):
        try:
            with zipfile.ZipFile(os.path.join(self.downloads_path, zip_filename), 'r') as z:
                files = [x for x in z.namelist() if not x.endswith('/')]
                if files: return datetime.fromtimestamp((self.get_staging_path() / files[0]).stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        except: pass
        return "—"

    def setup_folder_monitor(self):
        f = Gio.File.new_for_path(self.downloads_path)
        self.monitor = f.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", lambda m, f, of, et: self.create_downloads_page() or self.update_indicators() if et in [Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED] else None)

    def on_filter_toggled(self, btn, f_name):
        if btn.get_active():
            self.current_filter = f_name
            if hasattr(self, 'list_box'): self.list_box.invalidate_filter()

    def find_hero_image(self, steam_base, app_id):
        if not steam_base or not app_id: return None
        cache_dir = os.path.join(steam_base, "appcache", "librarycache")
        targets = [f"{app_id}_library_hero.jpg", "library_hero.jpg"]
        for name in targets:
            path = os.path.join(cache_dir, name)
            if os.path.exists(path): return path
        appid_dir = os.path.join(cache_dir, str(app_id))
        if os.path.exists(appid_dir):
            for root, _, files in os.walk(appid_dir):
                if "library_hero.jpg" in files: return os.path.join(root, "library_hero.jpg")
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
        if btn.get_active(): 
            self.active_tab = name
            self.view_stack.set_visible_child_name(name)
            self.update_indicators()

    def on_back_clicked(self, btn):
        self.app.do_activate(); self.close()

    def on_launch_clicked(self, btn):
        if self.app_id: webbrowser.open(f"steam://launch/{self.app_id}")

    def launch(self): self.present()