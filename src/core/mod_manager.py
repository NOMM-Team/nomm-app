import os
import shutil
import yaml
import threading
import subprocess
import zipfile
import vdf
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from gi.repository import GLib
from core.tools import load_yaml, write_yaml
from core.user_config import load_user_config
from core.archive_manager import extract_archive
from platforms.steam import add_launch_options

meta_lock = threading.Lock()

#TODO:Change the logic to deploy last mods from the index first
def deploy_mod_files(staging_dir: str, dest_dir: str, mod_files: list, mod_name: str) -> bool:
    dest_path = Path(dest_dir)
    
    staging_meta_path = os.path.join(Path(staging_dir), ".staging.nomm.yaml")
    staging_metadata = load_staging_metadata(staging_meta_path)
    
    folder_name=staging_metadata["mods"][mod_name].get("folder_name", staging_metadata["mods"][mod_name].get("display_name"))

    staging_mod_dir = Path(staging_dir) / folder_name
    
    is_success = True

    for mod_file in mod_files:
        source_item = Path(staging_mod_dir) / mod_file
        link_item = Path(dest_path) / mod_file

        if not source_item.exists():
            print(f"Mod file could not be found while deploying mod : {source_item}")
            continue
        
        # Creates parent folder
        link_item.parent.mkdir(parents=True, exist_ok=True)
        
        # (Override) Delete file if there is conflict
        if link_item.is_symlink():
            try:
                if not os.path.samefile(source_item, link_item):
                    print(f"Override: replaced {link_item} by {source_item}")
                    link_item.unlink()
                else:
                    print(f"File ignored: {mod_file} was already present in {dest_path}")
            #TODO: Check error use case
            except OSError:
                print(f"Failed to delete {source_item}: {OSError}")
                
        # Linking files
        if not link_item.exists():
            try:
                # symlink
                os.symlink(source_item, link_item)
                print(f"[+] Successfully linked {source_item}")
            except Exception as sym_e:
                print(f"Error creating a Symlink {link_item}: {sym_e}")
                is_success = False
    
    # Update game status
    if not is_success:
        unlink_mod_files(staging_mod_dir, dest_dir, mod_files)
        staging_metadata["mods"][mod_name].pop("enabled_timestamp", None)
        write_yaml(staging_metadata, staging_meta_path)
        return is_success
    
    return is_success

def get_mod_statistics(staging_meta_path: str, downloads_path: str) -> dict:
    stats = {
        "mods_inactive": 0,
        "mods_active": 0,
        "downloads_available": 0,
        "downloads_installed": 0
    }

    staging_metadata = load_staging_metadata(staging_meta_path)    
    if staging_metadata:
        # Loop to count mods active and inactive
        for mod_val in staging_metadata.get("mods", {}).values():
            if "enabled_timestamp" in mod_val:
                stats["mods_active"] += 1
            elif "enabled_timestamp" not in mod_val:
                stats["mods_inactive"] += 1
    
    if os.path.exists(downloads_path):
        archives = [f for f in os.listdir(downloads_path) if f.lower().endswith(('.zip', '.rar', '.7z'))]
        
        installed_archives = set()
        if staging_metadata:
            for mod_val in staging_metadata.get("mods", {}).values():
                if mod_val.get("archive_name"):
                    stats["downloads_installed"] += 1
                    installed_archives.add(mod_val.get("archive_name"))
        #  Loop to count downloads installed and available
        total_downloads = 0
        for f in archives:
            total_downloads += 1
        stats["downloads_available"] = total_downloads - stats["downloads_installed"]
        if stats["downloads_available"] < 0:
            stats["downloads_available"] = 0
    return stats

# Reworked during the refactor, loops on the mods in staging_metadata and checks
def is_mod_installed(archive_filename, staging_metadata) -> bool:
    if staging_metadata:
        for mod_val in staging_metadata.get("mods", {}).values():
            if mod_val.get("archive_name") == archive_filename:
                return True
    return False

# Checks if mod files from staging and dest folders are the same and remove the symlink if they are
def unlink_mod_files(staging_dir: str, dest_dir: str, mod_files: list[str]) -> bool:
    dest_path = Path(dest_dir)
    staging_path = Path(staging_dir)
    
    success = True
    
    for mod_file in mod_files:
        link_item = dest_path / mod_file
        source_item = staging_path / mod_file

        if link_item.exists() or link_item.is_symlink():
            try:
                if os.path.samefile(source_item, link_item):
                    link_item.unlink()
                    print(f"[-] Successfully unlinked {source_item}")
            except Exception as e:
                success = False
                print(f"Failed to unlink {link_item}: {e}")

        current_dir = link_item.parent
        while current_dir != dest_path:
            try:
                current_dir.rmdir()
            except OSError:
                break
            current_dir = current_dir.parent
    
    return success

