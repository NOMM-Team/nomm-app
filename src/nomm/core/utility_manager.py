from urllib.parse import unquote
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from nomm.core.archive_manager import extract_archive
from nomm.core.tools import interpret_filter_string
from nomm.core.wine_manager import run_windows_exe, ensure_dotnet7_installed

NOMM_BACKUP_SUFFIX = ".nomm-backup"


def deploy_essential_utility(util_config: dict, downloads_path: str, staging_path: str, game_path: str, file_name: str):
    archive_path = os.path.join(downloads_path, "utilities", file_name)
    staging_path = Path(staging_path) / "utilities" / util_config["name"]

    game_root = Path(game_path)

    # Archive extraction to staging
    print("Extracting utility contents")
    extract_archive(archive_path, staging_path)

    # Whitelist and blacklist management
    whitelist = interpret_filter_string(util_config.get("whitelist", ""))
    blacklist = interpret_filter_string(util_config.get("blacklist", ""))

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
                    pass  # Folder is not empty, so skip it

    # Actual deployment to game files if needed
    if util_config.get("deploy_to_game_files", True):
        install_subpath = util_config["deployment_path"].strip("/")  # remove any starting slashes
        target_dir = game_root / install_subpath
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"Deploying utility files to game directory: {target_dir}")
        for root, dirs, files in os.walk(str(staging_path)):
            for file_name in files:
                source_file = os.path.join(root, file_name)

                relative_path = os.path.relpath(source_file, str(staging_path))
                destination_file = target_dir / relative_path
                destination_file.parent.mkdir(parents=True, exist_ok=True)
                if os.path.exists(destination_file):
                    backup_file = f"{destination_file}{NOMM_BACKUP_SUFFIX}"
                    os.rename(destination_file, backup_file)
                    print(f"[i] Backed up existing file: {destination_file}")
                try:
                    shutil.copy2(source_file, destination_file)
                    print(f"[+] Deployed: {relative_path}")
                except Exception as e:
                    print(f"[!] Failed to copy {relative_path} to game directory: {e}")

    # Some utilities require a command to be launched as a one-shot to enable the utility
    command = util_config.get("enable_command")
    if command:
        print(f"Running utility enable command: {command}")
        subprocess.run(command, shell=True, cwd=game_root)


def launch_utility(util_config: dict, staging_dir: Path, staging_metadata_path: str, headers: dict):

    if util_config["executable_type"] == "browser":
        webbrowser.open(util_config["executable_path"])
        return

    executable_path = staging_dir / util_config["executable_path"]

    if util_config["executable_type"] == "windows":

        ensure_dotnet7_installed(headers)
        run_windows_exe(executable_path)

    else:  # linux executable
        subprocess.run(executable_path, shell=True, cwd=os.path.dirname(executable_path))


def get_utility_status(utility_config: dict, download_path: str, staging_path: str, all_utility_configs: list) -> str:
    file_name = get_downloaded_utility_file_name(utility_config, download_path)
    if utility_config["source_type"] == "flatpak":
        package_name = utility_config["source_url"].replace("appstream://", "")
        flatpak_path = os.path.expanduser(f"~/.var/{package_name}")
        if os.path.exists(flatpak_path):
            return "installed"
        else:
            return "to_download"
    if utility_config["source_type"] in ["nexus", "github", "direct"]:
        if os.path.exists(download_path) and file_name in os.listdir(download_path):
            if os.path.exists(staging_path):
                return "installed"
            else:
                lock_group = utility_config.get("installation_lock_group")
                if lock_group:
                    for other_utility in all_utility_configs:
                        if other_utility is utility_config:
                            continue
                        if other_utility.get("installation_lock_group") == lock_group:
                            other_staging_path = staging_path.parent / other_utility["name"]
                            if os.path.exists(other_staging_path):
                                return "blocked"
                return "to_install"
        else:
            return "to_download"


def get_downloaded_utility_file_name(utility_config: dict, download_path: str):
    if utility_config["source_type"] in ["direct", "github"]:
        decoded_url = unquote(utility_config["source_url"])
        if "/" in decoded_url:
            return decoded_url.split("/")[-1]
        else:
            return decoded_url
    elif utility_config["source_type"] == "flatpak":
        return None
    elif utility_config["source_type"] == "nexus":
        file_name_start = utility_config["nexus_file_name_start"]
        if not os.path.exists(download_path):
            return None
        for file_name in os.listdir(download_path):
            if file_name_start in file_name:
                return file_name
    else:
        print(f"Error: unrecognised source type for utility: {utility_config["name"]}")

    return None


def remove_utility(util_config: dict, downloads_path: Path, staging_path: Path, game_path: str, archive_name: str):
    """Deletes staged utility files and removes any utility files that were copied to the game's directory"""
    game_root = Path(game_path)
    archive_path = downloads_path / archive_name

    if util_config.get("deploy_to_game_files", True) and staging_path.exists():
        install_subpath = util_config["deployment_path"].strip("/")
        target_dir = game_root / install_subpath

        print(f"Removing utility files from game directory: {target_dir}")

        for root, dirs, files in os.walk(str(staging_path)):
            for file_name in files:
                source_file = os.path.join(root, file_name)
                relative_path = os.path.relpath(source_file, str(staging_path))
                destination_file = target_dir / relative_path

                if destination_file.exists():
                    try:
                        destination_file.unlink()
                        print(f"[-] Removed deployed file: {relative_path}")
                    except Exception as e:
                        print(f"[!] Failed to remove {destination_file}: {e}")

                backup_file = Path(f"{destination_file}{NOMM_BACKUP_SUFFIX}")
                if backup_file.exists():
                    try:
                        if destination_file.exists():
                            destination_file.unlink()
                        backup_file.rename(destination_file)
                        print(f"[i] Restored backup: {destination_file}")
                    except Exception as e:
                        print(f"[!] Failed to restore backup {backup_file}: {e}")

        for root, dirs, files in os.walk(str(target_dir), topdown=False):
            for dir_name in dirs:
                dir_full_path = Path(root) / dir_name
                try:
                    dir_full_path.rmdir()
                except OSError:
                    pass  # Directory is not empty

    if staging_path.exists():
        try:
            shutil.rmtree(staging_path)
            print(f"[-] Cleaned up staging directory: {staging_path}")
        except Exception as e:
            print(f"[!] Failed to delete staging path {staging_path}: {e}")

    if archive_path.exists():
        archive_path.unlink()
