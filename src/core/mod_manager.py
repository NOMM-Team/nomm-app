# src/core/mod_manager.py

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
import shutil
import zipfile
import subprocess
from pathlib import Path
from datetime import datetime

from core.config import load_metadata, save_metadata

def deploy_mod_files(staging_dir: str, dest_dir: str, mod_files: list[str]) -> bool:
    """
    Déploie les fichiers du mod vers le dossier du jeu.
    Tente d'abord de créer un Hardlink (Proton-friendly), 
    avec un repli sur un Symlink classique si les disques sont différents.
    """
    dest_path = Path(dest_dir)
    staging_path = Path(staging_dir)
    success = True

    for mod_file in mod_files:
        source_item = staging_path / mod_file
        link_item = dest_path / mod_file

        # 1. Ignorer les dossiers
        if source_item.is_dir():
            continue

        # 2. Créer les dossiers parents dans le dossier du jeu si besoin
        link_item.parent.mkdir(parents=True, exist_ok=True)

        # 3. Créer le lien
        if not link_item.exists():
            try:
                # TENTATIVE 1 : Hardlink (Fait croire au jeu que c'est un vrai fichier)
                os.link(source_item, link_item)
            except OSError as e:
                # Erreur classique si les dossiers sont sur des disques/partitions différents
                print(f"Hardlink impossible pour {link_item} (Disques différents ?). Repli sur Symlink. Erreur: {e}")
                try:
                    # TENTATIVE 2 : Symlink classique
                    os.symlink(source_item, link_item)
                except Exception as sym_e:
                    print(f"Erreur lors de la création du Symlink {link_item}: {sym_e}")
                    success = False
        else:
            # Sécurité : on vérifie si le fichier qui existe est bien LE NOTRE
            try:
                if not os.path.samefile(source_item, link_item):
                    print(f"Conflit: {link_item} existe déjà et n'appartient pas à ce mod. Ignoré.")
            except OSError:
                print(f"Conflit d'accès sur {link_item}.")
                
    return success

def remove_mod_files(staging_dir: str, dest_dir: str, mod_files: list[str]):
    """
    Supprime les liens (Hardlinks ou Symlinks) d'un mod ET nettoie les dossiers laissés vides.
    """
    dest_path = Path(dest_dir)
    staging_path = Path(staging_dir)

    for mod_file in mod_files:
        link_item = dest_path / mod_file
        source_item = staging_path / mod_file

        if link_item.exists() or link_item.is_symlink():
            try:
                # SÉCURITÉ MAXIMALE : On supprime UNIQUEMENT si le fichier cible 
                # pointe vers les mêmes données que notre fichier staging
                if os.path.samefile(source_item, link_item):
                    link_item.unlink()
            except Exception as e:
                print(f"Erreur lors de la suppression de {link_item}: {e}")

        # Nettoyer les dossiers parents laissés vides
        current_dir = link_item.parent
        while current_dir != dest_path:
            try:
                current_dir.rmdir()
            except OSError:
                break
            current_dir = current_dir.parent

def completely_uninstall_mod(staging_dir: str, dest_dir: str, mod_files: list[str]):
    """
    Supprime les liens symboliques ET efface définitivement le mod du dossier staging.
    """
    remove_mod_files(staging_dir, dest_dir, mod_files)
    
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)
        
def check_for_conflicts(staging_metadata_path: str) -> list:
    """Vérifie le dossier staging pour trouver des conflits entre fichiers de mods."""
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

def find_text_file(mod_files: list) -> str:
    """Cherche un fichier texte (ex: readme) dans une liste de fichiers de mod."""
    for file_path in mod_files:
        if ".txt" in file_path:
            return file_path
    return None

def is_utility_installed(local_zip_path: Path, target_dir: Path) -> bool:
    """Vérifie si un utilitaire/framework est déjà déployé en comparant avec le contenu de son archive."""
    if not local_zip_path.exists():
        return False
    try:
        with zipfile.ZipFile(local_zip_path, 'r') as z:
            return all((target_dir / name).exists() for name in z.namelist() if not name.endswith('/'))
    except Exception: 
        return False

def deploy_essential_utility(util_config: dict, downloads_path: str, game_path: str):
    """Déploie un utilitaire (extraction ciblée via liste blanche/noire + exécution de commande)."""
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
        
def toggle_mod_state(mod_name: str, mod_files: list, state: bool, staging_path: str, deployment_targets: list, metadata_path: str) -> bool:
    """
    Active ou désactive un mod, met à jour les liens (symlinks/hardlinks) et les métadonnées.
    Retourne True si l'opération a réussi, False sinon.
    """
    staging_metadata = load_metadata(metadata_path)
    
    if not deployment_targets or not staging_metadata or mod_name not in staging_metadata.get("mods", {}):
        return False

    # 1. Trouver le répertoire de destination correct
    dest_dir = deployment_targets[0]["path"]
    mod_meta = staging_metadata["mods"][mod_name]
    
    if "deployment_target" in mod_meta:
        for target in deployment_targets:
            if target["name"] == mod_meta["deployment_target"]:
                dest_dir = target["path"]
                break

    staging_mod_dir = os.path.join(staging_path, mod_name)

    # 2. Appliquer l'état (Activation ou Désactivation)
    if state:
        # Tenter de déployer
        success = deploy_mod_files(staging_mod_dir, dest_dir, mod_files)
        if success:
            mod_meta["status"] = "enabled"
            mod_meta["enabled_timestamp"] = datetime.now().strftime("%c")
            save_metadata(staging_metadata, metadata_path)
            return True
        return False
    else:
        # Retirer les fichiers
        remove_mod_files(staging_mod_dir, dest_dir, mod_files)
        mod_meta["status"] = "disabled"
        mod_meta.pop("enabled_timestamp", None)
        save_metadata(staging_metadata, metadata_path)
        return True