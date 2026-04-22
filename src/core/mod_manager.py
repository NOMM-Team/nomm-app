import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.config import load_yaml, write_yaml

# To check
def deploy_mod_files(staging_dir: str, dest_dir: str, mod_files: list[str]) -> bool:
    dest_path = Path(dest_dir)
    staging_path = Path(staging_dir)
    success = True

    for mod_file in mod_files:
        
        source_item = Path(staging_path) / mod_file
        link_item = Path(dest_path) / mod_file

        if not source_item.exists():
            continue

        # Creates parent folder
        link_item.parent.mkdir(parents=True, exist_ok=True)
        
        # (Override) Delete file if there is conflict
        if link_item.exists() or link_item.is_symlink():
            try:
                if not os.path.samefile(source_item, link_item):
                    link_item.unlink()
            except OSError:
                link_item.unlink()
                
        # Linking files
        if not link_item.exists():
            try:
                # symlink
                os.symlink(source_item, link_item)
                print(f"successfully created a symlink as a fallback for {link_item}")
            except Exception as sym_e:
                print(f"Error creating a Symlink {link_item}: {sym_e}")
                success = False                
    return success

# Just a loop that deploy mods following the index list
def deploy_all_ordered_mods(staging_path: str, game_path: str, staging_metadata_path: str):
    indexed_mods = read_index(staging_metadata_path)
    metadata = load_metadata(staging_metadata_path)
    
    for mod_name in indexed_mods:
        if mod_name in metadata.get("mods", {}):
            mod_info = metadata["mods"][mod_name]
            if mod_info.get("status") == "enabled":
                source_dir = os.path.join(staging_path, mod_name)
                deploy_mod_files(
                    source_dir, 
                    game_path, 
                    mod_info.get("files", [])
                )

# 100% same function
def get_mod_statistics(staging_metadata_path: str, downloads_path: str) -> dict:
    stats = {
        "mods_inactive": 0,
        "mods_active": 0,
        "downloads_available": 0,
        "downloads_installed": 0
    }

    staging_metadata = load_metadata(staging_metadata_path)    
    if staging_metadata:
        for mod_val in staging_metadata.get("mods", {}).values():
            if mod_val.get("status") == "enabled":
                stats["mods_active"] += 1
            elif mod_val.get("status") == "disabled":
                stats["mods_inactive"] += 1
    
    if downloads_path and os.path.exists(downloads_path):
        archives = [f for f in os.listdir(downloads_path) if f.lower().endswith(('.zip', '.rar', '.7z'))]
        
        installed_archives = set()
        if staging_metadata:
            for mod_val in staging_metadata.get("mods", {}).values():
                arch = mod_val.get("archive_name")
                if arch:
                    installed_archives.add(arch)
        
        for f in archives:
            if f in installed_archives:
                stats["downloads_installed"] += 1
            else:
                stats["downloads_available"] += 1
                
    return stats

# No changes
def is_mod_installed(archive_filename, staging_metadata):
    if staging_metadata:
        for mod_val in staging_metadata.get("mods", {}).values():
            if mod_val.get("archive_name") == archive_filename:
                return True
    return False


def remove_mod_files(staging_dir: str, dest_dir: str, mod_files: list[str]):
    dest_path = Path(dest_dir)
    staging_path = Path(staging_dir)

    for mod_file in mod_files:
        link_item = dest_path / mod_file
        source_item = staging_path / mod_file

        if link_item.exists() or link_item.is_symlink():
            try:
                if os.path.samefile(source_item, link_item):
                    link_item.unlink()
            except Exception as e:
                print(f"Erreur lors de la suppression de {link_item}: {e}")

        current_dir = link_item.parent
        while current_dir != dest_path:
            try:
                current_dir.rmdir()
            except OSError:
                break
            current_dir = current_dir.parent

def completely_uninstall_mod(staging_dir: str, dest_dir: str, mod_files: list[str]):
    remove_mod_files(staging_dir, dest_dir, mod_files)
    
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)

