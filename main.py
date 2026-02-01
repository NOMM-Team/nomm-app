import os
import yaml
import threading
import re
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gdk, Gio

# --- CSS for Glossy Effect ---
CSS = """
.game-card {
    border-radius: 12px;
    transition: all 300ms cubic-bezier(0.25, 1, 0.5, 1);
    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
}

.game-card:hover {
    transform: scale(1.04);
    filter: brightness(1.1) contrast(1.05);
    box-shadow: 0 0 15px rgba(255, 255, 255, 0.1), 0 12px 30px rgba(0,0,0,0.6);
}
"""

def slugify(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

class SteamScannerApp(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(application_id='com.fedora.steam_scanner', **kwargs)
        self.matches = []
        self.steam_base = self.get_steam_base_dir()

    def get_steam_base_dir(self):
        paths = [
            os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/"),
            os.path.expanduser("~/.local/share/Steam/"),
            os.path.expanduser("~/snap/steam/common/.local/share/Steam/")
        ]
        for p in paths:
            if os.path.exists(p): return p
        return None

    def find_steam_art(self, app_id):
        if not self.steam_base or not app_id: return None
        app_cache_root = os.path.join(self.steam_base, "appcache/librarycache", str(app_id))
        if not os.path.exists(app_cache_root): return None
        
        target_files = ["library_capsule.jpg", "library_600x900.jpg"]
        for root, _, files in os.walk(app_cache_root):
            for target in target_files:
                if target in files:
                    return os.path.join(root, target)
        return None

    def apply_styles(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        self.apply_styles()
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        self.win = Adw.ApplicationWindow(application=self)
        self.win.set_title("Steam Library Manager")
        self.win.set_default_size(1400, 900)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.win.set_content(self.main_box)

        self.status_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.status_container.set_valign(Gtk.Align.CENTER)
        self.status_container.set_vexpand(True)
        
        self.spinner = Adw.Spinner()
        self.spinner.set_size_request(80, 80)
        self.status_label = Gtk.Label(label="Initializing Library...")
        self.status_label.add_css_class("title-1")
        
        self.status_container.append(self.spinner)
        self.status_container.append(self.status_label)
        self.main_box.append(self.status_container)

        self.win.present()
        threading.Thread(target=self.run_background_workflow, daemon=True).start()

    def run_background_workflow(self):
        config_dir = "./game_configs/"
        user_config_path = "./user_config.yaml"
        found_libs = set()

        if not os.path.exists(config_dir):
            GLib.idle_add(self.status_label.set_label, "Error: 'game_configs' missing")
            return

        # 1. Check for cached paths first
        if os.path.exists(user_config_path):
            try:
                with open(user_config_path, 'r') as ucf:
                    cache = yaml.safe_load(ucf)
                    if cache and "library_paths" in cache:
                        found_libs = set(cache["library_paths"])
                        print("Loaded paths from user_config.yaml")
            except: pass

        # 2. If cache is empty, perform the deep system scan
        if not found_libs:
            GLib.idle_add(self.status_label.set_label, "Scanning drives for Steam libraries...")
            potential_mounts = {"/", os.path.expanduser("~")}
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 3 and parts[2] in ['ext4', 'btrfs', 'vfat', 'exfat', 'ntfs3', 'xfs']:
                            if parts[1].startswith(('/', '/run/media', '/mnt')):
                                potential_mounts.add(parts[1])
            except: pass

            targets = ["SteamLibrary/steamapps/common", "steamapps/common"]
            for m in potential_mounts:
                if not os.path.exists(m): continue
                for root, dirs, _ in os.walk(m):
                    if any(root.endswith(t) for t in targets):
                        # FIX: Sets use .add() instead of .append()
                        real_lib_path = os.path.realpath(root)
                        found_libs.add(real_lib_path)
                        del dirs[:] 
                        break

            # Save the new findings
            try:
                config_data = {"library_paths": sorted(list(found_libs))}
                with open(user_config_path, 'w') as ucf:
                    yaml.dump(config_data, ucf, default_flow_style=False)
            except Exception as e:
                print(f"Failed to save user_config: {e}")

        # 3. Matching YAML configs
        self.matches = []
        for filename in os.listdir(config_dir):
            if filename.lower().endswith((".yaml", ".yml")):
                try:
                    with open(os.path.join(config_dir, filename), 'r') as f:
                        data = yaml.safe_load(f)
                        y_name, app_id = data.get("name"), data.get("steamappid")
                        if not y_name: continue
                        
                        y_slug = slugify(y_name)
                        for lib in found_libs:
                            if not os.path.exists(lib): continue
                            # Search only the top-level folders in the library
                            for folder in os.listdir(lib):
                                if slugify(folder) == y_slug:
                                    self.matches.append({
                                        "display_name": y_name,
                                        "image": self.find_steam_art(app_id),
                                        "path": os.path.join(lib, folder)
                                    })
                                    break
                except: continue

        GLib.idle_add(self.show_library_ui)

    def show_library_ui(self):
        if hasattr(self, 'status_container') and self.status_container.get_parent():
            self.main_box.remove(self.status_container)
        
        self.main_box.append(Adw.HeaderBar())

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        flowbox = Gtk.FlowBox(valign=Gtk.Align.START, selection_mode=Gtk.SelectionMode.NONE,
                             margin_top=40, margin_bottom=40, margin_start=40, margin_end=40,
                             column_spacing=30, row_spacing=30)

        W, H = 300, 450

        for game in self.matches:
            aspect = Gtk.AspectFrame.new(0.5, 0.5, 0.666, False)
            aspect.set_size_request(W, H)
            aspect.set_tooltip_text(f"{game['display_name']}\n{game['path']}")
            aspect.add_css_class("game-card")

            img_widget = None
            if game['image'] and os.path.exists(game['image']):
                try:
                    file_obj = Gio.File.new_for_path(game['image'])
                    texture = Gdk.Texture.new_from_file(file_obj)
                    img_widget = Gtk.Picture(paintable=texture, can_shrink=False)
                    img_widget.set_content_fit(Gtk.ContentFit.COVER)
                except: pass

            if img_widget is None:
                img_widget = self.get_placeholder_icon(W, H)
            
            aspect.set_child(img_widget)
            flowbox.append(aspect)

        scrolled.set_child(flowbox)
        self.main_box.append(scrolled)

    def get_placeholder_icon(self, w, h):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        box.set_size_request(w, h)
        icon = Gtk.Image.new_from_icon_name("input-gaming-symbolic")
        icon.set_pixel_size(128)
        box.append(icon)
        return box

if __name__ == "__main__":
    app = SteamScannerApp()
    app.run(None)