def completely_uninstall_mod(staging_dir: str, dest_dir: str, mod_files: list[str]):
    unlink_mod_files(staging_dir, dest_dir, mod_files)
    
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)

def check_for_conflicts(staging_meta_path: str) -> list:
    path_registry = {}
    staging_metadata = load_staging_metadata(staging_meta_path)

    if not staging_metadata:
        return []

    for mod in staging_metadata.get("mods", {}):
        for file_path in staging_metadata["mods"][mod].get("mod_files", []):
            if file_path not in path_registry:
                path_registry[file_path] = []
            path_registry[file_path].append(mod)
    
    # Extract only the lists where multiple mods claim the same file
    conflicts = []
    for mod_list in path_registry.values():
        if len(mod_list) > 1:
            unique_mods = sorted(list(set(mod_list)))
            if unique_mods not in conflicts:
                conflicts.append(unique_mods)

    return conflicts

def build_deployment_map(staging_metadata: dict) -> dict:
    
    if not staging_metadata:
        return []
    
    deployment_map = {}
    for mod in reversed(staging_metadata["index"]):
        if "enabled_timestamp" in staging_metadata["mods"][mod]:
            for file_path in staging_metadata["mods"][mod].get("mod_files", []):
                if file_path not in deployment_map:
                    deployment_map[file_path] = mod
    
    return deployment_map

def check_for_deployment_map_change(new_deployment_map: dict, current_deployment_map: dict) -> list:
    changes = {
        'additions': {},
        'deletions': {}
    }
    
    for file in new_deployment_map:
        if file not in current_deployment_map or current_deployment_map.get(file) != new_deployment_map.get(file) :
            additional_change = {
                'current_source' : current_deployment_map.get(file), 
                'new_source' : new_deployment_map.get(file)
            }
            changes['additions'][file] = additional_change
            
    for file in current_deployment_map:
        if file not in new_deployment_map:
            changes['deletions'][file] = current_deployment_map.get(file)
    
    return changes

def apply_deployment_map_changes(staging_dir: str, dest_dir: str, changes: dict, mod_name: str) -> bool:
    files_to_unlink = {}
    files_to_link = {}
    
    # Apply additions
    for change in changes['additions']:
        deleting_mod_name = changes['additions'][change].get('current_source')
        deploying_mod_name = changes['additions'][change].get('new_source')
        
        if deleting_mod_name:
            if not files_to_unlink.get(deleting_mod_name, []):
                files_to_unlink[deleting_mod_name] = []
            files_to_unlink[deleting_mod_name].append(change)
        
        if not files_to_link.get(deploying_mod_name, []):
            files_to_link[deploying_mod_name] = []
        
        files_to_link[deploying_mod_name].append(change)
    
    # Apply deletions
    for file in changes['deletions']:
        deploying_mod_name = changes['deletions'][file]
        if not files_to_unlink.get(deploying_mod_name, []):
            files_to_unlink[deploying_mod_name] = []    
        
        files_to_unlink[deploying_mod_name].append(file)
    
    # Starts unlinking files
    def unlink_files(staging_dir, dest_dir, files_to_unlink, files_to_link):
        metadata = load_staging_metadata(os.path.join(staging_dir, ".staging.nomm.yaml"))
        for mod in files_to_unlink:
            mod_info = metadata["mods"].get(mod, {})
            folder_name = mod_info.get("folder_name", mod_info.get("display_name", mod))
            staging_mod_dir = Path(staging_dir) / folder_name
            unlink_mod_files(staging_mod_dir, dest_dir, files_to_unlink[mod])
        GLib.idle_add(on_unlink_finish, staging_dir, dest_dir, files_to_link)
    
    # Starts deploying files
    def on_unlink_finish(staging_dir, dest_dir, files_to_link):
        for mod in files_to_link:
            if deploy_mod_files(staging_dir, dest_dir, files_to_link[mod], mod) == False:
                print(f"Error while deploying: {mod}")
                return False
    
    threading.Thread(target=unlink_files, args=(staging_dir, dest_dir, files_to_unlink, files_to_link), daemon=True).start()
    
    return True

# Dashboard.py/find_text_file
def find_text_file(mod_files: list) -> str:
    for file_path in mod_files:
        if ".txt" in file_path:
            return file_path
    return ""

