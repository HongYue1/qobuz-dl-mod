from setuptools import setup, find_packages


VERSION = "1.0.2"


def read_file(fname):
    with open(fname, "r", encoding="utf-8") as f:
        return f.read()


requirements = [
    "pathvalidate",
    "aiohttp",
    "mutagen",
    "beautifulsoup4",
    "aiofiles",
    "typer",
    "rich",
]

setup(
    name="qobuz-dl",
    version=VERSION,
    author="HongYue1",
    author_email="",
    description="A fast, modern, and concurrent music downloader for Qobuz.",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/HongYue1/qobuz-dl-mod/",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "qobuz-dl = qobuz_dl.cli:main",
            "qdl = qobuz_dl.cli:main",
        ],
    },
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)
