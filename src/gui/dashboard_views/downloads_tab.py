import gettext
import os
import shutil
import webbrowser
from datetime import datetime
from pathlib import Path

import yaml
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from core.archive_manager import (delete_downloaded_archive, extract_archive,
                                  get_all_relative_files)
from core.config import (finalize_mod_metadata, load_metadata,
                         remove_mod_from_metadata)
from core.fomod_manager import apply_fomod_selection, parse_fomod_xml
from core.mod_manager import is_mod_installed
from gui.dashboard_views.fomod_dialog import FomodSelectionDialog

_ = gettext.gettext

class DownloadsTab(Gtk.Box):
    def __init__(self, dashboard):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_start(100)
        self.set_margin_end(100)
        self.set_margin_top(40)
        
        self.dashboard = dashboard
        self.current_filter = "all"

        # --- ACTION BAR ---
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        filter_group = Gtk.Box(css_classes=["linked"])
        
        self.all_filter_btn = Gtk.ToggleButton(label=_("All"), active=True)
        self.all_filter_btn.connect("toggled", self.on_filter_toggled, "all")
        filter_group.append(self.all_filter_btn)
        
        for n, l in [("uninstalled", _("Uninstalled")), ("installed", _("Installed"))]:
            b = Gtk.ToggleButton(label=l, group=self.all_filter_btn)
            b.connect("toggled", self.on_filter_toggled, n)
            filter_group.append(b)
            
        action_bar.append(filter_group)
        
        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", css_classes=["flat"])
        folder_btn.set_halign(Gtk.Align.END)
        folder_btn.set_hexpand(True)
        folder_btn.connect("clicked", lambda x: webbrowser.open(f"file://{self.dashboard.downloads_path}"))
        action_bar.append(folder_btn)
        
        self.append(action_bar)

        # --- LISTE DES TÉLÉCHARGEMENTS ---
        self.list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.list_box.set_filter_func(self.filter_list_rows)

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_file_drop)
        drop_target.connect("enter", self.on_drag_enter)
        drop_target.connect("leave", self.on_drag_leave)
        
        self.add_controller(drop_target)
        
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_child(self.list_box)
        self.append(scrolled)

        if self.dashboard.downloads_path and os.path.exists(self.dashboard.downloads_path):
            self.setup_folder_monitor()
            
        self.populate_list()

    def populate_list(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        if not (self.dashboard.downloads_path and os.path.exists(self.dashboard.downloads_path)):
            return

        files = [f for f in os.listdir(self.dashboard.downloads_path) if f.lower().endswith(('.zip', '.rar', '.7z'))]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(self.dashboard.downloads_path, f)), reverse=True)

        staging_metadata = load_metadata(self.dashboard.staging_metadata_path)
        
        for file_name in files:
            installed = is_mod_installed(file_name, staging_metadata)
            
            display_name, version_text, changelog = file_name, "—", ""
            meta_path = self.dashboard.downloads_metadata_path
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r') as meta_f:
                        metadata = yaml.safe_load(meta_f)
                        if file_name in metadata.get("mods", {}):
                            display_name = metadata["mods"][file_name].get("name", file_name)
                            version_text = metadata["mods"][file_name].get("version", "—")
                            changelog = metadata["mods"][file_name].get("changelog", "")
                except: pass

            row = Adw.ActionRow(title=display_name)
            row.is_installed = installed
            if display_name != file_name: row.set_subtitle(file_name)

            # Version badge
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

            # Timestamps
            ts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, margin_end=15)
            dl_ts_text = _("Downloaded: {}").format(self.get_download_timestamp(file_name))
            ts_box.append(Gtk.Label(label=dl_ts_text, xalign=1, css_classes=["dim-label", "caption"]))

            if installed:
                inst_ts = None
                for mod_key, mod_val in staging_metadata.get("mods", {}).items():
                    if mod_val.get("archive_name") == file_name:
                        inst_ts = mod_val.get("install_timestamp")
                        break
                if inst_ts:
                    inst_text = _("Installed: {}").format(inst_ts)
                    ts_box.append(Gtk.Label(label=inst_text, xalign=1, css_classes=["dim-label", "caption"]))
            row.add_suffix(ts_box)

            # Install Button
            install_btn = Gtk.Button(label=_("Reinstall") if installed else _("Install"), valign=Gtk.Align.CENTER)
            if not installed: install_btn.add_css_class("suggested-action")
            install_btn.set_cursor_from_name("pointer")
            install_btn.connect("clicked", self.on_install_clicked, file_name, display_name)
            row.add_suffix(install_btn)

            # Trash Button
            d_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False, interpolate_size=True)
            b_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
            b_btn.set_cursor_from_name("pointer")
            c_btn = Gtk.Button(label=_("Are you sure?"), valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
            c_btn.connect("clicked", self.on_delete_downloaded_archive, file_name)
            
            b_btn.connect("clicked", lambda b, s=d_stack: [
                s.set_visible_child_name("c"),
                GLib.timeout_add_seconds(3, lambda: s.set_visible_child_name("b") or False)
            ])
            d_stack.add_named(b_btn, "b"); d_stack.add_named(c_btn, "c")
            row.add_suffix(d_stack)
            
            self.list_box.append(row)

    # --- CORE FUNCTIONS ---
    def filter_list_rows(self, row):
        if self.current_filter == "all": return True
        if hasattr(row, 'is_installed'):
            if self.current_filter == "installed": return row.is_installed
            if self.current_filter == "uninstalled": return not row.is_installed
        return True

    def on_filter_toggled(self, btn, f_name):
        if btn.get_active():
            self.current_filter = f_name
            self.list_box.invalidate_filter()

    def on_delete_downloaded_archive(self, btn, file_name):
        try:
            delete_downloaded_archive(self.dashboard, self.dashboard.downloads_path, file_name)
        except OSError as e:
            self.dashboard.show_message(_("Error"), _("Could not delete the file: {}").format(e))

        try:
            remove_mod_from_metadata(self.dashboard.downloads_metadata_path, file_name)
        except OSError as e:
            self.dashboard.show_message(_("Error"), _("Could not delete metadata for file: {}").format(e))

        self.populate_list()
        self.dashboard.update_indicators()

    def setup_folder_monitor(self):
        f = Gio.File.new_for_path(self.dashboard.downloads_path)
        self.monitor = f.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_downloads_folder_changed)

    def on_downloads_folder_changed(self, monitor, file, other_file, event_type):
        relevant_events = [Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED]
        if event_type in relevant_events:
            GLib.idle_add(self.populate_list)
            GLib.idle_add(self.dashboard.update_indicators)

    def get_download_timestamp(self, f):
        return datetime.fromtimestamp(os.path.getmtime(os.path.join(self.dashboard.downloads_path, f))).strftime('%c')

    # Install
    def on_install_clicked(self, btn, filename, display_name):
        display_name = display_name.replace(".zip", "").replace(".rar", "").replace(".7z", "")
        mod_staging_dir = os.path.join(self.dashboard.staging_path, display_name)
        archive_full_path = os.path.join(self.dashboard.downloads_path, filename)
        
        if not self.dashboard.deployment_targets:
            self.dashboard.show_message(_("Error"), _("Installation failed: Your configuration YAML is missing a mods_path..."))
            return

        try:
            extract_archive(archive_full_path, mod_staging_dir)
            all_files = get_all_relative_files(mod_staging_dir)

            if not all_files:
                self.dashboard.show_message(_("Error"), _("No files were found in your mod archive."))
                return

            fomod_xml_path = next((f for f in all_files if f.lower().endswith("fomod/moduleconfig.xml")), None)

            if fomod_xml_path:
                xml_path = os.path.join(mod_staging_dir, fomod_xml_path)
                with open(xml_path, 'rb') as f:
                    xml_data = f.read()
                
                module_name, options = parse_fomod_xml(xml_data)
                
                if options:
                    dialog = FomodSelectionDialog(self.dashboard.app.win, module_name, options)
                    dialog.connect("response", self.on_fomod_dialog_response, mod_staging_dir, filename)
                    dialog.present()
                    return

            self.resolve_deployment_path(filename, all_files)

        except Exception as e:
            self.dashboard.show_message(_("Error"), _("Installation failed: {}").format(e))

    def on_file_drop(self, _targer, value, _x, _y):
        if isinstance(value, Gdk.FileList):
            files = value.get_files()
            uris = [f.get_uri() for f in files]

            from core.drag_drop_file import process_dropped_files
            mods = process_dropped_files(uris, self.dashboard.downloads_path)

            if mods:
                return True
        return False

    def on_drag_enter(self, _target, _x, _y):
        self.list_box.add_css_class("drop-active")
        return Gdk.DragAction.COPY

    def on_drag_leave(self, _target):
        self.list_box.remove_css_class("drop-active")

    def on_fomod_dialog_response(self, dialog, response, mod_staging_dir, filename):
        if response == Gtk.ResponseType.OK:
            source_folder_name = dialog.get_selected_source()
            if source_folder_name:
                try:
                    # APPEL AU CORE
                    final_files = apply_fomod_selection(mod_staging_dir, source_folder_name)
                    self.resolve_deployment_path(filename, final_files)
                except Exception as e:
                    self.dashboard.show_message(_("Error"), str(e))
        else:
            import shutil
            shutil.rmtree(mod_staging_dir, ignore_errors=True)

        dialog.destroy()

    def resolve_deployment_path(self, filename: str, extracted_roots: list):
        def on_path_resolved(deployment_target):
            if not deployment_target:
                return
            self.finalise_installation(filename, extracted_roots, deployment_target)

        if len(self.dashboard.deployment_targets) > 1:
            self.choose_deployment_path(on_path_resolved)
        else:
            on_path_resolved(self.dashboard.deployment_targets[0])

    def choose_deployment_path(self, callback):
        dialog = Gtk.Dialog(
            title=_("Select Deployment Path"),
            transient_for=self.dashboard.app.win,
            modal=True,
            decorated=False,
            default_width=450
        )
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        content_area = dialog.get_content_area()
        content_area.set_spacing(12)
        content_area.set_margin_top(15); content_area.set_margin_bottom(15)
        content_area.set_margin_start(15); content_area.set_margin_end(15)

        header = Gtk.Label(label=_("Multiple deployment locations available:"))
        header.set_halign(Gtk.Align.START)
        header.add_css_class("heading") 
        content_area.append(header)

        listbox = Gtk.ListBox(css_classes=["boxed-list"])
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.set_activate_on_single_click(True)

        row_data_map = {}
        for item in self.dashboard.deployment_targets:
            row = Gtk.ListBoxRow()
            row.set_tooltip_text(item.get("description", ""))
            
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_margin_top(12); vbox.set_margin_bottom(12)
            vbox.set_margin_start(12); vbox.set_margin_end(12)

            name_label = Gtk.Label(halign=Gtk.Align.START)
            name_label.set_markup(f"<b>{item['name']}</b>")
            
            path_label = Gtk.Label(halign=Gtk.Align.START)
            path_label.set_markup(f"<span size='small' alpha='70%'>{item['path']}</span>")
            path_label.set_ellipsize(Pango.EllipsizeMode.END)

            vbox.append(name_label); vbox.append(path_label)
            row.set_child(vbox)
            listbox.append(row)
            row_data_map[row] = item

        scrolled = Gtk.ScrolledWindow(vexpand=True, propagate_natural_height=True)
        scrolled.set_child(listbox)
        content_area.append(scrolled)

        def on_row_activated(lb, row):
            dialog.selected_data = row_data_map[row]
            dialog.response(Gtk.ResponseType.OK)

        listbox.connect("row-activated", on_row_activated)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.OK:
                callback(getattr(dialog, 'selected_data', None))
            else:
                callback(None)
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def finalise_installation(self, filename, extracted_roots, deployment_target):
        try:
            # APPEL AU CORE
            finalize_mod_metadata(
                filename, 
                extracted_roots, 
                deployment_target["name"], 
                self.dashboard.staging_metadata_path, 
                self.dashboard.downloads_metadata_path
            )
        except Exception as e:
            self.dashboard.show_message("Error", f"Installation failed: There was an issue creating/updating the metadata file: {e}")

        self.populate_list()
        
        if hasattr(self.dashboard, 'mods_tab'):
            self.dashboard.mods_tab.populate_list()
            
        self.dashboard.update_indicators()