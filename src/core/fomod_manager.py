import os
import pprint
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET

# Parsing the fomod from the XML
def parse_fomod_xml(xml_data) -> dict :
    fomod_data = {}
    try:
        
        # Module dependency tree
        dependencies_data = {}
        module_dependencies = xml_data.find('moduleDependencies')
        if module_dependencies is not None:
            dependencies_data = dependencies_loops(module_dependencies)
        else:
            dependencies_data = {}
        
        # Module tree, where options are actually stored
        module_data = {}
        steps = xml_data.findall('.//installStep')
        step_list = []
        for step in steps:
            step_name = step.get('name')
            group_list = []
            for group in step.findall('.//group'):
                group_name = group.get('name')
                group_type = group.get('type')
                group_data = {
                    'name' : group_name,
                    'type' : group_type,
                    'plugins' : []
                }
                group_list.append(group_data)
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
                        dest = dest.replace('\\', '/')
                        plugin_folder = {
                            'source': source.replace('\\', '/'),
                            'destination': dest.lstrip('\\/')
                        }
                        folders_data.append(plugin_folder)
                    condition_flags = []
                    condition_flags_tag = plugin.find('conditionFlags')
                    if condition_flags_tag is not None:
                        for flag in condition_flags_tag.findall('flag'):
                            condition_flags.append({
                                'name': flag.get('name'),
                                'value': flag.text
                            })
                    type_descriptor = {'default_type': 'Optional', 'conditional_types': []}
                    type_descriptor_tag = plugin.find('typeDescriptor')
                    if type_descriptor_tag is not None:
                        dependency_type_tag = type_descriptor_tag.find('dependencyType')
                        if dependency_type_tag is not None:
                            default_type_tag = dependency_type_tag.find('defaultType')
                            type_descriptor['default_type'] = default_type_tag.get('name') if default_type_tag is not None else 'Optional'
                            for cond_pattern in dependency_type_tag.findall('.//pattern'):
                                deps = cond_pattern.find('dependencies')
                                file_deps = []
                                flag_deps = []
                                if deps is not None:
                                    operator = deps.get('operator') or 'And'
                                    for file_dep in deps.findall('fileDependency'):
                                        file_deps.append({
                                            'req_file': file_dep.get('file'),
                                            'state': file_dep.get('state')
                                        })
                                    for flag_dep in deps.findall('flagDependency'):
                                        flag_deps.append({
                                            'flag': flag_dep.get('flag'),
                                            'value': flag_dep.get('value')
                                        })
                                cond_type_tag = cond_pattern.find('type')
                                type_descriptor['conditional_types'].append({
                                    'type': cond_type_tag.get('name') if cond_type_tag is not None else 'Optional',
                                    'dependencies': {
                                        'operator': operator,
                                        'file_dependencies': file_deps,
                                        'flag_dependencies': flag_deps
                                    }
                                })
                        else:
                            simple_type = type_descriptor_tag.find('type')
                            type_descriptor['default_type'] = simple_type.get('name') if simple_type is not None else 'Optional'
                    group_data['plugins'].append({
                        'name': plugin_name,
                        'desc': plugin_desc.strip(),
                        'image_path': plugin_image_path,
                        'folders': folders_data,
                        'condition_flags': condition_flags,
                        'type_descriptor': type_descriptor
                    })
            step_data = {
                'step_name' : step_name,
                'group' : group_list
            }
            step_list.append(step_data)
        module_data = step_list
        
        # Conditional file installs
        conditional_installs = xml_data.find('conditionalFileInstalls')
        flags_data = []
        if conditional_installs is not None:
            for pattern in conditional_installs.findall('.//pattern'):
                deps = pattern.find('dependencies')
                flags = []
                for flag_dep in deps.findall('flagDependency'):
                    flags.append({
                        'flag': flag_dep.get('flag'),
                        'value': flag_dep.get('value')
                    })
                files_tag = pattern.find('files')
                items = files_tag.findall('folder') + files_tag.findall('file')
                files = []
                for item in items:
                    source = item.get('source', '').replace('\\', '/')
                    dest = item.get('destination', '').replace('\\', '/')
                    files.append({
                        'source': source,
                        'destination': dest.lstrip('\\/')
                    })
                flags_data.append({
                    'dependencies': {
                        'operator': deps.get('operator') or 'And',
                        'flags': flags
                    },
                    'files': files
                })
        
        # dump_fomod_data(dependencies_data)
        # dump_fomod_data(module_data)
        # dump_fomod_data(flags_data)
        return dependencies_data, module_data, flags_data
    except Exception as e:
        print(f"Failed to parse FOMOD XML: {e}")
        return {}
    
def get_fomod_step_count(parsed_fomod_metadata: dict) -> int:
    return len(parsed_fomod_metadata)

def get_fomod_group_count(parsed_fomod_metadata: dict, step_index: int = 0) -> int:
    return len(parsed_fomod_metadata[step_index]['group'])

def get_fomod_group_info(parsed_fomod_metadata: dict, step_index: int = 0, group_index: int = 0) -> dict:
    group = parsed_fomod_metadata[step_index]['group'][group_index]
    return {
        'type': group['type'],
        'name': group['name']
    }

def get_fomod_module_name(parsed_fomod_metadata: dict) -> str:
    return 'lol'

