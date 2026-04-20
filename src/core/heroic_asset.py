# Ce fichier fait partie de Yamm (Yet Another Mod Manager).
# Yamm est un fork de Nomm, développé initialement par Allexio.
#
# Copyright (C) 2026 Emetros
# Copyright (C) 2024 Allexio
#
# Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier
# selon les termes de la Licence Publique Générale GNU telle que publiée par la
# Free Software Foundation, soit la version 3 de la Licence, soit (à votre
# discrétion) toute version ultérieure.
#
# Ce programme est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE
# GARANTIE ; sans même la garantie implicite de COMMERCIALISATION ou
# d'ADÉQUATION À UN USAGE PARTICULIER. Voir la Licence Publique Générale GNU
# pour plus de détails.
#
# Vous devriez avoir reçu une copie de la Licence Publique Générale GNU
# avec ce programme. Sinon, voir <https://www.gnu.org/licenses/>.

import os
import json
import requests
from gi.repository import GLib

def download_heroic_assets(appName: str, platform: str):
    # --- AJOUT: Forcer la conversion en string pour éviter les erreurs de comparaison
    if isinstance(appName, list):
        appName = str(appName[0])
    else:
        appName = str(appName)
    # ---
    
    # 1. Define Paths
    json_path = os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic/store/download-manager.json") # flatpak
    if not os.path.exists(json_path):
        json_path = os.path.expanduser("~/.config/heroic/store/download-manager.json") # not flatpak

    if isinstance(appName, list):
        appName = appName[0]
    
    cache_base = os.path.join(GLib.get_user_data_dir(), f"yamm/image-cache/{platform}/{appName}")
    
    # 2. CACHE CHECK: If the directory exists, check for existing files
    if os.path.exists(cache_base):
        existing_files = {}
        for entry in os.listdir(cache_base):
            if entry.startswith("art_square"):
                existing_files["art_square"] = os.path.join(cache_base, entry)
            elif entry.startswith("art_hero"):
                existing_files["art_hero"] = os.path.join(cache_base, entry)
        
        if "art_square" in existing_files:
            print(f"Using cached assets for {appName}")
            return existing_files

    # 3. If not cached, proceed to JSON parsing
    if not os.path.exists(json_path):
        print(f"Heroic config not found at {json_path}")
        return None

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        finished_apps = data.get("finished", [])
        target_info = None

        for entry in finished_apps:
            params = entry.get("params", {})
            game_info = params.get("gameInfo", {})
            
            if params.get("appName") == appName or game_info.get("title") == appName:
                target_info = game_info
                break
        
        if not target_info:
            return None

        # 4. Extraction Logic
        urls = {
            "art_square": target_info.get("art_square"),
            "art_hero": target_info.get("art_background") or target_info.get("art_cover")
        }

        os.makedirs(cache_base, exist_ok=True)
        downloaded_paths = {}

        for key, url in urls.items():
            if not url:
                continue
                
            ext = os.path.splitext(url)[1] if "." in url.split("/")[-1] else ".jpg"
            if "?" in ext: ext = ext.split("?")[0]
            
            local_path = os.path.join(cache_base, f"{key}{ext}")

            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(r.content)
                    downloaded_paths[key] = local_path
                    print(f"Downloaded: {local_path}")
            except Exception as e:
                print(f"Error downloading {key}: {e}")

        return downloaded_paths

    except Exception as e:
        print(f"Failed to process Heroic JSON: {e}")
        return None