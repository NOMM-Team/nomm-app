import os
import subprocess
import zipfile

import rarfile

# Point rarfile to the bundled binary
rarfile.UNRAR_TOOL = "/app/bin/unrar"

def get_archive_type(file_path: str) -> str:
    lower_path = file_path.lower()
    if lower_path.endswith('.zip'): return 'zip'
    if lower_path.endswith('.rar'): return 'rar'
    if lower_path.endswith('.7z'): return '7z'
    return 'unknown'

def delete_downloaded_archive(self, btn, file_name):
    zip_path = os.path.join(self.dashboard.downloads_path, file_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)

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
            # Run and capture output to avoid spamming the console
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

def get_all_relative_files(directory_path: str) -> list[str]:
    all_files = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, directory_path)
            all_files.append(rel_path.replace('\\', '/'))
    return all_files