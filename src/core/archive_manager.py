import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import unquote

import rarfile

# Point rarfile to the bundled binary
rarfile.UNRAR_TOOL = "/app/bin/unrar"

# dashboard.py/on_install_clicked
def get_archive_type(file_path: str) -> str:
    lower_path = file_path.lower()
    if lower_path.endswith('.zip'): return 'zip'
    if lower_path.endswith('.rar'): return 'rar'
    if lower_path.endswith('.7z'): return '7z'
    return 'unknown'

# Cleaning method after extracting the archive
# Dashboard.py/delete_download_package + downloads tab for the try/catch
def delete_downloaded_archive(widget, btn, file_name):
    zip_path = os.path.join(widget.downloads_path, file_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)

# dashboard.py/on_install_clicked
def extract_archive(archive_path: str, destination_path: str) -> bool:
    arc_type = get_archive_type(archive_path)
    os.makedirs(destination_path, exist_ok=True)

    try:
        if arc_type == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(destination_path)
        elif arc_type == 'rar':
            with rarfile.RarFile(archive_path, 'r') as rf:
                rf.extractall(destination_path)
        elif arc_type == '7z':
            subprocess.run(
                ["7z", "x", archive_path, f"-o{destination_path}", "-y"],
                capture_output=True, 
                text=True,
                check=True
            )
        else:
            raise ValueError(f"Unknown archive type {archive_path}")
        return True
    except Exception as e:
        raise Exception(f"Error while extracting {arc_type} : {e}")

# Builds path toward the desired file by returning the files one by one in a list of string
# dashboard.py/on_install_clicked
def get_all_relative_files(directory_path: str) -> list[str]:
    all_files = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, directory_path)
            all_files.append(rel_path.replace('\\', '/'))
    return all_files

# Drop file on the download tab to import mods
# new
def process_dropped_files(uri_list: list[str], destination_path: str) -> list[str]:
    # Init var
    copied_files = []
    dest_path = Path(destination_path)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    # For each file/archive dropped
    for uri in uri_list:
        if not uri.strip():
            continue
        
        file_path = unquote(uri.replace('file://', '').strip())
        file_path = file_path.replace('\r', '').replace('\n', '')

        src_file = Path(file_path)

        if src_file.is_file():
            try:
                target_file = dest_path / src_file.name
                #Copy 2 is like shutil.copy but keeps metadata
                shutil.copy2(src_file, target_file)
                copied_files.append(src_file.name)
            except Exception as e:
                print(f"Error while copying  {src_file.name}: {e}")

    return copied_files