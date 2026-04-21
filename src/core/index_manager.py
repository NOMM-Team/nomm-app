#src/core/index_manager.py

import os

from core.config import write_yaml, load_yaml

INDEX_FILE = ".index_manager.yamm.yaml"

# Creates an index_manager.Yamm.yaml in the mod folder
def init_index(staging_path: str) -> List[str]:
    index_path = os.path.join(staging_path, INDEX_FILE)
    
    if not os.path.exists(index_path):
        try:
            write_yaml([], index_path)
            return True
        except Exception as e:
            print(f"Error while creating the index : {e}")
            return False
    return False

# Reads the index and return an array or something like that
def read_index(staging_path: str) -> bool:
    index_path = os.path.join(staging_path, INDEX_FILE)
    
    if os.path.exists(index_path):
        data = load_yaml(index_path)
        if isinstance(data, list):
            return data
        
    return []

# Adds a mod at the end of the index list
def add_mod_to_index(staging_path:str, mod_name:str) -> List[str]:
    data=read_index(staging_path)
    
    if mod_name not in data:
        data.append(mod_name)
        index_path = os.path.join(staging_path, INDEX_FILE)
        try:
            write_yaml(data, index_path)
            return True
        except Exception as e:
            print(f"Error while adding mod to index: {e}")
            return False
    
    return False


# Removes a mod from the index list
def delete_mod_from_index(staging_path: str, mod_name: str):
    data=read_index(staging_path)
    
    if mod_name in data:
        data.remove(mod_name)
        index_path = os.path.join(staging_path, INDEX_FILE)
        try:
            write_yaml(data, index_path)
            return True
        except Exception as e:
            print(f"Error while deleting mod from index: {e}")
            return False
    
    return False

# Change the mod index from the index list
def change_mod_index(staging_path: str, mod_name: str, index: int):
    data=read_index(staging_path)
    
    if mod_name in data:
        pos = data.index(mod_name)
        mod = data.pop(pos)
        data.insert(index, mod)
        
        index_path = os.path.join(staging_path, INDEX_FILE)
        try:
            write_yaml(data, index_path)
            return True
        except Exception as e:
            print(f"Error while changing mod index: {e}")
            return False
    return False

# Check if the mod_index mods are also present from the mod folder and vice versa
def check_index(staging_path: str):
    if not os.path.exists(staging_path):
        return []
        
    physical_folders = [
        f for f in os.listdir(staging_path) 
        if os.path.isdir(os.path.join(staging_path, f)) and not f.startswith('.')
    ]

    current_index = read_index(staging_path)
    new_index = [mod for mod in current_index if mod in physical_folders]
    
    changed = False
    for folder in physical_folders:
        if folder not in new_index:
            new_index.append(folder)
            changed = True
            
    if len(new_index) != len(current_index):
        changed = True

    if changed:
        index_path = os.path.join(staging_path, INDEX_FILE)
        try:
            write_yaml(new_index, index_path)
        except Exception as e:
            print(f"Error while syncing index : {e}")

    return new_index