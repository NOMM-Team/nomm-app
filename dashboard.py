import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class GameDashboard(Adw.Window):
    def __init__(self, game_name, game_path, application, **kwargs):
        super().__init__(application=application, **kwargs)
        self.app = application
        
        self.set_title(f"NOMM - {game_name}")
        self.maximize()
        self.fullscreen()
        
        # 1. Root Container
        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # 2. Header
        header = Adw.HeaderBar()
        main_layout.append(header)

        # 3. Full-Width Tab Switcher Area
        # homogeneous=True makes all children the same width
        tab_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True)
        
        # Using Gtk.Stack for tab content
        self.view_stack = Gtk.Stack()
        self.view_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.view_stack.set_transition_duration(400)
        self.view_stack.set_vexpand(True)

        # Create Rectangular ToggleButtons
        self.mods_tab_btn = Gtk.ToggleButton(label="MODS")
        self.dl_tab_btn = Gtk.ToggleButton(label="DOWNLOADS")
        
        for btn in [self.mods_tab_btn, self.dl_tab_btn]:
            btn.set_size_request(-1, 80)    # Height of 80px, width scales to fill
            btn.set_hexpand(True)           # Take up all horizontal space
            btn.set_cursor_from_name("pointer")
            # We explicitly do NOT add the "pill" class here to keep them rectangular
            tab_container.append(btn)

        # Group them so they act as a selection pair
        self.dl_tab_btn.set_group(self.mods_tab_btn)
        self.mods_tab_btn.set_active(True)

        # Connect signals
        self.mods_tab_btn.connect("toggled", self.on_tab_changed, "mods")
        self.dl_tab_btn.connect("toggled", self.on_tab_changed, "downloads")

        main_layout.append(tab_container)
        
        # 4. Tab Content
        self.create_mods_page()
        self.create_downloads_page()
        main_layout.append(self.view_stack)

        # 5. Footer (Bottom Navigation)
        footer = Gtk.CenterBox(margin_start=40, margin_end=40, margin_bottom=40, margin_top=20)
        
        back_btn = Gtk.Button(label="Change Game")
        back_btn.add_css_class("flat")
        back_btn.set_cursor_from_name("pointer")
        back_btn.connect("clicked", self.on_back_clicked)
        footer.set_start_widget(back_btn)
        
        launch_btn = Gtk.Button(label="Launch Game")
        launch_btn.add_css_class("suggested-action")
        launch_btn.set_cursor_from_name("pointer")
        launch_btn.set_size_request(240, 64)
        launch_btn.connect("clicked", self.on_launch_clicked, game_path)
        footer.set_end_widget(launch_btn)

        main_layout.append(footer)
        self.set_content(main_layout)

    def on_tab_changed(self, btn, name):
        if btn.get_active():
            self.view_stack.set_visible_child_name(name)

    def create_mods_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        label = Gtk.Label(label="Installed Mods Content")
        label.add_css_class("title-1")
        box.append(label)
        self.view_stack.add_named(box, "mods")

    def create_downloads_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        label = Gtk.Label(label="Available Downloads Content")
        label.add_css_class("title-1")
        box.append(label)
        self.view_stack.add_named(box, "downloads")

    def on_back_clicked(self, btn):
        self.app.do_activate() 
        self.close()

    def on_launch_clicked(self, btn, path):
        print(f"Launching: {path}")

    def launch(self):
        self.present()