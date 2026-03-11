import pytest
from PySide6.QtCore import QCoreApplication
import sys
import os

# Ensure the src directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app

from MergePicFolders.worker import Worker

def test_worker_stop(qapp, qtbot):
    """
    Test that calling Worker.stop() sets _is_running to False and emits a progress signal.
    """
    worker = Worker(task_type="scan_subfolder_images")

    assert worker._is_running is True

    with qtbot.waitSignal(worker.progress, timeout=1000) as blocker:
        worker.stop()

    assert blocker.args == ["Task cancellation requested..."]
    assert worker._is_running is False
