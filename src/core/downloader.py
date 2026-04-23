import os
import threading

import requests
from gi.repository import GLib

from gui.notifications import send_download_notification
from typing import Optional, Callable

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
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(chunk_size=4096):
                f.write(data)
        success = True
    except Exception as e:
        print(f"Download error: {e}")
        success = False

    return success

# Used for download_utility
def download_file_async(url: str, dest_folder: str, on_success_callback: Optional[Callable], on_error_callback: Optional[callable]) -> None:
    # Downloader function
    def worker():
        filename = url.split('/')[-1].split('?')[0] or "download"
        dest_path = os.path.join(dest_folder, filename)
        # exist_ok=true prevents from sending an error if path exists (and from adding a if not path.exist logic)
        os.makedirs(dest_folder, exist_ok=True)

        try:
            # Stream=true loads headers so you can get the response and keep the connexion open instead of directly download the whole body of the request
            # Request is processed with response.itter_content()
            response = requests.get(url, stream=True, timeout=15)
            # Identical to is_valid = response.status_code == 200, personal preferences only matters here
            response.raise_for_status()
            
            # Opens the file, wb means write and binary, binary is used for system compatibility, but useless if only used on linux
            with open(dest_path, 'wb') as f:
                # Splits the response in chunks of 4096 to prevent RAM from storing the whole data
                # Writes the data on the disk chunk by chunk istead of doing (1) download everything (2) move everything from the RAM to the storage
                for data in response.iter_content(chunk_size=4096):
                    f.write(data)
            
            # callback
            if on_success_callback:
                GLib.idle_add(on_success_callback)
                
        except Exception as e:
            print(f"Download utility error: {e}")
            if on_error_callback:
                GLib.idle_add(on_error_callback, str(e))

    # Launchs the previous function (worker) in a separate thread to prevent the app from freezing
    threading.Thread(target=worker, daemon=True).start()