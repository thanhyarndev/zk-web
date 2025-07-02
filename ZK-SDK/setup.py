"""
Setup script for UHF RFID Reader Python SDK
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "UHF RFID Reader Python SDK"

setup(
    name="PythonSDK",
    version="1.0.0",
    author="Python SDK Team",
    author_email="support@example.com",
    description="Python SDK for UHF RFID Reader communication",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/example/uhf-rfid-sdk",
    packages=["PythonSDK"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Communications",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.7",
    install_requires=[
        "pyserial>=3.5",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
            "mypy>=0.800",
        ],
    },
    keywords="rfid uhf reader serial tcp communication",
    project_urls={
        "Bug Reports": "https://github.com/example/uhf-rfid-sdk/issues",
        "Source": "https://github.com/example/uhf-rfid-sdk",
        "Documentation": "https://github.com/example/uhf-rfid-sdk/blob/main/README.md",
    },
) 