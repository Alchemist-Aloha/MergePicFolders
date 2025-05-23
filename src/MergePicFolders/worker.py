from PySide6.QtWidgets import QApplication
import time
import os
import shutil
from PySide6.QtCore import QThread, Signal
from pathlib import Path
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
# --- Worker Thread for Background Tasks ---
class Worker(QThread):
    progress = Signal(str)
    finished = Signal(str, bool)
    error = Signal(str)
    image_paths = Signal(list)
    folder_preview_image = Signal(str, str)  # New signal: folder_path, image_path
    subfolders_found = Signal(list)  # Signal to emit found subdirectories

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
        """
        Initialize a worker thread for background processing tasks.
        
        This worker can handle multiple task types including scanning folders for images,
        generating folder previews, populating subfolder lists, and merging subfolders.
        
        Args:
            task_type (str): Type of task to perform. Valid values are:
                "scan_subfolder_images", "get_folder_preview", 
                "populate_subfolders", "merge_subs"
            folder_to_scan (str, optional): Path to folder to scan for images or previews.
            source_folder_paths (list, optional): List of folder paths to merge from.
            target_folder_path (str, optional): Target folder path for merge operation.
            root_folder_to_scan (str, optional): Root folder to scan for subfolders.
            parent (QObject, optional): Parent object for the thread.
            
        Note:
            The worker uses signals to communicate progress, errors and results back
            to the main thread. Different tasks require different parameters.
        """
        super().__init__(parent)
        self.task_type = task_type
        self.folder_to_scan = Path(folder_to_scan) if folder_to_scan else None
        self.root_folder_to_scan = Path(root_folder_to_scan) if root_folder_to_scan else None
        self.source_merge_folders = (
            [Path(p) for p in source_folder_paths] if source_folder_paths else []
        )
        self.target_merge_folder = (
            Path(target_folder_path) if target_folder_path else None
        )
        self._is_running = True
        self._success = False  # Track task success

    def run(self):
        """
        Execute the worker task based on the task_type.
        
        This method is automatically called when the thread starts. It determines
        which operation to perform based on the task_type and available parameters,
        then executes the appropriate task method.
        
        The method handles all exceptions and reports errors via signals.
        It also tracks and reports the success status of the task.
        
        Side effects:
            - Emits progress, error, and other task-specific signals during execution
            - Sets the internal success flag based on task completion
            - Emits the finished signal when done with task_type and success status
        """
        self._is_running = True
        self._success = False  # Reset success status
        try:
            if self.task_type == "scan_subfolder_images" and self.folder_to_scan:
                self._scan_folder_for_images(self.folder_to_scan)
                self._success = True  # Assume success if no exception
            elif self.task_type == "get_folder_preview" and self.folder_to_scan:
                self._get_folder_preview_image(self.folder_to_scan)
                self._success = True
            elif self.task_type == "populate_subfolders" and self.root_folder_to_scan:
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
                    and not self.root_folder_to_scan
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
        """
        Request the worker thread to stop execution.
        
        This method sets a flag that causes task methods to exit their
        processing loops when checked. It doesn't immediately terminate
        the thread but allows it to exit cleanly.
        
        Side effects:
            - Sets internal _is_running flag to False
            - Emits a progress signal indicating cancellation was requested
        """
        self._is_running = False
        self.progress.emit("Task cancellation requested...")

    def _scan_folder_for_images(self, folder_path):
        """
        Scan a specific folder recursively for image files.
        
        This method searches the specified folder and all its subfolders
        for image files with supported extensions. Found images are emitted
        in batches using the image_paths signal.
        
        Args:
            folder_path (Path): Path object representing the folder to scan
            
        Side effects:
            - Emits progress updates during scanning
            - Emits image_paths signal with batches of found image paths
            - Emits error signal if scanning fails
            
        Raises:
            Exception: Re-raises any exceptions after reporting them via error signal
        """
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
        """
        Generate a unique path in the target folder for a source file.
        
        If the target path already exists, this method appends a counter or
        timestamp to the filename to make it unique and avoid overwriting.
        
        Args:
            source_path (Path): Path object representing the source file
            target_folder (Path): Path object representing the target folder
            
        Returns:
            Path: A unique Path object for the target file, or None if a unique
                 name cannot be generated after 1000 attempts
                 
        Note:
            This method implements a collision resolution strategy where it first
            tries to append incremental numbers, then falls back to a timestamp
            if needed.
        """
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
        """
        Move content from source folders into the target folder.
        
        This method processes all source folders, moving their files to the target
        folder while handling name conflicts. After moving files, it optionally
        deletes empty source directories.
        
        Side effects:
            - Moves files from source folders to target folder
            - May delete empty directories in source folders
            - Emits progress updates during merge operation
            - Emits error signal for any issues encountered
            - Updates the internal success flag based on outcome
            
        Note:
            This method carefully tracks statistics about the merge operation
            including moved files, skipped files, and deleted directories.
            The operation can be cancelled at any point via the stop() method.
        """
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
        """
        Find the first suitable image in a folder to use as a preview thumbnail.
        
        This method searches for image files in the specified folder and up to
        2 levels of subfolders. It returns the first valid image found that can
        be accessed and has a non-zero size.
        
        The search follows this pattern:
        1. Look for images in the immediate folder
        2. If none found, search one level of subfolders
        3. If still none found, search two levels of subfolders
        
        Args:
            folder_path (Path): Path object representing the folder to search for preview images
            
        Side effects:
            - Emits folder_preview_image signal with the folder path and the found image path
            - Emits progress updates for certain conditions
            - Emits error signal if the folder is invalid or errors occur
            
        Note:
            This method only processes files with extensions defined in SUPPORTED_IMAGE_EXTENSIONS.
            It skips files that cannot be accessed due to permissions or other I/O errors.
        """
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
        """
        Scan the root folder for immediate subdirectories.
        
        This method iterates through the contents of the root folder and
        collects all directory entries, emitting them via the subfolders_found signal.
        It does not recursively search for subdirectories beyond the first level.
        
        Args:
            root_folder_path (Path): Path object representing the root folder to scan
            
        Side effects:
            - Emits progress updates at start and completion
            - Emits subfolders_found signal with list of Path objects
            - Emits error signal if the folder is invalid or errors occur
            
        Raises:
            Exception: Re-raises any exceptions after reporting them via error signal
        """
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