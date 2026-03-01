import os
import zipfile
import yaml
import shutil
import xml.etree.ElementTree as ET

import gi 
gi.require_version("Gtk", "4.0") 
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class FomodSelectionDialog(Gtk.Dialog):
    def __init__(self, parent, module_name, options):
        super().__init__(title=f"Installer: {module_name}", transient_for=parent, modal=True)
        self.set_default_size(500, -1)
        self.add_css_class("fomod-dialog")
        self.options_map = {}
        
        content_area = self.get_content_area()
        content_area.set_spacing(15)
        
        # Manually setting margins because Gtk.Box doesn't support set_margin_all
        content_area.set_margin_top(20)
        content_area.set_margin_bottom(20)
        content_area.set_margin_start(20)
        content_area.set_margin_end(20)

        header = Gtk.Label(label=module_name, xalign=0)
        header.add_css_class("title-2")
        content_area.append(header)

        # 1. Create the ListBox to house our clickable rows
        self.list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        
        # Connect the signal so clicking anywhere in the row toggles the radio
        self.list_box.connect("row-activated", self.on_row_activated)

        first_radio = None
        
        for name, desc, source in options:
            # 2. Create the Radio Button
            radio = Gtk.CheckButton(group=first_radio)
            if not first_radio:
                first_radio = radio
            
            # 3. Create the Row Layout
            row_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row_content.set_margin_start(12)
            row_content.set_margin_end(12)
            row_content.set_margin_top(10)
            row_content.set_margin_bottom(10)
            
            text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            
            name_label = Gtk.Label(label=name, xalign=0)
            name_label.add_css_class("heading")
            
            desc_label = Gtk.Label(label=desc, xalign=0, wrap=True)
            desc_label.add_css_class("dim-label")
            desc_label.add_css_class("caption")
            
            text_vbox.append(name_label)
            text_vbox.append(desc_label)
            
            row_content.append(radio)
            row_content.append(text_vbox)

            # 4. Wrap everything in a ListBoxRow
            row = Gtk.ListBoxRow()
            row.set_child(row_content)
            
            # Custom attribute to link the row back to its radio button
            row.radio_button = radio
            
            self.list_box.append(row)
            self.options_map[radio] = source

        # 5. Add a ScrolledWindow
        # We add 'vexpand=True' so it grows with the window
        scrolled = Gtk.ScrolledWindow(
            propagate_natural_height=True, 
            vexpand=True, 
            hexpand=True
        )
        
        # You can keep max_content_height for the INITIAL size, 
        # but vexpand will override it once the window is resized.
        scrolled.set_max_content_height(700)
        
        scrolled.set_child(self.list_box)
        content_area.append(scrolled)

        # 6. Action Buttons
        self.add_button("Install", Gtk.ResponseType.OK)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.set_default_response(Gtk.ResponseType.OK)

    def on_row_activated(self, list_box, row):
        """Callback to toggle the radio button when the row is clicked."""
        if hasattr(row, "radio_button"):
            row.radio_button.set_active(True)

    def get_selected_source(self):
        """Returns the source folder associated with the selected radio button."""
        for radio, source in self.options_map.items():
            if radio.get_active():
                return source
        return None

def parse_fomod_xml(xml_data):
    """Parses the FOMOD XML and returns a list of (name, description, source_folder)"""
    try:
        root = ET.fromstring(xml_data)
        options = []
        # Find all plugins (options) within the XML structure
        for plugin in root.findall(".//plugin"):
            name = plugin.get('name')
            desc_node = plugin.find('description')
            desc = desc_node.text.strip() if desc_node is not None and desc_node.text else "No description provided."
            
            folder_node = plugin.find(".//folder")
            source = folder_node.get('source') if folder_node is not None else None
            
            if source:
                options.append((name, desc, source))
        
        module_name = root.findtext('moduleName') or "Unknown Mod"
        return module_name, options
    except Exception as e:
        print(f"Failed to parse FOMOD XML: {e}")
        return None, []
