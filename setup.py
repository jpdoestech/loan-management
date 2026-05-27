"""Setup script (optional — primarily for editable installs during development)."""
from setuptools import setup, find_packages

setup(
    name="employee-cash-advance-manager",
    version="1.0.0",
    description="Desktop app for managing employee cash advances",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "bcrypt>=4.0.1",
        "rapidfuzz>=3.0.0",
        "openpyxl>=3.1.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "server": ["Flask>=3.0.0", "Flask-HTTPAuth>=4.8.0"],
        "fast-import": ["pandas>=2.0.0"],
    },
    entry_points={
        "console_scripts": ["ecam=app:main"],
    },
)
