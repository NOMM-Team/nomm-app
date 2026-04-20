# src/gui/dialogs.py

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

from gi.repository import Gtk

class FomodSelectionDialog(Gtk.Dialog):
    def __init__(self, parent, module_name, options):
        super().__init__(title=f"Installer: {module_name}", transient_for=parent, modal=True)
        self.set_default_size(500, -1)
        self.add_css_class("fomod-dialog")
        self.options_map = {}
        
        content_area = self.get_content_area()
        content_area.set_spacing(15)
        
        content_area.set_margin_top(20)
        content_area.set_margin_bottom(20)
        content_area.set_margin_start(20)
        content_area.set_margin_end(20)

        header = Gtk.Label(label=module_name, xalign=0)
        header.add_css_class("title-2")
        content_area.append(header)

        self.list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.connect("row-activated", self.on_row_activated)

        first_radio = None
        
        for name, desc, source in options:
            radio = Gtk.CheckButton(group=first_radio)
            if not first_radio:
                first_radio = radio
            
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

            row = Gtk.ListBoxRow()
            row.set_child(row_content)
            row.radio_button = radio
            
            self.list_box.append(row)
            self.options_map[radio] = source

        scrolled = Gtk.ScrolledWindow(
            propagate_natural_height=True, 
            vexpand=True, 
            hexpand=True
        )
        scrolled.set_max_content_height(700)
        scrolled.set_child(self.list_box)
        content_area.append(scrolled)

        self.add_button("Install", Gtk.ResponseType.OK)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.set_default_response(Gtk.ResponseType.OK)

    def on_row_activated(self, list_box, row):
        if hasattr(row, "radio_button"):
            row.radio_button.set_active(True)

    def get_selected_source(self):
        for radio, source in self.options_map.items():
            if radio.get_active():
                return source
        return None