import os
import threading

import requests
from gi.repository import GLib, GObject

from gui.notifications import send_download_notification

class Downloader(GObject.Object):
    __gsignals__ = {
        'progress-changed': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'download-complete': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'download-error': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }
    
    def __init__(self):
            super().__init__()
            self._cancel = threading.Event()
            self._active_downloads = set()
            self._downloads_lock = threading.Lock()
    
    def cancel_all(self):
            self._cancel.set()

    def download_mod(self, url: str, dest_folder: str) -> bool:
        filename = url.split('/')[-1].split('?')[0] or "download"
        
        with self._downloads_lock:
            if filename in self._active_downloads:
                print(f"Download already in progress: {filename}")
                return False
            self._active_downloads.add(filename)
          
        dest_path = os.path.join(dest_folder, filename)
        os.makedirs(dest_folder, exist_ok=True)
        
        # Send a notification when downloading
        send_download_notification("started", file_name=filename)
          
        try:
            # Background task: downloading
            response = requests.get(url, stream=True, timeout=(15, 120))
            total_size = int(response.headers.get('content-length', 0))
            response.raise_for_status()
            downloaded = 0
            with open(dest_path, 'wb') as f:
                for data in response.iter_content(chunk_size=4096):
                    if self._cancel.is_set():
                          response.close()
                          os.remove(dest_path)
                          return False
                    f.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                            dl_ratio = downloaded / total_size
                            download_data = {
                                'filename' : filename,
                                'progress' : dl_ratio
                            }
                            GLib.idle_add(self.emit, 'progress-changed', download_data)
            send_download_notification("success", file_name=filename)
            
            GLib.idle_add(self.emit, 'download-complete', filename)
            return True
        except Exception as e:
            send_download_notification("failure-game-not-found", file_name=filename)
            print(f"Download error: {e}")
            error_data = {
                'filename' : filename,
                'error' : e
            }
            GLib.idle_add(self.emit, 'download-error', error_data)
            return False
        finally:
            with self._downloads_lock:
                self._active_downloads.discard(filename)