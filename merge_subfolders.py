import sys
import os
import shutil
from pathlib import Path
import time  # For unique naming fallback
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QMessageBox,
    QSplitter,
    QScrollArea,
    QAbstractItemView,
    QFrame,
)
from PySide6.QtGui import QPixmap, QIcon, QFont, QImageReader
from PySide6.QtCore import Qt, QSize, QThread, Signal, Slot

# --- Configuration ---
SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".webp",
}
THUMBNAIL_SIZE = QSize(128, 128)
PREVIEW_AREA_MIN_WIDTH = 400


# --- Worker Thread for Background Tasks ---
class Worker(QThread):
    progress = Signal(str)
    finished = Signal(str, bool)
    error = Signal(str)
    image_paths = Signal(list)
    folder_preview_image = Signal(str, str)  # New signal: folder_path, image_path

    # Use keyword arguments for flexibility
    def __init__(
        self,
        task_type,
        *,  # Make subsequent args keyword-only
        folder_to_scan=None,
        source_folder_paths=None,
        target_folder_path=None,
        parent=None,
    ):
        super().__init__(parent)
        self.task_type = task_type
        self.folder_to_scan = Path(folder_to_scan) if folder_to_scan else None
        self.source_merge_folders = (
            [Path(p) for p in source_folder_paths] if source_folder_paths else []
        )
        self.target_merge_folder = (
            Path(target_folder_path) if target_folder_path else None
        )
        self._is_running = True
        self._success = False  # Track task success

    def run(self):
        self._is_running = True
        self._success = False  # Reset success status
        try:
            if self.task_type == "scan_subfolder_images" and self.folder_to_scan:
                self._scan_folder_for_images(self.folder_to_scan)
                self._success = True  # Assume success if no exception
            elif self.task_type == "get_folder_preview" and self.folder_to_scan:
                self._get_folder_preview_image(self.folder_to_scan)
                self._success = True
            elif (
                self.task_type == "merge_subs"
                and self.target_merge_folder
                and self.source_merge_folders
            ):
                self._merge_subfolders_to_target()
                self._success = True  # Assume success if no major exception
            else:
                # More specific error reporting based on inputs
                if not self.task_type:
                    self.error.emit("Worker started with no task type.")
                elif (
                    self.task_type == "scan_subfolder_images"
                    and not self.folder_to_scan
                ):
                    self.error.emit("Scan task started with no folder provided.")
                elif self.task_type == "merge_subs" and (
                    not self.target_merge_folder or not self.source_merge_folders
                ):
                    self.error.emit(
                        "Merge task started with invalid source or target folders."
                    )
                else:
                    self.error.emit(
                        f"Unknown task type or missing required folders: {self.task_type}"
                    )

        except Exception as e:
            self.error.emit(f"Unexpected error in worker ({self.task_type}): {e}")
            self._success = False
        finally:
            self._is_running = False
            self.finished.emit(
                self.task_type, self._success
            )  # Emit task type and success

    def stop(self):
        self._is_running = False
        self.progress.emit("Task cancellation requested...")

    def _scan_folder_for_images(self, folder_path):
        """Scans a specific folder recursively for image files."""
        if not folder_path.is_dir():
            self.error.emit(
                f"Cannot scan: '{folder_path.name}' is not a valid directory."
            )
            return

        try:
            self.progress.emit(f"Scanning '{folder_path.name}' for images...")
            count = 0
            paths_to_emit = []
            # Use rglob to find images recursively within this specific folder
            for item in folder_path.rglob("*"):
                if not self._is_running:
                    self.progress.emit("Scan cancelled.")
                    return
                if item.is_file() and item.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    # Emit full path
                    paths_to_emit.append(str(item))
                    count += 1
                    if len(paths_to_emit) >= 50:
                        self.image_paths.emit(paths_to_emit)  # Emit batch
                        paths_to_emit = []
                        QApplication.processEvents()

            if paths_to_emit:  # Emit any remaining paths
                self.image_paths.emit(paths_to_emit)

            self.progress.emit(
                f"Scan of '{folder_path.name}' complete. Found {count} images."
            )
        except Exception as e:
            self.error.emit(f"Error during scan of '{folder_path.name}': {e}")
            raise  # Re-raise to indicate failure to the run() method

    def _generate_unique_target_path(self, source_path, target_folder):
        """Generates a unique path in the target folder for a source file."""
        target_path = target_folder / source_path.name
        if not target_path.exists():
            return target_path  # Path is already unique

        # Collision detected, generate a new name
        counter = 1
        stem = source_path.stem
        suffix = source_path.suffix
        while target_path.exists():
            target_path = target_folder / f"{stem}_{counter}{suffix}"
            counter += 1
            if counter > 1000:  # Safety break
                # Extremely unlikely, use timestamp as fallback
                timestamp = int(time.time() * 1000)
                target_path = target_folder / f"{stem}_{timestamp}{suffix}"
                if target_path.exists():  # If STILL exists, give up
                    return None  # Indicate failure to find unique name
                break  # Exit loop with timestamp name
        return target_path

    def _merge_subfolders_to_target(self):
        """Moves content from source folders into the target folder."""
        if self.target_merge_folder:
            self.progress.emit(
                f"Starting merge into target: {self.target_merge_folder.name}"
            )
        else:
            self.error.emit("Target merge folder is not set. Aborting merge.")
            return
        moved_count = 0
        skipped_count = 0
        deleted_source_dirs = 0
        processed_sources = []

        if not self.target_merge_folder.exists():
            self.error.emit(
                f"Merge target folder '{self.target_merge_folder.name}' does not exist (should have been created). Aborting merge."
            )
            return  # Critical error if target wasn't created

        try:
            for source_folder in self.source_merge_folders:
                if not self._is_running:
                    self.progress.emit(
                        "Merge cancelled during source folder processing."
                    )
                    return

                if not source_folder.is_dir():
                    self.error.emit(
                        f"Source '{source_folder.name}' is not a valid directory. Skipping."
                    )
                    continue

                self.progress.emit(f"Processing source: {source_folder.name}...")
                items_to_move = list(source_folder.rglob("*"))
                processed_items_in_source = 0

                for item_path in items_to_move:
                    if not self._is_running:
                        self.progress.emit("Merge cancelled during file processing.")
                        return

                    if item_path.is_file():  # Only move files
                        source_path = item_path
                        target_path = self._generate_unique_target_path(
                            source_path, self.target_merge_folder
                        )

                        if target_path is None:
                            self.error.emit(
                                f"Could not generate unique name for '{source_path.name}' in target. Skipping."
                            )
                            skipped_count += 1
                            continue  # Skip this file

                        try:
                            shutil.move(str(source_path), str(target_path))
                            self.progress.emit(
                                f"Moved: {source_path.name} -> {target_path.name} (into {self.target_merge_folder.name})"
                            )
                            moved_count += 1
                        except Exception as move_error:
                            self.error.emit(
                                f"Error moving {source_path.name}: {move_error}"
                            )
                            skipped_count += 1

                    processed_items_in_source += 1
                    if processed_items_in_source % 20 == 0:
                        QApplication.processEvents()

                processed_sources.append(source_folder)
                QApplication.processEvents()

            # --- Optional Deletion of Empty Source Folders ---
            self.progress.emit("Checking source folders for deletion...")
            for source_folder in processed_sources:
                # (Deletion logic remains the same as previous version)
                # ... [omitted for brevity, but it's the same os.walk bottom-up check] ...
                if not self._is_running:
                    break
                try:
                    empty_dirs_in_source = []
                    for root, dirs, files in os.walk(str(source_folder), topdown=False):
                        if not self._is_running:
                            break
                        root_path = Path(root)
                        if not dirs and not files:
                            empty_dirs_in_source.append(root_path)
                    if not self._is_running:
                        break

                    for dir_to_delete in empty_dirs_in_source:
                        if not self._is_running:
                            break
                        try:
                            dir_to_delete.rmdir()
                            self.progress.emit(
                                f"Deleted empty directory: {dir_to_delete}"
                            )
                            if dir_to_delete == source_folder:
                                deleted_source_dirs += 1
                        except OSError as rmdir_error:
                            self.progress.emit(
                                f"Could not delete dir {dir_to_delete.name}: {rmdir_error}"
                            )
                except Exception as del_check_err:
                    self.error.emit(
                        f"Error during deletion check for {source_folder.name}: {del_check_err}"
                    )
            # -----------------------------------------------------

            if skipped_count > 0:
                self.progress.emit(
                    f"Merge partially complete. Moved {moved_count} files, **skipped {skipped_count} due to errors/naming conflicts**. Processed {len(processed_sources)} sources, deleted {deleted_source_dirs} empty source folders."
                )
                # Mark overall success as False if files were skipped
                self._success = False
            else:
                self.progress.emit(
                    f"Merge complete. Moved {moved_count} files. Processed {len(processed_sources)} sources, deleted {deleted_source_dirs} empty source folders."
                )
                self._success = True  # Mark success only if no skips

        except Exception as e:
            self.error.emit(f"Error during merging process: {e}")
            self._success = False  # Ensure failure is marked on exception
            # No need to re-raise, error is emitted

    def _get_folder_preview_image(self, folder_path):
        """Finds the first image in a folder to use as a preview thumbnail."""
        if not folder_path.is_dir():
            self.error.emit(
                f"Cannot scan: '{folder_path.name}' is not a valid directory."
            )
            return

        try:
            self.progress.emit(f"Finding preview image for '{folder_path.name}'...")

            # First try to find an image directly in this folder (not recursive)
            for item in folder_path.glob("*"):
                if not self._is_running:
                    return
                if item.is_file() and item.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    # Add explicit checks for file existence and accessibility
                    try:
                        if (
                            os.path.getsize(str(item)) > 0
                        ):  # Make sure file is not empty
                            self.folder_preview_image.emit(str(folder_path), str(item))
                            return
                    except (OSError, PermissionError) as e:
                        self.progress.emit(
                            f"Skipping inaccessible image: {item.name} - {e}"
                        )
                        continue

            # If no image found, search recursively but limited depth
            max_depth = 2  # Only go 2 levels deep at most
            for depth in range(1, max_depth + 1):
                pattern = "/".join(["*"] * depth)
                for item in folder_path.glob(pattern):
                    if not self._is_running:
                        return
                    if (
                        item.is_file()
                        and item.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
                    ):
                        # Add the same file validation here
                        try:
                            if os.path.getsize(str(item)) > 0:
                                self.folder_preview_image.emit(
                                    str(folder_path), str(item)
                                )
                                return
                        except (OSError, PermissionError) as e:
                            self.progress.emit(
                                f"Skipping inaccessible image: {item.name} - {e}"
                            )
                            continue

            # No image found
            self.progress.emit(f"No preview image found for '{folder_path.name}'")

        except Exception as e:
            self.error.emit(f"Error finding preview for '{folder_path.name}': {e}")


