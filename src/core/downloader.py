#src/core/downloader.py

import os
import requests
import threading
from gi.repository import GLib
from gui.notifications import send_download_notification

def download_mod(url: str, dest_folder: str) -> bool:
    filename = url.split('/')[-1].split('?')[0] or "download"
    dest_path = os.path.join(dest_folder, filename)
    os.makedirs(dest_folder, exist_ok=True)

    # Send a notification when downloading
    send_download_notification("started", file_name=filename)

    success = False
    try:
        # Background task: downloading
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status() # Ajout d'une bonne pratique standard (lance une erreur si code HTTP n'est pas 200)
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(chunk_size=4096):
                f.write(data)
        success = True
    except Exception as e:
        print(f"Download error: {e}")
        success = False

    return success

def download_file_async(url: str, dest_folder: str, on_success_callback: Optional[Callable], on_error_callback: Optional[callable]) -> None:
    def worker():
        # Extract game name
        filename = url.split('/')[-1].split('?')[0] or "download"
        dest_path = os.path.join(dest_folder, filename)
        os.makedirs(dest_folder, exist_ok=True)

        try:
            response = requests.get(url, stream=True, timeout=15)
            response.raise_for_status() # Lève une erreur si le téléchargement échoue (ex: 404, 403)
            
            with open(dest_path, 'wb') as f:
                for data in response.iter_content(chunk_size=4096):
                    f.write(data)
            
            if on_success_callback:
                GLib.idle_add(on_success_callback)
                
        except Exception as e:
            print(f"Download utility error: {e}")
            if on_error_callback:
                GLib.idle_add(on_error_callback, str(e))

    # Lance le téléchargement dans un thread séparé
    threading.Thread(target=worker, daemon=True).start()