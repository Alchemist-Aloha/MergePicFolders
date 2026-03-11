import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from MergePicFolders.worker import Worker

def test_generate_unique_target_path_no_conflict():
    worker = Worker("test_task")
    source_path = Path("source/image.png")
    target_folder = Path("target")

    # Mock exists to return False
    with patch("pathlib.Path.exists", return_value=False):
        result = worker._generate_unique_target_path(source_path, target_folder)

    assert result == target_folder / "image.png"

def test_generate_unique_target_path_with_conflict():
    worker = Worker("test_task")
    source_path = Path("source/image.png")
    target_folder = Path("target")

    # Mock exists: True for "image.png", False for "image_1.png"
    def mock_exists(self):
        return self.name == "image.png"

    with patch("pathlib.Path.exists", autospec=True, side_effect=mock_exists):
        result = worker._generate_unique_target_path(source_path, target_folder)

    assert result == target_folder / "image_1.png"

def test_generate_unique_target_path_multiple_conflicts():
    worker = Worker("test_task")
    source_path = Path("source/image.png")
    target_folder = Path("target")

    # Mock exists: True for "image.png", "image_1.png", "image_2.png", False for "image_3.png"
    def mock_exists(self):
        return self.name in ["image.png", "image_1.png", "image_2.png"]

    with patch("pathlib.Path.exists", autospec=True, side_effect=mock_exists):
        result = worker._generate_unique_target_path(source_path, target_folder)

    assert result == target_folder / "image_3.png"

@patch("MergePicFolders.worker.time.time", return_value=1234567890.123)
def test_generate_unique_target_path_safety_break_timestamp_success(mock_time):
    worker = Worker("test_task")
    source_path = Path("source/image.png")
    target_folder = Path("target")

    # Mock exists to always return True for counter names, but False for the timestamp name
    def mock_exists(self):
        return "1234567890123" not in self.name

    with patch("pathlib.Path.exists", autospec=True, side_effect=mock_exists):
        result = worker._generate_unique_target_path(source_path, target_folder)

    # 1234567890.123 * 1000 = 1234567890123
    assert result == target_folder / "image_1234567890123.png"

@patch("MergePicFolders.worker.time.time", return_value=1234567890.123)
def test_generate_unique_target_path_safety_break_timestamp_failure(mock_time):
    worker = Worker("test_task")
    source_path = Path("source/image.png")
    target_folder = Path("target")

    # Mock exists to always return True
    with patch("pathlib.Path.exists", return_value=True):
        result = worker._generate_unique_target_path(source_path, target_folder)

    assert result is None
