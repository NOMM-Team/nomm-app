import os
import shutil
import xml.etree.ElementTree as ET

# Parsing the fomod from the XML
def parse_fomod_xml(xml_data) -> dict :
    fomod_data = {}
    try:
        module_name = xml_data.findtext('moduleName')
        steps = xml_data.findall('.//installStep')
        fomod_data[module_name] = {}
        for step in steps:
            step_name = step.get('name')
            fomod_data[module_name][step_name] = {}
            for group in step.findall('.//group'):
                group_name = group.get('name')
                group_type = group.get('type')
                fomod_data[module_name][step_name][group_name] = {
                    'type' : group_type,
                    'plugins' : []
                }
                for plugin in group.findall('.//plugin'):
                    plugin_name = plugin.get('name')
                    plugin_desc = plugin.findtext('description', default='No description provided')
                    if plugin.find('image') != None:
                        image_tag = plugin.find('image')
                        plugin_image_path = image_tag.get('path')
                    else:
                        plugin_image_path = ''
                    items = plugin.findall('.//folder') + plugin.findall('.//file')
                    folders_data = []
                    plugin_folder = {}
                    for index,item in enumerate(items):
                        source = item.get('source')
                        dest = item.get('destination')
                        plugin_folder = {
                            'source': source.replace('\\', '/'),
                            'destination': dest.replace('\\', '/')
                        }
                        folders_data.append(plugin_folder)
                    type_tag = plugin.find('.//type')
                    plugin_type = type_tag.get('name') if type_tag is not None else 'Optional'
                    fomod_data[module_name][step_name][group_name]['plugins'].append({
                        'name': plugin_name,
                        'desc': plugin_desc.strip(),
                        'image_path': plugin_image_path,
                        'folders': folders_data,
                        'type': plugin_type
                    })
        return fomod_data
    except Exception as e:
        print(f"Failed to parse FOMOD XML: {e}")
        return {}
    
def get_fomod_step_count(parsed_fomod_metadata:dict) -> int:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_count = len(parsed_fomod_metadata[module_name])
    
    return step_count
    
def get_fomod_group_count(parsed_fomod_metadata:dict, step_index: int = 0) -> int:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_count = len(parsed_fomod_metadata[module_name][step_name])
    
    return group_count

def get_fomod_group_info(parsed_fomod_metadata:dict, step_index: int = 0, group_index: int = 0) -> dict[str]:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    group_type = parsed_fomod_metadata[module_name][step_name][group_name]['type']
    data = {
        'type' : group_type,
        'name' : group_name
    }
    return data

def get_fomod_module_name(parsed_fomod_metadata:dict) -> str:
    return list(parsed_fomod_metadata.keys())[0]

def get_fomod_group_options(parsed_fomod_metadata:dict, step_index: int = 0, group_index: int = 0) -> list:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    options = []
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        # Plugin name
        plugin_name = plugin['name']

        # Plugin description
        plugin_desc = plugin['desc']

        # Source path
        sources = []
        source_items = plugin['folders']
        for source_item in source_items:
            source = source_item
            sources.append(source)
        options.append((plugin_name, plugin_desc, sources))
    
    return options

def get_plugin_image_path(parsed_fomod_metadata:dict, plugin_name:str, step_index: int = 0, group_index: int = 0) -> str:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['image_path']
    return ''

def have_plugins_images(parsed_fomod_metadata:dict, step_index: int = 0, group_index: int = 0) -> bool:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['image_path']:
            return True
    return False

def get_plugin_type(parsed_fomod_metadata:dict, plugin_name:str, step_index: int = 0, group_index: int = 0) -> str:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['type']
    return ''

def apply_fomod_selection(mod_staging_dir: str, source_folder_name: str, dest_path: str) -> list:

    normalized_source = source_folder_name.replace('\\', '/').strip('/')
    source_path = None
    
    direct_path = os.path.join(mod_staging_dir, normalized_source)
    if os.path.isdir(direct_path):
        # checks if direct path is the same as source_path, which means all we have to do is copy the files as it is once extracted
        source_path = direct_path
    else:
        # Explore the folder to find normalized source from the root
        for root, _, files in os.walk(mod_staging_dir):
            # Calculates relative root and replaces \\ for compatibility
            rel_root = os.path.relpath(root, mod_staging_dir).replace('\\', '/')
            #If we find the folder, then we break
            if rel_root == normalized_source or rel_root.endswith('/' + normalized_source):
                source_path = root
                break
            # To comment
            for f in files:
                rel_file = os.path.relpath(os.path.join(root, f), mod_staging_dir).replace('\\', '/')
                if rel_file == normalized_source or rel_file.endswith('/' + normalized_source):
                    source_path = os.path.join(root, f)
                    break
            if source_path:
                break
            
    if not source_path:
        raise FileNotFoundError(f"Could not find folder or file '{normalized_source}' in extracted mod.")

    copied_files = []
    # As we now handle multiple dest_path we have to build the dest path too
    if os.path.isdir(source_path):
        os.makedirs(dest_path, exist_ok=True)
        shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
        
        for root, _, files in os.walk(source_path):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), source_path)
                copied_files.append(rel_path.replace('\\', '/'))
    else:
        os.makedirs(dest_path if os.path.isdir(dest_path) else os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(source_path, dest_path)
        copied_files.append(os.path.basename(source_path))

    return copied_files

def get_required_files(parsed_fomod_metadata: dict) -> list:
    required_items = []
    module_name = list(parsed_fomod_metadata.keys())[0]
    # Walk through the whole metadatas to retrieve every required files
    for step in parsed_fomod_metadata[module_name].values():
        for group in step.values():
            for plugin in group['plugins']:
                if plugin['type'] == 'Required':
                    required_items.extend(plugin['folders'])
    return required_items