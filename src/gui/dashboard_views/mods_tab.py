# src/gui/tabs/mods_tab.py

# Ce fichier fait partie de Yamm (Yet Another Mod Manager).
# Yamm est un fork de Nomm, développé initialement par Allexio.
#
# Copyright (C) 2026 Emetros
# Copyright (C) 2024 Allexio
#
# Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier
# selon les termes de la Licence Publique Générale GNU telle que publiée par la
# Free Software Foundation, soit la version 3 de la Licence, soit (à votre
# discrétion) toute version ultérieure.
#
# Ce programme est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE
# GARANTIE ; sans même la garantie implicite de COMMERCIALISATION ou
# d'ADÉQUATION À UN USAGE PARTICULIER. Voir la Licence Publique Générale GNU
# pour plus de détails.
#
# Vous devriez avoir reçu une copie de la Licence Publique Générale GNU
# avec ce programme. Sinon, voir <https://www.gnu.org/licenses/>.

import os
import webbrowser
import gettext
from pathlib import Path
from datetime import datetime

from gi.repository import Gtk, Adw, GLib, Gdk, GObject
from core.config import load_metadata, save_metadata
from core.mod_manager import deploy_mod_files, remove_mod_files, toggle_mod_state, deploy_all_ordered_mods
from core.nexus_api import check_for_mod_updates_async
from core.index_manager import read_index, change_mod_index

# ui imports
from gui.app_views.loading_view import LoadingView

_ = gettext.gettext
ngettext = gettext.ngettext

class ModsTab(Gtk.Box):
    def __init__(self, dashboard):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_start(30)
        self.set_margin_end(30)
        self.set_margin_top(20)
        
        self.dashboard = dashboard
        
        # --- ACTION BAR ---
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

        # --- LISTE DES MODS ---
        self.mods_list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.mods_list_box.set_filter_func(self.filter_mods_rows)
        
        self.populate_list()
        
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.mods_list_box)
        self.append(sc)

    def populate_list(self):
        # Vider la liste existante
        while child := self.mods_list_box.get_first_child():
            self.mods_list_box.remove(child)

        staging_path = self.dashboard.staging_path
        staging_metadata = load_metadata(self.dashboard.staging_metadata_path)
        
        if not staging_metadata or not staging_metadata.get("mods"):
            self.append(Gtk.Label(label=_("The staging metadata file could not be found, did you install any mods?"), css_classes=["dim-label"]))
            return

        conflicts = self.dashboard.check_for_conflicts()
        file_badge_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        load_index_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        version_badge_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        
        indexed_mods = read_index(self.dashboard.staging_path)
        
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
            
            if len(mod_files) == 1:
                row.set_subtitle(mod_files[0])
            row.mod_name = display_name.lower()

            row_element_margin = 10

            # Toggle Switch
            mod_toggle_switch = Gtk.Switch(active=True if "enabled_timestamp" in mod_metadata else False, valign=Gtk.Align.CENTER, css_classes=["accent-switch"])
            mod_toggle_switch.connect("state-set", self.on_mod_toggled, mod_files, mod)
            row.add_prefix(mod_toggle_switch)
            
            # Drag for load order
            drag_handle = Gtk.Image.new_from_icon_name("open-menu-symbolic")
            drag_handle.set_cursor_from_name("grab")
            drag_handle.set_margin_end(6)
            drag_source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
            drag_source.connect("prepare", self.on_drag_prepare, mod) # 'mod' est le nom du dossier
            drag_handle.add_controller(drag_source)
            row.add_prefix(drag_handle)

            # Nombre de fichiers
            number_of_files = len(mod_files)
            if number_of_files >= 0:
                file_list_badge = Gtk.CenterBox(orientation=Gtk.Orientation.HORIZONTAL)
                file_list_badge.set_tooltip_text("\n".join(mod_files))
                file_list_badge.add_css_class("badge-action-row")
                file_list_badge.set_valign(Gtk.Align.CENTER)
                file_list_badge.set_margin_end(row_element_margin)
                label_text = ngettext("{} file", "{} files", number_of_files).format(number_of_files)
                file_list_badge.set_center_widget(Gtk.Label(label=label_text))
                file_badge_sizegroup.add_widget(file_list_badge)
                row.add_prefix(file_list_badge)
                
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
                button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                info_icon = Gtk.Image.new_from_icon_name("help-about-symbolic")
                info_icon.set_pixel_size(14)
                button_content.append(info_icon)
                info_text_badge.add_css_class("help-about-symbolic")
                info_text_badge.set_tooltip_text(_("This mod contains a text file, click to view."))
                info_text_badge.set_child(button_content)
                info_text_badge.set_cursor_from_name("pointer")
                info_text_badge.connect("clicked", self.dashboard.load_text_file, Path(staging_path) / mod / text_file)
                info_text_badge.set_valign(Gtk.Align.CENTER)
                info_text_badge.set_margin_end(row_element_margin)
                row.add_suffix(info_text_badge)
            
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
            
            version_badge_sizegroup.add_widget(version_badge)
            row.add_suffix(version_badge)

            # Poubelle
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

    # --- MÉTHODES MÉTIER DU TAB ---
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
        # APPEL AU CORE
        success = toggle_mod_state(
            mod_name=mod,
            mod_files=mod_files,
            state=state,
            staging_path=str(self.dashboard.staging_path),
            deployment_targets=self.dashboard.deployment_targets,
            metadata_path=self.dashboard.staging_metadata_path
        )

        # Gestion de l'UI si l'activation échoue
        if state and not success:
            switch.set_active(False) 
            return False

        # Rafraîchissement de l'interface
        self.dashboard.update_indicators()
        self.populate_list()
        
        return False
    
    def on_drag_prepare(self, source, x, y, mod_name):
        value = GObject.Value(GObject.TYPE_STRING, mod_name)
        return Gdk.ContentProvider.new_for_value(value)
    
    def on_row_drop(self, target, value, x, y, mod_name):
        if value == mod_name:
            return False
        
        current_mods = read_index(self.dashboard.staging_path)
        
        if mod_name in current_mods:
            target_index = current_mods.index(mod_name)
            change_mod_index(self.dashboard.staging_path, value, target_index)
            GLib.idle_add(
                deploy_all_ordered_mods,
                self.dashboard.staging_path,
                self.dashboard.game_path,
                self.dashboard.staging_metadata_path
            )
            self.populate_list()
            return True
        return False

    def check_for_updates(self, btn):
        staging_metadata = load_metadata(self.dashboard.staging_metadata_path)
        if not staging_metadata: return
        game_id = staging_metadata.get("info", {}).get("nexus_id")
        if not game_id: return

        btn.set_sensitive(False)

        def on_updates_checked(mods_updated, updated_metadata):
            if mods_updated:
                save_metadata(updated_metadata, self.dashboard.staging_metadata_path)
                self.populate_list()
            btn.set_sensitive(True)

        check_for_mod_updates_async(staging_metadata, self.dashboard.headers, game_id, on_updates_checked)