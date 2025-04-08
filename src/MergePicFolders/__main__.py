import sys
from PySide6.QtWidgets import QApplication
from .window import ImageFolderTool

def main():
    """
    Main function to run the ImageFolderTool application.
    """
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

if __name__ == "__main__":
    main()
