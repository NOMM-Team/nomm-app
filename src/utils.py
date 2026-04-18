#utils.py

#Global imports
import os, json, requests, threading, gi, yaml, random

#Specific imports
from gi.repository import Gtk, Adw, GLib, Gdk, Gio, GdkPixbuf, Notify

def download_heroic_assets(appName: str, platform: str):
    # 1. Define Paths
    json_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/store/download-manager.json") # flatpak
    if not os.path.exists(json_path):
        json_path = os.path.expanduser("~/.config/heroic/store/download-manager.json") # not flatpak

    if isinstance(appName, list):
        appName = appName[0]
    
    cache_base = os.path.join(GLib.get_user_data_dir(), f"nomm/image-cache/{platform}/{appName}")
    
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

    # 1. Envoyer une notification de démarrage
    send_download_notification("started", file_name=filename)

    success = False
    try:
        # 2. Télécharger le fichier silencieusement
        response = requests.get(url, stream=True, timeout=15)
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(chunk_size=4096):
                f.write(data)
        success = True
    except Exception as e:
        print(f"Download error: {e}")
        success = False

    return success

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
    Notify.init("NOMM")
    
    if status == "success":
        title = "Téléchargement terminé"
        full_body = f"Le fichier {file_name} a été téléchargé avec succès pour {game_name}."
    elif status == "failure-game-not-found":
        title = "Échec du téléchargement"
        full_body = f"Le jeu {game_name} n'a pas été trouvé dans NOMM."
    elif status == "started":
        title = "Téléchargement en cours..."
        full_body = f"Le téléchargement de {file_name} a démarré en arrière-plan."
    else:
        return

    notification = Notify.Notification.new(title, full_body)

    # Handle the Icon
    if icon_path and os.path.exists(icon_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 64, 64, True)
            notification.set_icon_from_pixbuf(pixbuf)
        except Exception as e:
            print(f"Error loading notification pixbuf: {e}")
            notification.set_hint("desktop-entry", GLib.Variant.new_string("nomm"))
    else:
        notification.set_hint("desktop-entry", GLib.Variant.new_string("nomm"))

    try:
        notification.show()
    except Exception as e:
        print(f"libnotify failed: {e}")
