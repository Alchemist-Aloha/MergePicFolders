import sys
import os
import shutil
from pathlib import Path
import time  # For unique naming fallback
import re  # Add this to the imports at the top of the file
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
    ".heic"
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
    subfolders_found = Signal(list)  # Signal to emit found subdirectories

    # Use keyword arguments for flexibility
    def __init__(
        self,
        task_type,
        *,  # Make subsequent args keyword-only
        folder_to_scan=None,
        source_folder_paths=None,
        target_folder_path=None,
        root_folder_to_scan=None,  # Added for populate task
        parent=None,
    ):
        super().__init__(parent)
        self.task_type = task_type
        self.folder_to_scan = Path(folder_to_scan) if folder_to_scan else None
        self.root_folder_to_scan = Path(root_folder_to_scan) if root_folder_to_scan else None  # Store root folder
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
            elif self.task_type == "populate_subfolders" and self.root_folder_to_scan:  # Handle new task
                self._populate_subfolders(self.root_folder_to_scan)
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
                elif (
                    self.task_type == "populate_subfolders"
                    and not self.root_folder_to_scan  # Check for root folder
                ):
                    self.error.emit("Populate task started with no root folder provided.")
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
                self._success = False
            else:
                self.progress.emit(
                    f"Merge complete. Moved {moved_count} files. Processed {len(processed_sources)} sources, deleted {deleted_source_dirs} empty source folders."
                )
                self._success = True

        except Exception as e:
            self.error.emit(f"Error during merging process: {e}")
            self._success = False

    def _get_folder_preview_image(self, folder_path):
        """Finds the first image in a folder to use as a preview thumbnail."""
        if not folder_path.is_dir():
            self.error.emit(
                f"Cannot scan: '{folder_path.name}' is not a valid directory."
            )
            return

        try:
            # self.progress.emit(f"Finding preview image for '{folder_path.name}'...")

            for item in folder_path.glob("*"):
                if not self._is_running:
                    return
                if item.is_file() and item.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    try:
                        if os.path.getsize(str(item)) > 0:
                            self.folder_preview_image.emit(str(folder_path), str(item))
                            return
                    except (OSError, PermissionError) as e:
                        self.progress.emit(
                            f"Skipping inaccessible image: {item.name} - {e}"
                        )
                        continue

            max_depth = 2
            for depth in range(1, max_depth + 1):
                pattern = "/".join(["*"] * depth)
                for item in folder_path.glob(pattern):
                    if not self._is_running:
                        return
                    if (
                        item.is_file()
                        and item.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
                    ):
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

            self.progress.emit(f"No preview image found for '{folder_path.name}'")

        except Exception as e:
            self.error.emit(f"Error finding preview for '{folder_path.name}': {e}")

    def _populate_subfolders(self, root_folder_path):
        """Scans the root folder for immediate subdirectories."""
        if not root_folder_path.is_dir():
            self.error.emit(
                f"Cannot populate: '{root_folder_path.name}' is not a valid directory."
            )
            return

        try:
            self.progress.emit(f"Scanning '{root_folder_path.name}' for subfolders...")
            subdirs = []
            for item in root_folder_path.iterdir():
                if not self._is_running:
                    self.progress.emit("Subfolder scan cancelled.")
                    return
                if item.is_dir():
                    subdirs.append(item)

            if self._is_running:
                self.subfolders_found.emit(subdirs)
                self.progress.emit(f"Found {len(subdirs)} subfolders.")
        except Exception as e:
            self.error.emit(
                f"Error during subfolder scan of '{root_folder_path.name}': {e}"
            )
            raise


