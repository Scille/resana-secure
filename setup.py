from setuptools import setup, find_packages

setup(
    name="resana_secure",
    packages=find_packages(include=["resana_secure", "resana_secure.*"]),
    package_dir={"resana_secure": "resana_secure"},
)
