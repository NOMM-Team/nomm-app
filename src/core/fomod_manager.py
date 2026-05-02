import os
import shutil
import xml.etree.ElementTree as ET

from core.archive_manager import get_all_relative_files

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
                            'source': source,
                            'destination': dest
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
                    source_for_option = ''
                    if len(folders_data) > 0:
                        source_for_option = folders_data[0].get('source')
                    desc = plugin_desc
                
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

def get_fomod_group_type(parsed_fomod_metadata:dict, step_index: int = 0, group_index: int = 0) -> str:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    group_type = parsed_fomod_metadata[module_name][step_name][group_name]['type']
    
    return group_type

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
            source = source_item.get('source')
            sources.append(source)
        options.append((plugin_name, plugin_desc, sources))
    
    # TODO:Target path should also be sent with source path
    return options

def get_plugin_image_path(parsed_fomod_metadata:dict, plugin_name:str, step_index: int = 0, group_index: int = 0) -> string:
    module_name = list(parsed_fomod_metadata.keys())[0]
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['image_path']
    return ''

def apply_fomod_selection(mod_staging_dir: str, source_folder_name: str) -> list:
    normalized_source = source_folder_name.replace('\\', '/').strip('/')
    source_path = None
    
    
    direct_path = os.path.join(mod_staging_dir, normalized_source)
    # checks if file exists
    if os.path.isdir(direct_path):
        # checks if direct path is the same as source_path, which means all we have to do is copy the files as it is once extracted
        source_path = direct_path
    else:
        #Explore the folder to find normalized source from the root
        for root, _, _ in os.walk(mod_staging_dir):
            # Calculates relative root and replaces \\ for compatibility
            rel_root = os.path.relpath(root, mod_staging_dir).replace('\\', '/')
            #If we find the folder, then we break
            if rel_root == normalized_source or rel_root.endswith('/' + normalized_source):
                source_path = root
                break

    if not source_path:
        raise FileNotFoundError(f"Could not find folder '{normalized_source}' in extracted mod.")

    temp_safe_dir = f"{mod_staging_dir}_temp_fomod"
    # Moves the folder to a temporary direction before installing it
    shutil.move(source_path, temp_safe_dir)
    shutil.rmtree(mod_staging_dir)
    os.rename(temp_safe_dir, mod_staging_dir)

    return get_all_relative_files(mod_staging_dir)