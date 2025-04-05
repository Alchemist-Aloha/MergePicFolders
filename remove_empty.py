import os
import argparse
import logging

def setup_logging():
    """Configure logging format and level"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def remove_empty_folders(root_dir, dry_run=False):
    """
    Recursively removes empty folders starting from the deepest level
    
    Args:
        root_dir (str): Path to the directory to clean
        dry_run (bool): If True, only report what would be removed without actually removing
    
    Returns:
        int: Number of directories removed
    """
    if not os.path.isdir(root_dir):
        logging.error(f"'{root_dir}' is not a valid directory")
        return 0
    
    logging.info(f"Scanning for empty directories in: {root_dir}")
    
    count = 0
    # Walk bottom-up so we handle the deepest directories first
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        # Skip the root directory itself
        if dirpath == root_dir:
            continue
        
        # Check if this directory is empty (no files and no non-empty subdirectories)
        if not filenames and not dirnames:
            if dry_run:
                logging.info(f"Would remove empty directory: {dirpath}")
            else:
                try:
                    os.rmdir(dirpath)
                    logging.info(f"Removed empty directory: {dirpath}")
                    count += 1
                except OSError as e:
                    logging.error(f"Failed to remove directory '{dirpath}': {e}")
    
    action = "Would remove" if dry_run else "Removed"
    logging.info(f"{action} {count} empty directories")
    return count

def main():
    parser = argparse.ArgumentParser(description="Remove empty subdirectories from a given folder")
    parser.add_argument("target_dir", help="Target directory to clean empty folders from")
    parser.add_argument("--dry-run", action="store_true", 
                        help="Only report what would be removed without actually removing")
    
    args = parser.parse_args()
    
    setup_logging()
    
    target_path = os.path.abspath(args.target_dir)
    if not os.path.exists(target_path):
        logging.error(f"Directory does not exist: {target_path}")
        return 1
    
    remove_empty_folders(target_path, args.dry_run)
    return 0

if __name__ == "__main__":
    exit(main())