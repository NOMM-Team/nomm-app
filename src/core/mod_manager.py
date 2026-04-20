# src/core/mod_manager.py

import os
import shutil
from pathlib import Path

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