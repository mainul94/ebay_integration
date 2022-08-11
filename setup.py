from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in ebay_integration/__init__.py
from ebay_integration import __version__ as version

setup(
	name="ebay_integration",
	version=version,
	description="Pull Order from eBay and update order Status on Deispuch Delivrey Note.",
	author="Mainul Islam",
	author_email="mainulkhan94@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
