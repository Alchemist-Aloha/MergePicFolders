from setuptools import setup, find_packages

setup(
    name="MergePicFolders",
    version="1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=["PySide6"],
    entry_points={
        "console_scripts": [
            "mergepicfolders=MergePicFolders.__main__:main",
        ],
    },
    author="Alchemist-Aloha",
    description="A modern GUI tool to manage and merge image folders, built with PySide6.",
    url="https://github.com/Alchemist-Aloha/MergePicFolders",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
