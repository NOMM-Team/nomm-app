# src/core/nexus_api.py

import requests
import threading
from gi.repository import GLib

def check_for_mod_updates_async(staging_metadata: dict, headers: dict, game_id: str, on_complete_callback):
    """
    Vérifie les mises à jour des mods en arrière-plan sans figer l'interface.
    Appelle `on_complete_callback(mods_updated, staging_metadata)` quand c'est fini.
    """
    def worker():
        print("Checking for updates in background...")
        mods_updated = False

        for mod_name, details in staging_metadata.get("mods", {}).items():
            mod_id = details.get("mod_id")
            local_version = str(details.get("version", ""))
            if not mod_id:
                print(f"No mod ID found for {mod_name}, skipping update check")
                continue

            print(f"Checking for update for mod: {mod_name}")
            try:
                # 1. Check for new version
                mod_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}.json"
                resp = requests.get(mod_url, headers=headers, timeout=10)
                
                if resp.status_code == 200:
                    remote_data = resp.json()
                    remote_version = str(remote_data.get("version", ""))

                    if remote_version and remote_version != local_version:
                        details["new_version"] = remote_version
                        mods_updated = True

                        # 2. Fetch the latest changelog
                        changelog_url = f"https://api.nexusmods.com/v1/games/{game_id}/mods/{mod_id}/changelogs.json"
                        changelog_resp = requests.get(changelog_url, headers=headers, timeout=10)
                        
                        if changelog_resp.status_code == 200:
                            logs = changelog_resp.json()
                            new_log = logs.get(remote_version)
                            if new_log:
                                details["changelog"] = "\n".join(new_log) if isinstance(new_log, list) else new_log
                else:
                    print(f"Error getting update info for {mod_name}: {resp.status_code}")

            except Exception as e:
                print(f"Error checking {mod_name}: {e}")

        # Une fois fini, on repasse sur le thread principal de l'UI pour mettre à jour l'affichage
        GLib.idle_add(on_complete_callback, mods_updated, staging_metadata)

    # Lance le travail dans un thread séparé
    threading.Thread(target=worker, daemon=True).start()