# --- Main Application Window ---
class ImageFolderTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Folder Preview & Merge Tool v3 (PySide6)")
        self.setGeometry(100, 100, 1300, 800)

        # --- State Variables ---
        self.current_root_folder = None
        # Removed self.target_subfolder
        self.image_files_in_preview = []  # Tracks images currently shown
        self.worker_thread = None
        self.current_task_type = None
        self.last_previewed_folder = None  # Track which folder is being previewed
        self.folder_preview_tasks = {}  # Map folder path to worker
        self.folder_preview_cache = {}  # Cache of folder path to thumbnail image path
        self.waiting_folders = []  # Queue for waiting folders

        # --- Central Widget and Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Top Panel: Folder Selection ---
        top_panel = QWidget()
        top_layout = QHBoxLayout(top_panel)
        self.select_folder_button = QPushButton(
            QIcon.fromTheme("folder-open"), " Select Root Folder"
        )
        self.select_folder_button.clicked.connect(self.select_root_folder)
        self.folder_label = QLabel("No folder selected.")
        self.folder_label.setFont(QFont("SansSerif", 10))
        self.folder_label.setWordWrap(True)
        top_layout.addWidget(self.select_folder_button)
        top_layout.addWidget(self.folder_label, 1)
        main_layout.addWidget(top_panel)

        # --- Middle Panel Splitter ---
        splitter_main = QSplitter(Qt.Orientation.Horizontal)

        # --- Left Panel: Subfolder List & Merge Button ---
        left_panel_widget = QWidget()
        left_layout = QVBoxLayout(left_panel_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Subfolder List Area
        subfolder_group = QWidget()
        subfolder_layout = QVBoxLayout(subfolder_group)
        subfolder_layout.setContentsMargins(5, 5, 5, 5)

        subfolder_title = QLabel("Subfolders (Click to Preview, Check to Merge)")
        subfolder_title.setFont(QFont("SansSerif", 11, QFont.Weight.Bold))
        subfolder_layout.addWidget(subfolder_title)

        self.subfolder_list_widget = QListWidget()
        self.subfolder_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.subfolder_list_widget.currentItemChanged.connect(
            self.trigger_subfolder_preview
        )
        self.subfolder_list_widget.itemChanged.connect(self.update_merge_button_state)
        self.subfolder_list_widget.setIconSize(QSize(64, 64))
        subfolder_layout.addWidget(self.subfolder_list_widget, 1)  # Allow list to grow

        # Merge Button (Moved below the list)
        self.merge_button = QPushButton(
            QIcon.fromTheme("document-save-as"), "Merge Checked Folders into New Folder"
        )
        self.merge_button.clicked.connect(self.confirm_and_start_merge_to_new)
        self.merge_button.setEnabled(False)  # Disabled initially
        subfolder_layout.addWidget(self.merge_button)

        # Removed Target label and button

        left_layout.addWidget(subfolder_group, 1)  # Let subfolder section expand

        # --- Separator --- (Optional visual separation)
        line_sep = QFrame()
        line_sep.setFrameShape(QFrame.Shape.VLine)
        line_sep.setFrameShadow(QFrame.Shadow.Sunken)
        # Might need to place this differently if used, perhaps in splitter context

        splitter_main.addWidget(left_panel_widget)  # Add left panel to splitter

        # --- Right Panel: Image Preview List & Large Preview ---
        right_panel_widget = QWidget()
        right_layout = QVBoxLayout(right_panel_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Image Preview List (Shows content of selected subfolder)
        image_list_title = QLabel("Image Preview (Content of selected folder)")
        image_list_title.setFont(QFont("SansSerif", 11, QFont.Weight.Bold))
        right_layout.addWidget(image_list_title)

        self.image_list_widget = QListWidget()
        self.image_list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.image_list_widget.setIconSize(THUMBNAIL_SIZE)
        self.image_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.image_list_widget.setWordWrap(True)
        # Connect selection here to the large preview display
        self.image_list_widget.itemSelectionChanged.connect(self.show_large_preview)
        right_layout.addWidget(self.image_list_widget, 1)  # Allow list to stretch

        # Large Preview Area (Below image list)
        preview_area_title = QLabel("Selected Image Preview")
        preview_area_title.setFont(QFont("SansSerif", 11, QFont.Weight.Bold))
        right_layout.addWidget(preview_area_title)

        self.image_path_label = QLabel(
            "Select an image from the list above"
        )  # Updated label
        self.image_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_path_label.setWordWrap(True)
        right_layout.addWidget(self.image_path_label)

        self.preview_label = QLabel("Image Preview")  # The actual large image display
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(PREVIEW_AREA_MIN_WIDTH, 200)  # Min size
        self.preview_label.setStyleSheet(
            "QLabel { background-color : lightgray; border: 1px solid gray; }"
        )

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.preview_label)
        right_layout.addWidget(scroll_area, 2)  # Give large preview more space

        splitter_main.addWidget(right_panel_widget)  # Add right panel to splitter
        splitter_main.setSizes([450, 850])  # Adjust initial sizes

        main_layout.addWidget(splitter_main, 1)

        # --- Bottom Panel: Log Area ---
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Monospace", 9))
        self.log_edit.setFixedHeight(100)
        main_layout.addWidget(self.log_edit)

    # --- Slot Methods ---

    @Slot(str)
    def log_message(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_edit.append(f"[{timestamp}] {message}")
        self.log_edit.verticalScrollBar().setValue(
            self.log_edit.verticalScrollBar().maximum()
        )
        QApplication.processEvents()

    @Slot(str)
    def update_progress(self, message):
        self.log_message(f"PROGRESS: {message}")

    @Slot(str)
    def handle_error(self, error_message):
        self.log_message(f"ERROR: {error_message}")
        QMessageBox.critical(self, "Error", error_message)
        # Don't necessarily re-enable UI here, wait for finished signal

    # Modify finished slot to preserve thumbnails during refresh
    @Slot(str, bool)
    def task_finished(self, task_type, success):
        self.log_message(
            f"Task '{task_type}' finished {'successfully' if success else 'with errors/cancellation'}."
        )
        original_worker = self.sender()  # Get the worker that emitted the signal
        # Only clear worker if it's the one that just finished
        if self.worker_thread == original_worker:
            self.worker_thread = None
            self.current_task_type = None
            self.enable_ui(True)  # Re-enable UI now that task is done

        # Refresh subfolder list after a merge operation completes
        if task_type == "merge_subs":
            self.log_message("Refreshing subfolder list...")
            self.clear_preview_area()  # Clear previews after merge
            # Don't clear the folder thumbnail cache here
            self.populate_subfolder_list()  # Reload subfolders

        # Update status after scan finishes
        elif task_type == "scan_subfolder_images":
            if success:
                count = self.image_list_widget.count()
                folder_name = (
                    self.last_previewed_folder.name
                    if self.last_previewed_folder
                    else "selected folder"
                )
                self.image_path_label.setText(
                    f"{count} images found in '{folder_name}'. Select one."
                )
            else:
                self.image_path_label.setText(
                    f"Error scanning '{self.last_previewed_folder.name if self.last_previewed_folder else 'folder'}'."
                )

    @Slot(bool)
    def enable_ui(self, enabled):
        """Enables or disables UI elements during background tasks."""
        self.select_folder_button.setEnabled(enabled)
        self.subfolder_list_widget.setEnabled(enabled)
        # Merge button state depends on selection
        if enabled and self.current_root_folder:
            self.update_merge_button_state()
        else:
            self.merge_button.setEnabled(False)
        self.image_list_widget.setEnabled(enabled)

    @Slot()
    def select_root_folder(self):
        """Opens a dialog to select the root folder."""
        self.stop_worker_thread()

        folder = QFileDialog.getExistingDirectory(
            self, "Select Root Folder Containing Subfolders"
        )
        if folder:
            self.current_root_folder = Path(folder)
            self.folder_label.setText(f"Selected: {self.current_root_folder}")
            self.log_message(f"Root folder selected: {self.current_root_folder}")

            # Reset state
            self.subfolder_list_widget.clear()
            self.clear_preview_area()  # Clear image list and preview
            self.merge_button.setEnabled(False)
            self.last_previewed_folder = None

            # Populate subfolders ONLY
            self.populate_subfolder_list()
            # DO NOT automatically scan all images anymore

    @Slot()
    def populate_subfolder_list(self):
        """Finds immediate subdirectories and adds them as checkable items to the list."""
        try:
            # Save current checked folders before clearing
            checked_folder_names = set()
            for index in range(self.subfolder_list_widget.count()):
                item = self.subfolder_list_widget.item(index)
                if item and item.checkState() == Qt.CheckState.Checked:
                    checked_folder_names.add(item.text())

            # Save current thumbnails (map folder name to thumbnail path for more resilience)
            cached_thumbnails_by_name = {}
            for folder_path_str, image_path in self.folder_preview_cache.items():
                folder_name = Path(folder_path_str).name
                cached_thumbnails_by_name[folder_name] = image_path

            self.subfolder_list_widget.clear()

            # Clean up any existing preview tasks
            for worker in self.folder_preview_tasks.values():
                if worker and worker.isRunning():
                    worker.stop()

            self.folder_preview_tasks.clear()  # Reset preview tasks
            self.waiting_folders.clear()  # Clear waiting folders

            # Initialize thumbnail loading with caution
            max_initial_workers = 2  # Only start 2 workers initially
            active_workers = 0

            if not self.current_root_folder or not self.current_root_folder.is_dir():
                return

            count = 0
            try:
                subdirs = [d for d in self.current_root_folder.iterdir() if d.is_dir()]
                if not subdirs:
                    self.log_message("No subfolders found in the selected root folder.")
                    return

                # First, add all items to the list
                for subdir in sorted(subdirs, key=lambda p: p.name):
                    item = QListWidgetItem(subdir.name)
                    item.setData(Qt.ItemDataRole.UserRole, subdir)  # Store Path object
                    item.setIcon(QIcon.fromTheme("folder"))  # Default folder icon
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    if subdir.name in checked_folder_names:
                        item.setCheckState(Qt.CheckState.Checked)
                    else:
                        item.setCheckState(Qt.CheckState.Unchecked)
                    self.subfolder_list_widget.addItem(item)
                    count += 1

                    # Update folder cache with new path structure
                    folder_path_str = str(subdir)
                    if subdir.name in cached_thumbnails_by_name:
                        cached_image_path = cached_thumbnails_by_name[subdir.name]
                        if os.path.isfile(cached_image_path) and os.access(
                            cached_image_path, os.R_OK
                        ):
                            # Update cache with the new path structure
                            self.folder_preview_cache[folder_path_str] = (
                                cached_image_path
                            )
                            # Apply the thumbnail immediately
                            self.set_folder_thumbnail(
                                folder_path_str, cached_image_path
                            )

                # Process thumbnails for folders that don't have cached thumbnails
                folders_needing_thumbnails = []
                for i in range(self.subfolder_list_widget.count()):
                    item = self.subfolder_list_widget.item(i)
                    folder_path = item.data(Qt.ItemDataRole.UserRole)
                    if str(folder_path) not in self.folder_preview_cache:
                        folders_needing_thumbnails.append((folder_path, item))

                # Start a limited number immediately
                for i in range(
                    min(max_initial_workers, len(folders_needing_thumbnails))
                ):
                    folder_path, item = folders_needing_thumbnails[i]
                    self.request_folder_preview(folder_path, item)
                    active_workers += 1

                # Queue the rest for later
                for i in range(max_initial_workers, len(folders_needing_thumbnails)):
                    folder_path, item = folders_needing_thumbnails[i]
                    self.waiting_folders.append((folder_path, item))

                self.log_message(f"Found {count} subfolders.")

            except Exception as e:
                self.handle_error(f"Error listing subfolders: {e}")
            self.update_merge_button_state()
        except Exception as e:
            self.handle_error(f"Critical error in populate_subfolder_list: {e}")

    @Slot(str, bool)
    def folder_preview_task_finished(self, task_type, success):
        """Handle completion of a folder preview task."""
        if task_type != "get_folder_preview":
            return

        # Get the worker that finished
        worker = self.sender()

        # Remove from active tasks
        for folder_path, w in list(self.folder_preview_tasks.items()):
            if w == worker:
                del self.folder_preview_tasks[folder_path]
                break

        # Start a waiting folder if available
        if self.waiting_folders:
            next_folder, next_item = self.waiting_folders.pop(0)
            self.request_folder_preview(next_folder, next_item)

    def request_folder_preview(self, folder_path, list_item):
        """Starts a background task to find a preview image for a folder."""
        try:
            # Skip invalid folders
            if not folder_path or not folder_path.is_dir():
                return

            # Check if we already have a cached preview for this folder
            folder_path_str = str(folder_path)
            if folder_path_str in self.folder_preview_cache:
                cached_path = self.folder_preview_cache[folder_path_str]
                if Path(cached_path).exists() and os.access(cached_path, os.R_OK):
                    self.set_folder_thumbnail(folder_path_str, cached_path)
                    return

            # Limit active workers to prevent resource exhaustion
            max_workers = 2  # Reduce from 3 to 2
            if len(self.folder_preview_tasks) >= max_workers:
                # Queue this folder for later
                self.waiting_folders.append((folder_path, list_item))
                return

            # Start a new worker to find a preview image
            worker = Worker(
                task_type="get_folder_preview", folder_to_scan=folder_path_str
            )
            worker.progress.connect(self.update_progress)
            worker.error.connect(self.handle_error)
            worker.folder_preview_image.connect(self.set_folder_thumbnail)
            worker.finished.connect(self.folder_preview_task_finished)

            # Store reference to worker with folder path
            self.folder_preview_tasks[folder_path_str] = worker
            worker.start()
        except Exception as e:
            self.log_message(f"Error requesting folder preview: {e}")

    @Slot(str, str)
    def set_folder_thumbnail(self, folder_path_str, image_path_str):
        """Sets the thumbnail for a folder in the subfolder list."""
        # Cache this preview for future use
        try:
            self.folder_preview_cache[folder_path_str] = image_path_str

            # Ensure the image file exists and is readable
            if not os.path.isfile(image_path_str) or not os.access(
                image_path_str, os.R_OK
            ):
                self.log_message(f"Thumbnail image not accessible: {image_path_str}")
                return

            # Find the corresponding item in the list
            found_item = False
            for i in range(
                self.subfolder_list_widget.count()
            ):  # Fixed: Added missing closing parenthesis
                try:
                    item = self.subfolder_list_widget.item(i)
                    if not item:  # Skip if item is None
                        continue

                    item_folder = item.data(Qt.ItemDataRole.UserRole)
                    if not item_folder:  # Skip if no folder data
                        continue

                    if str(item_folder) == folder_path_str:
                        found_item = True
                        try:
                            # Safely create and set thumbnail
                            reader = QImageReader(image_path_str)
                            reader.setScaledSize(QSize(64, 64))

                            if reader.canRead():
                                thumbnail = reader.read()
                                if not thumbnail.isNull():
                                    pixmap = QPixmap.fromImage(thumbnail)
                                    if not pixmap.isNull():
                                        item.setIcon(QIcon(pixmap))
                                    else:
                                        self.log_message(
                                            f"Created null pixmap for {Path(image_path_str).name}"
                                        )
                                else:
                                    self.log_message(
                                        f"Image read failed: {Path(image_path_str).name}: {reader.errorString()}"
                                    )
                            else:
                                self.log_message(
                                    f"Cannot read image: {Path(image_path_str).name}: {reader.errorString()}"
                                )
                        except Exception as thumbnail_error:
                            self.log_message(
                                f"Error creating thumbnail: {thumbnail_error}"
                            )
                        break
                except Exception as item_error:
                    self.log_message(f"Error processing list item: {item_error}")
                    continue

            if not found_item:
                self.log_message(
                    f"No matching folder item found for {Path(folder_path_str).name}"
                )
        except Exception as e:
            self.log_message(f"Error in set_folder_thumbnail: {e}")

    @Slot(QListWidgetItem, QListWidgetItem)  # previous, current
    def trigger_subfolder_preview(self, current, previous):
        """Starts scanning the currently focused subfolder for images."""
        if current:  # Check if current item is valid
            subfolder_path = current.data(Qt.ItemDataRole.UserRole)
            if subfolder_path and subfolder_path.is_dir():
                # Check if already previewing this folder or task running
                if (
                    subfolder_path == self.last_previewed_folder
                    and self.worker_thread
                    and self.current_task_type == "scan_subfolder_images"
                ):
                    self.log_message(f"Already scanning '{subfolder_path.name}'.")
                    return

                self.stop_worker_thread()  # Stop any previous task (scan or merge)
                self.clear_preview_area()  # Clear previous preview
                self.last_previewed_folder = subfolder_path
                self.log_message(f"Previewing folder: {subfolder_path.name}")
                self.image_path_label.setText(f"Scanning '{subfolder_path.name}'...")
                self.start_subfolder_scan(subfolder_path)

    def start_subfolder_scan(self, folder_path):
        """Initiates the background worker to scan a specific folder."""
        self.enable_ui(False)  # Disable UI during scan
        self.current_task_type = "scan_subfolder_images"
        self.worker_thread = Worker(
            task_type="scan_subfolder_images", folder_to_scan=str(folder_path)
        )
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.error.connect(self.handle_error)
        self.worker_thread.image_paths.connect(self.add_image_paths_to_list)
        self.worker_thread.finished.connect(self.task_finished)
        self.worker_thread.start()

    @Slot()
    def clear_preview_area(self):
        """Clears the image list and large preview display."""
        self.image_list_widget.clear()
        self.preview_label.clear()
        self.preview_label.setText("Image Preview")
        self.image_path_label.setText("Select subfolder to preview images")
        self.image_files_in_preview = []

    @Slot(list)
    def add_image_paths_to_list(self, paths):
        """Adds image paths from the worker to the image list with optimized thumbnail loading."""
        worker = self.sender()
        # Ensure signal is from the correct worker and task type
        if (
            worker != self.worker_thread
            or self.current_task_type != "scan_subfolder_images"
        ):
            return  # Ignore signals from old/wrong workers

        for image_path_str in paths:
            image_path = Path(image_path_str)
            item = QListWidgetItem(image_path.name)
            item.setData(
                Qt.ItemDataRole.UserRole, image_path_str
            )  # Store full path string

            # Use QImageReader for efficient thumbnail loading
            try:
                reader = QImageReader(image_path_str)
                # Set the scaled size before reading the image
                reader.setScaledSize(THUMBNAIL_SIZE)
                # Only load what's needed for the thumbnail
                thumbnail = reader.read()

                if not thumbnail.isNull():
                    item.setIcon(QIcon(QPixmap.fromImage(thumbnail)))
                else:
                    self.log_message(
                        f"Could not load thumbnail for {image_path.name}: {reader.errorString()}"
                    )
                    item.setIcon(QIcon.fromTheme("image-missing"))
            except Exception as e:
                self.log_message(f"Thumbnail error for {image_path.name}: {e}")
                item.setIcon(QIcon.fromTheme("image-missing"))

            self.image_list_widget.addItem(item)
            self.image_files_in_preview.append(image_path_str)  # Keep track

    @Slot()
    def show_large_preview(self):
        """Displays the selected image from the image_list_widget."""
        selected_items = self.image_list_widget.selectedItems()
        if not selected_items:
            # Clear preview if selection is cleared
            self.preview_label.clear()
            self.preview_label.setText("Image Preview")
            self.image_path_label.setText("Select an image from the list above")
            return

        item = selected_items[0]
        image_path_str = item.data(Qt.ItemDataRole.UserRole)
        if not image_path_str:
            return

        image_path = Path(image_path_str)
        if not image_path.is_file():
            self.log_message(f"Preview error: File not found - {image_path_str}")
            self.preview_label.setText("Error: File not found")
            self.image_path_label.setText("Error: File not found")
            return

        # Display filename or partial path in label
        self.image_path_label.setText(
            f"...{os.path.sep}{image_path.parent.name}{os.path.sep}{image_path.name}"
        )
        pixmap = QPixmap(image_path_str)

        if pixmap.isNull():
            self.log_message(f"Preview error: Could not load image - {image_path_str}")
            self.preview_label.setText(f"Cannot load\n{image_path.name}")
            return

        try:
            # Find the scroll area by looking upward through the parent hierarchy
            scroll_area = None
            parent = self.preview_label.parent()
            while parent:
                if isinstance(parent, QScrollArea):
                    scroll_area = parent
                    break
                parent = parent.parent()

            # Get available width - first try from scroll area if found
            available_width = PREVIEW_AREA_MIN_WIDTH  # Default fallback

            if scroll_area and scroll_area.viewport():
                available_width = scroll_area.viewport().width() - 20
            elif self.preview_label.width() > 50:
                available_width = self.preview_label.width() - 20

            # Ensure we have a reasonable width
            available_width = max(available_width, 300)

            # Scale the pixmap if needed
            if pixmap.width() > available_width:
                scaled_pixmap = pixmap.scaledToWidth(
                    available_width, Qt.TransformationMode.SmoothTransformation
                )
            else:
                scaled_pixmap = pixmap

            self.preview_label.setPixmap(scaled_pixmap)
        except Exception as e:
            self.log_message(f"Error scaling preview: {e}")
            self.preview_label.setText("Error displaying preview")

    @Slot()
    def update_merge_button_state(self):
        """Enable merge button only if >= 1 subfolder is checked."""
        checked_items = self.get_checked_subfolder_items()
        self.merge_button.setEnabled(
            len(checked_items) > 0 and self.current_root_folder is not None
        )

    def get_checked_subfolder_items(self):
        """Returns all checked subfolder items."""
        checked_items = []
        for index in range(self.subfolder_list_widget.count()):
            item = self.subfolder_list_widget.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                checked_items.append(item)
        return checked_items

    @Slot()
    def confirm_and_start_merge_to_new(self):
        """Confirms merge, determines target, creates it, and starts worker."""
        if not self.current_root_folder:
            return
        self.stop_worker_thread()  # Stop any running task

        # --- Get checked sources ---
        checked_items = self.get_checked_subfolder_items()
        source_folders = []
        source_names = []
        for item in checked_items:
            folder_path = item.data(Qt.ItemDataRole.UserRole)
            if folder_path and folder_path.is_dir():
                source_folders.append(folder_path)
                source_names.append(folder_path.name)
            else:
                QMessageBox.critical(
                    self,
                    "Merge Error",
                    f"Invalid source folder in selection: {item.text()}",
                )
                return  # Should not happen if list is populated correctly

        if not source_folders:
            QMessageBox.warning(
                self, "Merge Error", "No valid source subfolders checked."
            )
            return

        # --- Determine Target Name ---
        source_names.sort()  # Sort alphabetically
        first_source_name = source_names[0]

        # Check if the name already contains a merged suffix
        if "_merged" in first_source_name.lower():
            target_folder_name = f"{first_source_name}1"
        else:
            target_folder_name = f"{first_source_name}_merged"

        target_folder_path = self.current_root_folder / target_folder_name

        # --- Check if Target Conflicts with Sources ---
        if target_folder_path in source_folders:
            QMessageBox.critical(
                self,
                "Merge Conflict",
                f"The automatically determined target folder name '{target_folder_name}' "
                f"conflicts with one of the selected source folders. Please deselect "
                f"'{first_source_name}' or rename it before merging.",
            )
            return

        # --- Confirmation Dialog ---
        source_list_str = "\n - ".join(
            sorted([p.name for p in source_folders])
        )  # Show sorted names
        confirmation_message = (
            f"This will merge ALL content recursively from the following SOURCE subfolders:\n"
            f" - {source_list_str}\n\n"
            f"INTO a NEW target subfolder named:\n"
            f" '{target_folder_name}'\n"
            f"(This folder will be created inside '{self.current_root_folder.name}')\n\n"
            f"Name conflicts within '{target_folder_name}' will be resolved by renaming.\n"
            f"Empty source folders may be deleted after merging.\n\n"
            f"Proceed with merge?"
        )

        # Handle case where target folder *already* exists
        if target_folder_path.exists():
            confirmation_message = (
                f"The target folder '{target_folder_name}' already exists.\n\n"
                + confirmation_message
                + "\n\nFiles will be merged into the existing folder."
            )

        reply = QMessageBox.question(
            self,
            "Confirm Merge",
            confirmation_message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # --- Create Target Directory ---
            try:
                target_folder_path.mkdir(
                    parents=True, exist_ok=True
                )  # Create target dir
                self.log_message(f"Ensured target folder exists: {target_folder_path}")
            except OSError as e:
                self.handle_error(
                    f"Could not create target folder '{target_folder_name}': {e}"
                )
                return

            # --- Start Worker ---
            source_paths_str = [str(p) for p in source_folders]
            target_path_str = str(target_folder_path)
            self.start_merge_task(source_paths_str, target_path_str)

    def start_merge_task(self, source_paths_str, target_path_str):
        """Starts the background thread to merge folders."""
        self.log_message(f"Starting merge into '{Path(target_path_str).name}'...")
        self.enable_ui(False)

        self.current_task_type = "merge_subs"
        self.worker_thread = Worker(
            task_type="merge_subs",
            source_folder_paths=source_paths_str,
            target_folder_path=target_path_str,
        )
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.error.connect(self.handle_error)
        self.worker_thread.finished.connect(self.task_finished)
        self.worker_thread.start()

    def stop_worker_thread(self):
        """Stops the current worker thread if it's running."""
        if self.worker_thread and self.worker_thread.isRunning():
            task = self.current_task_type or "unknown task"
            self.log_message(f"Attempting to cancel {task}...")
            self.worker_thread.stop()
            if not self.worker_thread.wait(1500):  # Shorter wait
                self.log_message(
                    f"Warning: Worker thread ({task}) did not stop gracefully. Terminating."
                )
                self.worker_thread.terminate()
                self.worker_thread.wait()
            # Check if it was the expected worker before clearing
            if (
                self.worker_thread == self.sender() or not self.sender()
            ):  # Handle direct calls too
                self.worker_thread = None
                self.current_task_type = None
                # Avoid enabling UI if another task might be queued immediately
                # self.enable_ui(True)
                self.log_message(f"{task.capitalize()} stopped.")

    def closeEvent(self, event):
        """Ensure the worker thread is stopped when closing the window."""
        self.stop_worker_thread()

        # Also stop all folder preview tasks
        for worker in self.folder_preview_tasks.values():
            if worker and worker.isRunning():
                worker.stop()
                worker.wait(100)  # Brief wait

        self.folder_preview_tasks.clear()
        event.accept()


# --- Main Execution ---
if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = ImageFolderTool()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Critical error in application: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
