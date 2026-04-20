# src/core/archive_manager.py

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
import subprocess
import zipfile
import rarfile

# Point rarfile to the bundled binary
rarfile.UNRAR_TOOL = "/app/bin/unrar"

def get_archive_type(file_path: str) -> str:
    """Détecte le type d'archive selon l'extension."""
    lower_path = file_path.lower()
    if lower_path.endswith('.zip'): return 'zip'
    if lower_path.endswith('.rar'): return 'rar'
    if lower_path.endswith('.7z'): return '7z'
    return 'unknown'

def extract_archive(archive_path: str, destination_path: str) -> bool:
    """
    Extrait n'importe quelle archive supportée vers la destination.
    Retourne True si succès, lève une exception sinon.
    """
    arc_type = get_archive_type(archive_path)
    os.makedirs(destination_path, exist_ok=True)

    try:
        if arc_type == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(destination_path)
        elif arc_type == 'rar':
            with rarfile.RarFile(archive_path, 'r') as rf:
                rf.extractall(destination_path)
        elif arc_type == '7z':
            # Run and capture output to avoid spamming the console
            subprocess.run(
                ["7z", "x", archive_path, f"-o{destination_path}", "-y"],
                capture_output=True, 
                text=True,
                check=True # Lève une erreur si 7z échoue
            )
        else:
            raise ValueError(f"Type d'archive non reconnu pour {archive_path}")
        return True
    except Exception as e:
        raise Exception(f"Erreur lors de l'extraction de l'archive {arc_type} : {e}")

def get_all_relative_files(directory_path: str) -> list[str]:
    """Retourne une liste de tous les fichiers d'un dossier, avec chemin relatif."""
    all_files = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, directory_path)
            all_files.append(rel_path.replace('\\', '/'))
    return all_files