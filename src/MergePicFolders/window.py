import os
import time
from pathlib import Path
import re
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
from PySide6.QtCore import Qt, QSize, Slot
from .worker import Worker  # Assuming you have a Worker class defined in worker.py
# --- Configuration ---
THUMBNAIL_SIZE = QSize(128, 128)
PREVIEW_AREA_MIN_WIDTH = 400
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
            
            /* Checkbox style in list - INCREASED SIZE */
            QListWidget::indicator {{
                width: 48px;
                height: 48px;
                border-radius: 32px;
                border: 3px solid {colors["primary"]};
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
        '''
        Log a message to the activity log area.
        
        Args:
            message (str): The message to log. 
            
        This method appends the message to the log area with a timestamp.
        It also ensures that the log area scrolls to the bottom to show the latest message.'''
        timestamp = time.strftime("%H:%M:%S")
        self.log_edit.append(f"[{timestamp}] {message}")
        self.log_edit.verticalScrollBar().setValue(
            self.log_edit.verticalScrollBar().maximum()
        )
        QApplication.processEvents()

    @Slot(str)
    def update_progress(self, message):
        '''
        Update the progress message in the log area.
        
        Args:
            message (str): The progress message to log.

        '''
        self.log_message(f"PROGRESS: {message}")

    @Slot(str)
    def handle_error(self, error_message):
        '''
        Handle errors during worker tasks.
        
        Args:
            error_message (str): The error message to log.
            
        This method logs the error message and shows a critical error dialog to the user.
        It also stops the current worker thread if it exists.
        '''
        self.log_message(f"ERROR: {error_message}")
        QMessageBox.critical(self, "Error", error_message)
        if self.worker_thread:
            self.enable_ui(True)
            self.worker_thread = None
            self.current_task_type = None

    @Slot(str, bool)
    def task_finished(self, task_type, success):
        '''
        Handle the completion of a worker task.
        Args:
            task_type (str): The type of task that finished.
            success (bool): Whether the task completed successfully or not.
        This method logs the task completion message and updates the UI accordingly.
        It also handles specific tasks like merging subfolders and scanning images.
        '''
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
        '''
        Enable or disable the UI elements based on the provided flag.
        Args:
            enabled (bool): True to enable the UI, False to disable it.
        This method enables or disables the select folder button, subfolder list,   
        image list, and merge button based on the provided flag.
        '''
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
        '''
        Open a file dialog to select the root folder containing subfolders.
        This method stops any running worker thread, clears the preview area,
        and resets the state variables before allowing the user to select a new folder.
        '''
        
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
        '''
        Populate the subfolder list widget with subfolders from the selected root folder.
        This method stops any running worker thread, clears the preview area,
        and starts a new worker thread to scan for subfolders.
        It also handles the caching of folder thumbnails and manages the UI state.
        '''
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
        '''
        Handle the subfolders found by the worker thread.
        Args:
            subdirs (list): List of subdirectories found by the worker.
        This method populates the subfolder list widget with the found subdirectories,
        sets their icons, and manages the thumbnail caching.
        It also handles the sorting of the subfolders based on the current sort mode.
        '''
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
        """
        Handle the completion of a folder preview generation task.
        
        This slot is connected to the 'finished' signal of Worker objects created for folder preview
        tasks. When a folder preview task completes, this method removes it from the tracking
        dictionary and starts the next waiting task from the queue if available.
        
        Args:
            task_type (str): The type of task that finished, should be "get_folder_preview".
            success (bool): Whether the task completed successfully or not.
            
        Note:
            This method is automatically called by the Qt signal-slot system when a Worker
            object emits its 'finished' signal. It identifies which worker emitted the signal
            using self.sender() and manages the task queue accordingly.
            
        Side effects:
            - Removes the completed task from self.folder_preview_tasks
            - May start a new folder preview task from self.waiting_folders queue
        """
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
        """
        Request a thumbnail preview generation for a specific folder.
        
        This method manages the creation and execution of worker threads that generate
        thumbnail previews for folders. It implements a throttling mechanism to limit
        the number of concurrent preview tasks and maintains a queue of waiting folders.
        
        If a preview for the folder already exists in the cache, it uses the cached preview
        instead of starting a new task. Otherwise, it either starts a new worker thread or
        adds the folder to the waiting queue if the maximum number of concurrent workers
        has been reached.
        
        Args:
            folder_path (Path): Path object representing the folder to generate a preview for
            list_item (QListWidgetItem): The list widget item associated with this folder,
                                         which will display the thumbnail when ready
                                         
        Side effects:
            - May add entries to self.folder_preview_tasks dictionary
            - May add entries to self.waiting_folders list
            - May start a Worker thread to generate the preview
            - May update the icon of the provided list_item if a cached preview exists
            
        Raises:
            Various exceptions may be caught and logged, but not propagated
        """
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
        """
        Set the thumbnail for a folder in the subfolder list widget.
        
        This method updates the icon of a list widget item to display a thumbnail
        image representing the folder's contents. It handles various edge cases and
        error conditions when loading or displaying thumbnails.
        
        Args:
            folder_path_str (str): The path of the folder for which to set the thumbnail
            image_path_str (str): The path of the thumbnail image to set
            
        Side effects:
            - Updates the folder_preview_cache dictionary
            - Sets the icon of the corresponding list widget item
            - Logs any errors encountered during thumbnail loading or setting
        """
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
        '''
        Triggered when the user selects a subfolder from the list.
        This method checks if the selected item is a valid subfolder and starts
        a scan for images in that subfolder. It also handles the case where
        the user selects a different subfolder while a scan is already in progress.
        Args:
            current (QListWidgetItem): The currently selected item in the subfolder list.
            previous (QListWidgetItem): The previously selected item in the subfolder list.
        This method stops any running worker thread, clears the preview area,
        and starts a new worker thread to scan for images in the selected subfolder.
        '''
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
        '''
        Start a scan for images in the selected subfolder.
        Args:
            folder_path (Path): The path of the subfolder to scan for images.
        This method stops any running worker thread, clears the preview area,
        and starts a new worker thread to scan for images in the selected subfolder.
        It also updates the UI state to indicate that a scan is in progress.
        '''
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
        '''
        Clear the image preview area and reset the state variables.
        This method clears the image list widget, resets the preview label,
        and updates the image path label to indicate that no image is selected.
        It also clears the list of image files in the preview area.
        '''
        self.image_list_widget.clear()
        self.preview_label.clear()
        self.preview_label.setText("Image Preview")
        self.image_path_label.setText("Select subfolder to preview images")
        self.image_files_in_preview = []

    @Slot(list)
    def add_image_paths_to_list(self, paths):
        '''
        Add image paths to the image list widget and set their thumbnails.
        Args:
            paths (list): List of image paths to add to the image list widget.
        This method iterates over the provided image paths, creates a QListWidgetItem
        for each image, and sets its icon to the corresponding thumbnail. It also
        handles errors while loading thumbnails and logs any issues encountered.
        '''
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
        '''
        Show a large preview of the selected image in the image list widget.
        This method retrieves the currently selected image from the list widget,
        loads its thumbnail, and displays it in the preview area. It also updates
        the image path label to show the selected image's path.
        If no image is selected, it clears the preview area and resets the labels.
        '''
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
        """
        Update the enabled state and text of the merge button based on folder selection.
        
        This method checks if there are any checked subfolder items and 
        if a root folder is selected. The merge button is enabled only when
        at least one subfolder is checked and a valid root folder exists.
        
        The button text is updated to show the count of selected folders.
        
        Side effects:
            - Changes the enabled state of self.merge_button
            - Updates the text of self.merge_button with selection count
        """
        checked_items = self.get_checked_subfolder_items()
        count = len(checked_items)
        
        # Update button text to include folder count
        if count > 0:
            self.merge_button.setText(f"Merge Selected Folders ({count})")
        else:
            self.merge_button.setText("Merge Selected Folders")
        
        self.merge_button.setEnabled(
            count > 0 and self.current_root_folder is not None
        )

    def get_checked_subfolder_items(self):
        """
        Get all checked items from the subfolder list widget.
        
        This method iterates through all items in the subfolder list widget
        and collects those that are checked by the user.
        
        Returns:
            list: A list of QListWidgetItems that are checked in the subfolder list
        """
        checked_items = []
        for index in range(self.subfolder_list_widget.count()):
            item = self.subfolder_list_widget.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                checked_items.append(item)
        return checked_items

    @Slot()
    def confirm_and_start_merge_to_new(self):
        """
        Confirm and initiate the folder merge operation.
        
        This method:
        1. Validates the checked folder selection
        2. Generates a target folder name based on the first source folder
        3. Shows a confirmation dialog with details about the merge operation
        4. Creates the target folder if it doesn't exist
        5. Starts the actual merge worker task
        
        The method handles various edge cases:
        - No root folder selected
        - No valid source folders checked
        - Target folder name conflicts with source folders
        - Target folder already exists
        
        Side effects:
            - Creates a new folder on the filesystem
            - Stores merge source and target information
            - Starts a worker thread for the merge operation
            - Disables the UI during the merge operation
        """
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
        """
        Start the worker thread to merge folders.
        
        This method initializes and runs the merge operation in a background thread.
        It updates the UI to show progress and disables user interaction during the merge.
        
        Args:
            source_paths_str (list): List of source folder paths as strings
            target_path_str (str): Target folder path as string
            
        Side effects:
            - Creates a worker thread
            - Disables the UI
            - Sets the current task type to "merge_subs"
        """
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
        """
        Safely stop any running worker thread.
        
        This method attempts to gracefully stop the currently running worker thread.
        If the thread doesn't stop within the timeout period, it is forcefully terminated.
        The UI is re-enabled after the thread is stopped.
        
        Side effects:
            - May stop a running worker thread
            - Resets worker thread related state variables
            - Re-enables the UI
            - Logs the thread stopping status
        """
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
        """
        Uncheck all items in the subfolder list.
        
        This method iterates through all items in the subfolder list widget,
        unchecking any that are currently checked. It also clears the checked
        folder names cache and updates the merge button state.
        
        Side effects:
            - Unchecks all items in the subfolder list widget
            - Clears the checked folder names cache
            - Updates the merge button state
            - Logs the action
        """
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
        """
        Toggle between natural and alphabetical sorting for the subfolder list.
        
        Natural sorting treats numbers in folder names as actual numbers,
        causing "folder2" to appear before "folder10", while alphabetical
        sorting would place "folder10" before "folder2".
        
        Side effects:
            - Updates the sort toggle button text
            - Changes the sort mode flag
            - Resorts the subfolder list
            - Logs the sort mode change
        """
        self.use_natural_sort = self.sort_toggle_button.isChecked()
        self.sort_toggle_button.setText(f"Natural Sort: {'On' if self.use_natural_sort else 'Off'}")
        self.log_message(f"Sorting mode: {'Natural' if self.use_natural_sort else 'Alphabetical'}")
        self.sort_subfolder_list()
    
    def sort_subfolder_list(self):
        """
        Sort the subfolder list based on the current sort mode.
        
        This method preserves the selection and checked state of items while 
        reordering them according to the current sort mode (natural or alphabetical).
        
        The process involves:
        1. Storing the current selection and checked states
        2. Removing all items from the list
        3. Sorting the items using the appropriate sort key
        4. Reinserting the sorted items into the list
        5. Restoring the previous checked states and selection
        
        Side effects:
            - Reorders the items in the subfolder list widget
            - Preserves item checked states and selection
        """
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
        Generate a natural sort key for a string containing numbers.
        
        This function splits text at number boundaries and converts numeric
        segments to integers, allowing for "natural" sorting where "2" comes
        before "10" when sorting filenames or folder names with numbers.
        
        Args:
            text (str): The text to convert to a natural sort key
            
        Returns:
            list: A list where numeric segments are converted to integers,
                  suitable for use as a sort key
                  
        Example:
            "folder10" will be sorted after "folder2" when using this key
        """
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

    def closeEvent(self, event):
        """
        Handle the window close event.
        
        This method is called automatically when the application window is closing.
        It performs clean shutdown operations:
        1. Stops the main worker thread
        2. Stops all folder preview worker threads
        3. Clears task queues and caches
        4. Logs the application shutdown
        
        Args:
            event (QCloseEvent): The close event object
            
        Side effects:
            - Stops all running worker threads
            - Clears task queues and caches
            - Logs application shutdown
        """
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