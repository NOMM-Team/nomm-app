import gi
from nomm.core.tools import retrieve_casesensitive_paths
from nomm.core.archive_manager import get_archive_type, extract_archive, get_all_relative_files
import hashlib
from os import path
import os
from pathlib import Path

from nomm.core.user_config import load_user_config, load_yaml, update_user_config, DATA_DIR
from nomm.core.tools import write_yaml
from nomm.core.downloader import Downloader

gi.require_version('Gtk', '4.0')


def test_load_yaml():
    user_config_path = os.path.join(DATA_DIR, 'user_config.yaml')
    config = {
        "api_key": "",
        "download_paths": []
    }
    write_yaml(config, user_config_path)

    output = load_user_config()

    assert output == config


def test_update_user_config():
    user_config_path = os.path.join(DATA_DIR, 'user_config.yaml')
    config = {
        "api_key": "",
        "download_paths": []
    }
    write_yaml(config, user_config_path)

    new_value = "nomm_is_so_cool"
    edited_config = {
        "api_key": new_value,
        "download_paths": []
    }

    update_user_config("api_key", new_value)

    assert edited_config == load_yaml(user_config_path)


def test_download_file(tmpdir):
    url = "https://github.com/nomm-team/nomm-app/releases/download/0.5.0/nomm.flatpak"
    downloader = Downloader()
    dir = tmpdir.mkdir("downloads")
    thing = downloader.download_mod(url, dir)
    file_path = dir.join('nomm.flatpak')
    h = hashlib.sha256()
    with open(file_path, 'rb') as fh:
        while True:
            data = fh.read(4096)
            if len(data) == 0:
                break
            else:
                h.update(data)
    assert (h.hexdigest() == "c6db511262705aacf545b1ed1cc695df309628789075f4464ea5909fe88ce4d1")
    assert path.exists(file_path)


def test_retrieve_casesensitive_filepath(tmpdir):
    dir = tmpdir.mkdir("wrong")
    wrong_path = os.path.abspath(dir.join("Paths/are/Annoying"))
    right_path = os.path.abspath(dir.join("paths/are/annoying"))
    Path(right_path).mkdir(parents=True, exist_ok=True)

    corrected_path = retrieve_casesensitive_paths(wrong_path)

    assert corrected_path == right_path


def test_get_archive_type(tmpdir):
    url = "https://github.com/nomm-team/nomm-app/archive/refs/tags/0.5.0.zip"
    dir = tmpdir.mkdir("downloads")
    downloader = Downloader()
    downloader.download_mod(url, dir)
    filepath = os.path.abspath(dir.join("nomm-app-0.5.0.zip"))

    assert get_archive_type(filepath) == "zip"


def test_extract_archive(tmpdir):
    url = "https://github.com/nomm-team/nomm-app/archive/refs/tags/0.5.0.zip"
    dir = tmpdir.mkdir("downloads")
    dest = tmpdir.mkdir("target")
    downloader = Downloader()
    downloader.download_mod(url, dir)
    filepath = os.path.abspath(dir.join("nomm-app-0.5.0.zip"))
    target_dir = os.path.abspath(dest.join("nomm-app-0.5.0"))

    assert extract_archive(filepath, dest)
    assert path.exists(target_dir)


def test_get_relative_files(tmpdir):
    url = "https://github.com/nomm-team/nomm-app/archive/refs/tags/0.5.0.zip"
    dir = tmpdir.mkdir("downloads")
    dest = tmpdir.mkdir("target")
    downloader = Downloader()
    downloader.download_mod(url, dir)
    filepath = os.path.abspath(dir.join("nomm-app-0.5.0.zip"))
    target_dir = os.path.abspath(dest.join("nomm-app-0.5.0"))

    extract_archive(filepath, dest)
    file_list = get_all_relative_files(dest)

    for file_name in file_list:
        assert path.exists(dest.join(file_name))

    assert len(file_list) == 29
