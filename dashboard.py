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
import fomod_handler

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

        # 3. TOOLS TAB
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
        self.create_tools_page()  # Fixed: Calling the method to populate the tab
        
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

    def execute_inline_delete_with_meta(self, btn, f):
        """Deletes the mod zip and its associated .nomm.yaml file if it exists."""
        try:
            # Delete ZIP
            zip_path = os.path.join(self.downloads_path, f)
            if os.path.exists(zip_path):
                os.remove(zip_path)
            
            # Delete Metadata
            meta_path = zip_path + ".nomm.yaml"
            if os.path.exists(meta_path):
                os.remove(meta_path)
                
            self.create_downloads_page()
            self.update_indicators()
        except Exception as e:
            self.show_message("Error", f"Could not delete file: {e}")

    def load_game_config(self):
        config_dir = os.path.expanduser("~/nomm/game_configs")
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
            # --- ADD THIS FILTER ---
            # Ignore hidden files (starts with .) and metadata (ends with .nomm.yaml)
            if item.startswith('.') or item.lower().endswith('.nomm.yaml'):
                continue
            # -----------------------

            if dest_dir and (dest_dir / item).is_symlink():
                m_active += 1
            else:
                m_inactive += 1
        
        self.mods_inactive_label.set_text(str(m_inactive))
        self.mods_active_label.set_text(str(m_active))

        # 2. Update Downloads Stats
        d_avail, d_inst = 0, 0
        if self.downloads_path and os.path.exists(self.downloads_path):
            # This part is already correct because it filters for '.zip'
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

    def on_mod_search_changed(self, entry):
        if hasattr(self, 'mods_list_box'):
            self.mods_list_box.invalidate_filter()

    def filter_mods_rows(self, row):
        search_text = self.mod_search_entry.get_text().lower()
        if not search_text:
            return True
        # Check if the text is in the mod name we stored on the row
        return search_text in getattr(row, 'mod_name', '')

    def create_mods_page(self):
        if self.view_stack.get_child_by_name("mods"): 
            self.view_stack.remove(self.view_stack.get_child_by_name("mods"))
            
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        
        # Action Bar (Search & Folder)
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.mod_search_entry = Gtk.SearchEntry(placeholder_text="Search mods...")
        self.mod_search_entry.set_size_request(300, -1) 
        self.mod_search_entry.connect("search-changed", self.on_mod_search_changed)
        action_bar.append(self.mod_search_entry)

        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", css_classes=["flat"])
        folder_btn.set_halign(Gtk.Align.END); folder_btn.set_hexpand(True)
        folder_btn.set_cursor_from_name("pointer")
        folder_btn.connect("clicked", lambda x: webbrowser.open(f"file://{self.get_staging_path()}"))
        action_bar.append(folder_btn)
        container.append(action_bar)

        self.mods_list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.mods_list_box.set_filter_func(self.filter_mods_rows)
        
        s = self.get_staging_path()
        d = self.get_game_destination_path()
        items = os.listdir(s) if s.exists() else []
        
        for i in sorted(items, key=lambda x: os.path.getmtime(s/x), reverse=True):
            if i.lower().endswith(".nomm.yaml"):
                continue

            # --- METADATA SEARCH ---
            display_name, version_text, changelog , mod_link = i, "—", "", ""
            for meta_file in os.listdir(s):
                if meta_file.endswith(".nomm.yaml") and i in meta_file:
                    try:
                        with open(s / meta_file, 'r') as f:
                            data = yaml.safe_load(f)
                            display_name = data.get("name", i)
                            version_text = data.get("version", "—")
                            changelog = data.get("changelog", "")
                            mod_link = data.get("mod_link", "")
                        break 
                    except: pass

            # Use standard title/subtitle to keep the row height and layout stable
            row = Adw.ActionRow(title=display_name)
            if display_name != i:
                row.set_subtitle(i)
            row.mod_name = i.lower() 

            # Prefix: Switch
            sw = Gtk.Switch(active=(d/i).is_symlink() if d else False, valign=Gtk.Align.CENTER, css_classes=["green-switch"])
            sw.connect("state-set", self.on_switch_toggled, i)
            row.add_prefix(sw)

            # --- VERSION BADGE (Left-most Suffix) ---
            # Adding this first keeps it closest to the title
            version_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            version_badge.add_css_class("version-badge")
            version_badge.set_valign(Gtk.Align.CENTER)
            version_badge.set_margin_end(15) 
            
            v_label = Gtk.Label(label=version_text)
            version_badge.append(v_label)

            # --- Mod Link Badge
            if mod_link:
                mod_link_badge = Gtk.Button()
                mod_link_badge.add_css_class("flat") # Keeps it from looking like a chunky button
                mod_link_badge.add_css_class("version-badge")
                mod_link_badge.set_valign(Gtk.Align.CENTER)
                mod_link_badge.set_margin_end(15)
                mod_link_badge.set_cursor_from_name("pointer")
                
                # Create the External Link Icon
                link_icon = Gtk.Image.new_from_icon_name("external-link-symbolic")
                link_icon.set_pixel_size(14) # Matches your changelog icon size
                
                mod_link_badge.set_child(link_icon)
                mod_link_badge.connect("clicked", lambda b, l=mod_link: webbrowser.open(l))
                row.add_suffix(mod_link_badge)

            if changelog:
                version_badge.set_tooltip_text(changelog)
                q_icon = Gtk.Image.new_from_icon_name("help-about-symbolic")
                q_icon.set_pixel_size(14)
                version_badge.append(q_icon)
            
            row.add_suffix(version_badge)

            # --- OTHER SUFFIXES (Timestamp & Trash) ---
            mtime = os.path.getmtime(s/i)
            ts_label = Gtk.Label(label=datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M'), css_classes=["dim-label"], margin_end=10)
            row.add_suffix(ts_label)

            # Trash Bin Stack (Restored your specific logic)
            u_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
            bin_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
            conf_del_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
            conf_del_btn.connect("clicked", self.on_uninstall_item, i) 
            
            bin_btn.connect("clicked", lambda b, s=u_stack: [
                s.set_visible_child_name("c"), 
                GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)
            ])
            u_stack.add_named(bin_btn, "b"); u_stack.add_named(conf_del_btn, "c")
            row.add_suffix(u_stack)

            self.mods_list_box.append(row)
        
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.mods_list_box)
        container.append(sc)
        self.view_stack.add_named(container, "mods")

    def create_downloads_page(self):
        if not hasattr(self, 'view_stack'): return
        if self.view_stack.get_child_by_name("downloads"):
            self.view_stack.remove(self.view_stack.get_child_by_name("downloads"))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        
        # ... (Action Bar code remains the same)
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
        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", css_classes=["flat"])
        folder_btn.set_halign(Gtk.Align.END); folder_btn.set_hexpand(True)
        folder_btn.connect("clicked", lambda x: webbrowser.open(f"file://{self.downloads_path}"))
        action_bar.append(folder_btn)
        container.append(action_bar)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.list_box.set_filter_func(self.filter_list_rows)

        staging_path = self.get_staging_path()

        if self.downloads_path and os.path.exists(self.downloads_path):
            files = [f for f in os.listdir(self.downloads_path) if f.lower().endswith('.zip')]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.downloads_path, f)), reverse=True)

            for f in files:
                installed = self.is_mod_installed(f)
                zip_full_path = os.path.join(self.downloads_path, f)
                
                # Metadata extraction (as before)
                display_name, version_text, changelog = f, "—", ""
                meta_path = os.path.join(self.downloads_path, f + ".nomm.yaml")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r') as meta_f:
                            data = yaml.safe_load(meta_f)
                            display_name = data.get("name", f)
                            version_text = data.get("version", "—")
                            changelog = data.get("changelog", "")
                    except: pass

                row = Adw.ActionRow(title=display_name)
                row.is_installed = installed
                if display_name != f: row.set_subtitle(f)

                # --- VERSION BADGE ---
                version_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                version_badge.add_css_class("version-badge")
                version_badge.set_valign(Gtk.Align.CENTER)
                version_badge.set_margin_end(20) 
                
                v_label = Gtk.Label(label=version_text)
                version_badge.append(v_label)
                if changelog:
                    version_badge.set_tooltip_text(changelog)
                    q_icon = Gtk.Image.new_from_icon_name("help-about-symbolic")
                    q_icon.set_pixel_size(14)
                    version_badge.append(q_icon)
                
                row.add_suffix(version_badge)

                # --- TIMESTAMPS BOX ---
                ts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, margin_end=15)
                
                # Download Timestamp
                dl_ts_text = f"Downloaded: {self.get_download_timestamp(f)}"
                dl_ts = Gtk.Label(label=dl_ts_text, xalign=1, css_classes=["dim-label", "caption"])
                ts_box.append(dl_ts)

                # Installation Timestamp (Found by checking zip root folder in staging)
                if installed:
                    inst_ts_val = None
                    try:
                        with zipfile.ZipFile(zip_full_path, 'r') as z:
                            # Get the root folder/file from the zip
                            first_item = z.namelist()[0].split('/')[0]
                            target_item = staging_path / first_item
                            
                            if target_item.exists():
                                mtime = os.path.getmtime(target_item)
                                inst_ts_val = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                    except: pass

                    if inst_ts_val:
                        inst_ts = Gtk.Label(label=f"Installed: {inst_ts_val}", xalign=1, css_classes=["dim-label", "caption"])
                        ts_box.append(inst_ts)
                
                row.add_suffix(ts_box)

                # --- BUTTONS ---
                install_btn = Gtk.Button(label="Reinstall" if installed else "Install", valign=Gtk.Align.CENTER)
                if not installed: install_btn.add_css_class("suggested-action")
                install_btn.set_cursor_from_name("pointer")
                install_btn.connect("clicked", self.on_install_clicked, f)
                row.add_suffix(install_btn)

                # TRASH BIN
                d_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                b_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
                b_btn.set_cursor_from_name("pointer")
                c_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
                c_btn.connect("clicked", self.execute_inline_delete_with_meta, f)
                
                b_btn.connect("clicked", lambda b, s=d_stack: [
                    s.set_visible_child_name("c"), 
                    GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)
                ])
                d_stack.add_named(b_btn, "b"); d_stack.add_named(c_btn, "c")
                row.add_suffix(d_stack)
                
                self.list_box.append(row)

        scrolled.set_child(self.list_box)
        container.append(scrolled)
        self.view_stack.add_named(container, "downloads")

    def create_tools_page(self):
        if self.view_stack.get_child_by_name("tools"):
            self.view_stack.remove(self.view_stack.get_child_by_name("tools"))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        
        utilities_cfg = self.game_config.get("essential-utilities", {})
        
        if not utilities_cfg or not isinstance(utilities_cfg, dict):
            container.append(Gtk.Label(label="No utilities defined.", css_classes=["dim-label"]))
        else:
            list_box = Gtk.ListBox(css_classes=["boxed-list"])
            list_box.set_selection_mode(Gtk.SelectionMode.NONE)

            for util_id, util in utilities_cfg.items():
                row = Adw.ActionRow(title=util.get("name", util_id))
                
                # --- CREATOR BADGE (Prefix) ---
                creator = util.get("creator", "Unknown")
                link = util.get("creator-link", "#")
                
                creator_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                creator_box.set_valign(Gtk.Align.CENTER)
                creator_box.set_margin_end(12)
                
                creator_btn = Gtk.Button(label=creator)
                creator_btn.add_css_class("flat")
                creator_btn.add_css_class("version-badge") 
                creator_btn.set_cursor_from_name("pointer")
                creator_btn.connect("clicked", lambda b, l=link: webbrowser.open(l))
                
                creator_box.append(creator_btn)
                row.add_prefix(creator_box)

                # --- VERSION BADGE (New Suffix) ---
                # Pulls version from the yaml; defaults to "—" if missing
                util_version = util.get("version", "—")
                
                version_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                version_badge.set_valign(Gtk.Align.CENTER)
                version_badge.set_margin_end(15) # Space before the Install/Download button
                
                v_label = Gtk.Label(label=util_version)
                v_label.add_css_class("version-badge") # Applying pill style to label
                
                version_badge.append(v_label)
                row.add_suffix(version_badge)

                # --- Path & Installation Logic ---
                source = util.get("source", "")
                filename = source.split("/")[-1] if "/" in source else f"{util_id}.zip"
                util_dir = Path(self.downloads_path) / "utilities"
                local_zip_path = util_dir / filename
                target_dir = Path(self.game_path) / util.get("utility_path", "")

                is_installed = False
                if local_zip_path.exists():
                    try:
                        with zipfile.ZipFile(local_zip_path, 'r') as z:
                            is_installed = all((target_dir / name).exists() for name in z.namelist() if not name.endswith('/'))
                    except: is_installed = False

                stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
                
                dl_btn = Gtk.Button(label="Download", css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
                dl_btn.connect("clicked", self.on_utility_download_clicked, util, stack)
                
                inst_btn = Gtk.Button(label="Reinstall" if is_installed else "Install", valign=Gtk.Align.CENTER)
                if not is_installed: inst_btn.add_css_class("suggested-action")
                inst_btn.connect("clicked", self.on_utility_install_clicked, util)
                
                stack.add_named(dl_btn, "download")
                stack.add_named(inst_btn, "install")
                stack.set_visible_child_name("install" if local_zip_path.exists() else "download")
                
                row.add_suffix(stack)
                list_box.append(row)
            
            scrolled = Gtk.ScrolledWindow(vexpand=True)
            scrolled.set_child(list_box)
            container.append(scrolled)

        # --- Load Order Button ---
        load_order_rel = self.game_config.get("load_order_path")
        if load_order_rel:
            btn_container = Gtk.CenterBox(margin_top=20, margin_bottom=20)
            load_order_btn = Gtk.Button(label="Edit Load Order", css_classes=["pill"])
            load_order_btn.set_size_request(200, 40)
            load_order_btn.set_cursor_from_name("pointer")
            load_order_btn.connect("clicked", self.on_open_load_order)
            btn_container.set_center_widget(load_order_btn)
            container.append(btn_container)

        self.view_stack.add_named(container, "tools")

    def on_open_load_order(self, btn):
        load_order_rel = self.game_config.get("load_order_path")
        if not load_order_rel:
            return

        full_path = Path(self.game_path) / load_order_rel
        
        if full_path.exists():
            # file:// protocol usually triggers the default text editor for text files
            webbrowser.open(f"file://{full_path.resolve()}")
        else:
            self.show_message("Error", f"Load order file not found at:\n{full_path}")

    def on_utility_download_clicked(self, btn, util, stack):
        source_url = util.get("source")
        if not source_url: return

        util_dir = Path(self.downloads_path) / "utilities"
        util_dir.mkdir(parents=True, exist_ok=True)
        
        filename = source_url.split("/")[-1]
        target_file = util_dir / filename

        # Simple background downloader
        def download_thread():
            try:
                import urllib.request
                urllib.request.urlretrieve(source_url, target_file)
                GLib.idle_add(lambda: stack.set_visible_child_name("install"))
            except Exception as e:
                GLib.idle_add(self.show_message, "Download Failed", str(e))

        import threading
        threading.Thread(target=download_thread, daemon=True).start()

    def on_utility_install_clicked(self, btn, util):
        msg = "Warning: This process may be destructive to existing game files. Please ensure you have backed up your game directory before proceeding."
        
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Confirm Installation",
            body=msg
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install Anyway")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.DESTRUCTIVE)
        
        def on_response(d, response_id):
            if response_id == "install":
                self.execute_utility_install(util)
            d.close()

        dialog.connect("response", on_response)
        dialog.present()

    def execute_utility_install(self, util):
        try:
            source_url = util.get("source")
            filename = source_url.split("/")[-1]
            zip_path = Path(self.downloads_path) / "utilities" / filename
            
            game_root = Path(self.game_path)
            install_subpath = util.get("utility_path", "")
            target_dir = game_root / install_subpath
            target_dir.mkdir(parents=True, exist_ok=True)

            # Extract content
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(target_dir)

            # Run enable command if provided
            cmd = util.get("enable_command")
            if cmd:
                import subprocess
                subprocess.run(cmd, shell=True, cwd=game_root)

            self.show_message("Success", f"{util.get('name')} has been installed.")
        except Exception as e:
            self.show_message("Installation Error", str(e))


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
            staging_path = self.get_staging_path()
            zip_full_path = os.path.join(self.downloads_path, filename)
            
            with zipfile.ZipFile(zip_full_path, 'r') as z:
                # 1. Case-insensitive check for fomod/ModuleConfig.xml
                all_files = z.namelist()
                fomod_xml_path = next((f for f in all_files if f.lower().endswith("fomod/moduleconfig.xml")), None)

                if fomod_xml_path:
                    xml_data = z.read(fomod_xml_path)
                    # Proceed with your FOMOD logic...
                    module_name, options = fomod_handler.parse_fomod_xml(xml_data)
                    
                    if options:
                        dialog = fomod_handler.FomodSelectionDialog(self, module_name, options)
                        # We pass the filename to the response handler so it knows which ZIP to finish extracting
                        dialog.connect("response", self.on_fomod_dialog_response, zip_full_path, filename)
                        dialog.present()
                        return

                # 2. Standard Installation (If not FOMOD or parsing failed)
                z.extractall(staging_path)
                # Use the first folder in zip as the root name for metadata
                extracted_root = z.namelist()[0].split('/')[0]
                self.post_install_actions(filename, extracted_root)

        except Exception as e:
            self.show_message("Error", f"Installation failed: {e}")

    def on_fomod_dialog_response(self, dialog, response, zip_path, filename):
        if response == Gtk.ResponseType.OK:
            source_folder_name = dialog.get_selected_source()
            if source_folder_name:
                staging_path = self.get_staging_path()
                
                with zipfile.ZipFile(zip_path, 'r') as z:
                    all_files = z.namelist()
                    
                    # 1. Find where the source_folder actually lives in the ZIP
                    # We look for a directory entry that ends with our source_folder name
                    actual_prefix = None
                    for f in all_files:
                        if f.endswith(f"{source_folder_name}/"):
                            actual_prefix = f
                            break
                    
                    # Fallback: if no directory entry, look for files contained within it
                    if not actual_prefix:
                        for f in all_files:
                            if f"/{source_folder_name}/" in f or f.startswith(f"{source_folder_name}/"):
                                actual_prefix = f.split(source_folder_name)[0] + source_folder_name + "/"
                                break

                    if actual_prefix:
                        for member in all_files:
                            if member.startswith(actual_prefix) and not member.endswith('/'):
                                # 2. Flatten the path: 
                                # Remove the prefix so it extracts directly into staging
                                arcname = os.path.relpath(member, actual_prefix)
                                target_path = os.path.join(staging_path, source_folder_name, arcname)
                                
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                with z.open(member) as source_file, open(target_path, "wb") as target_file:
                                    shutil.copyfileobj(source_file, target_file)
                        
                        self.post_install_actions(filename, source_folder_name)
                    else:
                        print(f"Could not find {source_folder_name} inside the ZIP.")

        dialog.destroy()

    def post_install_actions(self, filename, extracted_root):
        """Standardized cleanup for all installation types"""
        meta_source = os.path.join(self.downloads_path, filename + ".nomm.yaml")
        if os.path.exists(meta_source):
            meta_dest = os.path.join(self.get_staging_path(), f".{extracted_root}.nomm.yaml")
            shutil.copy2(meta_source, meta_dest)

        self.create_downloads_page()
        self.create_mods_page()
        self.update_indicators()

    def on_uninstall_item(self, btn, item_name):
        try:
            dest = self.get_game_destination_path()
            staging_path = self.get_staging_path()
            
            # Remove symlink from game folder
            if dest and (dest / item_name).is_symlink(): 
                (dest / item_name).unlink()
            
            # Remove the actual files from staging
            path = staging_path / item_name
            if path.exists():
                if path.is_dir(): shutil.rmtree(path)
                else: path.unlink()
            
            # --- NEW: Cleanup corresponding metadata if it exists ---
            # We look for any .nomm.yaml files that might be associated with this item
            # (Note: This assumes the item_name matches the base of the zip)
            for meta_file in staging_path.glob("*.nomm.yaml"):
                # If you want to be precise, you'd need to track which zip created which files
                # For now, this is a placeholder check
                pass

            self.create_mods_page()
            self.create_downloads_page()
            self.update_indicators()
        except Exception as e: 
            self.show_message("Error", str(e))

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