import os
import json
import requests
import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, GLib, Gio, Notify, GdkPixbuf

def download_heroic_assets(appName: str, platform: str):
    # 1. Define Paths
    json_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/store/download-manager.json")
    cache_base = os.path.expanduser(f"~/nomm/image-cache/{platform}/{appName}")
    
    # 2. CACHE CHECK: If the directory exists, check for existing files
    if os.path.exists(cache_base):
        existing_files = {}
        # We look for any file starting with our keys (to handle different extensions)
        for entry in os.listdir(cache_base):
            if entry.startswith("art_square"):
                existing_files["art_square"] = os.path.join(cache_base, entry)
            elif entry.startswith("art_hero"):
                existing_files["art_hero"] = os.path.join(cache_base, entry)
        
        # If we found at least the square art, we consider it cached
        if "art_square" in existing_files:
            print(f"Using cached assets for {appName}")
            return existing_files

    # 3. If not cached, proceed to JSON parsing
    if not os.path.exists(json_path):
        print(f"Heroic config not found at {json_path}")
        return None

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        finished_apps = data.get("finished", [])
        target_info = None

        for entry in finished_apps:
            params = entry.get("params", {})
            game_info = params.get("gameInfo", {})
            
            # Match by internal appName (e.g., 'Curry') or title (e.g., 'ABZÛ')
            if params.get("appName") == appName or game_info.get("title") == appName:
                target_info = game_info
                break
        
        if not target_info:
            return None

        # 4. Extraction Logic
        urls = {
            "art_square": target_info.get("art_square"),
            "art_hero": target_info.get("art_background") or target_info.get("art_cover")
        }

        os.makedirs(cache_base, exist_ok=True)
        downloaded_paths = {}

        for key, url in urls.items():
            if not url:
                continue
                
            ext = os.path.splitext(url)[1] if "." in url.split("/")[-1] else ".jpg"
            # Ensure extensions like .jpg?foo=bar are cleaned
            if "?" in ext: ext = ext.split("?")[0]
            
            local_path = os.path.join(cache_base, f"{key}{ext}")

            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(r.content)
                    downloaded_paths[key] = local_path
                    print(f"Downloaded: {local_path}")
            except Exception as e:
                print(f"Error downloading {key}: {e}")

        return downloaded_paths

    except Exception as e:
        print(f"Failed to process Heroic JSON: {e}")
        return None

def download_with_progress(url, dest_folder):
    filename = url.split('/')[-1].split('?')[0] or "download"
    dest_path = os.path.join(dest_folder, filename)
    os.makedirs(dest_folder, exist_ok=True)

    # State tracking
    status = {"success": False, "finished": False}
    event = threading.Event()

    def create_ui():
        win = Gtk.Window(title="Downloader", modal=True)
        win.set_default_size(400, 150)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
        win.set_child(box)

        lbl_name = Gtk.Label(label=f"<b>File:</b> {filename}", use_markup=True, xalign=0)
        lbl_dest = Gtk.Label(label=f"<b>To:</b> {dest_folder}", use_markup=True, xalign=0)
        lbl_dest.add_css_class("caption") # Small dim text
        
        progress_bar = Gtk.ProgressBar(show_text=True)
        
        box.append(lbl_name)
        box.append(lbl_dest)
        box.append(progress_bar)
        
        win.present()
        return win, progress_bar

    # Initialize UI on main thread
    window, pbar = create_ui()

    def run_download():
        try:
            response = requests.get(url, stream=True, timeout=15)
            total_size = int(response.headers.get('content-length', 0))
            
            downloaded = 0
            with open(dest_path, 'wb') as f:
                for data in response.iter_content(chunk_size=4096):
                    f.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        percent = downloaded / total_size
                        # Update UI Progress
                        GLib.idle_add(pbar.set_fraction, percent)
            
            status["success"] = True
        except Exception as e:
            print(f"Download error: {e}")
            status["success"] = False
        finally:
            status["finished"] = True
            GLib.idle_add(window.destroy) # Close window when done
            event.set() # Wake up the calling thread

    # Start download thread
    thread = threading.Thread(target=run_download)
    thread.start()

    # We use a nested main loop to make this method "block" 
    # until the download finishes without freezing the UI.
    while not status["finished"]:
        GLib.MainContext.default().iteration(True)

    return status["success"]





def send_download_notification(status, file_name="", game_name=None, icon_path=None):
    # ... (Initialization and Title/Body logic remains the same) ...
    Notify.init("NOMM")
    
    if status == "success":
        title = "Download Successful"
        full_body = f"File {file_name} successfully downloaded for {game_name}"
    elif status == "failure-game-not-found":
        title = "Download Failed"
        full_body = f"Game {game_name} could not be found in game_configs, are you sure it is defined?"
    else:
        return

    notification = Notify.Notification.new(title, full_body)

    # 4. Handle the Icon
    if icon_path and os.path.exists(icon_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 64, 64, True)
            notification.set_icon_from_pixbuf(pixbuf)
        except Exception as e:
            print(f"Error loading notification pixbuf: {e}")
            # FIX: Wrap string in GLib.Variant
            notification.set_hint("desktop-entry", GLib.Variant.new_string("nomm"))
    else:
        # FIX: Wrap string in GLib.Variant
        # Use "nomm" to match your actual .desktop filename
        notification.set_hint("desktop-entry", GLib.Variant.new_string("nomm"))

    try:
        notification.show()
    except Exception as e:
        print(f"libnotify failed: {e}")