# 100% identical      
def check_for_conflicts(staging_metadata_path: str) -> list:
    path_registry = {}
    staging_metadata = load_metadata(staging_metadata_path)

    if not staging_metadata:
        return []

    for mod in staging_metadata.get("mods", {}):
        for file_path in staging_metadata["mods"][mod].get("mod_files", []):
            if file_path not in path_registry:
                path_registry[file_path] = []
            path_registry[file_path].append(mod)

    conflicts = []
    for mod_list in path_registry.values():
        if len(mod_list) > 1:
            unique_mods = sorted(list(set(mod_list)))
            if unique_mods not in conflicts:
                conflicts.append(unique_mods)

    return conflicts

# Litterally the same
def find_text_file(mod_files: list) -> str:
    for file_path in mod_files:
        if ".txt" in file_path:
            return file_path
    return None

# TO CHECk
def is_utility_installed(local_zip_path: Path, target_dir: Path) -> bool:
    if not local_zip_path.exists():
        return False
    try:
        with zipfile.ZipFile(local_zip_path, 'r') as z:
            return all((target_dir / name).exists() for name in z.namelist() if not name.endswith('/'))
    except Exception: 
        return False

 # 100% identical
def deploy_essential_utility(util_config: dict, downloads_path: str, game_path: str):
    source_url = util_config.get("source")
    filename = source_url.split("/")[-1]
    zip_path = Path(downloads_path) / "utilities" / filename
    
    game_root = Path(game_path)
    install_subpath = util_config.get("utility_path", "")
    target_dir = game_root / install_subpath
    target_dir.mkdir(parents=True, exist_ok=True)

    whitelist = util_config.get("whitelist", [])
    blacklist = util_config.get("blacklist", [])

    with zipfile.ZipFile(zip_path, 'r') as z:
        if not whitelist and not blacklist:
            z.extractall(target_dir)
        else:
            for file_info in z.infolist():
                file_name = file_info.filename
                if whitelist and not any(allowed in file_name for allowed in whitelist):
                    continue
                if blacklist and any(blocked in file_name for blocked in blacklist):
                    continue
                z.extract(file_info, target_dir)

    cmd = util_config.get("enable_command")
    if cmd:
        subprocess.run(cmd, shell=True, cwd=game_root)

# To check
def toggle_mod_state(mod_name: str, mod_files: list, state: bool, staging_path: str, deployment_targets: list, metadata_path: str) -> bool:
    staging_metadata = load_metadata(metadata_path)
    
    if not deployment_targets or not staging_metadata or mod_name not in staging_metadata.get("mods", {}):
        return False

    dest_dir = deployment_targets[0]["path"]
    mod_meta = staging_metadata["mods"][mod_name]
    
    if "deployment_target" in mod_meta:
        for target in deployment_targets:
            if target["name"] == mod_meta["deployment_target"]:
                dest_dir = target["path"]
                break

    staging_mod_dir = os.path.join(staging_path, mod_name)

    if state:
        success = deploy_mod_files(staging_mod_dir, dest_dir, mod_files)
        if success:
            mod_meta["status"] = "enabled"
            mod_meta["enabled_timestamp"] = datetime.now().strftime("%c")
            write_yaml(staging_metadata, metadata_path)
            return True
        return False
    else:
        remove_mod_files(staging_mod_dir, dest_dir, mod_files)
        mod_meta["status"] = "disabled"
        mod_meta.pop("enabled_timestamp", None)
        write_yaml(staging_metadata, metadata_path)
        return True

# PREVIOUSLY IN CONFIG -- As this part is related to modlist/mod order/... It probably should end up here
def get_metadata_path(base_folder: str, is_staging: bool = True) -> str:
    filename = ".staging.nomm.yaml" if is_staging else ".downloads.nomm.yaml"
    return os.path.join(base_folder, filename)

def load_metadata(path: str) -> dict:
    data = load_yaml(path)
    
    if not isinstance(data, dict):
        data = {}
    if "mods" not in data:
        data["mods"] = {}
    if "info" not in data:
        data["info"] = {}
    if "index" not in data:
        data["index"] = []
        
    return data

