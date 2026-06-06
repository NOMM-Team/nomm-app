import gettext
import os
import webbrowser
import threading

from datetime import datetime
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, GObject, Gtk, Gio, GdkPixbuf, Pango

from core.mod_manager import (apply_deployment_map_changes, build_deployment_map,
                              change_mod_index, check_for_conflicts,
                              check_for_deployment_map_change,
                              load_staging_metadata, read_index,
                              toggle_mod_state)
from core.nexus_api import check_for_mod_updates_async, endorse_nexus_mod
from core.tools import timestamp_converter, write_yaml, process_bbcode
from gui.text_window import TextWindow

_ = gettext.gettext
ngettext = gettext.ngettext

class ModsTab(Gtk.Box):
    def __init__(self, dashboard):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_start(15)
        self.set_margin_end(15)
        self.set_margin_top(20)

        self.dashboard = dashboard

        # Deployment map is used to redeploy files while moving items
        staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
        self.deployment_map = build_deployment_map(staging_metadata)

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
        self.mods_list_box = Gtk.ListBox(css_classes=["dashboard-list"])
        self.mods_list_box.set_filter_func(self.filter_mods_rows)
        self.mods_list_box.connect("row-activated", self.on_row_clicked) 
        self.mods_list_box.set_overflow(Gtk.Overflow.HIDDEN)
        self.list_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, css_classes=["shadow-box"])
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
        self.preview_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_start=15)
        self.preview_pane.set_size_request(390, -1)
        self.preview_pane.set_hexpand(False)

        # This is used for the close button left of the preview
        self.preview_overlay = Gtk.Overlay()

        # Container for the image to handle centering and potential rounding
        self.thumb_container = Gtk.Box(halign=Gtk.Align.CENTER)
        self.thumb_container.set_size_request(300, 168)
        self.thumb_container.add_css_class("rounded-thumb")
        self.thumb_container.set_overflow(Gtk.Overflow.HIDDEN)
        self.thumb_container.set_hexpand(False)
        self.preview_pane.append(self.thumb_container)

        # Header with close button
        header = Gtk.CenterBox(margin_top=10)
        self.preview_title = Gtk.Label(css_classes=["title-1"])
        self.preview_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.preview_title.set_max_width_chars(38)
        #self.preview_title.set_width_chars(35)
        header.set_center_widget(self.preview_title)
        
        self.preview_pane.append(header)

        # Metadata Display
        self.details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_start=10, margin_end=10)

        # Info Row
        self.info_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.info_row.set_margin_top(10)
        self.info_row.set_visible(False)
        # Info Row title
        info_row_label = Gtk.Label(label=_("More Info:"), css_classes=["dim-label"])
        self.info_row.append(info_row_label)
        # Description button
        self.description_btn = Gtk.Button(label=_("Mod Description"))
        self.description_btn.set_cursor_from_name("pointer")
        self.description_btn.add_css_class("badge-action-row")
        self.info_row.append(self.description_btn)
        # Nexus button
        self.nexus_btn = Gtk.Button(label=_("Nexus"))
        self.nexus_btn.set_cursor_from_name("pointer")
        self.nexus_btn.add_css_class("badge-action-row")
        self.info_row.append(self.nexus_btn)
        self.details_box.append(self.info_row)

        # Contents Row
        self.contents_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.contents_row.set_visible(False)
        contents_row_label = Gtk.Label(label=_("Mod Contents:"), css_classes=["dim-label"])
        self.contents_row.append(contents_row_label)
        # File counter
        self.files_btn = Gtk.Button()
        self.files_btn.set_cursor_from_name("pointer")
        self.files_btn.add_css_class("badge-action-row")
        self.contents_row.append(self.files_btn)
        self.details_box.append(self.contents_row)

        # Version Row
        self.version_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.version_row.set_visible(False)
        version_row_label = Gtk.Label(label=_("Versioning:"), css_classes=["dim-label"])
        self.version_row.append(version_row_label)
        # Version Badge
        self.version_btn = Gtk.Button()
        self.version_btn.set_cursor_from_name("pointer")
        button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_content.set_halign(Gtk.Align.CENTER)
        self.version_btn_changelog_icon = Gtk.Image.new_from_icon_name("help-about-symbolic")
        self.version_btn_changelog_icon.set_visible(False)
        self.version_btn_label = Gtk.Label()
        self.version_btn_upgrade_icon = Gtk.Image.new_from_icon_name("software-update-available-symbolic")
        self.version_btn_upgrade_icon.set_visible(False)
        self.version_btn_label_new = Gtk.Label()
        self.version_btn_label_new.set_visible(False)
        button_content.append(self.version_btn_changelog_icon)
        button_content.append(self.version_btn_label)
        button_content.append(self.version_btn_upgrade_icon)
        button_content.append(self.version_btn_label_new)
        self.version_btn.set_child(button_content)
        self.version_btn.add_css_class("badge-action-row")
        self.version_row.append(self.version_btn)
        self.details_box.append(self.version_row)
        
        # Deployment Row
        self.deployment_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.deployment_row.set_visible(False)
        deployment_row_label = Gtk.Label(label=_("Deploy to Path:"), css_classes=["dim-label"])
        self.deployment_row.append(deployment_row_label)
        # Deployment path button
        self.deployment_btn = Gtk.Button()
        self.deployment_btn.set_cursor_from_name("pointer")
        self.deployment_btn.add_css_class("badge-action-row")
        self.deployment_label = Gtk.Label()
        self.deployment_label.set_ellipsize(Pango.EllipsizeMode.START)
        self.deployment_label.set_max_width_chars(25)
        self.deployment_btn.set_child(self.deployment_label)
        self.deployment_row.append(self.deployment_btn)
        # Deployment path change button
        self.deployment_update_btn = Gtk.Button()
        self.deployment_update_btn.set_cursor_from_name("pointer")
        self.deployment_update_btn.add_css_class("badge-action-row")
        deployment_update_btn_icon = Gtk.Image.new_from_icon_name("edit-symbolic")
        self.deployment_update_btn.set_child(deployment_update_btn_icon)
        self.deployment_row.append(self.deployment_update_btn)
        self.details_box.append(self.deployment_row)

        # Uploader Row
        self.uploader_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.uploader_row.set_visible(False)
        uploader_row_label = Gtk.Label(label=_("Uploader:"), css_classes=["dim-label"])
        self.uploader_row.append(uploader_row_label)
        # Uploader button
        self.uploader_btn = Gtk.Button()
        self.uploader_btn.set_cursor_from_name("pointer")
        self.uploader_btn.add_css_class("badge-action-row")
        self.uploader_row.append(self.uploader_btn)
        self.details_box.append(self.uploader_row)

        # Endorsement Row
        self.endorsement_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.endorsement_row.set_visible(False)
        endorsement_row_label = Gtk.Label(label=_("Endorsements:"), css_classes=["dim-label"])
        self.endorsement_row.append(endorsement_row_label)
        # Endorse button
        self.endorse_btn = Gtk.Button()
        self.endorse_btn.set_cursor_from_name("pointer")
        endorse_button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        endorse_button_content.set_halign(Gtk.Align.CENTER)
        self.endorse_btn_icon = Gtk.Image()
        self.endorse_btn_label = Gtk.Label()
        endorse_button_content.append(self.endorse_btn_label)
        endorse_button_content.append(self.endorse_btn_icon)
        self.endorse_btn.set_child(endorse_button_content)
        self.endorse_btn.add_css_class("badge-action-row")
        self.endorsement_row.append(self.endorse_btn)
        self.details_box.append(self.endorsement_row)

        # Mod ID matcher Row
        self.mod_id_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mod_id_row_label = Gtk.Label(label=_("Mod ID:"), css_classes=["dim-label"])
        self.mod_id_row.append(mod_id_row_label)
        # Mod ID update button
        self.mod_id_btn = Gtk.Button()
        self.mod_id_btn.set_cursor_from_name("pointer")
        self.mod_id_btn.add_css_class("badge-action-row")
        self.mod_id_row.append(self.mod_id_btn)
        self.details_box.append(self.mod_id_row)

        self.preview_pane.append(self.details_box)
        self.preview_overlay.set_child(self.preview_pane)

        # Close button
        close_btn = Gtk.Button(icon_name="go-next-symbolic", css_classes=["flat"], halign=Gtk.Align.CENTER)
        close_btn.set_cursor_from_name("pointer")
        close_btn.add_css_class("floating-close-btn")
        close_btn.connect("clicked", lambda x: self.on_close_preview())
        close_btn.set_valign(Gtk.Align.CENTER)
        close_btn.set_halign(Gtk.Align.START)
        self.preview_overlay.add_overlay(close_btn)
        
        self.revealer.set_child(self.preview_overlay)

    def on_close_preview(self):
        self.mods_list_box.select_row(None)
        self.revealer.set_reveal_child(False)

    def on_row_clicked(self, listbox, row):
        # We need to fetch the metadata associated with this row

        mod_name = row.get_title() # ActionRow title
        mod_info = row.mod_data

        # Update labels
        self.preview_title.set_label(mod_name)

        # Add thumbnail
        thumbnail_path = mod_info.get("thumbnail")
        if thumbnail_path and os.path.exists(thumbnail_path):
            thumb_path = thumbnail_path
        else:
            thumb_path = self.dashboard.assets_path + "/nomm.png"

        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            thumb_path, 405, 1000, True
        )
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        self.preview_thumbnail = Gtk.Picture.new_for_paintable(texture)
        self.preview_thumbnail.set_hexpand(False)
        self.preview_thumbnail.set_vexpand(False)
        # Clear previous image
        while child := self.thumb_container.get_first_child():
            self.thumb_container.remove(child)
        # Add new one
        self.thumb_container.append(self.preview_thumbnail)

        # Info Row
        if "description" in mod_info and mod_info["description"]:
            # Description button
            with open(mod_info["description"]) as f:
                description = f.read()
            self.info_row.set_visible(True)
            title = _(f"Mod Description for {mod_info.get("display_name", mod_info.get("name"))}")
            if hasattr(self, "_desc_handler_id"):
                self.description_btn.disconnect(self._desc_handler_id)    
            self._desc_handler_id = self.description_btn.connect("clicked", self.on_description_btn_clicked, title, description)
            # Nexus button
            if hasattr(self, "_nexus_link_handler_id"):
                self.nexus_btn.disconnect(self._nexus_link_handler_id)    
            self._nexus_link_handler_id = self.nexus_btn.connect("clicked", lambda b: webbrowser.open(mod_info["mod_link"]))
        else:
            self.info_row.set_visible(False)

        # Contents row
        if "mod_files" in mod_info:
            number_of_files = len(mod_info["mod_files"])
            self.files_btn.set_tooltip_text("\n".join(mod_info["mod_files"]))
            self.files_btn.set_label(ngettext("{} File", "{} Files", number_of_files).format(number_of_files))
            folder_path = self.dashboard.staging_path / mod_info.get("folder_name", mod_info.get("display_name"))
            # Disconnect previous connect
            if hasattr(self, "_files_handler_id") and self._files_handler_id:
                self.files_btn.disconnect(self._files_handler_id)
            # Connect and store new ID
            self._files_handler_id = self.files_btn.connect("clicked", lambda x: webbrowser.open(f"file://{folder_path}"))
            self.contents_row.set_visible(True)
        else:
            self.contents_row.set_visible(False)

        # Version Row
        if "version" in mod_info:
            self.version_btn_label.set_label(mod_info["version"])
            self.version_row.set_visible(True)
            if hasattr(self, "_version_link_handler_id"):
                self.version_btn.disconnect(self._version_link_handler_id)    
            self._version_link_handler_id = self.version_btn.connect("clicked", lambda b: webbrowser.open(mod_info["mod_link"] + "?tab=files"))
            # Changelog Tooltip
            if "changelog" in mod_info and mod_info["changelog"]:
                self.version_btn_changelog_icon.set_visible(True)
                self.version_btn.set_tooltip_text(mod_info["changelog"])
            else:
                self.version_btn_changelog_icon.set_visible(False)
                self.version_btn.set_tooltip_text("")
            # Update management
            if "new_version" in mod_info and mod_info["version"] != mod_info["new_version"]:
                self.version_btn.add_css_class("badge-action-row-accent")
                self.version_btn_label.set_label(mod_info["version"])
                self.version_btn_label_new.set_label(mod_info["new_version"])
                self.version_btn_label_new.set_visible(True)
                self.version_btn_upgrade_icon.set_visible(True)
            else:
                self.version_btn.remove_css_class("badge-action-row-accent")
                self.version_btn_label_new.set_visible(False)
                self.version_btn_upgrade_icon.set_visible(False)
        else:
            self.version_row.set_visible(False)

        # Deployment Row
        if "deployment_path" in mod_info:
            self.deployment_label.set_label(mod_info["deployment_path"])
            self.deployment_label.set_tooltip_text(mod_info["deployment_path"])
            if hasattr(self, "_deployment_handler_id") and self._deployment_handler_id:
                self.deployment_btn.disconnect(self._deployment_handler_id)
            # Connect and store new ID
            self._deployment_handler_id = self.deployment_btn.connect("clicked", lambda x: webbrowser.open(f"file://{mod_info["deployment_path"]}"))
            self.deployment_row.set_visible(True)
            if mod_info["status"] == "disabled": # only show modify button if the mod is disabled
                self.deployment_update_btn.set_visible(True)
                if hasattr(self, "_update_handler_id") and self._update_handler_id:
                    self.deployment_update_btn.disconnect(self._update_handler_id)
                self._update_handler_id = self.deployment_update_btn.connect(
                    "clicked",
                    lambda x: self.pick_new_deployment_path(mod_info, row.mod_data_index))
            else:
                self.deployment_update_btn.set_visible(False)
        else:
            self.deployment_row.set_visible(False)

        # Uploader Row
        if "uploader" in mod_info:
            self.uploader_btn.set_label(mod_info["uploader"])
            uploader_link = f"https://www.nexusmods.com/profile/{mod_info["uploader"]}"
            if hasattr(self, "_uploader_link_handler_id"):
                self.uploader_btn.disconnect(self._uploader_link_handler_id)    
            self._uploader_link_handler_id = self.uploader_btn.connect("clicked", lambda b: webbrowser.open(uploader_link))
            self.uploader_row.set_visible(True)
        else:
            self.uploader_row.set_visible(False)

        # Endorsement Row
        if "endorsements" in mod_info and mod_info["endorsements"]:
            self.endorse_btn_label.set_label(str(mod_info["endorsements"]))
            # Remove any current link on button
            if hasattr(self, "_endorse_link_handler_id"):
                self.endorse_btn.disconnect(self._endorse_link_handler_id)
            if "endorsed" not in mod_info or not mod_info.get("endorsed"):
                # Not endorsed yet
                self.endorse_btn_icon.set_from_icon_name("go-up-symbolic")
                self.endorse_btn.remove_css_class("badge-action-row-accent")
                self._endorse_link_handler_id = self.endorse_btn.connect("clicked", self.on_endorse_button_clicked, mod_info, row.mod_data_index, False)
            else:
                # Already endorsed
                self.endorse_btn_icon.set_from_icon_name("go-down-symbolic")
                self.endorse_btn.add_css_class("badge-action-row-accent")
                self._endorse_link_handler_id = self.endorse_btn.connect("clicked", self.on_endorse_button_clicked, mod_info, row.mod_data_index, True)
            self.endorsement_row.set_visible(True)
        else:
            self.endorsement_row.set_visible(False)

        # Mod Info Row
        if "mod_id" in mod_info and mod_info["mod_id"]:
            self.mod_id_btn.remove_css_class("badge-action-row-accent")
            self.mod_id_btn.set_label(mod_info["mod_id"])
        else:
            self.mod_id_btn.add_css_class("badge-action-row-accent")
            self.mod_id_btn.set_label(_("No mod ID registered"))
        self.mod_id_btn.set_tooltip_text(_("Change currently linked mod ID.\nThis will require a refresh of the metadata and will be reset if you reinstall the mod."))
        if hasattr(self, "_mod_id_handler_id") and self._mod_id_handler_id:
            self.mod_id_btn.disconnect(self._mod_id_handler_id)
        # Connect and store new ID
        self._mod_id_handler_id = self.mod_id_btn.connect("clicked", lambda x: self.pick_new_mod_id(mod_info, mod_name))

        # Display the pane!
        self.revealer.set_reveal_child(True)


    def on_description_btn_clicked(self, button, title, description):
        desc_win = TextWindow(self.dashboard.app.win, title, description, text_type="markup")
        desc_win.present()

    def pick_new_mod_id(self, mod_info, mod_index):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=_("Change Mod ID"),
            body=_("Enter the new Nexus ID for this mod. The next time you do a metadata update (top right button on the mods tab), this will completely replace the existing metadata for this mod.\nKeep in mind that if you reinstall this mod from its archive file, the metadata will be overwritten and you will have to change this value again."),
        )

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        
        # Style the 'Save' button using your theme's primary accent color
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        
        # Set 'Save' as the default action when hitting Enter
        dialog.set_default_response("save")

        entry_box = Gtk.ListBox()
        entry_box.add_css_class("boxed-list") # Crucial Adwaita styling class

        entry_row = Adw.EntryRow(title=_("Mod ID"))
        entry_row.set_activates_default(True) # Pressing Enter triggers the default dialog action
        
        # Pre-populate with current tracking ID
        current_id = str(mod_info.get("mod_id", ""))
        if current_id:
            entry_row.set_text(current_id)

        entry_box.append(entry_row)

        dialog.set_extra_child(entry_box)

        def on_response(source_dialog, response_id):
            if response_id == "save":
                new_id = entry_row.get_text().strip()
                if not new_id:
                    return # Skip if blank

                # Write changes back out to your YAML file context
                staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
                staging_metadata["mods"][mod_index]["mod_id"] = new_id
                write_yaml(staging_metadata, self.dashboard.staging_metadata_path)

                # Instantly reflect the change on the UI badge element
                self.mod_id_btn.set_label(new_id)
                self.mod_id_btn.remove_css_class("badge-action-row-accent")

            # Cleanly destroy the dialog window tracking allocation
            source_dialog.destroy()
            self.populate_list()
        dialog.connect("response", on_response)
        # Bring the layout cleanly into focus
        dialog.present()

    def pick_new_deployment_path(self, mod_info, mod_index):
        # Create the FileChooserNative
        picker = Gtk.FileChooserNative(
            title=_("Select New Deployment Directory"),
            transient_for=self.get_root(), # 'self' assumes you are in a widget/window
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label=_("_Select"),
            cancel_label=_("_Cancel"),
        )

        # Pre-select the existing path
        current_path = mod_info.get("deployment_path")
        if current_path:
            # Convert string path to a Gio.File object
            folder = Gio.File.new_for_path(current_path)
            picker.set_current_folder(folder)

        # Handle the response
        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                selected_file = dialog.get_file()
                new_path = selected_file.get_path()
                
                # Logic to save the new path
                staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
                staging_metadata["mods"][mod_index]["deployment_path"] = new_path
                write_yaml(staging_metadata, self.dashboard.staging_metadata_path)
                
                # Update UI label immediately
                self.deployment_label.set_label(new_path)
                self.deployment_label.set_tooltip_text(new_path)
                
            dialog.destroy()

        picker.connect("response", on_response)
        picker.show()

    def on_endorse_button_clicked(self, button, mod_info: dict, mod_index: str, unendorse: bool):
        if endorse_nexus_mod(self.dashboard.headers, self.dashboard.game_config["nexus_id"], mod_info["mod_id"], unendorse):
            if unendorse: # we just unendorsed the mod
                print(f"Successfully unendorsed mod {mod_info.get("display_name", mod_info.get("name"))}")
                self.endorse_btn_label.set_label(str(mod_info["endorsements"]))
                self.endorse_btn.remove_css_class("badge-action-row-accent")
                self.endorse_btn_icon.set_from_icon_name("go-up-symbolic")
            else: # we just endorsed the mod
                print(f"Successfully endorsed mod {mod_info.get("display_name", mod_info.get("name"))}")
                self.endorse_btn_label.set_label(str(mod_info["endorsements"] + 1))
                self.endorse_btn.add_css_class("badge-action-row-accent")
                self.endorse_btn_icon.set_from_icon_name("go-down-symbolic")
            # Save state to metadata
            staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
            staging_metadata["mods"][mod_index]["endorsed"] = not unendorse
            write_yaml(staging_metadata, self.dashboard.staging_metadata_path)
            self.populate_list()
        else:
            self.dashboard.show_message(_("Failed to endorse"), _("Could not endorse the selected mod, please make sure you have provided your API key and are connected to the internet."))

    def populate_list(self):
        while child := self.mods_list_box.get_first_child():
            self.mods_list_box.remove(child)

        staging_path = self.dashboard.staging_path
        staging_metadata = load_staging_metadata(self.dashboard.staging_metadata_path)
        
        if not staging_metadata or not staging_metadata.get("mods"):
            self.append(Gtk.Label(label=_("The staging metadata file could not be found, did you install any mods?"), css_classes=["dim-label"]))
            return

        conflicts = check_for_conflicts(self.dashboard.staging_metadata_path)
        load_index_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        
        indexed_mods = read_index(self.dashboard.staging_metadata_path)

        enable_file_counter = False
        for mod in staging_metadata.get("mods"):
            if len(staging_metadata["mods"][mod]["mod_files"]) > 1:
                enable_file_counter = True
                break
        
        for index, mod in enumerate(indexed_mods, start=1):
            
            if mod not in staging_metadata["mods"]:
                continue
            
            mod_metadata = staging_metadata["mods"][mod]

            display_name = mod_metadata.get("display_name", mod)
            folder_name = mod_metadata.get("folder_name", mod)
            
            changelog = mod_metadata.get("changelog", "")
            mod_link = mod_metadata.get("mod_link", "")
            mod_files = mod_metadata.get("mod_files", [])

            row = Adw.ActionRow(title=display_name)
            row.set_activatable(True)
            row.mod_data = mod_metadata
            row.mod_data_index = mod
            row.set_subtitle(mod_metadata.get("author", ""))
            row.mod_name = mod_metadata.get(display_name.lower)

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
            missing_files = []
            mod_dir = staging_path / folder_name
            for mod_file in mod_files:    
                if not os.path.exists(mod_dir/mod_file):
                    missing_files.append(mod_file)
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
                if mod in conflict_list:
                    other_mods = conflict_list.copy()
                    other_mods.remove(mod)
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
                info_text_badge.connect("clicked", self.dashboard.load_text_file, Path(staging_path) / mod_metadata["folder_name"] / text_file)
                info_text_badge.set_valign(Gtk.Align.CENTER)
                info_text_badge.set_margin_end(row_element_margin)
                row.add_suffix(info_text_badge)

            # Update available badge
            version_current = mod_metadata.get("version", "")
            version_new = mod_metadata.get("new_version", "")
            if version_current and version_new and (version_new != version_current):
                update_badge = Gtk.Button(margin_top=10, margin_bottom=10)
                update_badge_icon = Gtk.Image.new_from_icon_name("software-update-available-symbolic")
                update_badge_icon.set_pixel_size(22)
                update_badge.connect("clicked", lambda b, link=mod_link: webbrowser.open(link + "?tab=files"))
                update_badge_icon.add_css_class("transparent-bg-accent-icon")
                update_badge.set_child(update_badge_icon)
                update_badge.set_cursor_from_name("pointer")
                row.add_suffix(update_badge)

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

            self.mods_list_box.append(row)

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

        if state:
            self.deployment_update_btn.set_visible(False)
        else:
            self.deployment_update_btn.set_visible(True)
        
        def worker():
            deployment_output = toggle_mod_state(
                mod_name=mod,
                mod_files=mod_files,
                state=state,
                staging_dir=str(self.dashboard.staging_path),
                deployment_targets=self.dashboard.deployment_targets,
                deployment_map=self.deployment_map
            )
            GLib.idle_add(on_toggle_done, deployment_output)
            
        def on_toggle_done(deployment_output):
            if deployment_output["success"] == True:
                self.deployment_map = deployment_output['deployment_map']
            # UI Fallback if toggle fail
            self.dashboard.currently_toggling.discard(mod)
            switch.set_sensitive(True)
            if state and not deployment_output['success']:
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
    
    def on_row_drop(self, target, value, _x, _y, mod_name):
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
            new_staging_metadata = change_mod_index(self.dashboard.staging_metadata_path, value, target_index)
            
            # Redeploy the files that changed
            new_deployment_map = build_deployment_map(new_staging_metadata)
            if new_deployment_map != self.deployment_map:
                changes = check_for_deployment_map_change(new_deployment_map, self.deployment_map)
                apply_deployment_map_changes(self.dashboard.staging_path, dest_dir, changes, mod_name)
                self.deployment_map = new_deployment_map
            
            # Refresh UI
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

        def on_updates_checked(updated_metadata):
            write_yaml(updated_metadata, self.dashboard.staging_metadata_path)
            self.populate_list()
            btn.set_sensitive(True)

        check_for_mod_updates_async(staging_metadata, self.dashboard.headers, nexus_id, Path(self.dashboard.downloads_path), on_updates_checked)