# --- Main Application Window ---
class ImageFolderTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Folder Tool")
        self.setGeometry(100, 100, 1300, 800)

        # Initialize state variables (same as before)
        self.current_root_folder = None
        self.image_files_in_preview = []
        self.worker_thread = None
        self.current_task_type = None
        self.last_previewed_folder = None
        self.folder_preview_tasks = {}
        self.folder_preview_cache = {}
        self.waiting_folders = []
        self._checked_folder_names_cache = set()
        self.last_merged_sources = []
        self.last_merged_target = None

        # Create the modern UI
        self.setup_ui()
        
        # Apply the modern styling
        self.apply_modern_style()
        
        # Set natural sort as the default
        self.use_natural_sort = True

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Modern header area
        header = QWidget()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        app_title = QLabel("Image Folder Tool")
        app_title.setObjectName("heading")
        app_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        
        self.select_folder_button = QPushButton("Select Folder")
        self.select_folder_button.setObjectName("select_button")
        self.select_folder_button.setIcon(QIcon.fromTheme("folder-open"))
        self.select_folder_button.setIconSize(QSize(24, 24))
        self.select_folder_button.setFixedHeight(40)
        self.select_folder_button.clicked.connect(self.select_root_folder)
        
        header_layout.addWidget(app_title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.select_folder_button)
        
        main_layout.addWidget(header)
        
        # Path display with modern look
        path_frame = QFrame()
        path_frame.setObjectName("panel")
        path_layout = QHBoxLayout(path_frame)
        
        folder_icon = QLabel()
        folder_icon_pixmap = QIcon.fromTheme("folder").pixmap(QSize(24, 24))
        folder_icon.setPixmap(folder_icon_pixmap)
        
        self.folder_label = QLabel("No folder selected.")
        self.folder_label.setFont(QFont("Segoe UI", 10))
        self.folder_label.setWordWrap(True)
        
        path_layout.addWidget(folder_icon)
        path_layout.addWidget(self.folder_label, 1)
        
        main_layout.addWidget(path_frame)

        # Main content splitter - now with THREE panels horizontally
        splitter_main = QSplitter(Qt.Orientation.Horizontal)
        splitter_main.setHandleWidth(2)
        splitter_main.setChildrenCollapsible(False)

        # ==== LEFT PANEL - Subfolder selection ====
        left_panel = QFrame()
        left_panel.setObjectName("panel")
        left_layout = QVBoxLayout(left_panel)
        
        # Header for subfolder section
        subfolder_header = QWidget()
        subfolder_header_layout = QHBoxLayout(subfolder_header)
        subfolder_header_layout.setContentsMargins(0, 0, 0, 10)
        
        subfolder_title = QLabel("Subfolders")
        subfolder_title.setObjectName("heading")
        subfolder_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        
        subfolder_header_layout.addWidget(subfolder_title)
        left_layout.addWidget(subfolder_header)
        
        # Controls for subfolder list
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 5)
        
        self.uncheck_all_button = QPushButton("Uncheck All")
        self.uncheck_all_button.setIcon(QIcon.fromTheme("edit-clear"))
        self.uncheck_all_button.clicked.connect(self.uncheck_all_subfolders)
        
        self.sort_toggle_button = QPushButton("Natural Sort: On")
        self.sort_toggle_button.setIcon(QIcon.fromTheme("view-sort"))
        self.sort_toggle_button.setCheckable(True)
        self.sort_toggle_button.setChecked(True)
        self.sort_toggle_button.clicked.connect(self.toggle_folder_sort)
        
        controls_layout.addWidget(self.uncheck_all_button)
        controls_layout.addWidget(self.sort_toggle_button)
        controls_layout.addStretch(1)
        
        left_layout.addWidget(controls_widget)
        
        # Modern subfolder list - INCREASED ICON SIZE
        self.subfolder_list_widget = QListWidget()
        self.subfolder_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.subfolder_list_widget.currentItemChanged.connect(self.trigger_subfolder_preview)
        self.subfolder_list_widget.itemChanged.connect(self.update_merge_button_state)
        self.subfolder_list_widget.setIconSize(QSize(96, 96))  # Increased from 64x64
        
        left_layout.addWidget(self.subfolder_list_widget, 1)
        
        # Merge button - make it stand out
        self.merge_button = QPushButton("Merge Selected Folders")
        self.merge_button.setObjectName("merge_button")
        self.merge_button.setIcon(QIcon.fromTheme("document-save-as"))
        self.merge_button.setIconSize(QSize(20, 20))
        self.merge_button.setFixedHeight(48)
        self.merge_button.clicked.connect(self.confirm_and_start_merge_to_new)
        self.merge_button.setEnabled(False)
        left_layout.addWidget(self.merge_button)

        # ==== MIDDLE PANEL - Folder contents ====
        middle_panel = QFrame()
        middle_panel.setObjectName("panel")
        middle_layout = QVBoxLayout(middle_panel)
        
        # Image list section
        image_list_title = QLabel("Folder Contents")
        image_list_title.setObjectName("heading")
        image_list_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        middle_layout.addWidget(image_list_title)
        
        # Modern thumbnail view for images
        self.image_list_widget = QListWidget()
        self.image_list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.image_list_widget.setIconSize(THUMBNAIL_SIZE)
        self.image_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.image_list_widget.setSpacing(8)
        self.image_list_widget.setWordWrap(True)
        self.image_list_widget.setUniformItemSizes(True)
        self.image_list_widget.itemSelectionChanged.connect(self.show_large_preview)
        middle_layout.addWidget(self.image_list_widget, 1)

        # ==== RIGHT PANEL - Preview ====
        right_panel = QFrame()
        right_panel.setObjectName("panel")
        right_layout = QVBoxLayout(right_panel)
        
        # Preview section
        preview_title = QLabel("Preview")
        preview_title.setObjectName("heading")
        preview_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        right_layout.addWidget(preview_title)
        
        self.image_path_label = QLabel("Select an image to preview")
        self.image_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_path_label.setWordWrap(True)
        self.image_path_label.setFont(QFont("Segoe UI", 9))
        right_layout.addWidget(self.image_path_label)
        
        # Modern preview area
        preview_frame = QFrame()
        preview_frame.setObjectName("panel")
        preview_layout = QVBoxLayout(preview_frame)
        
        self.preview_label = QLabel("Image Preview")
        self.preview_label.setObjectName("preview_label")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(PREVIEW_AREA_MIN_WIDTH, 250)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.preview_label)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        preview_layout.addWidget(scroll_area, 1)
        
        right_layout.addWidget(preview_frame, 1)
        
        # Add all three panels to splitter
        splitter_main.addWidget(left_panel)
        splitter_main.addWidget(middle_panel)
        splitter_main.addWidget(right_panel)
        
        # Set initial sizes for the three panels - distribute proportionally
        splitter_main.setSizes([300, 400, 300])  # Left, Middle, Right
        
        main_layout.addWidget(splitter_main, 1)
        
        # Modern log area
        log_title = QLabel("Activity Log")
        log_title.setObjectName("heading")
        log_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        main_layout.addWidget(log_title)
        
        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("log_edit")
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        self.log_edit.setFixedHeight(100)
        main_layout.addWidget(self.log_edit)

    def apply_modern_style(self):
        # Modern color palette
        colors = {
            "primary": "#50FA7B",
            "primary_hover": "#2bbd50",
            "secondary": "#FF79C6",
            "secondary_hover": "#D44C9A",
            "background": "#282A36",
            "card": "#44475A",
            "text": "#F8F8F2",
            "text_light": "#F8F8F2",
            "border": "#e0e0e0",
            "danger": "#FF5555"
        }
        
        self.setStyleSheet(f"""
            /* Global app styling */
            QMainWindow, QDialog {{
                background-color: {colors["background"]};
                color: {colors["text"]};
            }}
            
            /* Buttons */
            QPushButton {{
                background-color: {colors["primary"]};
                color: #F8F8F2;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            
            QPushButton:hover {{
                background-color: {colors["primary_hover"]};
            }}
            
            QPushButton:pressed {{
                background-color: {colors["primary_hover"]};
                padding: 7px 11px 5px 13px;
            }}
            
            QPushButton:disabled {{
                background-color: #bdc3c7;
                color: #95a5a6;
            }}
            
            /* Special buttons (like merge) */
            QPushButton#merge_button {{
                background-color: {colors["secondary"]};
                color: #F8F8F2;
            }}
            
            QPushButton#merge_button:hover {{
                background-color: {colors["secondary_hover"]};
            }}
            
            /* List widgets */
            QListWidget {{
                background-color: {colors["card"]};
                border-radius: 6px;
                border: 1px solid {colors["border"]};
                padding: 2px;
            }}
            
            QListWidget::item {{
                border-radius: 2px;
                padding: 4px;
                margin: 2px;
            }}
            
            QListWidget::item:selected {{
                background-color: {colors["primary"]};
                color: #F8F8F2;
            }}
            
            QListWidget::item:hover:!selected {{
                background-color: #ecf0f1;
            }}
            
            /* Checkbox style in list */
            QListWidget::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 2px solid {colors["primary"]};
            }}
            
            QListWidget::indicator:checked {{
                background-color: {colors["primary"]};
                image: url(checkmark.png);
            }}
            
            /* Panels and group boxes */
            QGroupBox, QFrame#panel {{
                background-color: {colors["card"]};
                border-radius: 8px;
                border: 1px solid {colors["border"]};
                margin-top: 8px;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: {colors["primary"]};
            }}
            
            /* Scrollbars */
            QScrollBar:vertical {{
                border: none;
                background-color: {colors["background"]};
                width: 8px;
                margin: 0px;
            }}
            
            QScrollBar::handle:vertical {{
                background-color: #bdc3c7;
                border-radius: 4px;
                min-height: 20px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background-color: #95a5a6;
            }}
            
            /* Labels */
            QLabel#heading {{
                font-size: 12pt;
                font-weight: bold;
                color: {colors["primary"]};
            }}
            
            /* Preview area */
            QLabel#preview_label {{
                background-color: {colors["background"]};
                border-radius: 6px;
                color: white;
            }}
            
            /* Log area */
            QTextEdit#log_edit {{
                background-color: #2c3e50;
                color: #ecf0f1;
                border-radius: 6px;
                font-family: "Consolas", monospace;
            }}
        """)

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
        if self.worker_thread:
            self.enable_ui(True)
            self.worker_thread = None
            self.current_task_type = None

    @Slot(str, bool)
    def task_finished(self, task_type, success):
        self.log_message(
            f"Task '{task_type}' finished {'successfully' if success else 'with errors/cancellation'}."
        )
        original_worker = self.sender()
        if self.worker_thread == original_worker:
            self.worker_thread = None
            self.current_task_type = None
            # Enable UI only after potential list update

        if task_type == "merge_subs":
            self.log_message("Updating subfolder list after merge...")
            self.clear_preview_area()  # Still clear the image preview

            # --- Temporarily disconnect signal ---
            try:
                self.subfolder_list_widget.currentItemChanged.disconnect(
                    self.trigger_subfolder_preview
                )
            except RuntimeError:  # Already disconnected or never connected
                pass
            # ------------------------------------

            if success and self.last_merged_target and self.last_merged_sources:
                # Remove source items
                items_to_remove = []
                source_paths_set = set(self.last_merged_sources)
                for index in range(self.subfolder_list_widget.count()):
                    item = self.subfolder_list_widget.item(index)
                    if item:
                        item_data = item.data(Qt.ItemDataRole.UserRole)
                        if item_data in source_paths_set:
                            items_to_remove.append(item)

                for item in items_to_remove:
                    row = self.subfolder_list_widget.row(item)
                    self.subfolder_list_widget.takeItem(row)
                    # Also remove from thumbnail cache if present
                    folder_path_str = str(item.data(Qt.ItemDataRole.UserRole))
                    if folder_path_str in self.folder_preview_cache:
                        del self.folder_preview_cache[folder_path_str]
                    if folder_path_str in self.folder_preview_tasks:
                        # Stop any preview task for the removed folder
                        preview_worker = self.folder_preview_tasks.pop(folder_path_str)
                        if preview_worker and preview_worker.isRunning():
                            preview_worker.stop()

                # Add target item (if it's directly under the root)
                if self.last_merged_target.parent == self.current_root_folder:
                    target_item = QListWidgetItem(self.last_merged_target.name)
                    target_item.setData(
                        Qt.ItemDataRole.UserRole, self.last_merged_target
                    )
                    target_item.setIcon(QIcon.fromTheme("folder"))
                    target_item.setFlags(
                        target_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    target_item.setCheckState(Qt.CheckState.Unchecked)
                    self.subfolder_list_widget.addItem(target_item)
                    # Optionally request its thumbnail immediately
                    self.request_folder_preview(self.last_merged_target, target_item)

                # Sort the list according to current sort mode instead of default
                self.sort_subfolder_list()  # This modifies the list heavily

                self.log_message("Subfolder list updated.")
            elif not success:
                self.log_message(
                    "Merge failed or cancelled. List not updated, consider refreshing manually if needed."
                )
            else:
                self.log_message(
                    "Merge completed but source/target info missing. Refreshing list fully."
                )
                self.populate_subfolder_list()  # Fallback to full refresh

            # Clear the stored paths
            self.last_merged_sources = []
            self.last_merged_target = None
            self.update_merge_button_state()  # Update button state

            # --- Reconnect signal ---
            self.subfolder_list_widget.currentItemChanged.connect(
                self.trigger_subfolder_preview
            )
            # ------------------------

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
        elif task_type == "populate_subfolders":
            if not success:
                self.log_message("Failed to populate subfolders.")

        # Re-enable UI at the very end, after potential list updates
        if self.worker_thread != original_worker:  # Check again in case a new task started
            self.enable_ui(True)

        # Final UI enable check if no worker is running
        if self.worker_thread is None:
            self.enable_ui(True)

    @Slot(bool)
    def enable_ui(self, enabled):
        self.select_folder_button.setEnabled(enabled)
        self.subfolder_list_widget.setEnabled(enabled)
        if enabled and self.current_root_folder:
            self.update_merge_button_state()
        else:
            self.merge_button.setEnabled(False)
        self.image_list_widget.setEnabled(enabled)
        self.subfolder_list_widget.setDisabled(not enabled)

    @Slot()
    def select_root_folder(self):
        self.stop_worker_thread()

        folder = QFileDialog.getExistingDirectory(
            self, "Select Root Folder Containing Subfolders"
        )
        if folder:
            self.current_root_folder = Path(folder)
            self.folder_label.setText(f"Selected: {self.current_root_folder}")
            self.log_message(f"Root folder selected: {self.current_root_folder}")

            self.subfolder_list_widget.clear()
            self.clear_preview_area()
            self.merge_button.setEnabled(False)
            self.last_previewed_folder = None
            self.folder_preview_cache.clear()
            self.folder_preview_tasks.clear()
            self.waiting_folders.clear()
            self._checked_folder_names_cache.clear()

            self.populate_subfolder_list()

    @Slot()
    def populate_subfolder_list(self):
        if not self.current_root_folder or not self.current_root_folder.is_dir():
            self.log_message("No valid root folder selected to populate.")
            return

        self.stop_worker_thread()

        self._checked_folder_names_cache = set()
        for index in range(self.subfolder_list_widget.count()):
            item = self.subfolder_list_widget.item(index)
            if item and item.checkState() == Qt.CheckState.Checked:
                self._checked_folder_names_cache.add(item.text())

        self.subfolder_list_widget.clear()
        self.log_message("Starting subfolder population task...")
        self.enable_ui(False)

        for worker in self.folder_preview_tasks.values():
            if worker and worker.isRunning():
                worker.stop()
        self.folder_preview_tasks.clear()
        self.waiting_folders.clear()

        self.current_task_type = "populate_subfolders"
        self.worker_thread = Worker(
            task_type="populate_subfolders",
            root_folder_to_scan=str(self.current_root_folder),
        )
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.error.connect(self.handle_error)
        self.worker_thread.subfolders_found.connect(self._handle_subfolders_found)
        self.worker_thread.finished.connect(self.task_finished)
        self.worker_thread.start()

    @Slot(list)
    def _handle_subfolders_found(self, subdirs):
        self.log_message(f"Received {len(subdirs)} subfolders from worker.")

        cached_thumbnails_by_name = {}
        for folder_path_str, image_path in self.folder_preview_cache.items():
            folder_name = Path(folder_path_str).name
            cached_thumbnails_by_name[folder_name] = image_path

        if not subdirs:
            self.log_message("No subfolders found by worker.")
            return

        count = 0
        folders_needing_thumbnails = []
        try:
            # Sort subdirs based on current sort mode
            if self.use_natural_sort:
                subdirs.sort(key=lambda p: self._natural_sort_key(p.name))
            else:
                subdirs.sort(key=lambda p: p.name)
                
            for subdir in subdirs:
                item = QListWidgetItem(subdir.name)
                item.setData(Qt.ItemDataRole.UserRole, subdir)
                item.setIcon(QIcon.fromTheme("folder"))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if subdir.name in self._checked_folder_names_cache:
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
                self.subfolder_list_widget.addItem(item)
                count += 1

                folder_path_str = str(subdir)
                if subdir.name in cached_thumbnails_by_name:
                    cached_image_path = cached_thumbnails_by_name[subdir.name]
                    if os.path.isfile(cached_image_path) and os.access(
                        cached_image_path, os.R_OK
                    ):
                        self.folder_preview_cache[folder_path_str] = cached_image_path
                        self.set_folder_thumbnail(folder_path_str, cached_image_path)
                    else:
                        folders_needing_thumbnails.append((subdir, item))
                        if folder_path_str in self.folder_preview_cache:
                            del self.folder_preview_cache[folder_path_str]
                else:
                    folders_needing_thumbnails.append((subdir, item))

            max_initial_workers = 2
            active_workers = 0

            for i in range(min(max_initial_workers, len(folders_needing_thumbnails))):
                folder_path, item = folders_needing_thumbnails[i]
                self.request_folder_preview(folder_path, item)
                active_workers += 1

            for i in range(max_initial_workers, len(folders_needing_thumbnails)):
                folder_path, item = folders_needing_thumbnails[i]
                self.waiting_folders.append((folder_path, item))

            self.log_message(
                f"Populated list with {count} subfolders. Requesting thumbnails..."
            )

        except Exception as e:
            self.handle_error(f"Error populating subfolder list widget: {e}")
        finally:
            self.update_merge_button_state()

    @Slot(str, bool)
    def folder_preview_task_finished(self, task_type, success):
        if task_type != "get_folder_preview":
            return

        worker = self.sender()

        for folder_path, w in list(self.folder_preview_tasks.items()):
            if w == worker:
                del self.folder_preview_tasks[folder_path]
                break

        if self.waiting_folders:
            next_folder, next_item = self.waiting_folders.pop(0)
            self.request_folder_preview(next_folder, next_item)

    def request_folder_preview(self, folder_path, list_item):
        try:
            if not folder_path or not list_item or not folder_path.is_dir():
                return

            folder_path_str = str(folder_path)
            if folder_path_str in self.folder_preview_cache:
                cached_path = self.folder_preview_cache[folder_path_str]
                if Path(cached_path).exists() and os.access(cached_path, os.R_OK):
                    self.set_folder_thumbnail(folder_path_str, cached_path)
                    return

            if folder_path_str in self.folder_preview_tasks:
                # Skip if a preview task is already running for this folder
                return
            max_workers = 2
            if len(self.folder_preview_tasks) >= max_workers:
                self.waiting_folders.append((folder_path, list_item))
                return

            worker = Worker(
                task_type="get_folder_preview", folder_to_scan=folder_path_str
            )
            worker.progress.connect(self.update_progress)
            worker.error.connect(self.handle_error)
            worker.folder_preview_image.connect(self.set_folder_thumbnail)
            worker.finished.connect(self.folder_preview_task_finished)

            self.folder_preview_tasks[folder_path_str] = worker
            worker.start()
        except Exception as e:
            self.log_message(f"Error requesting folder preview: {e}")

    @Slot(str, str)
    def set_folder_thumbnail(self, folder_path_str, image_path_str):
        try:
            self.folder_preview_cache[folder_path_str] = image_path_str

            if not os.path.isfile(image_path_str) or not os.access(
                image_path_str, os.R_OK
            ):
                self.log_message(f"Thumbnail image not accessible: {image_path_str}")
                return

            found_item = False
            for i in range(self.subfolder_list_widget.count()):
                try:
                    item = self.subfolder_list_widget.item(i)
                    if not item:
                        continue

                    item_folder = item.data(Qt.ItemDataRole.UserRole)
                    if not item_folder:
                        continue

                    if str(item_folder) == folder_path_str:
                        found_item = True
                        try:
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

    @Slot(QListWidgetItem, QListWidgetItem)
    def trigger_subfolder_preview(self, current, previous):
        if current:
            subfolder_path = current.data(Qt.ItemDataRole.UserRole)
            if subfolder_path and subfolder_path.is_dir():
                if (
                    subfolder_path == self.last_previewed_folder
                    and self.worker_thread
                    and self.current_task_type == "scan_subfolder_images"
                ):
                    self.log_message(f"Already scanning '{subfolder_path.name}'.")
                    return

                self.stop_worker_thread()
                self.clear_preview_area()
                self.last_previewed_folder = subfolder_path
                self.log_message(f"Previewing folder: {subfolder_path.name}")
                self.image_path_label.setText(f"Scanning '{subfolder_path.name}'...")
                self.start_subfolder_scan(subfolder_path)

    def start_subfolder_scan(self, folder_path):
        self.enable_ui(False)
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
        self.image_list_widget.clear()
        self.preview_label.clear()
        self.preview_label.setText("Image Preview")
        self.image_path_label.setText("Select subfolder to preview images")
        self.image_files_in_preview = []

    @Slot(list)
    def add_image_paths_to_list(self, paths):
        worker = self.sender()
        if (
            worker != self.worker_thread
            or self.current_task_type != "scan_subfolder_images"
        ):
            return

        for image_path_str in paths:
            image_path = Path(image_path_str)
            item = QListWidgetItem(image_path.name)
            item.setData(Qt.ItemDataRole.UserRole, image_path_str)

            try:
                reader = QImageReader(image_path_str)
                reader.setScaledSize(THUMBNAIL_SIZE)
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
            self.image_files_in_preview.append(image_path_str)

    @Slot()
    def show_large_preview(self):
        selected_items = self.image_list_widget.selectedItems()
        if not selected_items:
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

        self.image_path_label.setText(
            f"...{os.path.sep}{image_path.parent.name}{os.path.sep}{image_path.name}"
        )
        pixmap = QPixmap(image_path_str)

        if pixmap.isNull():
            self.log_message(f"Preview error: Could not load image - {image_path_str}")
            self.preview_label.setText(f"Cannot load\n{image_path.name}")
            return

        try:
            scroll_area = None
            parent = self.preview_label.parent()
            while parent:
                if isinstance(parent, QScrollArea):
                    scroll_area = parent
                    break
                parent = parent.parent()

            available_width = PREVIEW_AREA_MIN_WIDTH

            if scroll_area and scroll_area.viewport():
                available_width = scroll_area.viewport().width() - 20
            elif self.preview_label.width() > 50:
                available_width = self.preview_label.width() - 20

            available_width = max(available_width, 300)

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
        checked_items = self.get_checked_subfolder_items()
        self.merge_button.setEnabled(
            len(checked_items) > 0 and self.current_root_folder is not None
        )

    def get_checked_subfolder_items(self):
        checked_items = []
        for index in range(self.subfolder_list_widget.count()):
            item = self.subfolder_list_widget.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                checked_items.append(item)
        return checked_items

    @Slot()
    def confirm_and_start_merge_to_new(self):
        if not self.current_root_folder:
            return
        self.stop_worker_thread()

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
                return

        if not source_folders:
            QMessageBox.warning(
                self, "Merge Error", "No valid source subfolders checked."
            )
            return

        source_names.sort()
        first_source_name = source_names[0]

        if "_merged" in first_source_name.lower():
            target_folder_name = f"{first_source_name}1"
        else:
            target_folder_name = f"{first_source_name}_merged"

        target_folder_path = self.current_root_folder / target_folder_name

        if target_folder_path in source_folders:
            QMessageBox.critical(
                self,
                "Merge Conflict",
                f"The automatically determined target folder name '{target_folder_name}' "
                f"conflicts with one of the selected source folders. Please deselect "
                f"'{first_source_name}' or rename it before merging.",
            )
            return

        source_list_str = "\n - ".join(sorted([p.name for p in source_folders]))
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
            try:
                target_folder_path.mkdir(parents=True, exist_ok=True)
                self.log_message(f"Ensured target folder exists: {target_folder_path}")
            except OSError as e:
                self.handle_error(
                    f"Could not create target folder '{target_folder_name}': {e}"
                )
                return

            # Store paths before starting task
            self.last_merged_sources = list(source_folders)  # Store a copy
            self.last_merged_target = target_folder_path

            source_paths_str = [str(p) for p in source_folders]
            target_path_str = str(target_folder_path)
            self.start_merge_task(source_paths_str, target_path_str)

    def start_merge_task(self, source_paths_str, target_path_str):
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
        worker_to_stop = self.worker_thread
        if worker_to_stop and worker_to_stop.isRunning():
            task = self.current_task_type or "unknown task"
            self.log_message(f"Attempting to cancel {task}...")
            worker_to_stop.stop()
            
            # Wait longer for thread to finish naturally
            if not worker_to_stop.wait(2000):  # Increase timeout to 2 seconds
                self.log_message(f"Warning: Worker thread ({task}) did not stop gracefully. Terminating.")
                worker_to_stop.terminate()
                # Always wait again after terminate()
                worker_to_stop.wait()

            if self.worker_thread == worker_to_stop:
                self.worker_thread = None
                self.current_task_type = None
                self.enable_ui(True)
                self.log_message(f"{task.capitalize()} stopped.")
            else:
                self.log_message(f"Stopped an older worker for task {task}.")

    @Slot()
    def uncheck_all_subfolders(self):
        """Uncheck all items in the subfolder list."""
        for index in range(self.subfolder_list_widget.count()):
            item = self.subfolder_list_widget.item(index)
            if item and item.checkState() == Qt.CheckState.Checked:
                item.setCheckState(Qt.CheckState.Unchecked)
        
        # Clear the checked names cache
        self._checked_folder_names_cache.clear()
        self.log_message("All folders unchecked.")
        self.update_merge_button_state()  # Update button state after changes

    @Slot()
    def toggle_folder_sort(self):
        """Toggle between natural and alphabetical sorting."""
        self.use_natural_sort = self.sort_toggle_button.isChecked()
        self.sort_toggle_button.setText(f"Natural Sort: {'On' if self.use_natural_sort else 'Off'}")
        self.log_message(f"Sorting mode: {'Natural' if self.use_natural_sort else 'Alphabetical'}")
        self.sort_subfolder_list()
    
    def sort_subfolder_list(self):
        """Sort the subfolder list based on the current sort mode."""
        # Store the current selection and checked state
        current_item = self.subfolder_list_widget.currentItem()
        current_path = current_item.data(Qt.ItemDataRole.UserRole) if current_item else None
        
        checked_items = {}
        for index in range(self.subfolder_list_widget.count()):
            item = self.subfolder_list_widget.item(index)
            if item:
                folder_path = item.data(Qt.ItemDataRole.UserRole)
                checked_items[str(folder_path)] = item.checkState() == Qt.CheckState.Checked
        
        # Get all items
        items = []
        for index in range(self.subfolder_list_widget.count()):
            item = self.subfolder_list_widget.takeItem(0)  # Always take from index 0
            if item:
                items.append(item)
        
        # Sort items
        if self.use_natural_sort:
            # Natural sort that handles numbers in folder names
            items.sort(key=lambda x: self._natural_sort_key(x.text()))
        else:
            # Regular alphabetical sort
            items.sort(key=lambda x: x.text().lower())
        
        # Re-add items in sorted order
        for item in items:
            self.subfolder_list_widget.addItem(item)
            # Restore checked state
            folder_path = item.data(Qt.ItemDataRole.UserRole)
            if str(folder_path) in checked_items and checked_items[str(folder_path)]:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
        
        # Restore current selection only if we had one
        if current_path:
            for index in range(self.subfolder_list_widget.count()):
                item = self.subfolder_list_widget.item(index)
                if item and item.data(Qt.ItemDataRole.UserRole) == current_path:
                    self.subfolder_list_widget.setCurrentItem(item)
                    break
    
    def _natural_sort_key(self, text):
        """
        Natural sort key function that handles numbers within text.
        For example: "folder10" will come after "folder2" in a natural sort.
        """
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

    def closeEvent(self, event):
        # First stop the main worker
        self.stop_worker_thread()

        # Then stop all preview tasks with proper logging
        active_preview_tasks = list(self.folder_preview_tasks.items())
        for folder_path, worker in active_preview_tasks:
            if worker and worker.isRunning():
                self.log_message(f"Stopping preview task for {Path(folder_path).name}...")
                worker.stop()
                # Wait longer during shutdown
                if not worker.wait(500):  # 500ms per thread
                    worker.terminate()
                    worker.wait()
                self.folder_preview_tasks.pop(folder_path, None)

        # Clear all remaining tasks
        self.folder_preview_tasks.clear()
        self.waiting_folders.clear()
        
        # Log application shutdown
        self.log_message("Application shutting down")
        event.accept()


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
