import os
import yaml
from gi.repository import GLib

def get_user_data_dir() -> str:
    """Retourne le dossier de données de l'application (~/.var/app/.../data/nomm ou ~/.local/share/nomm)."""
    return os.path.join(GLib.get_user_data_dir(), "nomm")

def get_user_config_path() -> str:
    """Retourne le chemin complet vers user_config.yaml."""
    return os.path.join(get_user_data_dir(), "user_config.yaml")

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

def load_user_config() -> dict:
    """Charge spécifiquement la configuration de l'utilisateur."""
    return load_yaml(get_user_config_path())

def update_user_config(key: str, value):
    """Met à jour une clé spécifique dans la configuration utilisateur."""
    config = load_user_config()
    config[key] = value
    write_yaml(config, get_user_config_path())