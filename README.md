# Merge Picture folders

A modern GUI tool to manage and merge image folders, built with PySide6.

![Program Screenshot](doc/screen.png)

## Features

- Interactive folder browser with drag and drop support
- Image preview functionality with thumbnails
- Background processing for folder operations
- Modern, stylish user interface with customizable themes
- Activity logging for operation tracking
- Support for multiple image formats (PNG, JPG, JPEG, BMP, GIF, TIFF, WEBP, HEIC)

## Requirements

- Python 3
- PySide6 (Qt for Python)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/Alchemist-Aloha/MergePicFolders.git
   cd MergePicFolders
   ```

2. Install the package:
   ```
   pip install -e .
   ```

## Usage

Run the application:
```bash
python -m MergePicFolders
```


## Project Structure

- `MergePicFolders/__main__.py` - Application entry point
- `MergePicFolders/window.py` - Main GUI implementation
- `MergePicFolders/worker.py` - Background task processing

## License

MIT