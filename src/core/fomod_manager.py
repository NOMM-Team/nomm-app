import os
import shutil
import xml.etree.ElementTree as ET

from core.archive_manager import get_all_relative_files

# Parsing the fomod from the XML
# fomod_handler.py/parse_fomod_xml
def parse_fomod_xml(xml_data):
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

# To check, really different
def apply_fomod_selection(mod_staging_dir: str, source_folder_name: str) -> list:
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