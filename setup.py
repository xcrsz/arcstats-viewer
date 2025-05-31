# setup.py

from setuptools import setup, find_packages

setup(
    name="arcstats-viewer",
    version="1.2.0",  # Bumped version
    description="A GTK3 ZFS ARC Stats Viewer for FreeBSD/GhostBSD",
    long_description="A GTK3 application to monitor ZFS ARC statistics in real-time with tables and graphs.",
    author="Vester Thacker",
    author_email="xcrsz@fastmail.jp",
    license="BSD-2-Clause",
    packages=find_packages(),
    # The 'gui_scripts' entry point creates the executable automatically
    entry_points={
        "gui_scripts": ["arcstats-viewer = arcstats_viewer.main:main"],
    },
    # Dependencies are simplified as theming files are removed
    install_requires=["PyGObject", "matplotlib"],
    python_requires='>=3.6',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: BSD :: FreeBSD",
        "Environment :: X11 Applications :: GTK",
        "License :: OSI Approved :: BSD License",
        "Topic :: System :: Monitoring",
    ],
)
