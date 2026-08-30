import os
import gettext

from gi.repository import GLib
from nomm.core.tools import load_yaml, write_yaml
from typing import List, Dict, Any
from enum import Enum

_ = gettext.gettext


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
    user_config_path = os.path.join(GLib.get_user_data_dir(), 'nomm', 'user_config.yaml')
    config = load_yaml(user_config_path)
    config[key] = value
    write_yaml(config, user_config_path)


def load_user_config() -> dict:
    """Returns the user's NOMM configuration file data as a dictionary"""
    user_config_path = os.path.join(GLib.get_user_data_dir(), 'nomm', 'user_config.yaml')
    return load_yaml(user_config_path)


def write_user_config(data: dict) -> dict:
    """Writes to the user's NOMM configuration file"""
    user_config_path = os.path.join(GLib.get_user_data_dir(), 'nomm', 'user_config.yaml')
    return write_yaml(data, user_config_path)


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
