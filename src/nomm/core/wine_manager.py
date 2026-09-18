
import urllib
import os
import re
import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from nomm.core.tools import get_latest_github_release_asset_url
from nomm.core.user_config import DATA_DIR, update_user_config

WINE_INSTALL_DIR = Path(os.path.join(DATA_DIR, "wine"))
WINE_BINARY_PATH = WINE_INSTALL_DIR / "bin" / "wine"
WINE_REPO_URL = "https://github.com/Kron4ek/Wine-Builds"


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


def get_wine() -> bool:
    """Downloads and extracts standalone Wine 11.17 if not already present.

    Returns True if the setup was successful.
    """

    print("Downloading standalone Wine...")

    wine_url = get_latest_github_release_asset_url(WINE_REPO_URL, r"wine-\d+\.\d+(?:-\d+)?-amd64-wow64\.tar\.xz")
    archive_path = WINE_INSTALL_DIR.parent / "wine-amd64-wow64.tar.xz"
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
    match = re.search(r"/releases/download/([^/]+)/", wine_url)
    wine_version = match.group(1) if match else None
    update_user_config("wine_version", wine_version)

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


def remove_wine():
    shutil.rmtree(WINE_INSTALL_DIR)
    update_user_config("wine_version", None)


def get_latest_wine_version(headers) -> str | None:
    # Convert standard repo URL to GitHub API releases endpoint
    # e.g., "https://github.com/Kron4ek/Wine-Builds" -> "Kron4ek/Wine-Builds"
    repo_path = WINE_REPO_URL.rstrip("/").removeprefix("https://github.com/")
    api_url = f"https://api.github.com/repos/{repo_path}/releases/latest"

    req = urllib.request.Request(api_url, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                tag_name = data.get("tag_name", "")
                return tag_name.lstrip("v")
    except Exception as e:
        print(f"[!] Error fetching latest Wine version: {e}")
        return None
