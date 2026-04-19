# src/core/fomod.py

import xml.etree.ElementTree as ET

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