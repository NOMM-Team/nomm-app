import os
import gettext

from gi.repository import GLib
from nomm.core.tools import load_yaml, write_yaml
from typing import List, Dict, Any
from enum import Enum

_ = gettext.gettext

if ".local" in GLib.get_user_data_dir():  # local installation i.e. running python
    DATA_DIR = os.path.join(GLib.get_user_data_dir(), "nomm")
else:  # a flatpak, no need to add "nomm" parent folder
    DATA_DIR = os.path.join(GLib.get_user_data_dir())

USER_CONFIG_PATH = os.path.join(DATA_DIR, "user_config.yaml")
PRESET_GAME_CONFIG_PATH = os.path.join(DATA_DIR, "preset_game_configs")
CUSTOM_GAME_CONFIG_PATH = os.path.join(DATA_DIR, "custom_game_configs")
SWITCH_GAME_CONFIG_PATH = os.path.join(DATA_DIR, "preset_game_configs", "emulation", "switch.yaml")


class LibrarySort(Enum):
    ALPHABETIC = _("Alphabetical Order")
    NUMBER_OF_MODS = _("Number of Mods")

    @property
    def display_name(self) -> str:
        """Return the translated display name for UI."""
        if self == LibrarySort.ALPHABETIC:
            return _("Alphabetical Order")
        return _("Number of Mods")

    @classmethod
    def from_string(cls, value: str) -> 'LibrarySort':
        try:
            return cls(value)
        except ValueError:
            return cls.NUMBER_OF_MODS


# changes user setting by changing/writing the value for an associated key string
def update_user_config(key: str, value: Any) -> None:
    config = load_user_config()
    config[key] = value
    write_user_config(config)


def load_user_config() -> dict:
    """Returns the user's NOMM configuration file data as a dictionary"""
    return load_yaml(USER_CONFIG_PATH)


def write_user_config(data: dict) -> dict:
    """Writes to the user's NOMM configuration file"""
    return write_yaml(data, USER_CONFIG_PATH)


def parse_mod_paths(deployment_dicts: list | str, game_path: str, user_data_path: str) -> List[Dict[str, str]]:

    # Handle case where there is only one path provided, and it's not a list of dicts
    if not isinstance(deployment_dicts, list):
        deployment_dicts = [{"name": "default", "path": deployment_dicts}]

    # Parse the paths
    for deployment_dict in deployment_dicts:
        deployment_path = deployment_dict["path"]
        if "}" not in deployment_path:  # NOMM 0.5 Format
            deployment_path = os.path.join(game_path, deployment_path)
        else:  # NOMM 0.6+ Format
            deployment_path = deployment_path.replace("{game_path}", game_path)
            deployment_path = deployment_path.replace("{user_data_path}", user_data_path)
        deployment_dict["path"] = deployment_path

    return deployment_dicts