def deploy_essential_utility(util_config: dict, downloads_path: str, staging_path: str, game_path: str, steam_base: str, steam_id: str):
    source_url = util_config.get("source")
    filename = source_url.split("/")[-1]
    archive_path = os.path.join(downloads_path, "utilities", filename)
    staging_path = Path(staging_path) / "utilities" / util_config["name"]
    
    game_root = Path(game_path)

    # Archive extraction to staging
    print("Extracting utility contents")
    extract_archive(archive_path, staging_path)

    # Whitelist and blacklist management
    whitelist = util_config.get("whitelist", [])
    blacklist = util_config.get("blacklist", [])

    if whitelist or blacklist:
        print("Applying whitelist/blacklist filters to extracted files...")
        files_to_remove = []

        for root, dirs, files in os.walk(staging_path):
            for file_name in files:
                file_full_path = Path(root) / file_name

                if blacklist and file_name in blacklist:
                    files_to_remove.append(file_full_path)
                    continue

                if whitelist and file_name not in whitelist:
                    files_to_remove.append(file_full_path)

        for file_to_remove in files_to_remove:
            try:
                file_to_remove.unlink()
                print(f"[-] Filtered out: {file_to_remove.name}")
            except Exception as e:
                print(f"[!] Failed to remove filtered file {file_to_remove}: {e}")

        # Empty folder cleanup
        for root, dirs, files in os.walk(staging_path, topdown=False):
            for dir_name in dirs:
                dir_full_path = Path(root) / dir_name
                try:
                    dir_full_path.rmdir()
                except OSError:
                    pass # Folder is not empty, so skip it

    # Actual deployment to game files if needed
    is_internal = util_config.get("install_in_game_files", True)
    if is_internal:
        install_subpath = util_config["utility_path"]
        target_dir = game_root / install_subpath        
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"Deploying utility files to game directory: {target_dir}")
        for root, dirs, files in os.walk(str(staging_path)):
            for file_name in files:
                source_file = os.path.join(root, file_name)

                relative_path = os.path.relpath(source_file, str(staging_path))
                destination_file = target_dir / relative_path
                destination_file.parent.mkdir(parents=True, exist_ok=True)

                try:
                    shutil.copy2(source_file, destination_file)
                    print(f"[+] Deployed & overwrote: {relative_path}")
                except Exception as e:
                    print(f"[!] Failed to copy {relative_path} to game directory: {e}")

    # Some utilities require a command to be launched as a one-shot to enable the utility
    command = util_config.get("enable_command")
    if command:
        print(f"Running utility enable command: {command}")
        subprocess.run(command, shell=True, cwd=game_root)

    # Some utilities require specific launch options to run properly
    launch_options = util_config.get("launch_options")
    if launch_options:
        add_launch_options(steam_base, launch_options)

def toggle_mod_state(mod_name: str, mod_files: list, state: bool, staging_dir: str, deployment_map: list) -> dict:
    staging_meta_path = os.path.join(staging_dir, ".staging.nomm.yaml")

    with meta_lock:
        staging_metadata = load_staging_metadata(staging_meta_path)

        if not staging_metadata or mod_name not in staging_metadata.get("mods", {}):
            return False

        mod_info = staging_metadata["mods"][mod_name]
        dest_dir = mod_info["deployment_path"]
        staging_mod_dir = os.path.join(staging_dir, mod_info["folder_name"])
        mod_files = mod_info.get("mod_files", [])

        conflicts_exist = check_for_conflicts(staging_meta_path)

        new_deployment_map = {}
        success = True

        # state is true so the mod has to be installed/deployed
        if state:
            # deploy_mod_files return true if it worked, false if it doesn't
            mod_info["enabled_timestamp"] = datetime.now()
            write_yaml(staging_metadata, staging_meta_path)
            if conflicts_exist:
                new_deployment_map = build_deployment_map(staging_metadata)
                if deployment_map != new_deployment_map:
                    changes = check_for_deployment_map_change(new_deployment_map, deployment_map)
                    success = apply_deployment_map_changes(staging_dir, dest_dir, changes, mod_name)
            else:
                if deploy_mod_files(staging_dir, dest_dir, mod_files, mod_name):
                    for mod_file in mod_files:
                        deployment_map[mod_file] = mod_name
                    print(f"Successfully deployed mod: {mod_name}")
                else:
                    success = False
        # state is false, deleting the datas and ensure metadata are set to proper value
        else:
            # Pop is a safety measure to prevent a crash for a missing key
            mod_info.pop("enabled_timestamp", None)
            write_yaml(staging_metadata, staging_meta_path)
            # If there is a conflict mods have to be reloaded in case you unloaded a mod that did an override
            if conflicts_exist:
                # Recalculating mod files
                new_deployment_map = build_deployment_map(staging_metadata)
                if deployment_map != new_deployment_map:
                    changes = check_for_deployment_map_change(new_deployment_map, deployment_map)
                    success = apply_deployment_map_changes(staging_dir, dest_dir, changes, mod_name)
            else:
                if unlink_mod_files(staging_mod_dir, dest_dir, mod_files):
                    for mod_file in mod_files:
                        del deployment_map[mod_file]
                    print(f"Successfully removed mod: {mod_name}")
                else:
                    success = False
        
        # Update deployment map
        if success and conflicts_exist:
            deployment_map = new_deployment_map
        
        deployment_output = {
            'success': success,
            'deployment_map': deployment_map
        }
        
        return deployment_output

