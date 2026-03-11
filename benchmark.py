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

if __name__ == '__main__':
    run_benchmark()
