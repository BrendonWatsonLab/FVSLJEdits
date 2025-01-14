from setuptools import setup, find_packages

setup(
    name="FVSLJ",
    version="0.1.1",
    packages=find_packages(),
    install_requires=[
        "labjack-ljm",
    ],
    entry_points={
        "console_scripts": [
            "FVSLJ=FVSLJ.FVSLJ:main",
            "FVSLJ_readbin=FVSLJ.readbin:main",
        ],
    },
    author="FVS LLC",
    author_email="feviscientific@gmail.com",
    description="Watson Lab data acquisition scripts using LabJack T7 devices",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)