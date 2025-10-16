# qobuz-dl-MOD

A fast, streamlined, and concurrent music downloader for [Qobuz](https://www.qobuz.com/).
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=VZWSWVGZGJRMU&source=url)

## Modifications from Original

This version of `qobuz-dl` has been significantly refactored to be faster, simpler, and more focused on its core purpose: downloading music.

- **Greatly Improved Performance:** Downloads are now fully concurrent. Entire albums, playlists, and discographies are downloaded in parallel, dramatically reducing the time you spend waiting.
- **Simplified Interface:** The `interactive` and `lucky` modes have been removed in favor of a clean, direct download workflow.
- **Easy Setup:** A non-interactive `init` command makes setting up your credentials quick and script-friendly.
- **No More Database:** The duplicate-checking database has been removed, simplifying the tool's operation. The focus is on providing a powerful, stateless downloader.
- **Token support** : Allows you to log in directly using a token.

## Features

- **Concurrent Downloading:** Downloads multiple tracks at once for maximum speed.
- **High-Quality Audio:** Supports all Qobuz formats, including MP3, CD-Lossless (FLAC), and Hi-Res FLAC up to 24-bit/192kHz.
- **Versatile Download Options:** Download albums, tracks, artists, playlists, and labels directly by URL.
- **Last.fm Playlist Support:** Download playlists from Spotify, Apple Music, and YouTube by importing them into Last.fm first.
- **M3U Playlist Generation:** Automatically creates `.m3u` files for downloaded playlists.
- **Bulk Downloads:** Can read a list of URLs from a text file for batch downloading.
- **Extended Metadata:** Embeds detailed tags and cover art into your music files.

## Getting Started

> You'll need an **active Qobuz subscription** to download music. Or borrow a token from a friend.

#### 1. Install `qobuz-dl` with pip or uv

**Linux / macOS**

```bash
pip3 install -U git+https://github.com/HongYue1/qobuz-dl-mod.git@master
```

or

```
uv pip install -U git+https://github.com/HongYue1/qobuz-dl-mod.git@master
```

**Windows**

```bash
pip install -U git+https://github.com/HongYue1/qobuz-dl-mod.git@master
```

or

```
uv pip install -U git+https://github.com/HongYue1/qobuz-dl-mod.git@master
```

#### 2. Configure Your Credentials

Before you can download, you must initialize the tool with your Qobuz credentials. This only needs to be done once.

**To log in with an email and password:**

```bash
qobuz-dl init your.email@example.com your_password
```

**Or, to log in with a token:**

```bash
qobuz-dl init YOUR_AUTH_TOKEN
```

## Examples

### Download by URL

**Download an album in Hi-Res quality (24-bit < 96kHz)**

```bash
qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb -q 7
```
#### Available qualites:
- `5 : mp3 320kbps`
- `6 : CD 16-bit/44.1 KHz`
- `7 : Hi-Res 24-bit/ up to 96 KHz`
- `27:Hi-Res 24-bit/ up to 192 KHz`


**Download multiple URLs to a custom directory**

```bash
qobuz-dl dl https://play.qobuz.com/artist/2038380 https://play.qobuz.com/album/ip8qjy1m6dakc -d "My Music/Pop"
```

**Download a list of URLs from a text file**

```bash
qobuz-dl dl path/to/my_urls.txt
```

**Download from a label and embed cover art into the files**

```bash
qobuz-dl dl https://play.qobuz.com/label/7526 -e
```

**Download a playlist in the maximum possible quality**

```bash
qobuz-dl dl https://play.qobuz.com/playlist/5388296 -q 27
```

**Download an artist's discography, but skip singles and EPs**

```bash
qobuz-dl dl https://play.qobuz.com/artist/2528676 --albums-only
```

### Download from Last.fm

You can download playlists from services like Spotify or Apple Music by importing them into Last.fm first.

1.  Go to `https://www.last.fm/user/your-username/playlists` and create a new playlist by importing it from another service.
2.  Use the URL of the Last.fm playlist with `qobuz-dl`.