# Removes the mod from the staging metadata -- metadata allows to list mods that are installed
def remove_mod_from_metadata(path: str, mod_name: str) -> bool:
    data = load_metadata(path)

    if mod_name in data["mods"]:
        del data["mods"][mod_name]
        if mod_name in data["index"]:
            data["index"].remove(mod_name)
        
        write_yaml(data, path)
        
        staging_path = os.path.dirname(path)
        
        return True
    return False

# OK
def finalize_mod_metadata(filename: str, extracted_roots: list, deployment_target_name: str, staging_meta_path: str, downloads_meta_path: str):
    from datetime import datetime
    
    current_staging_metadata = load_metadata(staging_meta_path)
    current_download_metadata = {}

    #This request should only fail if all previous files were manually added --> can be fixed with a rework of check_index
    if os.path.exists(downloads_meta_path):
        with open(downloads_meta_path, 'r') as f:
            current_download_metadata = yaml.safe_load(f) or {}

    if "info" not in current_staging_metadata and "info" in current_download_metadata:
        current_staging_metadata["info"] = current_download_metadata["info"]
    
    mod_name = filename.replace(".zip", "").replace(".rar", "").replace(".7z", "")
    
    if filename in current_download_metadata.get("mods", {}):
        mod_data = current_download_metadata["mods"][filename]
        mod_name = mod_data.get("name", mod_name)
        current_staging_metadata["mods"][mod_name] = mod_data
    else:
        current_staging_metadata["mods"][mod_name] = {}

    current_staging_metadata["mods"][mod_name]["mod_files"] = extracted_roots
    current_staging_metadata["mods"][mod_name]["status"] = "disabled"
    current_staging_metadata["mods"][mod_name]["archive_name"] = filename
    current_staging_metadata["mods"][mod_name]["install_timestamp"] = datetime.now().strftime("%c")
    current_staging_metadata["mods"][mod_name]["deployment_target"] = deployment_target_name
   
   #Adding index for load order
    if "index" not in current_staging_metadata:
        current_staging_metadata["index"] = []

    if mod_name not in current_staging_metadata["index"]:
        current_staging_metadata["index"].append(mod_name)
    
    staging_path = os.path.dirname(staging_meta_path)

    write_yaml(current_staging_metadata, staging_meta_path)

# Mostly returns index, will very likely disappear in the future
def read_index(staging_meta_path: str) -> bool:
    current_staging_metadata = load_metadata(staging_meta_path)
    return current_staging_metadata["index"]

# Change the mod index from the index list
def change_mod_index(staging_meta_path: str, mod_name: str, index: int):
    current_staging_metadata=load_metadata(staging_meta_path)
    
    if mod_name in current_staging_metadata["index"]:
        pos = current_staging_metadata["index"].index(mod_name)
        mod = current_staging_metadata["index"].pop(pos)
        current_staging_metadata["index"].insert(index, mod)
        
        try:
            write_yaml(current_staging_metadata, staging_meta_path)
            return True
        except Exception as e:
            print(f"Error while changing mod index: {e}")
            return False
    return False

# This method has to be changed so it refreshes ALL the metadata and loads everygame to make sure the display is never broken

##def check_index(staging_path: str):
##    if not os.path.exists(staging_path):
##        return []
##        
##    physical_folders = [
##        f for f in os.listdir(staging_path) 
##        if os.path.isdir(os.path.join(staging_path, f)) and not f.startswith('.')
##    ]
##
##    test_path = os.path.join(staging_path, ".staging.nomm.yaml")
##    current_index = read_index(test_path)
##    new_index = [mod for mod in current_index if mod in physical_folders]
##    
##    changed = False
##    for folder in physical_folders:
##        if folder not in new_index:
##            new_index.append(folder)
##            changed = True
##            
##    if len(new_index) != len(current_index):
##        changed = True
##
##    if changed:
##        try:
##            write_yaml(new_index, test_path)
##        except Exception as e:
##            print(f"Error while syncing index : {e}")
##
##    return new_index