import os
import pytest
from MergePicFolders.worker import Worker

def test_worker_no_qapplication_import():
    """Verify that Worker module doesn't import QApplication."""
    import MergePicFolders.worker as worker_module
    assert "QApplication" not in dir(worker_module), "QApplication should not be imported in worker.py"

def test_worker_source_no_processevents():
    """Verify that worker.py source code doesn't contain processEvents calls."""
    worker_file = os.path.join("src", "MergePicFolders", "worker.py")
    with open(worker_file, "r") as f:
        content = f.read()

    assert "processEvents" not in content, "QApplication.processEvents() calls should be removed from worker.py"

def test_worker_instantiation():
    """Verify that Worker can be instantiated (requires QCoreApplication/QApplication in some environments).
    This is more of a smoke test.
    """
    from PySide6.QtWidgets import QApplication
    import sys

    # We need a QApplication instance to instantiate QObjects/QThreads in many environments
    app = QApplication.instance() or QApplication(sys.argv)

    worker = Worker(task_type="scan_subfolder_images", folder_to_scan=".")
    assert worker is not None
    assert worker.task_type == "scan_subfolder_images"