**Download a Last.fm playlist in maximum quality**

```bash
qobuz-dl dl https://www.last.fm/user/vitiko98/playlists/11887574 -q 27
```

## Usage

```
usage: qobuz-dl [-h] [-r] [-sc] {init,dl} ...

A command-line tool to download high-quality music from Qobuz.

options:
  -h, --help      show this help message and exit
  -r, --reset     Alias for the 'init' command to configure credentials.
  -sc, --show-config
                  Display the current configuration and exit.

Available Commands:
  Run `qobuz-dl <command> --help` for more information on a specific command.

  {init,dl}
    init          Configure credentials (run this first).
    dl            Download music from a URL.
```

### `qobuz-dl init --help`:

```
usage: qobuz-dl init [-h] CREDENTIALS [CREDENTIALS ...]

Initializes the configuration file with your Qobuz credentials.
This command must be run before you can download anything.

Usage Examples:
  # Using a token
  qobuz-dl init YOUR_AUTH_TOKEN

  # Using an email and password
  qobuz-dl init your.email@example.com your_password

positional arguments:
  CREDENTIALS  Your authentication token, or your email and password separated by a space.

options:
  -h, --help   show this help message and exit
```

### `qobuz-dl dl --help`

```
usage: qobuz-dl dl [-h] [-d PATH] [-q ID] [-w INT] [--albums-only] [--no-m3u] [--no-fallback] [-e]
                   [--og-cover] [--no-cover] [-ff PATTERN] [-tf PATTERN] [-s]
                   URL_OR_FILE [URL_OR_FILE ...]

Download music from Qobuz by URL (album, track, artist, playlist, label).

positional arguments:
  URL_OR_FILE           One or more Qobuz URLs (space-separated) or a path to a text file containing URLs.

options:
  -h, --help            show this help message and exit
  -d, --directory PATH  Directory to save downloads (default: "Qobuz Downloads").
  -q, --quality ID      Audio quality for downloads. 5=MP3, 6=CD-Lossless, 7=Hi-Res <96kHz, 27=Hi-Res >96kHz
                        (default: 6).
  -w, --max-workers INT
                        Maximum number of concurrent download threads (default: 8).
  --albums-only         Skip downloading singles, EPs, and VA releases when downloading an artist's
                        discography.
  --no-m3u              Disable the creation of .m3u playlist files when downloading playlists.
  --no-fallback         Do not download a release if it's unavailable in the selected quality.
  -e, --embed-art       Embed cover art into audio files.
  --og-cover            Download cover art in its original, uncompressed quality.
  --no-cover            Do not download any cover art.
  -ff, --folder-format PATTERN
                        Pattern for formatting download folders (e.g., "{artist}/{album}").
  -tf, --track-format PATTERN
                        Pattern for formatting track filenames (e.g., "{tracknumber} - {tracktitle}").
  -s, --smart-discography
                        Filter out deluxe, live, and compilation albums when downloading an artist's
                        discography.
```

## Module Usage

Using `qobuz-dl` as a module is straightforward. The main entry point is the `QobuzDL` class from `core`.

```python
import logging
from qobuz_dl.core import QobuzDL

logging.basicConfig(level=logging.INFO)

# You must have a config file created via "qobuz-dl init" first.
# This example shows how to manually initialize if needed.

email = "your@email.com"
password = "your_password"

qobuz = QobuzDL()
# These values are normally read from the config file.
# For module usage, you can get them once and store them.
qobuz.get_tokens()
qobuz.initialize_client(email, password, qobuz.app_id, qobuz.secrets)

# Start a download
qobuz.handle_url("https://play.qobuz.com/album/va4j3hdlwaubc")
```

## A note about Qo-DL

`qobuz-dl` is inspired by the discontinued Qo-DL-Reborn. This tool uses some modules originally written by Sorrow446 and DashLt.

## Disclaimer

- This tool is for educational purposes. By using it, you are accepting the [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf). The developers are not responsible for misuse of this program.
- `qobuz-dl` is not affiliated with Qobuz.
