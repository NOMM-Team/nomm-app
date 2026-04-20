# src/core/fomod.py

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
import xml.etree.ElementTree as ET
from core.archive_manager import get_all_relative_files

def parse_fomod_xml(xml_data):
    """Parses the FOMOD XML and returns a list of (name, description, source_folder)"""
    try:
        root = ET.fromstring(xml_data)
        options = []
        # Find all plugins (options) within the XML structure
        for plugin in root.findall(".//plugin"):
            name = plugin.get('name')
            desc_node = plugin.find('description')
            desc = desc_node.text.strip() if desc_node is not None and desc_node.text else "No description provided."
            
            folder_node = plugin.find(".//folder")
            source = folder_node.get('source') if folder_node is not None else None
            
            if source:
                options.append((name, desc, source))
        
        module_name = root.findtext('moduleName') or "Unknown Mod"
        return module_name, options
    except Exception as e:
        print(f"Failed to parse FOMOD XML: {e}")
        return None, []
    
def apply_fomod_selection(mod_staging_dir: str, source_folder_name: str) -> list:
    """
    Applique le choix FOMOD : trouve le bon sous-dossier, l'isole, 
    supprime les fichiers inutiles et retourne la nouvelle liste des fichiers.
    """
    normalized_source = source_folder_name.replace('\\', '/').strip('/')
    source_path = None
    
    direct_path = os.path.join(mod_staging_dir, normalized_source)
    if os.path.isdir(direct_path):
        source_path = direct_path
    else:
        for root, _, _ in os.walk(mod_staging_dir):
            rel_root = os.path.relpath(root, mod_staging_dir).replace('\\', '/')
            if rel_root == normalized_source or rel_root.endswith('/' + normalized_source):
                source_path = root
                break

    if not source_path:
        raise FileNotFoundError(f"Could not find folder '{normalized_source}' in extracted mod.")

    temp_safe_dir = f"{mod_staging_dir}_temp_fomod"
    shutil.move(source_path, temp_safe_dir)
    shutil.rmtree(mod_staging_dir)
    os.rename(temp_safe_dir, mod_staging_dir)

    return get_all_relative_files(mod_staging_dir)