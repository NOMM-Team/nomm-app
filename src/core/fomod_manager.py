import os
import shutil
import xml.etree.ElementTree as ET

# Parsing the fomod from the XML
def parse_fomod_xml(xml_data) -> dict :
    fomod_data = {}
    try:
        
        # Module dependency tree
        module_dependencies = xml_data.find('moduleDependencies')
        if module_dependencies is not None:
            module_dependencies_type = module_dependencies.get('operator')
            root_dependency_metadata = module_dependencies.findall('fileDependency')
            required_files_root = []
            for file in root_dependency_metadata:
                req_file = file.get('file')
                req_file = req_file.replace('\\', '/')
                state = file.get('state')
                file_data = {
                'file' : req_file.lstrip('\\/'),
                'state' : state
                }
                required_files_root.append(file_data)
            global_root_data = {
                'operator' : module_dependencies_type,
                'req_files' : required_files_root
            }
            fomod_data['module_dependency'] = {
                'root_dependencies' : global_root_data,
                'nested_dependencies' : None
            }
            nested_dependencies = module_dependencies.findall('dependencies')
            global_nested_data = []
            for dependency in nested_dependencies:
                nested_dependency_type = dependency.get('operator')
                nested_dependencies_metadata = []
                for file in dependency.findall('fileDependency'):
                    req_file = file.get('file')
                    req_file = req_file.replace('\\', '/')
                    state = file.get('state')
                    file_data = {
                    'file' : req_file.lstrip('\\/'),
                    'state' : state
                    }
                    nested_dependencies_metadata.append(file_data)
                local_nested_data = {
                    'operator' : nested_dependency_type,
                    'req_files' : nested_dependencies_metadata
                }
                global_nested_data.append(local_nested_data)
            fomod_data['module_dependency']['nested_dependencies'] = global_nested_data
        else:
            fomod_data['module_dependency'] = None
        
        
        # Module tree, where options are actually stored
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
                                operator = deps.get('operator') or 'And'
                                if deps is not None:
                                    for file_dep in deps.findall('fileDependency'):
                                        file_deps.append({
                                            'file': file_dep.get('file'),
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
                                        'file_deps': file_deps,
                                        'flag_deps': flag_deps
                                    }
                                })
                        else:
                            simple_type = type_descriptor_tag.find('type')
                            type_descriptor['default_type'] = simple_type.get('name') if simple_type is not None else 'Optional'
                    fomod_data[module_name][step_name][group_name]['plugins'].append({
                        'name': plugin_name,
                        'desc': plugin_desc.strip(),
                        'image_path': plugin_image_path,
                        'folders': folders_data,
                        'condition_flags': condition_flags,
                        'type_descriptor': type_descriptor
                    })
        
        # Conditional file installs
        conditional_installs = xml_data.find('conditionalFileInstalls')
        conditional_installs_data = []
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
                conditional_installs_data.append({
                    'dependencies': {
                        'operator': deps.get('operator') or 'And',
                        'flags': flags
                    },
                    'files': files
                })
                
        fomod_data['conditional_installs'] = conditional_installs_data
        
        print_fomod_data(fomod_data)
        return fomod_data
    except Exception as e:
        print(f"Failed to parse FOMOD XML: {e}")
        return {}
    
def get_fomod_step_count(parsed_fomod_metadata:dict) -> int:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    step_count = len(parsed_fomod_metadata[module_name])
    
    return step_count
    
def get_fomod_group_count(parsed_fomod_metadata:dict, step_index: int = 0) -> int:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_count = len(parsed_fomod_metadata[module_name][step_name])
    
    return group_count

def get_fomod_group_info(parsed_fomod_metadata:dict, step_index: int = 0, group_index: int = 0) -> dict[str]:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    group_type = parsed_fomod_metadata[module_name][step_name][group_name]['type']
    data = {
        'type' : group_type,
        'name' : group_name
    }
    return data

def get_fomod_module_name(parsed_fomod_metadata:dict) -> str:
    reserved_keys = {'module_dependency', 'conditional_installs'}
    return next(k for k in parsed_fomod_metadata if k not in reserved_keys)

def get_fomod_group_options(parsed_fomod_metadata:dict, step_index: int = 0, group_index: int = 0) -> list:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
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
        
        # Condition flags
        condition_flags = plugin['condition_flags']
        
        options.append((plugin_name, plugin_desc, sources, condition_flags))
    
    return options

def get_plugin_image_path(parsed_fomod_metadata:dict, plugin_name:str, step_index: int = 0, group_index: int = 0) -> str:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['image_path']
    return ''

def have_plugins_images(parsed_fomod_metadata:dict, step_index: int = 0, group_index: int = 0) -> bool:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['image_path']:
            return True
    return False

def get_plugin_type(parsed_fomod_metadata:dict, plugin_name:str, step_index: int = 0, group_index: int = 0) -> str:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['name'] == plugin_name:
            return plugin['type_descriptor']['default_type']
    return ''

def get_plugin_flags(parsed_fomod_metadata:dict, plugin_name:str, step_index: int = 0, group_index: int = 0) -> str:
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    step_name = list(parsed_fomod_metadata[module_name].keys())[step_index]
    group_name = list(parsed_fomod_metadata[module_name][step_name].keys())[group_index]
    plugins = parsed_fomod_metadata[module_name][step_name][group_name]['plugins']
    for plugin in plugins:
        if plugin['condition_flags'] == plugin_flag:
            return plugin['condition_flags']
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
    module_name = get_fomod_module_name(parsed_fomod_metadata)
    # Walk through the whole metadatas to retrieve every required files
    for step in parsed_fomod_metadata[module_name].values():
        for group in step.values():
            for plugin in group['plugins']:
                if plugin['type_descriptor']['default_type'] == 'Required':
                    required_items.extend(plugin['folders'])
    return required_items

def generate_source_from_flags(parsed_fomod_metadata: dict, flags: list) -> dict:
    result = []
    for pattern in parsed_fomod_metadata['conditional_installs']:
        operator = pattern['dependencies']['operator']
        pattern_flags = pattern['dependencies']['flags']
        if operator == 'And':
            match = all(flags.get(f['flag']) == f['value'] for f in pattern_flags)
        else:
            match = any(flags.get(f['flag']) == f['value'] for f in pattern_flags)
        if match:
            result.extend(pattern['files'])
    return result
        