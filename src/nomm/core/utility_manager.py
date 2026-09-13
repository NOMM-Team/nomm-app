import os
import shutil
import threading
import subprocess
from pathlib import Path
from nomm.core.archive_manager import extract_archive

meta_lock = threading.Lock()


def deploy_essential_utility(util_config: dict, downloads_path: str, staging_path: str, game_path: str, file_name: str):
    archive_path = os.path.join(downloads_path, "utilities", file_name)
    staging_path = Path(staging_path) / "utilities" / util_config["name"]

    game_root = Path(game_path)

    # Archive extraction to staging
    print("Extracting utility contents")
    extract_archive(archive_path, staging_path)

    def interpret_filter_string(input_string):
        output_list = []
        if not input_string:
            return None
        elif "," in input_string:
            output_list = input_string.split(",")
        elif ";" in input_string:
            output_list = input_string.split(";")
        else:
            output_list = [input_string]
        return output_list

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
