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
        
        # The Main Container
        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # 1. HeaderBar (Standard window controls)
        header = Adw.HeaderBar()
        main_layout.append(header)
        
        # 2. Central Content Area
        content_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, 
            spacing=10, 
            valign=Gtk.Align.CENTER,
            vexpand=True
        )
        
        name_label = Gtk.Label(label=game_name)
        name_label.add_css_class("title-1")
        
        path_label = Gtk.Label(label=game_path)
        path_label.add_css_class("caption")
        path_label.set_opacity(0.6) # Subtle path text
        
        content_box.append(name_label)
        content_box.append(path_label)
        main_layout.append(content_box)

        # 3. Footer Bar
        footer = Gtk.CenterBox(margin_start=40, margin_end=40, margin_bottom=40)
        
        # Bottom Left: Change Game
        back_btn = Gtk.Button(label="Change Game")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", self.on_back_clicked)
        footer.set_start_widget(back_btn)
        
        # Bottom Right: Launch Game
        launch_btn = Gtk.Button(label=f"Launch {game_name}")
        launch_btn.add_css_class("suggested-action")
        launch_btn.set_size_request(240, 64)
        launch_btn.connect("clicked", self.on_launch_clicked, game_path)
        footer.set_end_widget(launch_btn)

        main_layout.append(footer)
        
        self.set_content(main_layout)

    def on_back_clicked(self, btn):
        self.app.do_activate() 
        self.close()

    def on_launch_clicked(self, btn, path):
        # We can implement the subprocess execution here next
        print(f"Launching: {path}")

    def launch(self):
        self.present()