def get_metadata_path(base_folder: str, is_staging: bool = True) -> str:
    filename = ".staging.nomm.yaml" if is_staging else ".downloads.nomm.yaml"
    return os.path.join(base_folder, filename)

def load_staging_metadata(path: str) -> dict:
    data = load_yaml(path)
    
    # load metadata also initialize the staging_metadata as a safety measure
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
    data = load_staging_metadata(path)

    if mod_name in data["mods"]:
        del data["mods"][mod_name]
        if mod_name in data["index"]:
            data["index"].remove(mod_name)
        
        write_yaml(data, path)
        
        staging_path = os.path.dirname(path)
        
        return True
    return False

# Writing the metadata with needed fields
def finalise_mod_metadata(filename: str, mod_files: list, deployment_target: dict, staging_meta_path: str, downloads_meta_path: str):
    current_download_metadata = {}

    mod_name = filename.replace(".zip", "").replace(".rar", "").replace(".7z", "")
    with meta_lock:
        current_staging_metadata = load_staging_metadata(staging_meta_path)
        # This request should only fail if all previous files were manually added --> can be fixed with a rework of check_index
        if os.path.exists(downloads_meta_path):
            with open(downloads_meta_path, 'r') as f:
                current_download_metadata = yaml.safe_load(f) or {}
            if "info" in current_download_metadata:
                current_staging_metadata["info"] = current_download_metadata["info"]
            if filename in current_download_metadata.get("mods"):
                mod_data = current_download_metadata["mods"][filename]
                mod_name = mod_data.get("name", mod_name)
                current_staging_metadata["mods"][mod_name] = mod_data
                if "folder_name" not in current_staging_metadata["mods"][mod_name]:
                    current_staging_metadata["mods"][mod_name]["folder_name"] = mod_data["name"]
                    current_staging_metadata["mods"][mod_name].pop("name")

        # Catch-all check in case we don't have the metadata initialised for that mod
        if mod_name not in current_staging_metadata["mods"]:
            current_staging_metadata["mods"][mod_name] = {}
            current_staging_metadata["mods"][mod_name]["folder_name"] = mod_name
            current_staging_metadata["mods"][mod_name]["display_name"] = mod_name

        current_staging_metadata["mods"][mod_name]["mod_files"] = mod_files
        current_staging_metadata["mods"][mod_name]["archive_name"] = filename
        current_staging_metadata["mods"][mod_name]["install_timestamp"] = datetime.now()
        current_staging_metadata["mods"][mod_name]["deployment_path"] = deployment_target["path"]
        if "folder_name" not in current_staging_metadata["mods"][mod_name]:
            current_staging_metadata["mods"][mod_name]["folder_name"] = current_staging_metadata["mods"][mod_name].get("display_name", current_staging_metadata["mods"][mod_name].get("name")) 

        if mod_name not in current_staging_metadata["index"]:
            current_staging_metadata["index"].append(mod_name)

        write_yaml(current_staging_metadata, staging_meta_path)

# Mostly returns index, will very likely disappear in the future
def read_index(staging_meta_path: str) -> List[str]:
    current_staging_metadata = load_staging_metadata(staging_meta_path)
    return current_staging_metadata["index"]

# Change the mod index from the index list
def change_mod_index(staging_meta_path: str, mod_name: str, index: int) -> dict:
    current_staging_metadata=load_staging_metadata(staging_meta_path)
    
    if mod_name in current_staging_metadata["index"]:
        pos = current_staging_metadata["index"].index(mod_name)
        mod = current_staging_metadata["index"].pop(pos)
        current_staging_metadata["index"].insert(index, mod)
        
        write_yaml(current_staging_metadata, staging_meta_path) 
    
    return current_staging_metadata