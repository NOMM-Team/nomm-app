import nomm.platforms.steam as steam
import os
import vdf
from pathlib import Path
import pathlib


def test_get_steam_base_dir_no_path(monkeypatch):
    target_path: str = os.path.expanduser("~/.local/share/Steam/")

    def mock_exists(path):
        return path == target_path

    monkeypatch.setattr(os.path, "exists", mock_exists)

    result: str | None = steam.get_steam_base_dir()
    assert result is None


def test_get_steam_base_dir_empty_steam_dir(monkeypatch):
    target_path: str = os.path.expanduser("~/.local/share/Steam/")

    def mock_exists(path):
        return path == target_path

    monkeypatch.setattr(os.path, "exists", mock_exists)

    result: str | None = steam.get_steam_base_dir()
    assert result is None


def test_get_steam_base_dir_success(monkeypatch):
    # Choose one of the paths from your search list
    target_path = Path.home() / ".local" / "share" / "Steam"
    config_file = target_path / "config" / "libraryfolders.vdf"
    userdata_dir = target_path / "userdata"

    def mock_exists(self: Path) -> bool:
        # Return True for the base path and its required critical sub-paths
        return self in (target_path, config_file, userdata_dir)

    monkeypatch.setattr(pathlib.Path, "exists", mock_exists)

    result = steam.get_steam_base_dir()
    assert result == str(target_path)


def test_get_steam_base_dir_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    assert steam.get_steam_base_dir() is None


def test_get_library_paths_success(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    vdf_file = config_dir / "libraryfolders.vdf"

    # Create dummy library locations on disk
    lib1 = tmp_path / "SteamLibrary1"
    lib2 = tmp_path / "SteamLibrary2"

    # Mock VDF dictionary structure
    vdf_content = {
        "libraryfolders": {
            "0": {"path": str(lib1)},
            "1": {"path": str(lib2)},
        }
    }

    with open(vdf_file, "w", encoding="utf-8") as f:
        vdf.dump(vdf_content, f)

    result = steam.get_library_paths(str(tmp_path))

    expected_path_1 = os.path.normpath(os.path.join(str(lib1), "steamapps"))
    expected_path_2 = os.path.normpath(os.path.join(str(lib2), "steamapps"))

    assert len(result) == 2
    assert expected_path_1 in result
    assert expected_path_2 in result


def test_get_library_paths_empty_or_none_input():
    assert steam.get_library_paths(None) == []
    assert steam.get_library_paths("") == []


def test_get_library_paths_missing_vdf_file(tmp_path):
    result = steam.get_library_paths(str(tmp_path))
    assert result == []


def test_get_library_paths_malformed_vdf(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    vdf_file = config_dir / "libraryfolders.vdf"

    vdf_file.write_text("invalid { vdf structure", encoding="utf-8")

    result = steam.get_library_paths(str(tmp_path))
    assert result == []


def test_get_library_paths_missing_path_key(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    vdf_file = config_dir / "libraryfolders.vdf"

    # VDF folder entry without a "path" key
    vdf_content = {
        "libraryfolders": {
            "0": {"label": "No path key here"}
        }
    }

    with open(vdf_file, "w", encoding="utf-8") as f:
        vdf.dump(vdf_content, f)

    result = steam.get_library_paths(str(tmp_path))
    assert result == []
