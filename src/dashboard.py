#Global imports
import os, yaml, shutil, zipfile, webbrowser, re, requests, fomod_handler, gi, rarfile

#Specific imports
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, Pango
from pathlib import Path
from datetime import datetime
from utils import download_heroic_assets

# Point rarfile to the bundled binary
rarfile.UNRAR_TOOL = "/app/bin/unrar"

class GameDashboard(Adw.Window):
    def __init__(self, game_name, game_path, application, steam_base=None, app_id=None, user_config_path=None, game_config_path=None, **kwargs):
        super().__init__(application=application, **kwargs)
        self.app = application
        self.game_name = game_name
        self.game_path = game_path
        self.app_id = app_id
        self.user_config_path = user_config_path
        self.game_config_path = game_config_path
        self.current_filter = "all" # default filter is all
        self.active_tab = "mods" # default tab is mods

        self.game_config = self.load_game_config()
        self.user_config = self.load_user_config()
        self.downloads_path = self.game_config.get("downloads_path")
        self.staging_path = Path(os.path.join(Path(self.user_config.get("staging_path")), game_name))
        self.platform = self.game_config.get("platform")
        
        self.staging_metadata_path = os.path.join(self.staging_path, ".staging.nomm.yaml")
        self.downloads_metadata_path = os.path.join(self.downloads_path, ".downloads.nomm.yaml")

        self.parse_deployment_paths() # parse the deployment paths

        self.headers = {
            'apikey': self.user_config["nexus_api_key"],
            'Application-Name': 'Nomm',
            'Application-Version': '0.5.0'
        }

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

        # Either get images from nomm cache (for gog and epic) or steam cache (for steam. duh.)
        if self.platform == "steam":
            hero_path = self.find_hero_image(steam_base, app_id)
        elif self.platform == "heroic-gog" or self.platform == "heroic-epic":
            image_paths = download_heroic_assets(app_id, self.platform)
            hero_path = image_paths["art_hero"]

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
        
        self.mods_inactive_label = Gtk.Label(label="0", css_classes=["badge-accent"])
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
        
        self.dl_avail_label = Gtk.Label(label="0", css_classes=["badge-accent"])
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

    def delete_download_package(self, btn, file_name):
        """Deletes the mod zip and associated data in downloads.nomm.yaml file if it exists."""
        try:
            # Delete ZIP
            zip_path = os.path.join(self.downloads_path, file_name)
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception as e:
            self.show_message("Error", f"Could not delete file: {e}")

        try:
            # Delete Metadata (if it exists)
            downloads_metadata = self.load_downloads_metadata()
            if downloads_metadata:
                if file_name in downloads_metadata["mods"]:
                    del downloads_metadata["mods"][file_name]
                    self.write_metadata(downloads_metadata, self.downloads_metadata_path)
        except Exception as e:
            self.show_message("Error", f"Could not delete metadata for file: {e}")

        self.create_downloads_page()
        self.update_indicators()

    def load_downloads_metadata(self):
        if not os.path.exists(self.downloads_metadata_path):
            return None
        with open(self.downloads_metadata_path, 'r') as f:
            return yaml.safe_load(f)

    def load_staging_metadata(self):
        if not os.path.exists(self.staging_metadata_path):
            return None
        with open(self.staging_metadata_path, 'r') as f:
            return yaml.safe_load(f)

    def write_metadata(self, metadata, metadata_path):
        if not os.path.exists(metadata_path):
            return
        with open(metadata_path, 'w') as f:
            return yaml.safe_dump(metadata, f)

    def load_user_config(self):
        # TODO: Homogenise this config load with one in launcher.py and probably load_game_config
        if os.path.exists(self.user_config_path):
            try:
                with open(self.user_config_path, 'r') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Error loading config: {e}")
                return {}
        return {}

    def get_current_game_config_path(self, game_config_path):
        #TODO: merge with below
        def slug(text): return re.sub(r'[^a-z0-9]', '', text.lower())
        target = slug(self.game_name)
        if os.path.exists(game_config_path):
            for filename in os.listdir(game_config_path):
                if filename.lower().endswith((".yaml")):
                    with open(os.path.join(game_config_path, filename), 'r') as f:
                        data = yaml.safe_load(f) or {}
                        if slug(data.get("name", "")) == target:
                            current_game_config_path = game_config_path + '/' + filename
                            return current_game_config_path

    def load_game_config(self):
        #TODO: merge this method and move to utils
        config_dir = self.game_config_path
        def slug(text): return re.sub(r'[^a-z0-9]', '', text.lower())
        target = slug(self.game_name)
        if os.path.exists(config_dir):
            for filename in os.listdir(config_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    with open(os.path.join(config_dir, filename), 'r') as f:
                        data = yaml.safe_load(f) or {}
                        if slug(data.get("name", "")) == target: return data
        return {}

    def get_mod_deployment_paths(self):
        game_path = self.game_config.get("game_path")
        mod_install_path_dicts = self.game_config.get("mods_path", "")
        if not game_path:
            return None
        if self.platform == "steam":
            user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(self.app_id) + "/pfx"
        elif self.platform == "heroic-gog" or self.platform == "heroic-gog":
            #TODO: implement support for heroic user data files
            print("user data folder not supported yet for heroic installations")

        if not isinstance(mod_install_path_dicts, list):
            mod_install_path_dicts = [{
                "name": "Default",
                "path": mod_install_paths}]
        
        for mod_install_path_dict in mod_install_path_dicts:
            deployment_path = mod_install_path_dict["path"]
            if "}" not in deployment_path: # if this is the nomm 0.5 format
                deployment_path = Path(game_path) / deployment_path
            else: # if this is in the nomm 0.6 format
                deployment_path = deployment_path.replace("{game_path}", game_path)
                deployment_path = deployment_path.replace("{user_data_path}", user_data_path)
            mod_install_path_dict["path"] = deployment_path
            Path(deployment_path).mkdir(parents=True, exist_ok=True)
        
        return mod_install_path_dicts

    def parse_deployment_paths(self):
        '''Parse game paths from {xxx} to proper paths'''
        game_path = self.game_config.get("game_path")
        deployment_dicts = self.game_config.get("mods_path", "")

        if not game_path:
            return

        if self.platform == "steam":
            user_data_path = os.path.dirname(os.path.dirname(game_path)) + "/compatdata/" + str(self.app_id) + "/pfx"
        elif self.platform == "heroic-gog" or self.platform == "heroic-gog":
            #TODO: implement support for heroic user data files
            print("user data folder not supported yet for heroic installations")
            return
        else:
            print("unrecognised platform")
            return

        # handle case where there is only one path provided, and it's not a list of dicts
        if not isinstance(deployment_dicts, list):
            deployment_dicts = [{
                "name": "default",
                "path": deployment_dicts}]
        
        # parse the paths
        for deployment_dict in deployment_dicts:
            deployment_path = deployment_dict["path"]
            if "}" not in deployment_path: # if this is the nomm 0.5 format
                deployment_path = game_path + "/" + deployment_path
            else: # if this is in the nomm 0.6 format
                deployment_path = deployment_path.replace("{game_path}", game_path)
                deployment_path = deployment_path.replace("{user_data_path}", user_data_path)
            deployment_dict["path"] = deployment_path
        
        self.deployment_targets = deployment_dicts


    def update_indicators(self):
        # Update Mods Stats
        mods_inactive, mods_active = 0, 0
        staging_dir = self.staging_path
        staging_metadata = self.load_staging_metadata()
        if staging_metadata:
            for mod in staging_metadata["mods"]:
                if staging_metadata["mods"][mod]["status"] == "enabled":
                    mods_active += 1
                elif staging_metadata["mods"][mod]["status"] == "disabled":
                    mods_inactive += 1
        
        self.mods_inactive_label.set_text(str(mods_inactive))
        self.mods_active_label.set_text(str(mods_active))

        # Update Downloads Stats
        d_avail, d_inst = 0, 0
        if self.downloads_path and os.path.exists(self.downloads_path):
            archives = [f for f in os.listdir(self.downloads_path) if f.lower().endswith('.zip') or f.lower().endswith('.rar') or f.lower().endswith('.7z')]
            for f in archives:
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

    def check_for_updates(self, btn):
        staging_metadata = self.load_staging_metadata()
        if not staging_metadata: return

        game_id = staging_metadata.get("info", {}).get("nexus_game_id")
        if not game_id: return

        mods_updated = False

        for mod_name, details in staging_metadata["mods"].items():
            mod_id = details.get("mod_id")
            local_version = str(details.get("version", ""))
            if not mod_id: continue

            try:
                # 1. Check for new version
                mod_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}.json"
                resp = requests.get(mod_url, headers=self.headers, timeout=10)
                
                if resp.status_code == 200:
                    remote_data = resp.json()
                    remote_version = str(remote_data.get("version", ""))

                    if remote_version and remote_version != local_version:
                        
                        details["new_version"] = remote_version
                        mods_updated = True

                        # 2. If the versions are different, fetch the latest changelog
                        changelog_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}/changelogs.json"
                        changelog_resp = requests.get(changelog_url, headers=self.headers, timeout=10)
                        
                        if changelog_resp.status_code == 200:
                            logs = changelog_resp.json()
                            # Nexus returns a dict where keys are version numbers
                            # We grab the log for the specific remote version found
                            new_log = logs.get(remote_version)
                            if new_log:
                                # Join list of changes into a single string if necessary
                                details["changelog"] = "\n".join(new_log) if isinstance(new_log, list) else new_log

            except Exception as e:
                print(f"Error checking {mod_name}: {e}")

        # 3. Save only if changes were actually made
        if mods_updated:
            self.write_metadata(staging_metadata, self.staging_metadata_path)
            print("Metadata updated with new version info and changelogs.")
            self.create_mods_page()

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

        # add the folder button
        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", css_classes=["flat"])
        folder_btn.set_halign(Gtk.Align.END); folder_btn.set_hexpand(True)
        folder_btn.set_cursor_from_name("pointer")
        folder_btn.connect("clicked", lambda x: webbrowser.open(f"file://{self.staging_path}"))
        action_bar.append(folder_btn)

        # add the update button
        update_btn = Gtk.Button(icon_name="view-refresh-symbolic", css_classes=["flat"])
        update_btn.set_halign(Gtk.Align.END);
        update_btn.set_cursor_from_name("pointer")
        update_btn.connect("clicked", self.check_for_updates)
        action_bar.append(update_btn)

        # add the action bar
        container.append(action_bar)

        self.mods_list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.mods_list_box.set_filter_func(self.filter_mods_rows)
        
        staging_path = self.staging_path
        
        staging_metadata = self.load_staging_metadata()
        if not staging_metadata:
            container.append(Gtk.Label(label="The staging metadata file could not be found, did you install any mods?", css_classes=["dim-label"]))
            staging_metadata = {}
            staging_metadata["mods"] = {}
        
        for mod in sorted(staging_metadata["mods"]):
            display_name = mod
            mod_metadata = staging_metadata["mods"][mod]

            # load the metadata from the file
            version_text = mod_metadata.get("version", "—")
            new_version = mod_metadata.get("new_version", "")
            changelog = mod_metadata.get("changelog", "")
            mod_link = mod_metadata.get("mod_link", "")
            mod_files = mod_metadata.get("mod_files", "")

            # Use standard title/subtitle to keep the row height and layout stable
            row = Adw.ActionRow(title=display_name)
            if len(mod_files) == 1:
                row.set_subtitle(mod_files[0])
            row.mod_name = display_name.lower()

            row_element_margin = 10

            # Prefix: Enable Switch
            mod_toggle_switch = Gtk.Switch(active=True if "enabled_timestamp" in mod_metadata else False, valign=Gtk.Align.CENTER, css_classes=["accent-switch"])
            mod_toggle_switch.connect("state-set", self.on_mod_toggled, mod_files, mod)
            row.add_prefix(mod_toggle_switch)

            # Prefix: # of files
            number_of_files = len(mod_files)
            if number_of_files > 1:
                file_list_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                file_list_badge.set_tooltip_text("\n".join(mod_files))
                file_list_badge.add_css_class("badge-action-row")
                file_list_badge.set_valign(Gtk.Align.CENTER)
                file_list_badge.set_margin_end(row_element_margin)
                file_list_badge.append(Gtk.Label(label=f"{number_of_files} file(s)"))
                row.add_prefix(file_list_badge)

            # Prefix: Missing Files
            missing_files = []
            for mod_file in mod_files:    
                if not os.path.exists(staging_path/display_name/mod_file):
                    missing_files.append(mod_file)
            if missing_files:
                missing_file_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                missing_file_badge.add_css_class("warning-badge")
                missing_file_badge.set_valign(Gtk.Align.CENTER)
                missing_file_badge.set_margin_end(row_element_margin)
                missing_file_badge.set_tooltip_text("Missing Files:\n"+"\n".join(missing_files))
                missing_file_badge.append(Gtk.Label(label=f"Missing {len(missing_files)} file(s)"))
                row.add_prefix(missing_file_badge)

            # --- Suffixes
            # Deployment target badge
            if len(self.deployment_targets) > 1 and "deployment_target" in mod_metadata:
                deployment_badge = Gtk.Button()
                button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                button_content.append(Gtk.Label(label=mod_metadata["deployment_target"]))
                deployment_badge.add_css_class("badge-action-row")
                for deployment_target in self.deployment_targets:
                    if deployment_target["name"] == mod_metadata["deployment_target"]:
                        deployment_path = deployment_target["path"]
                        deployment_description = deployment_target["description"]
                tooltip_text = deployment_path + "\n\n" + deployment_description
                deployment_badge.set_tooltip_text(tooltip_text)
                deployment_badge.set_child(button_content)
                deployment_badge.set_valign(Gtk.Align.CENTER)
                deployment_badge.set_margin_end(row_element_margin)
                row.add_suffix(deployment_badge)

            # Version badge
            version_badge = Gtk.Button()
            button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            button_content.append(Gtk.Label(label=version_text))

            if changelog:
                version_badge.set_tooltip_text(changelog)
                q_icon = Gtk.Image.new_from_icon_name("help-about-symbolic")
                q_icon.set_pixel_size(14)
                button_content.append(q_icon)
            
            version_badge.set_child(button_content)

            if new_version and new_version != version_text:
                version_badge.add_css_class("badge-action-row-accent")
            else:
                version_badge.add_css_class("badge-action-row")
            
            version_badge.set_cursor_from_name("pointer")
            version_badge.set_valign(Gtk.Align.CENTER)
            version_badge.set_margin_end(row_element_margin)

            if mod_link: # add mod link to the version badges
                version_badge.connect("clicked", lambda b, l=mod_link: webbrowser.open(l))
            
            row.add_suffix(version_badge)

            # Timestamps
            if "install_timestamp" in mod_metadata or "enabled_timestamp" in mod_metadata:
                timestamp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, margin_end=15)
                # Enabled Timestamp
                if "enabled_timestamp" in mod_metadata:
                    enabled_timestamp = Gtk.Label(label=f"Enabled: {mod_metadata["enabled_timestamp"]}", xalign=1, css_classes=["dim-label", "caption"])
                    timestamp_box.append(enabled_timestamp)

                # Installed Timestamp
                if "install_timestamp" in mod_metadata:
                    installed_timestamp = Gtk.Label(label=f"Installed: {mod_metadata["install_timestamp"]}", xalign=1, css_classes=["dim-label", "caption"])
                    timestamp_box.append(installed_timestamp)
                
                row.add_suffix(timestamp_box)

            # Trash Bin Stack
            u_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
            bin_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
            conf_del_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
            conf_del_btn.connect("clicked", self.on_uninstall_item, mod_files, mod)
            
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

        staging_path = self.staging_path

        if self.downloads_path and os.path.exists(self.downloads_path):
            files = [f for f in os.listdir(self.downloads_path) if f.lower().endswith('.zip') or f.lower().endswith('.rar') or f.lower().endswith('.7z')]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.downloads_path, f)), reverse=True)

            for file_name in files:
                installed = self.is_mod_installed(file_name)
                archive_full_path = os.path.join(self.downloads_path, file_name)
                
                # New Metadata extraction
                display_name, version_text, changelog = file_name, "—", ""
                meta_path = self.downloads_metadata_path
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r') as meta_f:
                            metadata = yaml.safe_load(meta_f)
                            display_name = metadata["mods"][file_name].get("name", file_name)
                            version_text = metadata["mods"][file_name].get("version", "—")
                            changelog = metadata["mods"][file_name].get("changelog", "")
                    except: pass

                row = Adw.ActionRow(title=display_name)
                row.is_installed = installed
                if display_name != file_name: row.set_subtitle(file_name)

                # --- VERSION BADGE ---
                version_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                version_badge.add_css_class("badge-action-row")
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
                dl_ts_text = f"Downloaded: {self.get_download_timestamp(file_name)}"
                dl_ts = Gtk.Label(label=dl_ts_text, xalign=1, css_classes=["dim-label", "caption"])
                ts_box.append(dl_ts)

                # Installation Timestamp (Found by checking staging metadata)
                if installed:
                    installation_timestamp_value = None
                    staging_metadata = self.load_staging_metadata()
                    for mods in staging_metadata["mods"]:
                        if "archive_name" in staging_metadata["mods"][mods] and staging_metadata["mods"][mods]["archive_name"] == file_name:
                            installation_timestamp_value = staging_metadata["mods"][mods]["install_timestamp"]

                    if installation_timestamp_value:
                        installation_timestamp_badge = Gtk.Label(label=f"Installed: {installation_timestamp_value}", xalign=1, css_classes=["dim-label", "caption"])
                        ts_box.append(installation_timestamp_badge)
                
                row.add_suffix(ts_box)

                # --- BUTTONS ---
                install_btn = Gtk.Button(label="Reinstall" if installed else "Install", valign=Gtk.Align.CENTER)
                if not installed: install_btn.add_css_class("suggested-action")
                install_btn.set_cursor_from_name("pointer")
                install_btn.connect("clicked", self.on_install_clicked, file_name, display_name)
                row.add_suffix(install_btn)

                # TRASH BIN
                d_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                b_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
                b_btn.set_cursor_from_name("pointer")
                c_btn = Gtk.Button(label="Are you sure?", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
                c_btn.connect("clicked", self.delete_download_package, file_name)
                
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
                creator_btn.add_css_class("badge-action-row") 
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
                v_label.add_css_class("badge-action-row") # Applying pill style to label
                
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

            whitelist = util.get("whitelist", [])
            blacklist = util.get("blacklist", [])

            # Filtering blacklisted files and whitelisted words
            with zipfile.ZipFile(zip_path, 'r') as z:
                # Small optimization to avoid loading RAM with the file
                if not whitelist and not blacklist:
                    z.extractall(target_dir)
                else:
                    for file_info in z.infolist():
                        file_name = file_info.filename

                        if whitelist and not any(allowed in file_name for allowed in whitelist):
                            continue

                        if blacklist and any(blocked in file_name for blocked in blacklist):
                            continue

                        # Extracting file_info.filename that are either (1) whitelisted (2) not blacklisted
                        z.extract(file_info, target_dir)

            # Run enable command if provided
            cmd = util.get("enable_command")
            if cmd:
                import subprocess
                subprocess.run(cmd, shell=True, cwd=game_root)

            self.show_message("Success", f"{util.get('name')} has been installed.")
        except Exception as e:
            self.show_message("Installation Error", str(e))

    def on_mod_toggled(self, switch, state, mod_files: list, mod: str):
        '''User clicked the toggle on the mods page: need to either enable or disable the mod'''
        deployment_targets = self.deployment_targets
        staging_metadata = self.load_staging_metadata()

        if not deployment_targets or not staging_metadata:
            return False

        if not "deployment_target" in staging_metadata["mods"][mod]:
            dest_dir = deployment_targets[0]["path"]
        else:
            for deployment_target in deployment_targets:
                if deployment_target["name"] == staging_metadata["mods"][mod]["deployment_target"]:
                    dest_dir = deployment_target["path"]

        # deploy the files
        for mod_file in mod_files:
            staging_item = self.staging_path / mod / mod_file # staging path / mod name / actual mod file
            link_path = Path(dest_dir) / mod_file

            # check path exists and create if not
            Path(dest_dir).mkdir(parents=True, exist_ok=True)

            if state:
                if not link_path.exists():
                    try:
                        os.symlink(staging_item, link_path)
                        if staging_metadata:
                            staging_metadata["mods"][mod]["status"] = "enabled"
                            staging_metadata["mods"][mod]["enabled_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")

                    except Exception as e:
                        print(f"Failed to enable mod {e}")
                        switch.set_active(False)
            else:
                if link_path.is_symlink():
                    try:
                        link_path.unlink()
                        if staging_metadata:
                            staging_metadata["mods"][mod]["status"] = "disabled"
                            del staging_metadata["mods"][mod]["enabled_timestamp"]
                    except Exception as e:
                        print(f"Failed to disable mod {e}")
                        switch.set_active(True)

        if staging_metadata:
            with open(self.staging_metadata_path, 'w') as f:
                yaml.safe_dump(staging_metadata, f)

        # update indicators & mods page
        self.update_indicators()
        self.create_mods_page()

        return False

    def on_install_clicked(self, btn, filename, display_name):
        
        # This is to ensure that all the files in staging are neatly arranged in their own folder
        # ...and avoid loose files or files within directories to be merged together
        staging_path = os.path.join(self.staging_path, display_name)
        archive_full_path = os.path.join(self.downloads_path, filename)
        
        # Determine archive type
        filename_lower = filename.lower()
        is_rar = filename_lower.endswith(".rar")
        is_7z = filename_lower.endswith(".7z")
        is_zip = filename_lower.endswith(".zip")

        try:
            # Extract and inspect based on type
            all_files = []
            if is_rar:
                with rarfile.RarFile(archive_full_path) as rf:
                    all_files = rf.namelist()
                    rf.extractall(staging_path)
            elif is_7z:
                pass
                # TODO: find a way to fix py7zr library in flatpak or use somthing else
                # Use py7zr for .7z files
                # with py7zr.SevenZipFile(archive_full_path, mode='r') as szf:
                    # all_files = szf.getnames()  # py7zr uses getnames()
                    # szf.extractall(path=staging_path)
            elif is_zip:
                with zipfile.ZipFile(archive_full_path, 'r') as zf:
                    all_files = zf.namelist()
                    zf.extractall(staging_path)
            else:
                print(f"Archive type not recognised for {filename}")
                return

            fomod_xml_path = next((f for f in all_files if f.lower().endswith("fomod/moduleconfig.xml")), None)

            if fomod_xml_path:
                # Re-read the XML from the extracted location
                xml_path = os.path.join(staging_path, fomod_xml_path)
                with open(xml_path, 'rb') as f:
                    xml_data = f.read()
                
                module_name, options = fomod_handler.parse_fomod_xml(xml_data)
                
                if options:
                    dialog = fomod_handler.FomodSelectionDialog(self, module_name, options)
                    # Pass None for archive_class as we already extracted it
                    dialog.connect("response", self.on_fomod_dialog_response, archive_full_path, filename, None)
                    dialog.present()
                    return

            # Standard Installation
            extracted_roots = list({name.split('/')[0] for name in all_files})
            self.resolve_deployment_path(filename, extracted_roots)

        except Exception as e:
            self.show_message("Error", f"Installation failed: {e}")

    def on_fomod_dialog_response(self, dialog, response, zip_path, filename):
        if response == Gtk.ResponseType.OK:
            source_folder_name = dialog.get_selected_source()
            if source_folder_name:
                staging_path = self.staging_path
                
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
                        
                        #temporary fix to not break fomod support
                        #TODO: handle FOMODs better
                        source_folder_name = [source_folder_name]
                        self.resolve_deployment_path(filename, source_folder_name)
                    else:
                        print(f"Could not find {source_folder_name} inside the ZIP.")

        dialog.destroy()

    def choose_deployment_path(self, callback):
        '''Method that lets user choose the deployment path when there are multiple defined in game config'''
        deployment_targets = self.deployment_targets

        dialog = Gtk.Dialog(
            title="Select Deployment Path",
            transient_for=self,
            modal=True,
            decorated=False,
            default_width=450
        )
        
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)

        content_area = dialog.get_content_area()
        content_area.set_spacing(12)
        
        # GTK 4 individual margin properties
        content_area.set_margin_top(15)
        content_area.set_margin_bottom(15)
        content_area.set_margin_start(15)
        content_area.set_margin_end(15)

        header = Gtk.Label(label="Multiple deployment locations available:")
        header.set_halign(Gtk.Align.START)
        header.add_css_class("heading") 
        content_area.append(header)

        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.set_activate_on_single_click(True)

        row_data_map = {}

        for item in deployment_targets:
            row = Gtk.ListBoxRow()
            row.set_tooltip_text(item.get("description", ""))
            
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            # Correcting margins for the row content as well
            vbox.set_margin_top(12)
            vbox.set_margin_bottom(12)
            vbox.set_margin_start(12)
            vbox.set_margin_end(12)

            name_label = Gtk.Label()
            name_label.set_markup(f"<b>{item['name']}</b>")
            name_label.set_halign(Gtk.Align.START)

            path_label = Gtk.Label()
            path_label.set_markup(f"<span size='small' alpha='70%'>{item['path']}</span>")
            path_label.set_halign(Gtk.Align.START)
            path_label.set_ellipsize(Pango.EllipsizeMode.END)

            vbox.append(name_label)
            vbox.append(path_label)
            row.set_child(vbox)
            
            listbox.append(row)
            row_data_map[row] = item

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_child(listbox)
        content_area.append(scrolled)

        def on_row_activated(lb, row):
            # 1. Store the choice in a place the response handler can see it
            # We can attach it to the dialog object itself for easy access
            dialog.selected_data = row_data_map[row]
            
            # 2. Emit the OK response. 
            # This triggers 'on_response' with Gtk.ResponseType.OK
            dialog.response(Gtk.ResponseType.OK)

        listbox.connect("row-activated", on_row_activated)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.OK:
                # Retrieve the data we stored earlier
                callback(getattr(dialog, 'selected_data', None))
            else:
                # This handles clicking Cancel, Escape, or the 'X' button
                callback(None)
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()


    def resolve_deployment_path(self, filename: str, extracted_roots: list):
        """Resolve deployment path before continuing installation"""

        def on_path_resolved(deployment_target):
            if not deployment_target:
                print("Installation cancelled by user.")
                return 
            
            # Pass the control to the finalisation logic
            self.finalise_installation(filename, extracted_roots, deployment_target)

        # Is there a need to ask user to choose
        if len(self.deployment_targets) > 1:
            self.choose_deployment_path(on_path_resolved)
        else:
            # If only one, call the resolver immediately
            on_path_resolved(self.deployment_targets[0])

    def finalise_installation(self, filename, extracted_roots, deployment_target):
        """Update the metadata"""

        metadata_source = self.downloads_metadata_path # get downloads metadata (need this data to update the data below)

        # if there is already a metadata file, go read the contents to make sure we don't overwrite anything.
        current_staging_metadata = self.load_staging_metadata()
        # if there isn't, instanciate it
        if not current_staging_metadata:
            current_staging_metadata = {}
            current_staging_metadata["mods"] = {}
        
        # this req should only fail if all previous files were manually downloaded
        if os.path.exists(metadata_source):
            with open(metadata_source, 'r') as f:
                current_download_metadata = yaml.safe_load(f)
                
                if "info" not in current_staging_metadata: # add basic info if it's not already there
                    current_staging_metadata["info"] = current_download_metadata["info"]
                
                # if the mod was downloaded with metadata, add all of the specific mod information
                if filename in current_download_metadata["mods"]:
                    mod_name = current_download_metadata["mods"][filename]["name"]
                    current_staging_metadata["mods"][mod_name] = current_download_metadata["mods"][filename]
                else: # if the mod was manually downloaded, add basic info only
                    mod_name = filename.replace(".zip", "").replace(".rar", "")
                    current_staging_metadata["mods"][mod_name] = {}
                # regardless, add the list of installed files
                current_staging_metadata["mods"][mod_name]["mod_files"] = extracted_roots
                current_staging_metadata["mods"][mod_name]["status"] = "disabled"
                current_staging_metadata["mods"][mod_name]["archive_name"] = filename
                current_staging_metadata["mods"][mod_name]["install_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                current_staging_metadata["mods"][mod_name]["deployment_target"] = deployment_target["name"]
            
            # write the updated staging metadata file
            self.write_metadata(current_staging_metadata, self.staging_metadata_path)

        self.create_downloads_page()
        self.create_mods_page()
        self.update_indicators()

    def on_uninstall_item(self, btn, mod_files: list, mod_name: str):
        '''Uninstall a mod from the downloads page'''
        # get the mod deployment path
        staging_metadata = self.load_staging_metadata()
        if len(self.deployment_targets) == 1 or "deployment_target" not in staging_metadata["mods"][mod_name]:
            dest = self.deployment_targets[0]["path"]
        else: # case when there are multiple paths defined for the game
            for deployment_target in self.deployment_targets:
                if deployment_target["name"] == staging_metadata["mods"][mod_name]["deployment_target"]:
                    dest = deployment_target["path"]

        # remove the files
        try:
            staging_path = self.staging_path
            dest = Path(dest)
            for item_name in mod_files:
                # Remove symlink from game folder
                if dest and (dest / item_name).is_symlink(): 
                    (dest / item_name).unlink()
                
                # Remove the mod files from staging
                path = staging_path / item_name
                if path.exists():
                    if path.is_dir(): shutil.rmtree(path)
                    else: path.unlink()

        except Exception as e:
            self.show_message("Error while disabling mod: ", str(e))

        # Cleanup corresponding metadata if it exists
        if staging_metadata:
            if mod_name in staging_metadata["mods"]:
                del staging_metadata["mods"][mod_name]
            with open(self.staging_metadata_path, 'w') as f:
                yaml.safe_dump(staging_metadata, f)

        self.create_mods_page()
        self.create_downloads_page()
        self.update_indicators()

    def is_mod_installed(self, archive_filename):
        staging = self.staging_path
        
        # 1. Metadata Check
        staging_metadata = self.load_staging_metadata()

        if staging_metadata:
            for mod in staging_metadata["mods"]:
                if "archive_name" not in staging_metadata["mods"][mod]: # temporary so that this doesn't crash current users
                    return False
                # print(f"{archive_filename} compared to {staging_metadata["mods"][mod]["archive_name"]}")
                if archive_filename == staging_metadata["mods"][mod]["archive_name"]:
                    return True

        archive_path = os.path.join(self.downloads_path, archive_filename)
        if not os.path.exists(archive_path):
            return False
        return False

    def get_download_timestamp(self, f):
        return datetime.fromtimestamp(os.path.getmtime(os.path.join(self.downloads_path, f))).strftime('%Y-%m-%d %H:%M')

    def setup_folder_monitor(self):
        f = Gio.File.new_for_path(self.downloads_path)
        self.monitor = f.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_downloads_folder_changed)

    def on_downloads_folder_changed(self, monitor, file, other_file, event_type):
        """Callback that handles file system events in the downloads folder"""
        
        # Define which events we actually care about
        relevant_events = [
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.DELETED
        ]

        if event_type in relevant_events:
            self.create_downloads_page()
            self.update_indicators()

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
        if self.app_id:
            if self.platform == "steam":
                webbrowser.open(f"steam://launch/{self.app_id}")
            elif self.platform == "heroic-gog":
                webbrowser.open(f"heroic://launch/gog/{self.app_id}")
            elif self.platform == "heroic-epic":
                webbrowser.open(f"heroic://launch/epic/{self.app_id}")





    def launch(self): self.present()
