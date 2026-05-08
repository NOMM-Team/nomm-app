import os
import pathlib
import re
import os
import pathlib
import re

from gi.repository import Adw, Gdk, GdkPixbuf, GObject, Gtk

from core.fomod_manager import (check_for_dependencies,
                                check_for_plugin_dependencies,
                                generate_source_from_flags,
                                get_fomod_group_count, get_fomod_group_info,
                                get_fomod_group_options, get_fomod_step_count,
                                get_plugin_image_path, get_plugin_type,
                                have_plugins_images, is_step_visible)
from core.tools import retrieve_casesensitive_paths
from gui.text_window import TextWindow


class FomodSelectionDialog(Adw.Window):
    
    __gsignals__ = {
        'response': (GObject.SignalFlags.RUN_LAST, None, (int,))
    }
    
    def __init__(self, parent, fomod_metadata, mod_staging_dir, game_dest):
        
        module_name = fomod_metadata['module_name']
        super().__init__(transient_for=parent, modal=True)
        
        self.module_data = fomod_metadata['module_data']
        self.flags_data = fomod_metadata['flags_data']
        
        # Sources registered for every step/group
        self.global_sources = []
        self.active_flags = {}
        self.flags_history = []
        self.required_data = fomod_metadata['required_data']
        dependencies_data = fomod_metadata['dependencies_data']
        
        # Sources registered for every step/group
        self.global_sources = []
        self.active_flags = {}
        self.flags_history = []
        self.required_data = fomod_metadata['required_data']
        dependencies_data = fomod_metadata['dependencies_data']
        
        # Initializing the current step for multiple-steps FOMods
        self.current_step = 0
        self.current_group = 0
        
        options = get_fomod_group_options(self.module_data)
        
        # Look for the fomod path in case the archive is 
        # mod_arc/mod_name/FOMOD instead of mod_arc/FOMOD
        self.fomod_staging_dir = mod_staging_dir
        for root, dirs, _files in os.walk(mod_staging_dir):
            if 'fomod' in [d.lower() for d in dirs]:
                self.fomod_staging_dir = root
                break
        
        self.game_dest = game_dest
        
        # Check if files exists
        if not check_for_dependencies(dependencies_data, self.game_dest):
           print('Error: Missing dependencies, mod probably wont work')
        
        self.set_default_size(1100, 622)
        self.add_css_class("fomod-dialog")
        self.options_map = {}
        self.flags_map = {}
        
        # Initializing every container
        root_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_container)

        # Window header bar
        header_bar = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(
            title=_("NOMM FOMOD Installer"),
        )
        header_bar.set_title_widget(self.title_widget)
        root_container.append(header_bar)

        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root_container.append(content_area)

        # Extra in-window header
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Others
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer_box.set_halign(Gtk.Align.FILL)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer_box.append(spacer)
        footer_box.add_css_class('footer-box')
        
        # Instructions
        self.fomod_desc = Gtk.Label(label='', xalign=0)
        self.fomod_desc.add_css_class("desc")
        self.fomod_desc.add_css_class("dim-label")
        
        # Instructions
        self.fomod_desc = Gtk.Label(label='', xalign=0)
        self.fomod_desc.add_css_class("desc")
        self.fomod_desc.add_css_class("dim-label")
        
        # Header alignments
        self.header_box.set_margin_top(15)
        self.header_box.set_margin_bottom(15)
        self.header_box.set_margin_start(30)
        self.header_box.set_margin_end(30)
        self.header_box.set_spacing(5)
        
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
        
        # Mod name
        header = Gtk.Label(label=module_name, xalign=0)
        header.add_css_class("title-1")
        self.header_box.append(header)
        
        self.header_box.append(self.fomod_desc)
        
        self.group_label = Gtk.Label(label='')
        self.group_label.add_css_class("title-2")
        self.group_label.add_css_class("dim-label")
        self.group_label.set_margin_top(10)
        self.group_label.set_margin_start(32)
        self.group_label.set_halign(Gtk.Align.START)
        
        # Initializing the list box to pick an option and adapting the instructions to match the selection mode
        main_box.list_box = Gtk.ListBox(css_classes=["boxed-list"])
        main_box.list_box.set_activate_on_single_click(True)
        main_box.list_box.connect("row-activated", self.on_row_selected)
        
        # Next button in case mod has multiple groups
        self.next_btn = Gtk.Button(label="Next")
        self.next_btn.connect("clicked", self.on_next_clicked, main_box.list_box)
        self.next_btn.set_cursor_from_name('pointer')
        self.next_btn.add_css_class('install-btn')
        
        # Previous button that will be displayed if current step > 1
        self.previous_btn = Gtk.Button(label="Previous")
        self.previous_btn.set_cursor_from_name('pointer')
        self.previous_btn.connect("clicked", self.on_previous_clicked, main_box.list_box)
        
        # Initializing buttons to confirm/cancel choices
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.set_cursor_from_name('pointer')
        cancel_btn.connect("clicked", self.on_cancel_clicked)
        
        self.install_btn = Gtk.Button(label="Install")
        self.install_btn.connect("clicked", self.on_install_clicked)
        self.install_btn.set_cursor_from_name('pointer')
        self.install_btn.add_css_class('install-btn')
        self.set_default_widget(self.install_btn)
            
        # Setting up a scrollable box
        self.scrolled = Gtk.ScrolledWindow(
            propagate_natural_height=True, 
            vexpand=True, 
            hexpand=False
        )
        self.scrolled.set_size_request(380, -1)
        self.scrolled.add_css_class("scrolled")
        self.scrolled.set_child(main_box.list_box)
        main_box.append(self.scrolled)
        
        # Vertical separator between the mod list and the preview
        self.vseparator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(self.vseparator)
        
        # Setting up the preview area on the right
        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.right_box.set_hexpand(True)
        self.right_box.add_css_class("boxed-preview")
        main_box.append(self.right_box)
        
        group_count = get_fomod_group_count(self.module_data)
        step_count = get_fomod_step_count(self.module_data)
        
        footer_box.append(cancel_btn)
        if group_count > 1 or step_count > 1:
            self.previous_btn.set_visible(False)
            footer_box.append(self.previous_btn)
            footer_box.append(self.next_btn)
        footer_box.append(self.install_btn)
        if group_count > 1 or step_count > 1:
            self.install_btn.set_visible(False)
        
        # Preparing two separators for the GUI
        title_separator = Gtk.Separator()
        title_separator2 = Gtk.Separator()
        
        self.populate_listbox(main_box.list_box, options)
        
        # Adding each components to the main container
        content_area.append(self.header_box)
        content_area.append(title_separator)
        content_area.append(self.group_label)
        content_area.append(main_box)
        content_area.append(title_separator2)
        content_area.append(footer_box)
    
    def populate_listbox(self, list_box, options):
        
        if not have_plugins_images(self.module_data, self.current_step, self.current_group):
            self.right_box.set_visible(False)
            self.vseparator.set_visible(False)
            self.scrolled.set_hexpand(True)
        else:
            self.right_box.set_visible(True)
            self.vseparator.set_visible(True)
            self.scrolled.set_hexpand(False)
        
        selection_type = get_fomod_group_info(self.module_data, self.current_step, self.current_group)['type']
        
        if selection_type == 'SelectExactlyOne':
            self.group_label.set_markup(_("<i>This mod offers multiple variants, pick one you'd like to install</i>"))
            list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        elif selection_type == 'SelectAtLeastOne':
            self.group_label.set_markup(_("<i>This mod offers multiple variants, pick one or more you'd like to install</i>"))
            list_box.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        elif selection_type == 'SelectAtMostOne':
            self.group_label.set_markup(_("<i>This mod offers multiple variants, pick at most one you'd like to install</i>"))
            list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        elif selection_type == 'SelectAny':
            self.group_label.set_markup(_("<i>This mod offers multiple variants, pick any plugin you'd like to install</i>"))
            list_box.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        elif selection_type == 'SelectAll':
            self.group_label.set_markup(_("<i>This mod offers multiple variants but you must pick all of them</i>"))
            list_box.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        elif selection_type == 'SelectAll':
            self.fomod_desc.set_label("This mod offers multiple variants but you must pick all of them")
            list_box.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        
        first_radio = None
        
        # Deleting the option map and flags map
        self.options_map = {}
        self.flags_map = {}
        
        extracted_information = []
        
        # Displaying group info if there is a group info
        group_name = get_fomod_group_info(self.module_data, self.current_step, self.current_group)['name']
        self.fomod_desc.set_label(group_name)
        
        plugin_index = 0
        
        is_not_usable = False
        
        plugin_index = 0
        
        is_not_usable = False
        
        # Looping on items to fill the list box
        for name, desc, source, flags in options:
            
            # Change dest dir to find the game folder
            plugin_type = check_for_plugin_dependencies(self.module_data, self.game_dest, self.current_step, self.current_group, plugin_index, self.active_flags)
            
            plugin_index += 1
            
            plugin_type = get_plugin_type(self.fomod_metadata, name, self.current_step, self.current_group)
            
            clean_desc = desc.replace('\n', ' ').replace('\r', '').strip()
            clean_desc = re.sub(' +', ' ', clean_desc)
            
            if plugin_type == 'Recommended':
                clean_desc = "This plugin is recommended by the author"
            elif plugin_type == 'Required':
                clean_desc = "This plugin has been defined as required by the author"
            elif plugin_type == 'NotUsable':
                clean_desc = "Not usable due to your previous choices or missing dependencies"
                is_not_usable = True
            elif plugin_type == 'CouldBeUsable':
                clean_desc = "Missing dependencies or conflict caused by previous selection"
            elif desc != '' and len(desc) >= 250:
                clean_desc = 'Plugin description is too long to be displayed here' 
            
            radio = Gtk.CheckButton(group=first_radio)
            if selection_type == 'SelectExactlyOne' or selection_type == 'SelectAtMostOne':    
                if not first_radio:
                    first_radio = radio
            
            # Setting up the row UI
            row_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row_content.set_margin_start(12)
            row_content.set_margin_end(8)
            row_content.set_margin_top(5)
            row_content.set_margin_bottom(10)
            
            text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            text_vbox.set_hexpand(True)
            
            name_label = Gtk.Label(label=name, xalign=0, wrap=False)
            name_label.set_ellipsize(3)
            name_label.add_css_class("heading")
            name_label.set_margin_bottom(2)
            
            desc_label = Gtk.Label(label=clean_desc, xalign=0, wrap=False)
            desc_label.add_css_class("dim-label")
            desc_label.add_css_class("caption")
            desc_label.set_ellipsize(3)
            desc_label.set_lines(2)
            
            text_vbox.append(name_label)
            text_vbox.append(desc_label)
            
            desc_btn = Gtk.Button()
            desc_btn.connect("clicked", self.on_show_desc_clicked, name, desc)
            desc_btn.set_icon_name('games-config-tiles-symbolic')
            desc_btn.add_css_class('show-desc-icon')
            desc_btn.set_halign(Gtk.Align.END)
            desc_btn.set_visible(False)
            
            row_content.append(radio)
            row_content.append(text_vbox)
            row_content.append(desc_btn)
            
            # Allows to retrieve row content
            row = Gtk.ListBoxRow()
            row.set_cursor_from_name('pointer')
            row.set_child(row_content)
            
            
            motion = Gtk.EventControllerMotion()
            row.add_controller(motion)
            if len(clean_desc) > 100:
                motion.connect('enter', lambda *_, btn=desc_btn: btn.set_visible(True))
                motion.connect('leave', lambda *_, btn=desc_btn: btn.set_visible(False))
            
            row.radio_button = radio
            row.name_label = name
            row.desc_label = desc
            
            radio.set_can_target(False)

            if selection_type == 'SelectExactlyOne' or selection_type == 'SelectAtMostOne':
                row.is_radio = True
            else:
                row.is_radio = False
            
            if plugin_type == 'Required':
                row.set_sensitive(False)
                row.radio_button.set_active(True)
            elif plugin_type == 'NotUsable':
                row.set_sensitive(False)
                row.radio_button.set_active(False)
            
            radio.set_can_target(False)

            if selection_type == 'SelectExactlyOne' or selection_type == 'SelectAtMostOne':
                row.is_radio = True
            else:
                row.is_radio = False
            
            if plugin_type == 'Required':
                row.set_can_target(False)
                row.radio_button.set_active(True)
            
            # Adding row to the UI
            list_box.append(row)
            self.options_map[radio] = source
            self.flags_map[radio] = flags
            
        if selection_type == 'SelectAtMostOne':
            default_row_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            default_row_content.set_margin_start(12)
            default_row_content.set_margin_end(12)
            default_row_content.set_margin_top(10)
            default_row_content.set_margin_bottom(10)
            
            default_radio = Gtk.CheckButton(group=first_radio)
            default_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            default_name_label = Gtk.Label(label='Skip', xalign=0)
            default_name_label.add_css_class('heading')
            
            default_vbox.append(default_name_label)
            default_row_content.append(default_radio)
            default_row_content.append(default_vbox)
            
            skip_row = Gtk.ListBoxRow()
            skip_row.set_child(default_row_content)
            
            default_radio.set_can_target(False)
            
            skip_row.is_radio = True
            
            skip_row.radio_button = default_radio
            skip_row.name_label = "Skip"
            
            if plugin_type == 'NotUsable':
                skip_row.radio_button.set_active(True)
            
            self.options_map[default_radio] = {}
                
            list_box.append(skip_row)
        
        # I need to patch this
        if selection_type == 'SelectAtLeastOne':
            if not radio.get_active():
                self.next_btn.set_sensitive(False)
                self.install_btn.set_sensitive(False)
        
        # Initialize the selector if needed
        if (selection_type == 'SelectAtMostOne' or selection_type == 'SelectExactlyOne') and is_not_usable == False :
            first_row = list_box.get_row_at_index(0)
            if first_row:
                list_box.select_row(first_row)
                self.on_row_selected(list_box, first_row)

    def on_row_selected(self, list_box, row):
        if row is not None:
            if hasattr(row, "radio_button"):
                if getattr(row, "is_radio", False):
                    # If radio, click on ligne can set status to active
                    row.radio_button.set_active(True)
                else:
                    # If toggle, we just reverse the current state
                    current_state = row.radio_button.get_active()
                    row.radio_button.set_active(not current_state)
            self.display_preview(list_box, row)
            
            selection_type = get_fomod_group_info(self.module_data, self.current_step, self.current_group)['type']
            if selection_type == 'SelectAtLeastOne':
                if row.radio_button.get_active():
                    self.next_btn.set_sensitive(True)
                    self.install_btn.set_sensitive(True)
                else:
                    self.next_btn.set_sensitive(False)
                    self.install_btn.set_sensitive(False)
    
    def on_next_clicked(self, button, list_box):
        # Source storing logic
        selected_sources = self.get_selected_source()
        self.global_sources.append(selected_sources)
        
        # Flags storing logic
        self.active_flags.update(self.get_selected_flags())
        self.flags_history.append(self.get_selected_flags())
        
        # Step and group enumeration
        step_count = get_fomod_step_count(self.module_data)
        group_count = get_fomod_group_count(self.module_data, self.current_step)
        if self.current_group < (group_count - 1):
            self.current_group += 1
        elif self.current_step < (step_count - 1):
            self.current_group = 0
            self.current_step += 1
        
        # Skip invisible steps when entering a new step
        while self.current_group == 0 and not is_step_visible(self.module_data, self.current_step, self.active_flags):
            if self.current_step < step_count - 1:
                self.current_step += 1
            else:
                self.on_install_clicked(button)
                return
        
        # Recounting groups since we might have moved to another step
        new_group_count = get_fomod_group_count(self.module_data, self.current_step)
        if (self.current_step == step_count - 1) and (self.current_group == new_group_count - 1):
            self.install_btn.set_visible(True)
            self.next_btn.set_visible(False)
        else:
            self.next_btn.set_visible(True)
            self.install_btn.set_visible(False)
            
        options = get_fomod_group_options(self.module_data, self.current_step, self.current_group)
        
        self.previous_btn.set_visible(True)
        
        # If there is a whole group with absolutely no source, we skip
        if all(not option[2] and not option[3] for option in options):
            self.on_next_clicked(self.next_btn, list_box)
            return
        
        # Listbox emptying logic
        while child := list_box.get_first_child():
            list_box.remove(child)
        while child := self.right_box.get_first_child():
            self.right_box.remove(child)
        
        self.populate_listbox(list_box, options)

    def on_previous_clicked(self, button, list_box):
        # Remove data logic
        if self.global_sources:
            self.global_sources.pop()
        
        step_flags = self.flags_history.pop()
        for flag in step_flags:
            self.active_flags.pop(flag, None)
    
        # Check if there is a next group or if we reset group to 0 and move steps instead
        step_count = get_fomod_step_count(self.module_data)
        group_count = get_fomod_group_count(self.module_data, self.current_step)
        
        ## Step and group enumeration
        if self.current_group > 0:
            self.current_group -= 1
        elif self.current_step > 0:
            self.current_step -= 1
            self.current_group = get_fomod_group_count(self.module_data, self.current_step) - 1
        self.install_btn.set_visible(False)
        self.next_btn.set_visible(True)
        
        # Skip invisible steps going backwards
        while not is_step_visible(self.module_data, self.current_step, self.active_flags):
            if self.current_step > 0:
                self.current_step -= 1
                self.current_group = get_fomod_group_count(self.module_data, self.current_step) - 1
            else:
                break
        
        if self.current_step == 0 and self.current_group == 0:
            self.previous_btn.set_visible(False)
        else:
            self.previous_btn.set_visible(True)
        
        options = get_fomod_group_options(self.module_data, self.current_step, self.current_group)
        # checks if a whole group has no source file then skip
        if all(not option[2] and not option[3] for option in options):
            self.on_previous_clicked(self.next_btn, list_box)
            return
        
        # Listbox emptying logic
        while child := list_box.get_first_child():
            list_box.remove(child)
        while child := self.right_box.get_first_child():
            self.right_box.remove(child)
        
        # Refreshing the view
        self.populate_listbox(list_box, options)
        
    # Which means that it will return a dict instead of a list
    def get_selected_source(self) -> list:
        all_selected_sources = []
    
        for radio, source in self.options_map.items():
            if radio.get_active():
                if isinstance(source, list):
                    all_selected_sources.extend(source)
                else:
                    all_selected_sources.append(source)        
        return all_selected_sources
    
    def get_selected_flags(self) -> dict:
      all_selected_flags = {}
      for radio, condition_flags in self.flags_map.items():
          if radio.get_active():
              for flag in condition_flags:
                  all_selected_flags[flag['name']] = flag['value']
      return all_selected_flags
    
    def get_global_sources(self) -> list[dict[str]]:
        files_to_install = []

        for items in self.global_sources:
            files_to_install.extend(items)
        return files_to_install
    
    def on_install_clicked(self, button):
        # Source storing
        selected_sources = self.get_selected_source()
        if selected_sources:
            self.global_sources.append(selected_sources)
        
        # Flag storing
        self.active_flags.update(self.get_selected_flags())
        
        # Prepend the required files so they are installed first anyway
        self.global_sources.insert(0, self.required_data)
        
        # Append the files installed from the matching flags
        converted_flags = generate_source_from_flags(self.flags_data, self.active_flags)
        self.global_sources.append(converted_flags)
        
        self.emit("response", Gtk.ResponseType.OK)
        self.close()

    def on_cancel_clicked(self, button):
        self.emit("response", Gtk.ResponseType.CANCEL)
        self.close()
        
    def display_preview(self, listbox, row):
        if row is not None:
            selected_plugin_name = row.name_label
            
        if not have_plugins_images(self.module_data, self.current_step, self.current_group):
            self.right_box.set_visible(False)
            self.vseparator.set_visible(False)
            self.scrolled.set_hexpand(True)
            return
        else:
            self.right_box.set_visible(True)
            self.vseparator.set_visible(True)
            self.scrolled.set_hexpand(False)
        
        # Destroy child if child exists
        while child := self.right_box.get_first_child():
            self.right_box.remove(child)

        image_path = get_plugin_image_path(self.module_data, selected_plugin_name, self.current_step, self.current_group)
        
        if image_path != '':
            clean_relative_path = image_path.replace('\\', '/')
            full_image_path = os.path.join(self.fomod_staging_dir, clean_relative_path)
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    full_image_path, 
                    width=800,
                    height=800,
                    preserve_aspect_ratio=True
                )
            except:
                full_image_path = retrieve_casesensitive_paths(full_image_path)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    full_image_path, 
                    width=800,
                    height=800,
                    preserve_aspect_ratio=True
                )

            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_overflow(Gtk.Overflow.HIDDEN)
            
            picture.set_hexpand(True)
            picture.set_vexpand(True)
            
            picture.add_css_class("fomod-preview-image")
            
            self.right_box.append(picture)
            
            self.right_box.set_visible(True)
            
        else:
            self.show_no_preview_label()
    
    def show_no_preview_label(self):
        no_image_label = Gtk.Label(label="No preview available")
        no_image_label.set_hexpand(True)
        no_image_label.set_vexpand(True)
        no_image_label.add_css_class("dim-label")
        self.right_box.append(no_image_label)
    
    def on_show_desc_clicked(self, button, title, content):
        self.desc_window = TextWindow(self, title, content)
        self.desc_window.present()
