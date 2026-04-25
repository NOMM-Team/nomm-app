import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from core.tools import show_message

from core.tools import load_yaml, write_yaml

#TODO:Change the logic to deploy last mods from the index first
def deploy_mod_files(staging_dir: str, dest_dir: str, mod_name: str) -> bool:
    dest_path = Path(dest_dir)
    staging_mod_path = os.path.join(Path(staging_dir), mod_name)
    
    staging_metadata_path = os.path.join(Path(staging_dir), ".staging.nomm.yaml")
    staging_metadata = load_metadata(staging_metadata_path)
    
    mod_info = staging_metadata["mods"][mod_name]
    mod_files = mod_info.get("mod_files", [])
    
    success = True

    for mod_file in mod_files:
        source_item = Path(staging_mod_path) / mod_file
        link_item = Path(dest_path) / mod_file

        if not source_item.exists():
            print(f"Mod file could not be found while deploying mod : {source_item}")
            continue
        
        # Resolve function was not working so link_item.resolve has been reversed to link_item temporarily
        # if os.path.isfile(link_item):
        #     print(f"Failed to install file: did not override standard file: {link_item}")
        #     return False
        
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
                link_item.unlink()
                
        # Linking files
        if not link_item.exists():
            try:
                # symlink
                os.symlink(source_item, link_item)
                print(f"Successfully created a symlink for {link_item}")
            except Exception as sym_e:
                print(f"Error creating a Symlink {link_item}: {sym_e}")
                success = False
    
    # Update game status
    if not success:
        unlink_mod_files(staging_mod_path, dest_dir, mod_files)
        staging_metadata["mods"][mod_name]["status"] = "disabled"
        mod_info.pop("enabled_timestamp", None)
        write_yaml(staging_metadata, staging_metadata_path)
        
    return success

# Just a loop that deploy mods following the index list
# new
def deploy_all_ordered_mods(staging_path: str, dest_dir: str) -> bool:
    staging_metadata_path = os.path.join(staging_path, ".staging.nomm.yaml")
    indexed_mods = read_index(staging_metadata_path)
    metadata = load_metadata(staging_metadata_path)
    
    for mod_name in metadata["mods"]:
        if metadata["mods"][mod_name]["status"] == "enabled":
            mod_staging_dir = os.path.join(staging_path, mod_name)
            unlink_mod_files(mod_staging_dir, dest_dir, metadata["mods"][mod_name].get("mod_files"))
    
    # Loop from item in index metadata, first on the list is deployed first etc...
    error_count = 0
    for mod_name in indexed_mods:
        if mod_name in metadata.get("mods", {}):
            mod_info = metadata["mods"][mod_name]
            if mod_info.get("status") == "enabled":
                if not deploy_mod_files(
                    staging_path,
                    dest_dir,
                    mod_name
                ):
                    error_count += 1
    if error_count:
        show_message(_("Error"), _("Installation failed: {}").format(e))
        show_message(_("Error"), ngettext(
                    "{} installation failed, see logs for more details",
                    "{} installations failed, see logs for more details",
                    error_count)
                ).format(error_count)
        return False
    return True

# dashboard.py/update_indicators with available downloads and mods grouped but logic is the same
def get_mod_statistics(staging_metadata_path: str, downloads_path: str) -> dict:
    # Dictionary is initialized here
    stats = {
        "mods_inactive": 0,
        "mods_active": 0,
        "downloads_available": 0,
        "downloads_installed": 0
    }

    staging_metadata = load_metadata(staging_metadata_path)    
    if staging_metadata:
        # Loop to count mods active and inactive
        for mod_val in staging_metadata.get("mods", {}).values():
            if mod_val.get("status") == "enabled":
                stats["mods_active"] += 1
            elif mod_val.get("status") == "disabled":
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
    return stats

# Reworked during the refactor, loops on the mods in staging_metadata and checks
# dashboard.py/is_mod_installed but f "archive_name" not in staging_metadata["mods"][mod] removed
def is_mod_installed(archive_filename, staging_metadata) -> bool:
    if staging_metadata:
        for mod_val in staging_metadata.get("mods", {}).values():
            if mod_val.get("archive_name") == archive_filename:
                return True
    return False

