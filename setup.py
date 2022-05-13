from setuptools import setup, find_packages
from pathlib import Path


PARSEC_PATH = Path(__file__).resolve().parent / "subtree/parsec-cloud"


# Awesome hack to load `__version__`
__version__ = None
exec(open("resana_secure/_version.py", encoding="utf-8").read())


setup(
    name="resana_secure",
    version=__version__,
    packages=find_packages(include=["resana_secure", "resana_secure.*"]),
    package_dir={"resana_secure": "resana_secure"},
    package_data={"resana_secure": ["*.png"]},
    install_requires=[
        "Quart~=0.14",
        "Quart-Trio~=0.7",
        "Quart-CORS~=0.4",
        "Hypercorn~=0.11",
        f"parsec-cloud[backend,core] @ file://localhost/{PARSEC_PATH.absolute()}",  # See https://www.python.org/dev/peps/pep-0440/#direct-references
    ],
)
