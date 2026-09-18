from xmlrpc.client import Boolean
import urllib
from urllib.parse import unquote
import os
import shutil
import subprocess
import webbrowser
import tarfile
from pathlib import Path
from nomm.core.archive_manager import extract_archive
from nomm.core.tools import interpret_filter_string
from nomm.core.user_config import DATA_DIR

NOMM_BACKUP_SUFFIX = ".nomm-backup"
WINE_INSTALL_DIR = Path(os.path.join(DATA_DIR, "wine"))
WINE_BINARY_PATH = WINE_INSTALL_DIR / "bin" / "wine"


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


def ensure_dotnet7_installed(wineprefix_name: str = "default") -> None:
    """Checks if .NET Desktop Runtime 7.0 is installed in the prefix.

    If missing, downloads and installs it silently.
    """
    data_home = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    prefix_dir = Path(data_home) / "wineprefixes" / wineprefix_name

    dotnet_path = (
        prefix_dir
        / "drive_c"
        / "Program Files"
        / "dotnet"
        / "shared"
        / "Microsoft.WindowsDesktop.App"
    )

    if dotnet_path.exists() and any(dotnet_path.iterdir()):
        return

    print("Installing .NET Desktop Runtime 7.0 into Wine prefix...")

    installer_url = "https://builds.dotnet.microsoft.com/dotnet/WindowsDesktop/7.0.20/windowsdesktop-runtime-7.0.20-win-x64.exe"
    cache_dir = Path(data_home) / "installer_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    installer_path = cache_dir / "dotnetdesktop7-x64.exe"

    # Download with a custom User-Agent to bypass Microsoft CDN 400 blocks
    if not installer_path.exists():
        req = urllib.request.Request(
            installer_url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        with (
            urllib.request.urlopen(req) as response,
            open(installer_path, "wb") as out_file,
        ):
            shutil.copyfileobj(response, out_file)

    # Execute installer in Wine silently
    proc = run_windows_exe(
        exe_path=str(installer_path),
        args=["/install", "/quiet", "/norestart"],
        wineprefix_name=wineprefix_name,
    )
    proc.wait()
    print(".NET Desktop Runtime 7.0 installation completed.")


def get_wine() -> Boolean:
    """Downloads and extracts standalone Wine 11.17 if not already present.

    Returns True if the setup was successful.
    """

    print("Downloading standalone Wine...")

    # TODO: we shouldn't take a hard coded version of wine but download the latest release from the Kron4ek releases

    wine_url = "https://github.com/Kron4ek/Wine-Builds/releases/download/11.17/wine-11.17-amd64-wow64.tar.xz"
    archive_path = WINE_INSTALL_DIR.parent / "wine-11.17-amd64-wow64.tar.xz"
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(
        wine_url, headers={"User-Agent": "Mozilla/5.0"}
    )
    with (
        urllib.request.urlopen(req) as response,
        open(archive_path, "wb") as out_file,
    ):
        shutil.copyfileobj(response, out_file)

    print("Extracting Wine...")

    WINE_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:xz") as tar:
        # Strip the top-level directory folder from tarball during extraction
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if len(parts) > 1:
                target_path = WINE_INSTALL_DIR / Path(*parts[1:])
                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        tar.extractfile(member) as src,
                        open(target_path, "wb") as dst,
                    ):
                        shutil.copyfileobj(src, dst)
                    # Retain execution permissions for binaries
                    target_path.chmod(member.mode)

    archive_path.unlink(missing_ok=True)
    print("Wine installation completed.")

    return True


def run_windows_exe(
    exe_path: str, args: list[str] = None, wineprefix_name: str = "default"
) -> subprocess.Popen:
    wine_cmd = WINE_BINARY_PATH if os.path.exists(WINE_BINARY_PATH) else shutil.which("wine")
    if not wine_cmd:
        raise FileNotFoundError("Wine executable not found.")

    target_exe = Path(exe_path).resolve()
    if not target_exe.exists():
        raise FileNotFoundError(f"Target executable does not exist: {target_exe}")

    data_home = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    prefix_dir = Path(data_home) / "wineprefixes" / wineprefix_name
    prefix_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix_dir)
    env["LD_LIBRARY_PATH"] = f"/app/lib:{env.get('LD_LIBRARY_PATH', '')}"

    env["WPF_DISABLE_HW_ACCELERATION"] = "1"  # WPF & Wine Rendering Fixes
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"  # Prevent d3d9/d3d11 crashes in pure Wine fallback mode
    env["WINEDEBUG"] = "-all"  # Suppress Wine logs to prevent buffer deadlocks on stdout/stderr

    cmd = [wine_cmd, str(target_exe)]
    if args:
        cmd.extend(args)

    return subprocess.Popen(
        cmd,
        env=env,
        cwd=str(target_exe.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def launch_utility(util_config: dict, staging_dir: Path, staging_metadata_path: str):

    if util_config["executable_type"] == "browser":
        webbrowser.open(util_config["executable_path"])
        return

    executable_path = staging_dir / util_config["executable_path"]

    if util_config["executable_type"] == "windows":

        ensure_dotnet7_installed()
        run_windows_exe(executable_path)

    else:  # linux executable
        subprocess.run(executable_path, shell=True, cwd=os.path.dirname(executable_path))


def get_utility_status(utility_config: dict, download_path: str, staging_path: str, all_utility_configs: list):
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
                if utility_config.get("installation_lock_group"):
                    for other_utility in all_utility_configs:
                        if utility_config["installation_lock_group"] == other_utility["installation_lock_group"]:
                            if get_utility_status(other_utility, download_path, staging_path, all_utility_configs) == "installed":
                                return "blocked"
                else:
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