# removes hardlinks and symlinks, in case hardlinks are necessary on some situations
# dashboard.py (l: 1069)
def unlink_mod_files(staging_dir: str, dest_dir: str, mod_files: list[str]):
    dest_path = Path(dest_dir)
    staging_path = Path(staging_dir)

    for mod_file in mod_files:
        link_item = dest_path / mod_file
        source_item = staging_path / mod_file

        if link_item.exists() or link_item.is_symlink():
            # This try prevents nomm from unlinking files that are from another mod
            # If texture_1 is installed by mod_1 and mod_2 did an override, texture_1
            # wont be unlinked on mod_1 uninstall
            try:
                if os.path.samefile(source_item, link_item):
                    link_item.unlink()
            except Exception as e:
                print(f"Failed to unlink {link_item}: {e}")

        current_dir = link_item.parent
        while current_dir != dest_path:
            try:
                current_dir.rmdir()
            except OSError:
                break
            current_dir = current_dir.parent

# Previous function + delete mod from staging folder
def completely_uninstall_mod(staging_dir: str, dest_dir: str, mod_files: list[str]):
    unlink_mod_files(staging_dir, dest_dir, mod_files)
    
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)

# dashboard.py/check_for_comflicts
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
    
    # Extract only the lists where multiple mods claim the same file
    conflicts = []
    for mod_list in path_registry.values():
        if len(mod_list) > 1:
            # We use set() then list() to ensure we don't 
            # list the same mod twice if it has weird internal duplicates
            unique_mods = sorted(list(set(mod_list)))
            if unique_mods not in conflicts:
                conflicts.append(unique_mods)

    return conflicts

# Dashboard.py/find_text_file
def find_text_file(mod_files: list) -> str:
    for file_path in mod_files:
        if ".txt" in file_path:
            return file_path
    return ""

# #dashboard.py (l:883)
def is_utility_installed(local_zip_path: Path, target_dir: Path) -> bool:
    if not local_zip_path.exists():
        return False
    try:
        with zipfile.ZipFile(local_zip_path, 'r') as z:
            return all((target_dir / name).exists() for name in z.namelist() if not name.endswith('/'))
    except Exception: 
        return False

 # dashboard.py/execute_utility_install
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
    
    # TODO:Replace function with extract_archive from archive_manager
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

# 
def toggle_mod_state(mod_name: str, mod_files: list, state: bool, staging_path: str, deployment_targets: list) -> bool:
    staging_metadata_path = os.path.join(staging_path, ".staging.nomm.yaml")
    staging_metadata = load_metadata(staging_metadata_path)
    
    if not deployment_targets or not staging_metadata or mod_name not in staging_metadata.get("mods", {}):
        return False

    dest_dir = deployment_targets[0]["path"]
    mod_info = staging_metadata["mods"][mod_name]
    
    if "deployment_target" in mod_info:
        for target in deployment_targets:
            if target["name"] == mod_info["deployment_target"]:
                dest_dir = target["path"]
                break

    staging_mod_dir = os.path.join(staging_path, mod_name)


    # state is true so the mod has to be installed/deployed
    if state:
        # deploy_mod_files return true if it worked, false if it doesn't
        if check_for_conflicts(staging_metadata_path):
            mod_info["status"] = "enabled"
            mod_info["enabled_timestamp"] = datetime.now().strftime("%c")
            write_yaml(staging_metadata, staging_metadata_path)
            # As we unlink every enabled mod before installing 
            success = deploy_all_ordered_mods(staging_path, dest_dir)
        else:
            success = deploy_mod_files(staging_path, dest_dir, mod_name)
        if success:
        ## #TODO: Remove status data
            print(f"Successfully deployed mod: {mod_name}")
            return True
        return False
    # state is false, deleting the datas and ensure metadata are set to proper value
    else:
        unlink_mod_files(staging_mod_dir, dest_dir, mod_files)
        mod_info["status"] = "disabled"
        # Pop is a safety measure to prevent a crash for a missing key
        mod_info.pop("enabled_timestamp", None)
        write_yaml(staging_metadata, staging_metadata_path)
        if check_for_conflicts(staging_metadata_path):
            success = deploy_all_ordered_mods(staging_path, dest_dir)
        return True

# method to get the metadata path that is used everywhere in the app
def get_metadata_path(base_folder: str, is_staging: bool = True) -> str:
    filename = ".staging.nomm.yaml" if is_staging else ".downloads.nomm.yaml"
    return os.path.join(base_folder, filename)

def load_metadata(path: str) -> dict:
    data = load_yaml(path)
    
    # load metadata also initialize the staging_metadata as a safety measure
    # this is a change reviewed
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
# Dashboard.py (l:216)
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

# Writing the metadata with needed fields
# dashboard.py/create_downloads_page (l:1339)
def finalize_mod_metadata(filename: str, extracted_roots: list, deployment_target_name: str, staging_meta_path: str, downloads_meta_path: str):
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
# New
def read_index(staging_meta_path: str) -> List[str]:
    current_staging_metadata = load_metadata(staging_meta_path)
    return current_staging_metadata["index"]

# Change the mod index from the index list
# New
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