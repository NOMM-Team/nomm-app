# src/core/drag_drop_file.py 

import os
import shutil
from urllib.parse import unquote
from pathlib import Path

from gi.repository import Gtk, Gdk, GObject

def process_dropped_files(uri_list: list[str], destination_path: str) -> list[str]:
    copied_files = []
    dest_path = Path(destination_path)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    for uri in uri_list:
        if not uri.strip():
            continue
        
        file_path = unquote(uri.replace('file://', '').strip())
        file_path = file_path.replace('\r', '').replace('\n', '')

        src_file = Path(file_path)

        if src_file.is_file():
            try:
                target_file = dest_path / src_file.name
                shutil.copy2(src_file, target_file)
                copied_files.append(src_file.name)
            except Exception as e:
                print(f"Error while copying  {src_file.name}: {e}")

    return copied_files

