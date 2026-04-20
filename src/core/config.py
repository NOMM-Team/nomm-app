import os
import yaml
from gi.repository import GLib

# Yaml write and load functions are handled here
def load_yaml(path: str) -> dict:
    """Charge un fichier YAML et retourne un dictionnaire."""
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Erreur lors du chargement du fichier {path}: {e}")
    return {}

def write_yaml(data: dict, path: str):
    """Écrit un dictionnaire dans un fichier YAML et crée les dossiers parents si besoin."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False)
    except Exception as e:
        print(f"Erreur lors de l'écriture dans {path}: {e}")

# User personal data such as settings and mod folders are handled here
def get_user_data_dir() -> str:
    """Retourne le dossier de données de l'application (~/.var/app/.../data/nomm ou ~/.local/share/nomm)."""
    return os.path.join(GLib.get_user_data_dir(), "nomm")

def get_user_config_path() -> str:
    """Retourne le chemin complet vers user_config.yaml."""
    return os.path.join(get_user_data_dir(), "user_config.yaml")

def load_user_config() -> dict:
    """Charge spécifiquement la configuration de l'utilisateur."""
    return load_yaml(get_user_config_path())

def update_user_config(key: str, value):
    """Met à jour une clé spécifique dans la configuration utilisateur."""
    config = load_user_config()
    config[key] = value
    write_yaml(config, get_user_config_path())

# Games YAML are handled here
def get_metadata_path(base_folder: str, is_staging: bool = True) -> str:
    """Retourne le chemin du fichier de métadonnées selon le type de dossier."""
    filename = ".staging.nomm.yaml" if is_staging else ".downloads.nomm.yaml"
    return os.path.join(base_folder, filename)

def load_metadata(path: str) -> dict:
    """
    Charge un fichier de métadonnées. 
    Garantit que la structure de base (mods et info) existe toujours, 
    évitant ainsi les KeyError et les vérifications constantes dans l'UI.
    """
    data = load_yaml(path)
    
    # On garantit toujours la présence de ces clés
    if not isinstance(data, dict):
        data = {}
    if "mods" not in data:
        data["mods"] = {}
    if "info" not in data:
        data["info"] = {}
        
    return data

def save_metadata(data: dict, path: str) -> None:
    """Sauvegarde les métadonnées."""
    write_yaml(data, path)

def remove_mod_from_metadata(path: str, mod_key: str) -> bool:
    """
    Supprime un mod spécifique des métadonnées s'il existe.
    Retourne True si le fichier a été modifié, False sinon.
    """
    data = load_metadata(path)
    if mod_key in data["mods"]:
        del data["mods"][mod_key]
        save_metadata(data, path)
        return True
    return False