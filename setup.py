# setup.py
from setuptools import setup, find_packages

setup(
    name="simulatore-calcio",
    version="1.0",
    packages=find_packages(),
    py_modules=['config'],  # Include config.py dalla root
    install_requires=[
        "python-dotenv>=1.0.0",
        "pymongo>=4.6.0",
        "pandas>=2.1.0",
        "numpy>=1.24.0"
    ],
)