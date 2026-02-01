import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class GameDashboard(Adw.Window):
    def __init__(self, game_name, game_path, **kwargs):
        super().__init__(**kwargs)
        
        self.set_title(f"NOMM - {game_name}")
        self.maximize() # Start maximized
        self.fullscreen() # Launch in full screen
        
        # Main layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        
        # Display Game Name
        name_label = Gtk.Label(label=game_name)
        name_label.add_css_class("title-1")
        name_label.set_css_classes(["display-text"]) # Using Adwaita's large display style
        
        # Display Game Path (for verification)
        path_label = Gtk.Label(label=f"Path: {game_path}")
        path_label.add_css_class("caption")
        
        # Back Button (To exit full screen/app for now)
        close_btn = Gtk.Button(label="Exit Dashboard")
        close_btn.set_halign(Gtk.Align.CENTER)
        close_btn.add_css_class("destructive-action")
        close_btn.connect("clicked", lambda x: self.close())

        box.append(name_label)
        box.append(path_label)
        box.append(close_btn)
        
        self.set_content(box)

    def launch(self):
        self.present()