import os
import yaml
import threading
import re
import shutil
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gdk, Gio

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
.setup-page {
    opacity: 0;
    transition: opacity 800ms ease-in;
}
.setup-page.visible {
    opacity: 1;
}
"""

def slugify(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

class nommlauncher(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(application_id='com.fedora.nomm', **kwargs)
        self.matches = []
        self.steam_base = self.get_steam_base_dir()
        self.user_config_path = "./user_config.yaml"

    def get_steam_base_dir(self):
        paths = [
            os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/"),
            os.path.expanduser("~/.local/share/Steam/"),
            os.path.expanduser("~/snap/steam/common/.local/share/Steam/")
        ]
        for p in paths:
            if os.path.exists(p): return p
        return None

    def sync_configs(self):
        src, dest = "./default_game_configs", "./game_configs"
        if not os.path.exists(src): return
        if not os.path.exists(dest): os.makedirs(dest)
        for filename in os.listdir(src):
            if filename.lower().endswith((".yaml", ".yml")):
                try: shutil.copy2(os.path.join(src, filename), os.path.join(dest, filename))
                except: pass

    def do_activate(self):
        self.sync_configs()
        self.apply_styles()
        
        self.win = Adw.ApplicationWindow(application=self)
        self.win.set_title("NOMM")
        self.win.set_default_size(1400, 900)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.win.set_content(self.stack)

        if not os.path.exists(self.user_config_path):
            self.show_setup_screen()
        else:
            self.show_loading_and_scan()

        self.win.present()

    def show_setup_screen(self):
        status_page = Adw.StatusPage(
            title="Welcome to NOMM",
            description="Please select the folder where your game downloads are located.",
            icon_name="folder-download-symbolic"
        )
        status_page.add_css_class("setup-page")
        
        btn = Gtk.Button(label="Set Download Path")
        btn.set_halign(Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.set_margin_top(24)
        btn.connect("clicked", self.on_select_folder_clicked)
        
        status_page.set_child(btn)
        self.stack.add_named(status_page, "setup")
        self.stack.set_visible_child_name("setup")
        
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def on_select_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title="Select Downloads Folder")
        dialog.select_folder(self.win, None, self.on_folder_selected_callback)

    def on_folder_selected_callback(self, dialog, result):
        try:
            selected_file = dialog.select_folder_finish(result)
            if selected_file:
                path = selected_file.get_path()
                config_data = {"download_path": path, "library_paths": []}
                with open(self.user_config_path, 'w') as f:
                    yaml.dump(config_data, f, default_flow_style=False)
                self.show_loading_and_scan()
        except GLib.Error as e:
            print(f"Selection cancelled: {e.message}")

    def show_loading_and_scan(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30, valign=Gtk.Align.CENTER)
        
        # UPDATED: Spinner size increased to 128
        spinner = Gtk.Spinner()
        spinner.set_size_request(128, 128)
        spinner.set_margin_bottom(10)
        spinner.start()
        
        label = Gtk.Label(label="NOMM: Mapping Libraries...")
        label.add_css_class("title-1")
        
        box.append(spinner)
        box.append(label)
        
        self.status_label = label
        self.stack.add_named(box, "loading")
        self.stack.set_visible_child_name("loading")
        
        threading.Thread(target=self.run_background_workflow, daemon=True).start()

    def run_background_workflow(self):
        config_dir = "./game_configs/"
        found_libs = set()
        current_config = {}

        try:
            with open(self.user_config_path, 'r') as f:
                current_config = yaml.safe_load(f) or {}
                found_libs = set(current_config.get("library_paths", []))
        except: pass

        if not found_libs:
            GLib.idle_add(self.status_label.set_label, "NOMM: Scanning Disks...")
            potential_mounts = {"/", os.path.expanduser("~")}
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 3 and parts[1].startswith(('/', '/run/media', '/mnt')):
                            potential_mounts.add(parts[1])
            except: pass

            targets = ["SteamLibrary/steamapps/common", "steamapps/common"]
            for m in potential_mounts:
                if not os.path.exists(m): continue
                for root, dirs, _ in os.walk(m):
                    if any(root.endswith(t) for t in targets):
                        found_libs.add(os.path.realpath(root))
                        del dirs[:]
                        break

            current_config["library_paths"] = sorted(list(found_libs))
            try:
                with open(self.user_config_path, 'w') as f:
                    yaml.dump(current_config, f, default_flow_style=False)
            except: pass

        self.matches = []
        if os.path.exists(config_dir):
            for filename in os.listdir(config_dir):
                if filename.lower().endswith((".yaml", ".yml")):
                    fpath = os.path.join(config_dir, filename)
                    try:
                        with open(fpath, 'r') as f:
                            data = yaml.safe_load(f)
                        
                        y_name, app_id = data.get("name"), data.get("steamappid")
                        if not y_name: continue
                        
                        slug = slugify(y_name)
                        for lib in found_libs:
                            if not os.path.exists(lib): continue
                            for folder in os.listdir(lib):
                                if slugify(folder) == slug:
                                    inst_path = os.path.join(lib, folder)
                                    data['user_path'] = inst_path
                                    with open(fpath, 'w') as f:
                                        yaml.dump(data, f, default_flow_style=False)
                                    
                                    self.matches.append({
                                        "name": y_name,
                                        "img": self.find_steam_art(app_id),
                                        "path": inst_path
                                    })
                                    break
                    except: pass

        GLib.idle_add(self.show_library_ui)

    def show_library_ui(self):
        view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        view.append(Adw.HeaderBar())

        scroll = Gtk.ScrolledWindow(vexpand=True)
        flow = Gtk.FlowBox(valign=Gtk.Align.START, selection_mode=0,
                           margin_top=40, margin_bottom=40, margin_start=40, margin_end=40,
                           column_spacing=30, row_spacing=30)

        for g in self.matches:
            frame = Gtk.AspectFrame.new(0.5, 0.5, 0.666, False)
            frame.set_size_request(300, 450)
            frame.add_css_class("game-card")
            frame.set_tooltip_text(f"{g['name']}\n{g['path']}")

            img = None
            if g['img'] and os.path.exists(g['img']):
                try:
                    tex = Gdk.Texture.new_from_file(Gio.File.new_for_path(g['img']))
                    img = Gtk.Picture(paintable=tex, can_shrink=False, content_fit=Gtk.ContentFit.COVER)
                except: pass

            frame.set_child(img if img else self.get_placeholder())
            flow.append(frame)

        scroll.set_child(flow)
        view.append(scroll)
        self.stack.add_named(view, "library")
        self.stack.set_visible_child_name("library")

    def get_placeholder(self):
        b = Gtk.Box(orientation=1, valign=Gtk.Align.CENTER)
        b.append(Gtk.Image.new_from_icon_name("input-gaming-symbolic", pixel_size=128))
        return b

    def apply_styles(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, 800)

    def find_steam_art(self, app_id):
        if not self.steam_base or not app_id: return None
        path = os.path.join(self.steam_base, "appcache/librarycache", str(app_id))
        if not os.path.exists(path): return None
        for root, _, files in os.walk(path):
            for t in ["library_capsule.jpg", "library_600x900.jpg"]:
                if t in files: return os.path.join(root, t)
        return None

if __name__ == "__main__":
    app = nommlauncher()
    app.run(None)