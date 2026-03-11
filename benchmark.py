import time
import sys
import os
from pathlib import Path

# Use offscreen platform for headless environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt
from src.MergePicFolders.window import ImageFolderTool

def run_benchmark():
    app = QApplication(sys.argv)
    window = ImageFolderTool()

    num_items = 5000
    for i in range(num_items):
        item = QListWidgetItem(f"folder_{i}")
        folder_path = Path(f"/fake/path/folder_{i}")
        item.setData(Qt.ItemDataRole.UserRole, folder_path)
        window.subfolder_list_widget.addItem(item)

    original_isfile = os.path.isfile
    original_access = os.access

    os.path.isfile = lambda path: True
    os.access = lambda path, mode: True

    start_time = time.time()
    for i in range(num_items):
        folder_path_str = str(Path(f"/fake/path/folder_{i}"))
        image_path_str = "/fake/image.png"
        window.set_folder_thumbnail(folder_path_str, image_path_str)

    end_time = time.time()

    os.path.isfile = original_isfile
    os.access = original_access

    print(f"Time for {num_items} thumbnails: {end_time - start_time:.4f} seconds")
import tempfile
from pathlib import Path
from src.MergePicFolders.worker import Worker

def test_unique_target_path(worker, num_files, num_conflicts, existing_files_set=None):
    with tempfile.TemporaryDirectory() as target_dir_name:
        target_dir = Path(target_dir_name)

        # Create initial conflicting files
        source_name = "image.jpg"
        target_dir.joinpath(source_name).touch()
        for i in range(1, num_conflicts + 1):
            target_dir.joinpath(f"image_{i}.jpg").touch()

        start_time = time.time()
        for _ in range(num_files):
            # Worker logic for creating a unique path
            source_path = Path("source_dir") / source_name
            target_path = worker._generate_unique_target_path(source_path, target_dir)
            if target_path:
                target_path.touch()

        end_time = time.time()

        return end_time - start_time

def run_benchmark():
    worker = Worker("test")
    # We want to measure the time it takes to add a file when there are already many conflicts

    print("Running baseline benchmarks...")

    # Baseline: no conflicts
    t = test_unique_target_path(worker, 50, 0)
    print(f"Time to add 50 files with 0 existing conflicts: {t:.4f}s")

    # Baseline: 100 conflicts
    t = test_unique_target_path(worker, 100, 100)
    print(f"Time to add 100 files with 100 existing conflicts: {t:.4f}s")

    # Baseline: 500 conflicts
    t = test_unique_target_path(worker, 100, 500)
    print(f"Time to add 100 files with 500 existing conflicts: {t:.4f}s")

    # Baseline: 900 conflicts
    t = test_unique_target_path(worker, 100, 900)
    print(f"Time to add 100 files with 900 existing conflicts: {t:.4f}s")

if __name__ == '__main__':
    run_benchmark()
