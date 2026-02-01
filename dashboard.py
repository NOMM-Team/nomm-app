import os
import gi
import yaml
import shutil
from PIL import Image

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio

class GameDashboard(Adw.Window):
    def __init__(self, game_name, game_path, application, steam_base=None, app_id=None, **kwargs):
        super().__init__(application=application, **kwargs)
        self.app = application
        self.game_name = game_name
        self.game_path = game_path
        
        # 1. Load Game Specific Config
        self.game_config = self.load_game_config()
        self.downloads_path = self.game_config.get("downloads_path")
        
        self.set_title(f"NOMM - {game_name}")
        self.maximize()
        self.fullscreen()
        
        # Calculate 15% of Window Height
        win_height = self.get_default_size()[1]
        if self.is_maximized():
            monitor = Gdk.Display.get_default().get_monitors().get_item(0)
            win_height = monitor.get_geometry().height
        banner_height = int(win_height * 0.15)

        # Dynamic Color Extraction
        hero_path = self.find_hero_image(steam_base, app_id)
        if hero_path:
            dominant_hex = self.get_dominant_color(hero_path)
            self.apply_dynamic_accent(dominant_hex)

        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        main_layout.append(header)

        banner_overlay = Gtk.Overlay()
        
        # Banner with Top-Crop
        if hero_path:
            banner_mask = Gtk.ScrolledWindow(propagate_natural_height=False, vexpand=False)
            banner_mask.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            banner_mask.set_size_request(-1, banner_height)
            
            try:
                hero_tex = Gdk.Texture.new_from_file(Gio.File.new_for_path(hero_path))
                hero_img = Gtk.Picture(paintable=hero_tex, content_fit=Gtk.ContentFit.COVER, can_shrink=True)
                hero_img.set_valign(Gtk.Align.START)
                banner_mask.set_child(hero_img)
                banner_mask.get_vadjustment().set_value(0)
                banner_overlay.set_child(banner_mask)
            except Exception as e:
                print(f"Error loading hero: {e}")

        # Tab Container
        tab_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True)
        self.mods_tab_btn = Gtk.ToggleButton(label="MODS")
        self.dl_tab_btn = Gtk.ToggleButton(label="DOWNLOADS")
        
        for btn in [self.mods_tab_btn, self.dl_tab_btn]:
            btn.set_hexpand(True)
            btn.add_css_class("overlay-tab")
            btn.set_cursor_from_name("pointer")
            tab_container.append(btn)

        self.dl_tab_btn.set_group(self.mods_tab_btn)
        self.mods_tab_btn.set_active(True)
        banner_overlay.add_overlay(tab_container)
        main_layout.append(banner_overlay)

        # View Stack
        self.view_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=400, vexpand=True)
        self.mods_tab_btn.connect("toggled", self.on_tab_changed, "mods")
        self.dl_tab_btn.connect("toggled", self.on_tab_changed, "downloads")

        main_layout.append(self.view_stack)
        self.create_mods_page()
        self.create_downloads_page()

        # Footer
        footer = Gtk.CenterBox(margin_start=40, margin_end=40, margin_top=20, margin_bottom=40)
        
        back_btn = Gtk.Button(label="Change Game")
        back_btn.add_css_class("flat")
        back_btn.set_cursor_from_name("pointer")
        back_btn.connect("clicked", self.on_back_clicked)
        footer.set_start_widget(back_btn)
        
        launch_btn = Gtk.Button(label="Launch Game")
        launch_btn.add_css_class("suggested-action")
        launch_btn.set_size_request(240, 64)
        launch_btn.set_cursor_from_name("pointer")
        launch_btn.connect("clicked", self.on_launch_clicked)
        footer.set_end_widget(launch_btn)

        main_layout.append(footer)
        self.set_content(main_layout)

    def load_game_config(self):
        config_dir = "./game_configs/"
        import re
        def slug(text): return re.sub(r'[^a-z0-9]', '', text.lower())
        target = slug(self.game_name)
        if os.path.exists(config_dir):
            for filename in os.listdir(config_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    with open(os.path.join(config_dir, filename), 'r') as f:
                        data = yaml.safe_load(f) or {}
                        if slug(data.get("name", "")) == target:
                            return data
        return {}

    def create_downloads_page(self):
        if self.view_stack.get_child_by_name("downloads"):
            self.view_stack.remove(self.view_stack.get_child_by_name("downloads"))

        # Main container with breathing room
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=100, margin_end=100, margin_top=40)
        
        # Utility bar for folder actions (Title removed)
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        spacer = Gtk.Box(hexpand=True)
        
        open_folder_btn = Gtk.Button(icon_name="folder-open-symbolic")
        open_folder_btn.set_tooltip_text("Open Downloads Folder")
        open_folder_btn.set_cursor_from_name("pointer")
        open_folder_btn.add_css_class("flat")
        open_folder_btn.connect("clicked", lambda x: os.system(f'xdg-open "{self.downloads_path}"'))
        
        action_bar.append(spacer)
        action_bar.append(open_folder_btn)
        box.append(action_bar)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")

        if self.downloads_path and os.path.exists(self.downloads_path):
            files = os.listdir(self.downloads_path)
            if not files:
                self.list_box.append(Adw.ActionRow(title="No mod files found", subtitle="Drop files into the folder."))
            else:
                for f in files:
                    row = Adw.ActionRow(title=f)
                    row.add_prefix(Gtk.Image.new_from_icon_name("package-x-generic-symbolic"))
                    
                    install_btn = Gtk.Button(label="Install")
                    install_btn.add_css_class("suggested-action")
                    install_btn.set_valign(Gtk.Align.CENTER)
                    install_btn.set_cursor_from_name("pointer")
                    row.add_suffix(install_btn)

                    del_btn = Gtk.Button(icon_name="user-trash-symbolic")
                    del_btn.add_css_class("flat")
                    del_btn.set_valign(Gtk.Align.CENTER)
                    del_btn.set_cursor_from_name("pointer")
                    del_btn.connect("clicked", self.on_delete_file, f)
                    row.add_suffix(del_btn)
                    
                    self.list_box.append(row)
        else:
            self.list_box.append(Adw.ActionRow(title="Download path not configured"))

        scrolled.set_child(self.list_box)
        box.append(scrolled)
        self.view_stack.add_named(box, "downloads")

    def on_delete_file(self, btn, filename):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Delete File?",
            body=f"Are you sure you want to delete {filename} permanently?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        
        def on_response(diag, response):
            if response == "delete":
                file_path = os.path.join(self.downloads_path, filename)
                try:
                    os.remove(file_path)
                    self.create_downloads_page()
                except Exception as e:
                    print(f"Error: {e}")
            diag.close()

        dialog.connect("response", on_response)
        dialog.present()

    def get_dominant_color(self, image_path):
        try:
            with Image.open(image_path) as img:
                img = img.convert("RGB").resize((1, 1), resample=Image.Resampling.LANCZOS)
                r, g, b = img.getpixel((0, 0))
                return f"#{r:02x}{g:02x}{b:02x}"
        except: return "#3584e4"

    def apply_dynamic_accent(self, hex_color):
        css = f"@define-color accent_bg_color {hex_color}; @define-color accent_color {hex_color};"
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def find_hero_image(self, steam_base, app_id):
        if not steam_base or not app_id: return None
        cache_dir = os.path.join(steam_base, "appcache", "librarycache")
        lookups = [os.path.join(cache_dir, f"{app_id}_library_hero.jpg"), os.path.join(cache_dir, str(app_id), "library_hero.jpg")]
        for path in lookups:
            if os.path.exists(path): return path
        return None

    def on_tab_changed(self, btn, name):
        if btn.get_active(): self.view_stack.set_visible_child_name(name)

    def create_mods_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        lbl = Gtk.Label(label="Installed Mods")
        lbl.add_css_class("title-1")
        box.append(lbl)
        self.view_stack.add_named(box, "mods")

    def on_back_clicked(self, btn):
        self.app.do_activate() 
        self.close()

    def on_launch_clicked(self, btn):
        print(f"Launching: {self.game_path}")

    def launch(self): self.present()