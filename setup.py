from setuptools import setup, find_packages

pkg_name = "qobuz-dl"


def read_file(fname):
    with open(fname, "r") as f:
        return f.read()


requirements = [
    "pathvalidate",
    "requests",
    "mutagen",
    "tqdm",
    "beautifulsoup4",
    "colorama",
]

setup(
    name=pkg_name,
    version="1.0.0",
    author="HongYue1",
    author_email="",
    description="The complete Lossless and Hi-Res music downloader for Qobuz",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/HongYue1/qobuz-dl-mod/",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "qobuz-dl = qobuz_dl:main",
            "qdl = qobuz_dl:main",
        ],
    },
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)

# rm -f dist/*
# python3 setup.py sdist bdist_wheel
# twine upload dist/*

