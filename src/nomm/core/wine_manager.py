
import urllib
import os
import re
import json
import shutil
import subprocess
import tarfile
import time
from pathlib import Path
from nomm.core.tools import get_latest_github_release_asset_url, load_yaml, write_yaml
from nomm.core.user_config import DATA_DIR, update_user_config


WINE_INSTALL_DIR = Path(os.path.join(DATA_DIR, "wine"))
WINE_BINARY_PATH = WINE_INSTALL_DIR / "bin" / "wine"
WINE_PREFIX_DIR = Path(os.path.join(DATA_DIR, "wineprefixes"))
WINE_PREFIX_META_PATH = WINE_PREFIX_DIR / ".wineprefix_metadata.yaml"
WINE_REPO_URL = "https://github.com/Kron4ek/Wine-Builds"
COMMON_VERBS = {
    # Visual C++ Runtimes
    "vcrun2015": "Visual C++ 2015-2022 Runtimes",
    "vcrun2013": "Visual C++ 2013 Runtime",
    "vcrun2012": "Visual C++ 2012 Runtime",
    "vcrun2010": "Visual C++ 2010 Runtime",
    "vcrun2008": "Visual C++ 2008 Runtime",
    "vcrun2005": "Visual C++ 2005 Runtime",
    "vcrun6": "Visual C++ 6.0 Runtime",
    "vbrun6": "Visual Basic 6 Runtime",
    "vbrun5": "Visual Basic 5 Runtime",

    # .NET Frameworks & Runtimes
    "dotnet48": ".NET Framework 4.8",
    "dotnet472": ".NET Framework 4.7.2",
    "dotnet462": ".NET Framework 4.6.2",
    "dotnet45": ".NET Framework 4.5",
    "dotnet40": ".NET Framework 4.0",
    "dotnet35": ".NET Framework 3.5 (includes 2.0/3.0)",
    "dotnetdesktop8": ".NET 8 Desktop Runtime",
    "dotnetdesktop7": ".NET 7 Desktop Runtime",
    "dotnetdesktop6": ".NET 6 Desktop Runtime",

    # Fonts & Typography
    "corefonts": "Microsoft Core TrueType Fonts",
    "tahoma": "Microsoft Tahoma Font",
    "lucida": "Lucida TrueType Fonts",
    "consolas": "Microsoft Consolas Monospace Font",
    "allfonts": "All Standard Microsoft Fonts",

    # Windows System, Runtimes & Installers
    "msxml6": "MSXML 6.0 Parser",
    "msxml4": "MSXML 4.0 Parser",
    "msxml3": "MSXML 3.0 Parser",
    "wininet": "Microsoft WinINet API",
    "winhttp": "Microsoft WinHTTP Services",
    "richtx32": "Rich Text Control",
    "comctl32": "Common Controls 5.82/6.0",
    "mdac28": "Microsoft Data Access Components 2.8 (OLE DB/ODBC)",
    "jet40": "Microsoft Jet 4.0 Database Engine",
    "msi2": "Windows Installer 2.0",
}


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


def run_windows_exe(exe_path: str, args: list[str] = None, wineprefix_name: str = "default") -> subprocess.Popen:
    wine_cmd = WINE_BINARY_PATH if os.path.exists(WINE_BINARY_PATH) else shutil.which("wine")
    if not wine_cmd:
        raise FileNotFoundError("Wine executable not found.")

    target_exe = Path(exe_path).resolve()
    if not target_exe.exists():
        raise FileNotFoundError(f"Target executable does not exist: {target_exe}")

    record_prefix_use(wineprefix_name)

    prefix_dir = WINE_PREFIX_DIR / wineprefix_name
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


def generate_winetrick_command(utility_name: str, verbs: list):
    # WINEPREFIX="$HOME/.local/share/wineprefixes/<utility_name>" winetricks -q d3dx9 vcrun2015 dotnet48
    record_prefix_use(utility_name)
    prefix_path = str(WINE_PREFIX_DIR / utility_name)
    verb_string = " ".join(verbs)
    winetrick_command = f"WINEPREFIX={prefix_path} winetricks -q {verb_string}"
    return winetrick_command


def check_wineprefix_setup(utility_name: str):
    prefix_path = str(WINE_PREFIX_DIR / utility_name)
    if os.path.exists(prefix_path):
        return True
    else:
        return False


def record_prefix_use(utility_name: str):
    if WINE_PREFIX_META_PATH.exists():
        prefix_metadata = load_yaml(WINE_PREFIX_META_PATH)
    else:
        prefix_metadata = {}
    prefix_metadata[utility_name] = time.time()
    write_yaml(prefix_metadata, WINE_PREFIX_META_PATH)


def get_unused_wine_prefixes():
    unused_wine_prefixes = []
    if not WINE_PREFIX_META_PATH.exists():
        return []
    for prefix, last_used in load_yaml(WINE_PREFIX_META_PATH).items():
        if last_used < time.time() - 2592000:
            unused_wine_prefixes.append(prefix)
    return unused_wine_prefixes


def clean_wine_prefixes(unused_wine_prefixes: list):
    print(f"Cleaning unused Wine prefixes: {unused_wine_prefixes}")
    prefix_metadata = load_yaml(WINE_PREFIX_META_PATH)
    if not prefix_metadata:
        return
    for unused_prefix in unused_wine_prefixes:
        shutil.rmtree(WINE_PREFIX_DIR / unused_prefix)
        prefix_metadata.pop(unused_prefix)
    write_yaml(prefix_metadata, WINE_PREFIX_META_PATH)