def get_fomod_group_options(parsed_fomod_metadata: dict, step_index: int = 0, group_index: int = 0) -> list:
    options = []
    plugins = parsed_fomod_metadata[step_index]['group'][group_index]['plugins']
    for plugin in plugins:
        sources = list(plugin['folders'])
        condition_flags = plugin['condition_flags']
        options.append((plugin['name'], plugin['desc'], sources, condition_flags))
    return options

def get_plugin_image_path(parsed_fomod_metadata: dict, plugin_name: str, step_index: int = 0, group_index: int = 0) -> str:
    plugins = parsed_fomod_metadata[step_index]['group'][group_index]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['image_path']
    return ''

def have_plugins_images(parsed_fomod_metadata: dict, step_index: int = 0, group_index: int = 0) -> bool:
    plugins = parsed_fomod_metadata[step_index]['group'][group_index]['plugins']
    for plugin in plugins:
        if plugin['image_path']:
            return True
    return False

def get_plugin_type(parsed_fomod_metadata: dict, plugin_name: str, step_index: int = 0, group_index: int = 0) -> str:
    plugins = parsed_fomod_metadata[step_index]['group'][group_index]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['type_descriptor']['default_type']
    return ''

def get_plugin_flags(parsed_fomod_metadata: dict, plugin_name: str, step_index: int = 0, group_index: int = 0) -> list:
    plugins = parsed_fomod_metadata[step_index]['group'][group_index]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['condition_flags']
    return []

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

def dump_fomod_data(parsed_fomod_metadata: dict):
    pprint.pprint(parsed_fomod_metadata, indent=2, width=120)

def generate_source_from_flags(flags_metadata: dict, flags: list) -> dict:
    result = []
    for pattern in flags_metadata:
        operator = pattern['dependencies']['operator']
        pattern_flags = pattern['dependencies']['flags']
        if operator == 'And':
            match = all(flags.get(f['flag']) == f['value'] for f in pattern_flags)
        else:
            match = any(flags.get(f['flag']) == f['value'] for f in pattern_flags)
        if match:
            result.extend(pattern['files'])
    return result

def dependencies_loops(current_dependency_metadata) -> list:
    required_files_root = []
    for file in current_dependency_metadata.findall('fileDependency'):
        req_file = file.get('file')
        req_file = req_file.replace('\\', '/')
        state = file.get('state')
        file_data = {
        'file' : req_file.lstrip('\\/'),
        'state' : state
        }
        required_files_root.append(file_data)
    current_level_data = {
        'operator' : current_dependency_metadata.get('operator') or 'And',
        'req_files' : required_files_root
    }
    dependencies_data = {
        'file_dependencies' : current_level_data,
        'nested_dependencies' : None
    }
    
    nested = []
    for nested_dep in current_dependency_metadata.findall('dependencies'):
        nested.append(dependencies_loops(nested_dep))
    dependencies_data['nested_dependencies'] = nested if nested else None
    return dependencies_data


def check_for_dependencies(dependencies_data:dict, dest_dir: str) -> bool:
    if not dependencies_data:
        return True
    dep_item = dependencies_data['file_dependencies']['req_files']
    operator = dependencies_data['file_dependencies']['operator']
    search = False
    if operator == 'And':
        search = all((Path(dest_dir)/f['file']).exists() and (f['state'] == 'Active' or f['state'] == 'Inactive') for f in dep_item)
    if operator == 'Or':
        search = any((Path(dest_dir)/f['file']).exists() and (f['state'] == 'Active' or f['state'] == 'Inactive') for f in dep_item)
    if dependencies_data['nested_dependencies']:
        for nested in dependencies_data['nested_dependencies']:
            if not check_for_dependencies(nested, dest_dir):
                return False
    return search
    

def check_for_plugin_dependencies(parsed_fomod_metadata: dict, dest_dir: str, step_index: int = 0, group_index: int = 0, plugin_index: int = 0, selected_flags = None) -> str:
    plugin = parsed_fomod_metadata[step_index]['group'][group_index]['plugins'][plugin_index]
    
    # Check for file dependency
    for cond_type in plugin['type_descriptor']['conditional_types']:
        dependencies = cond_type['dependencies']
        operator = dependencies.get('operator')
        search = False
        if operator == 'And':
            search_file = all(
                (Path(dest_dir)/f['req_file']).exists() 
                and (f['state'] == 'Active' or f['state'] == 'Inactive')
                for f in dependencies['file_dependencies']
            )
            search_flag = all(
                f['flag'] in selected_flags
                and selected_flags[f['flag']] == f['value']
                for f in dependencies['flag_dependencies']
            ) if selected_flags else not dependencies['flag_dependencies']
            search = search_file and search_flag
        elif operator == 'Or':
            search_file = any(
                (Path(dest_dir)/f['req_file']).exists() 
                and (f['state'] == 'Active' or f['state'] == 'Inactive') 
                for f in dependencies['file_dependencies']
            )
            search_flag = any(
                f['flag'] in selected_flags
                and selected_flags[f['flag']] == f['value']
                for f in dependencies['flag_dependencies']
            ) if selected_flags else False
            search = search_file or search_flag
        if search:
            return cond_type['type']
    
    # Check for flag dependency
    return plugin['type_descriptor']['default_type']
    
    
    