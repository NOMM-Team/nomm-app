import gettext
import os
import webbrowser
import threading
from datetime import datetime
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, GObject, Gtk, Gio, GdkPixbuf

from core.mod_manager import (change_mod_index, check_for_conflicts,
                              deploy_all_ordered_mods, load_staging_metadata,
                              read_index, toggle_mod_state)
from core.nexus_api import check_for_mod_updates_async
from core.tools import timestamp_converter, write_yaml

_ = gettext.gettext
ngettext = gettext.ngettext

class ModsTab(Gtk.Box):
    def __init__(self, dashboard):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_start(30)
        self.set_margin_end(30)
        self.set_margin_top(20)
        
        self.dashboard = dashboard
        
        self.sc = Gtk.ScrolledWindow(vexpand=True)
        
        # Action bar top right
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.mod_search_entry = Gtk.SearchEntry(placeholder_text=_("Search mods..."))
        self.mod_search_entry.set_size_request(300, -1) 
        self.mod_search_entry.connect("search-changed", self.on_mod_search_changed)
        action_bar.append(self.mod_search_entry)

        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", css_classes=["flat"])
        folder_btn.set_halign(Gtk.Align.END); folder_btn.set_hexpand(True)
        folder_btn.set_cursor_from_name("pointer")
        folder_btn.connect("clicked", lambda x: webbrowser.open(f"file://{self.dashboard.staging_path}"))
        action_bar.append(folder_btn)

        update_btn = Gtk.Button(icon_name="view-refresh-symbolic", css_classes=["flat"])
        update_btn.set_halign(Gtk.Align.END)
        update_btn.set_cursor_from_name("pointer")
        update_btn.connect("clicked", self.check_for_updates)
        action_bar.append(update_btn)

        launch_btn = Gtk.Button(icon_name="media-playback-start", css_classes=["flat"])
        launch_btn.set_halign(Gtk.Align.END)
        launch_btn.set_cursor_from_name("pointer")
        launch_btn.connect("clicked", self.dashboard.on_launch_clicked)
        action_bar.append(launch_btn)

        self.append(action_bar)
        
        # Container for List + Preview
        self.main_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.append(self.main_content)

        # Mod list
        self.mods_list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.mods_list_box.set_filter_func(self.filter_mods_rows)
        self.mods_list_box.connect("row-activated", self.on_row_clicked) 
        self.list_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.list_scroll.set_child(self.mods_list_box)
        self.main_content.append(self.list_scroll)

        # Preview pane with Revealer
        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.revealer.set_hexpand(False) 
        self.revealer.set_halign(Gtk.Align.END)
        self.main_content.append(self.revealer)

        self.setup_preview_pane()
        self.populate_list()

    def setup_preview_pane(self):
        self.preview_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.preview_pane.set_size_request(350, -1)
        self.preview_pane.set_hexpand(True)
        self.preview_pane.add_css_class("background")

        # Container for the image to handle centering and potential rounding
        self.thumb_container = Gtk.Box(halign=Gtk.Align.CENTER, margin_top=10)
        self.thumb_container.set_size_request(300, 150)
        self.preview_thumbnail = Gtk.Image()
        # -1 for height allows it to maintain aspect ratio
        self.preview_thumbnail.set_pixel_size(300)
        self.preview_thumbnail.set_size_request(300, 150) # 16:9 ratio for 300 width
        
        # This is a GTK4 property that helps with clipping
        self.preview_thumbnail.set_overflow(Gtk.Overflow.HIDDEN)
        
        self.thumb_container.append(self.preview_thumbnail)
        self.preview_pane.append(self.thumb_container)

        # Header with close button
        header = Gtk.CenterBox(margin_top=10, margin_bottom=10)
        self.preview_title = Gtk.Label(css_classes=["title-2"])
        header.set_center_widget(self.preview_title)
        close_btn = Gtk.Button(icon_name="window-close-symbolic", css_classes=["flat"])
        close_btn.connect("clicked", lambda x: self.revealer.set_reveal_child(False))
        header.set_end_widget(close_btn)
        self.preview_pane.append(header)

        # Metadata Display
        self.preview_version = Gtk.Label(css_classes=["dim-label"])
        self.preview_pane.append(self.preview_version)

        self.revealer.set_child(self.preview_pane)

    def on_row_clicked(self, listbox, row):
        # We need to fetch the metadata associated with this row
        mod_name = row.get_title() # ActionRow title
        mod_info = row.mod_data

        # Update labels
        self.preview_title.set_label(mod_name)
        version = mod_info.get("version", "Unknown")
        self.preview_version.set_label(f"Version: {version}")
        

        # Add thumbnail
        thumbnail_path = mod_info.get("thumbnail")
        if thumbnail_path and os.path.exists(thumbnail_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                thumbnail_path, 300, 168, False
            )
            self.preview_thumbnail.set_from_pixbuf(pixbuf)
        else:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    self.dashboard.assets_path + "/nomm.png", 300, 168, True
                )
            self.preview_thumbnail.set_from_pixbuf(pixbuf)
        self.revealer.set_reveal_child(True)

    def populate_list(self):
        
        def prepare_data():
            staging_path = self.dashboard.staging_path
            staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
            
            indexed_mods = read_index(self.dashboard.staging_metadata_path)
            
            enable_file_counter = False
            for mod in staging_metadata.get("mods"):
                if len(staging_metadata["mods"][mod]["mod_files"]) > 1:
                    enable_file_counter = True
                    break
                
            missing_files_per_mod = {
                mod: [f for f in staging_metadata["mods"][mod].get("mod_files", [])
                        if not os.path.exists(staging_path / mod / f)]
                for mod in staging_metadata.get("mods", {})
            }
            
            conflicts = check_for_conflicts(self.dashboard.staging_metadata_path)
            
            GLib.idle_add(on_data_prepared, staging_path, staging_metadata, indexed_mods, enable_file_counter, conflicts, missing_files_per_mod)
            
        def on_data_prepared(staging_path, staging_metadata, indexed_mods, enable_file_counter, conflicts, missing_files_per_mod):
            valignment = self.sc.get_valign()

            while child := self.mods_list_box.get_first_child():
                self.mods_list_box.remove(child)

            if not staging_metadata or not staging_metadata.get("mods"):
                self.append(Gtk.Label(label=_("The staging metadata file could not be found, did you install any mods?"), css_classes=["dim-label"]))
                return

            file_badge_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
            load_index_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
            version_badge_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

            for index, mod in enumerate(indexed_mods, start=1):

                if mod not in staging_metadata["mods"]:
                    continue
                
                display_name = mod
                mod_metadata = staging_metadata["mods"][mod]

                version_text = mod_metadata.get("version", "—")
                new_version = mod_metadata.get("new_version", "")
                changelog = mod_metadata.get("changelog", "")
                mod_link = mod_metadata.get("mod_link", "")
                mod_files = mod_metadata.get("mod_files", [])

                row = Adw.ActionRow(title=display_name)

            # Timestamps
            if "install_timestamp" in mod_metadata or "enabled_timestamp" in mod_metadata:
                timestamp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, margin_end=15)

                # Enabled Timestamp
                if "enabled_timestamp" in mod_metadata:
                    enabled_timestamp_label = timestamp_converter(mod_metadata["enabled_timestamp"])
                    enabled_tooltip = _("Enabled: {}").format(timestamp_converter(mod_metadata["enabled_timestamp"], "long"))
                    
                    enabled_row = self.dashboard.create_timestamp_row(enabled_timestamp_label, enabled_tooltip, "enabled.svg")
                    timestamp_box.append(enabled_row)

                # Installed Timestamp
                if "install_timestamp" in mod_metadata:
                    installed_timestamp_label = timestamp_converter(mod_metadata["install_timestamp"])
                    installed_tooltip = _("Installed: {}").format(timestamp_converter(mod_metadata["install_timestamp"], "long"))
                    
                    installed_row = self.dashboard.create_timestamp_row(installed_timestamp_label, installed_tooltip, "installed.svg")
                    timestamp_box.append(installed_row)
                row.add_suffix(timestamp_box)

            # Trash
            u_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
            bin_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
            conf_del_btn = Gtk.Button(label=_("Are you sure?"), valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
            conf_del_btn.connect("clicked", self.dashboard.on_uninstall_item, mod_files, mod)
            
            bin_btn.connect("clicked", lambda b, s=u_stack: [
                s.set_visible_child_name("c"),
                GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)
            ])
            u_stack.add_named(bin_btn, "b"); u_stack.add_named(conf_del_btn, "c")
            row.add_suffix(u_stack)

                row_element_margin = 10

                # Toggle Switch
                mod_toggle_switch = Gtk.Switch(active=True if "enabled_timestamp" in mod_metadata else False, valign=Gtk.Align.CENTER, css_classes=["accent-switch"])
                mod_toggle_switch.connect("state-set", self.on_mod_toggled, mod_files, mod)
                if mod in self.dashboard.currently_toggling:
                    mod_toggle_switch.set_active(True)
                    mod_toggle_switch.set_sensitive(False)
                row.add_prefix(mod_toggle_switch)

                if conflicts:
                    # Drag for load order
                    drag_handle = Gtk.Image.new_from_icon_name("open-menu-symbolic")
                    drag_handle.set_cursor_from_name("grab")
                    drag_handle.set_margin_end(6)
                    drag_source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
                    drag_source.connect("prepare", self.on_drag_prepare, mod)
                    drag_handle.add_controller(drag_source)
                    row.add_prefix(drag_handle)

                if enable_file_counter:
                    number_of_files = len(mod_files)
                    file_list_badge = Gtk.CenterBox(orientation=Gtk.Orientation.HORIZONTAL)
                    file_list_badge.set_tooltip_text("\n".join(mod_files))
                    file_list_badge.add_css_class("badge-action-row")
                    file_list_badge.set_valign(Gtk.Align.CENTER)
                    file_list_badge.set_margin_end(row_element_margin)
                    label_text = ngettext("{} file", "{} files", number_of_files).format(number_of_files)
                    file_list_badge.set_center_widget(Gtk.Label(label=label_text))
                    file_badge_sizegroup.add_widget(file_list_badge)
                    row.add_prefix(file_list_badge)

                if conflicts:
                    # Load Index
                    index_label = Gtk.Label(label=f"{index}")
                    index_label.add_css_class("dim-label")
                    index_label.set_margin_end(6)
                    index_label.set_valign(Gtk.Align.CENTER)
                    load_index_sizegroup.add_widget(index_label)
                    row.add_prefix(index_label)

                drop_target = Gtk.DropTarget(actions=Gdk.DragAction.MOVE)
                drop_target.set_gtypes([GObject.TYPE_STRING])
                drop_target.connect("drop", self.on_row_drop, mod)
                row.add_controller(drop_target)

                # Suffix: Missing Files
                missing_files = missing_files_per_mod.get(display_name, [])
                if missing_files:
                    missing_file_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                    missing_file_badge.add_css_class("warning-badge")
                    missing_file_badge.set_valign(Gtk.Align.CENTER)
                    missing_file_badge.set_margin_end(row_element_margin)
                    label_text = ngettext(
                        "Missing {} file",
                        "Missing {} files",
                        len(missing_files)
                    ).format(len(missing_files))
                    missing_file_badge.set_tooltip_text(_("Missing Files:")+"\n\n".join(missing_files))
                    missing_file_badge.append(Gtk.Label(label=label_text))
                    row.add_prefix(missing_file_badge)

                # Conflits
                conflicting_mods = []
                for conflict_list in conflicts:
                    if display_name in conflict_list:
                        other_mods = conflict_list.copy()
                        other_mods.remove(display_name)
                        conflicting_mods.extend(other_mods)
                if conflicting_mods:
                    conflicts_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                    conflicts_badge.add_css_class("warning-badge")
                    conflicts_badge.set_valign(Gtk.Align.CENTER)
                    conflicts_badge.set_margin_end(row_element_margin)
                    label_text = ngettext("Conflicting mod: {}", "Conflicting mods: {}", len(conflicting_mods)).format("\n".join(conflicting_mods))
                    conflicts_badge.set_tooltip_text(label_text)
                    conflict_icon = Gtk.Image.new_from_icon_name("vcs-merge-request-symbolic")
                    conflict_icon.set_pixel_size(18)
                    conflicts_badge.append(conflict_icon)
                    row.add_suffix(conflicts_badge)

                # Text file (Readme)
                text_file = self.find_text_file(mod_metadata.get("mod_files", []))
                if text_file:
                    info_text_badge = Gtk.Button()
                    button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                    info_icon = Gtk.Image.new_from_file(os.path.join(self.dashboard.assets_path, "ui_icons", "breaking_news.svg"))
                    info_icon.set_pixel_size(22)
                    button_content.append(info_icon)
                    info_text_badge.add_css_class("help-about-symbolic")
                    info_text_badge.set_tooltip_text(_("This mod contains a text file, click to view."))
                    info_text_badge.set_child(button_content)
                    info_text_badge.set_cursor_from_name("pointer")
                    info_text_badge.connect("clicked", self.dashboard.load_text_file, Path(staging_path) / mod / text_file)
                    info_text_badge.set_valign(Gtk.Align.CENTER)
                    info_text_badge.set_margin_end(row_element_margin)
                    row.add_suffix(info_text_badge)

                # Timestamps
                if "install_timestamp" in mod_metadata or "enabled_timestamp" in mod_metadata:
                    timestamp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, margin_end=15)

                    # Enabled Timestamp
                    if "enabled_timestamp" in mod_metadata:
                        enabled_timestamp_label = timestamp_converter(mod_metadata["enabled_timestamp"])
                        enabled_tooltip = _("Enabled: {}").format(timestamp_converter(mod_metadata["enabled_timestamp"], "long"))

                        enabled_row = self.dashboard.create_timestamp_row(enabled_timestamp_label, enabled_tooltip, "enabled.svg")
                        timestamp_box.append(enabled_row)

                    # Installed Timestamp
                    if "install_timestamp" in mod_metadata:
                        installed_timestamp_label = timestamp_converter(mod_metadata["install_timestamp"])
                        installed_tooltip = _("Installed: {}").format(timestamp_converter(mod_metadata["install_timestamp"], "long"))

                        installed_row = self.dashboard.create_timestamp_row(installed_timestamp_label, installed_tooltip, "installed.svg")
                        timestamp_box.append(installed_row)

                    row.add_suffix(timestamp_box)

                # Version
                version_badge = Gtk.Button()
                button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                button_content.set_halign(Gtk.Align.CENTER)
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
                if mod_link: 
                    version_badge.connect("clicked", lambda b, l=mod_link: webbrowser.open(l))

                if len(version_text) < 10:
                    version_badge_sizegroup.add_widget(version_badge)
                row.add_suffix(version_badge)

                # Trash
                u_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
                bin_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
                conf_del_btn = Gtk.Button(label=_("Are you sure?"), valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
                conf_del_btn.connect("clicked", self.dashboard.on_uninstall_item, mod_files, mod)

                bin_btn.connect("clicked", lambda b, s=u_stack: [
                    s.set_visible_child_name("c"),
                    GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)
                ])
                u_stack.add_named(bin_btn, "b"); u_stack.add_named(conf_del_btn, "c")
                row.add_suffix(u_stack)

                self.mods_list_box.append(row)

            self.sc.set_valign(valignment)
        
        threading.Thread(target=prepare_data, daemon=True).start()

    def find_text_file(self, mod_files):
        for file_path in mod_files:
            if ".txt" in file_path:
                return file_path
        return None

    def on_mod_search_changed(self, entry):
        self.mods_list_box.invalidate_filter()

    def filter_mods_rows(self, row):
        search_text = self.mod_search_entry.get_text().lower()
        if not search_text: return True
        return search_text in getattr(row, 'mod_name', '')

    def on_mod_toggled(self, switch, state, mod_files: list, mod: str):
        
        switch.set_sensitive(False)
        self.dashboard.currently_toggling.add(mod)
        def worker():
            success = toggle_mod_state(
                mod_name=mod,
                mod_files=mod_files,
                state=state,
                staging_dir=str(self.dashboard.staging_path),
                deployment_targets=self.dashboard.deployment_targets
            )
            GLib.idle_add(on_toggle_done, success)
            
        def on_toggle_done(success):
            # UI Fallback if toggle fail
            self.dashboard.currently_toggling.discard(mod)
            switch.set_sensitive(True)
            if state and not success:
                switch.set_active(False) 
                return False
            
            # UI Refresh
            self.dashboard.update_indicators()
            self.populate_list()

            return False
        
        threading.Thread(target=worker, daemon=True).start()
    
    def on_drag_prepare(self, source, x, y, mod_name):
        value = GObject.Value(GObject.TYPE_STRING, mod_name)
        return Gdk.ContentProvider.new_for_value(value)
    
    def on_row_drop(self, target, _value, _x, _y, mod_name):
        if value == mod_name:
            return False
        
        current_mods = read_index(self.dashboard.staging_metadata_path)
        staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
        
        # get the mod deployment path
        dest_dir = self.dashboard.deployment_targets[0]["path"]
        if mod_name in staging_metadata["mods"] and "deployment_target" in staging_metadata["mods"][mod_name]:
            for target in self.dashboard.deployment_targets:
                if target["name"] == staging_metadata["mods"][mod_name]["deployment_target"]:
                    dest_dir = target["path"]
                    break
        
        if mod_name in current_mods:
            target_index = current_mods.index(mod_name)
            change_mod_index(self.dashboard.staging_metadata_path, value, target_index)
            deploy_all_ordered_mods(self.dashboard.staging_path, dest_dir)
            self.populate_list()
            return True
        return False

    def check_for_updates(self, btn):
        staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
        if not staging_metadata:
            print(f"Staging metadata not found at: {self.dashboard.staging_metadata_path}. Aborting update process.")
            return
        nexus_id = staging_metadata.get("info", {}).get("nexus_id")
        if not nexus_id:
            print(f"nexus_id not found in staging metadata. Aborting update process.")
            return

        btn.set_sensitive(False)

        def on_updates_checked(mods_updated, updated_metadata):
            if mods_updated:
                write_yaml(updated_metadata, self.dashboard.staging_metadata_path)
                self.populate_list()
            btn.set_sensitive(True)

        check_for_mod_updates_async(staging_metadata, self.dashboard.headers, nexus_id, on_updates_checked)