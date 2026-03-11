import time
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
