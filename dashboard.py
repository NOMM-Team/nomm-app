import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio

class GameDashboard(Adw.Window):
    def __init__(self, game_name, game_path, application, steam_base=None, app_id=None, **kwargs):
        super().__init__(application=application, **kwargs)
        self.app = application
        
        self.set_title(f"NOMM - {game_name}")
        self.maximize()
        self.fullscreen()
        
        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        header = Adw.HeaderBar()
        main_layout.append(header)

        banner_overlay = Gtk.Overlay()
        
        hero_path = self.find_hero_image(steam_base, app_id)
        if hero_path:
            banner_mask = Gtk.ScrolledWindow()
            banner_mask.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            banner_mask.set_propagate_natural_height(False)
            banner_mask.set_size_request(-1, 200)
            banner_mask.set_vexpand(False)
            
            try:
                hero_file = Gio.File.new_for_path(hero_path)
                hero_tex = Gdk.Texture.new_from_file(hero_file)
                hero_img = Gtk.Picture(paintable=hero_tex)
                hero_img.set_content_fit(Gtk.ContentFit.COVER)
                hero_img.set_can_shrink(True)
                banner_mask.set_child(hero_img)
                banner_overlay.set_child(banner_mask)
            except Exception as e:
                print(f"Error loading hero image: {e}")
                placeholder = Gtk.Box()
                placeholder.set_size_request(-1, 200)
                banner_overlay.set_child(placeholder)

        tab_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True)
        tab_container.set_valign(Gtk.Align.FILL)
        
        self.mods_tab_btn = Gtk.ToggleButton(label="MODS")
        self.dl_tab_btn = Gtk.ToggleButton(label="DOWNLOADS")
        
        for btn in [self.mods_tab_btn, self.dl_tab_btn]:
            btn.set_hexpand(True)
            btn.set_vexpand(True) 
            btn.set_cursor_from_name("pointer")
            btn.add_css_class("overlay-tab")
            tab_container.append(btn)

        self.dl_tab_btn.set_group(self.mods_tab_btn)
        self.mods_tab_btn.set_active(True)
        
        banner_overlay.add_overlay(tab_container)
        main_layout.append(banner_overlay)

        self.view_stack = Gtk.Stack()
        self.view_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.view_stack.set_transition_duration(400)
        self.view_stack.set_vexpand(True) 

        self.mods_tab_btn.connect("toggled", self.on_tab_changed, "mods")
        self.dl_tab_btn.connect("toggled", self.on_tab_changed, "downloads")

        main_layout.append(self.view_stack)
        self.create_mods_page()
        self.create_downloads_page()

        footer = Gtk.CenterBox()
        footer.set_margin_start(40)
        footer.set_margin_end(40)
        footer.set_margin_top(20)
        footer.set_margin_bottom(40)
        
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

    def find_hero_image(self, steam_base, app_id):
        if not steam_base or not app_id: return None
        cache_dir = os.path.join(steam_base, "appcache", "librarycache")
        if not os.path.exists(cache_dir): return None
        lookups = [
            os.path.join(cache_dir, f"{app_id}_library_hero.jpg"),
            os.path.join(cache_dir, str(app_id), "library_hero.jpg")
        ]
        for path in lookups:
            if os.path.exists(path): return path
        appid_dir = os.path.join(cache_dir, str(app_id))
        if os.path.exists(appid_dir):
            for root, _, files in os.walk(appid_dir):
                if "library_hero.jpg" in files:
                    return os.path.join(root, "library_hero.jpg")
        return None

    def on_tab_changed(self, btn, name):
        if btn.get_active():
            self.view_stack.set_visible_child_name(name)

    def create_mods_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        lbl = Gtk.Label(label="Installed Mods")
        lbl.add_css_class("title-1")
        box.append(lbl)
        self.view_stack.add_named(box, "mods")

    def create_downloads_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        lbl = Gtk.Label(label="Available Downloads")
        lbl.add_css_class("title-1")
        box.append(lbl)
        self.view_stack.add_named(box, "downloads")

    def on_back_clicked(self, btn):
        self.app.do_activate() 
        self.close()

    def on_launch_clicked(self, btn, path):
        print(f"Launching: {path}")

    def launch(self):
        self.present()