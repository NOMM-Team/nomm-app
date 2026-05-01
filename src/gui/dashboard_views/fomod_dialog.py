import re

from gi.repository import Adw, GObject, Gtk


class FomodSelectionDialog(Gtk.Window):
    
    __gsignals__ = {
        'response': (GObject.SignalFlags.RUN_LAST, None, (int,))
    }
    
    def __init__(self, parent, module_name, options):
        super().__init__(title=f"Installer: {module_name}", transient_for=parent, modal=True)
        self.set_default_size(1200, 800)
        self.add_css_class("fomod-dialog")
        self.options_map = {}
        
        # Initializing every container
        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer_box.set_halign(Gtk.Align.FILL)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer_box.append(spacer)
        footer_box.add_css_class('footer-box')
        
        self.set_child(content_area)
        
        # Header alignments
        header_box.set_margin_top(15)
        header_box.set_margin_bottom(15)
        header_box.set_margin_start(30)
        header_box.set_margin_end(30)
        header_box.set_spacing(5)
        
        # Main content alignment
        main_box.set_margin_top(15)
        main_box.set_margin_bottom(0)
        main_box.set_margin_start(30)
        main_box.set_margin_end(30)
        
        # Footer alignment
        footer_box.set_margin_top(0)
        footer_box.set_margin_bottom(0)
        footer_box.set_margin_start(0)
        footer_box.set_margin_end(0)
        footer_box.set_spacing(5)
        
        # Window title
        fomod_label = Gtk.Label(label='FOMOD INSTALLER', xalign=0)
        fomod_label.add_css_class("title-2")
        fomod_label.add_css_class("dim-label")
        header_box.append(fomod_label)
        
        # Mod name
        header = Gtk.Label(label=module_name, xalign=0)
        header.add_css_class("title-1")
        header_box.append(header)
        
        # Instructions
        fomod_desc = Gtk.Label(label="This mod offers multiple variants, pick one you'd like to install", xalign=0)
        fomod_desc.add_css_class("desc")
        fomod_desc.add_css_class("dim-label")
        header_box.append(fomod_desc)
        
        # Initializing the list box to pick an option
        main_box.list_box = Gtk.ListBox(css_classes=["boxed-list"])
        #TODO: add a condition if multiple choices are allowed
        main_box.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        main_box.list_box.connect("row-selected", self.on_row_selected)
        
        first_radio = None
        
        # Looping on items to fill the list box
        for name, desc, source in options:
            
            clean_desc = desc.replace('\n', ' ').replace('\r', '').strip()
            clean_desc = re.sub(' +', ' ', clean_desc)
            
            if source == '':
                continue
            radio = Gtk.CheckButton(group=first_radio)
            if not first_radio:
                first_radio = radio
            
            # Setting up the row UI
            row_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row_content.set_margin_start(12)
            row_content.set_margin_end(12)
            row_content.set_margin_top(10)
            row_content.set_margin_bottom(10)
            
            text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            
            name_label = Gtk.Label(label=name, xalign=0)
            name_label.add_css_class("heading")
            
            desc_label = Gtk.Label(label=clean_desc, xalign=0, wrap=False)
            desc_label.add_css_class("dim-label")
            desc_label.add_css_class("caption")
            desc_label.set_ellipsize(3)
            desc_label.set_lines(1)
            
            text_vbox.append(name_label)
            text_vbox.append(desc_label)
            
            row_content.append(radio)
            row_content.append(text_vbox)
            
            # Allows to retrieve row content
            row = Gtk.ListBoxRow()
            row.set_child(row_content)
            row.radio_button = radio
            row.name_label = name
            
            # Adding row to the UI
            main_box.list_box.append(row)
            self.options_map[radio] = source
            
        # Setting up a scrollable box
        scrolled = Gtk.ScrolledWindow(
            propagate_natural_height=True, 
            vexpand=True, 
            hexpand=False
        )
        scrolled.set_max_content_height(350)
        scrolled.add_css_class("scrolled")
        scrolled.set_child(main_box.list_box)
        main_box.append(scrolled)
        
        # Vertical separator between the mod list and the preview
        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(separator)
        
        # Setting up the preview area on the right
        content_area.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_area.right_box.set_hexpand(True)
        content_area.right_box.add_css_class("boxed-preview")
        main_box.append(content_area.right_box)
        
        # Replace box by an image once I retrieve datas from the FOMOD
        mod_image_preview = Gtk.Box()
        
        # Initializing buttons to confirm/cancel choices
        self.install_btn = Gtk.Button(label=f"Install")
        cancel_btn = Gtk.Button(label="Cancel")
        
        cancel_btn.connect("clicked", self.on_cancel_clicked)
        self.install_btn.connect("clicked", self.on_install_clicked)
        self.install_btn.add_css_class('install-btn')
        self.set_default_widget(self.install_btn)
        
        footer_box.append(cancel_btn)
        footer_box.append(self.install_btn)
        
        # Initializing selection at first row
        first_row = main_box.list_box.get_row_at_index(0)
        if first_row:
            main_box.list_box.select_row(first_row)
        
        # Preparing two separators for the GUI
        title_separator = Gtk.Separator()
        title_separator2 = Gtk.Separator()
        
        # Adding each components to the main container
        content_area.append(header_box)
        content_area.append(title_separator)
        content_area.append(main_box)
        content_area.append(title_separator2)
        content_area.append(footer_box)

    def on_row_selected(self, list_box, row):
        if hasattr(row, "radio_button"):
            self.install_btn.set_label(f"Install {row.name_label}")
            row.radio_button.set_active(True)

    def get_selected_source(self):
        for radio, source in self.options_map.items():
            if radio.get_active():
                return source
        return None
    
    def on_install_clicked(self, button):
        self.emit("response", Gtk.ResponseType.OK)
        self.close()

    def on_cancel_clicked(self, button):
        self.emit("response", Gtk.ResponseType.CANCEL)
        self.close()