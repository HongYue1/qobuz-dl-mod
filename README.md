# qobuz-dl-MOD

A fast, modern, and concurrent music downloader for [Qobuz](https://www.qobuz.com/).
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=VZWSWVGZGJRMU&source=url)
<img width="796" height="388" alt="1" src="https://github.com/user-attachments/assets/8635ecda-f239-4981-b8f2-1e12fdba8792" /> 

<img width="796" height="388" alt="2" src="https://github.com/user-attachments/assets/a6616fbc-3cf1-499c-8d09-72c0d0aa4deb" />

## Core Improvements

This version of `qobuz-dl` has been fundamentally rewritten with a focus on performance, modern features, and a superior user experience.

- **Token Support:** Allows you to log in directly using a Qobuz authentication token.
- **Fully Asynchronous Core:** Built on `asyncio` and `aiohttp` for massively concurrent downloads.
- **Powerful & Modern CLI:** The interface has been rebuilt with **Typer** and **Rich** for a clean, user-friendly experience with beautiful, formatted help and logging.
- **Advanced Output Formatting:** A powerful templating engine with conditional logic gives you complete control over your file paths and naming schemes.
- **Expanded Metadata Tagging:** Improved metadata handling for a richer music library.
- **Dry Run Mode:** Simulate a download with `--dry-run` to see exactly which files would be created without downloading a single byte.

## Getting Started

> You'll need an **active Qobuz subscription** to download music. Or borrow a token from a friend.

#### 1. Install `qobuz-dl-mod` with pip or uv

```bash
# For Linux (use pip3 instead of pip), macOS, or Windows
pip install -U "git+https://github.com/HongYue1/qobuz-dl-mod.git@master"
```

or

```bash
uv pip install -U "git+https://github.com/HongYue1/qobuz-dl-mod.git@master"
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

## Usage Examples

**Download an album in the highest possible quality**

```bash
qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb -q 27
```

**Available Qualities:**

- `5`: MP3 320kbps
- `6`: CD-Lossless 16-bit/44.1kHz
- `7`: Hi-Res 24-bit/up to 96kHz
- `27`: Hi-Res 24-bit/up to 192kHz

**Download a track with a custom output path**

By default, the script uses a smart template that handles multi-disc albums. To override it, use the `-o` flag.

```bash
qobuz-dl dl <URL> -o "{artist}/{album}/{tracknumber} - {tracktitle}.{ext}"
```

**Keep a collection updated by skipping previously downloaded tracks**

```bash
qobuz-dl dl <PLAYLIST_URL> --download-archive
```

Run this command on the same playlist or artist URL regularly. Only new tracks that are not in your archive will be downloaded.

**Download a list of URLs from a text file**

```bash
qobuz-dl dl path/to/my_urls.txt
```

---

## Advanced Output Formatting

You have full control over the directory structure and filenames using the `--output` or `-o` option.

### Default Template

The default template is designed to be smart and organized, automatically handling multi-disc albums.

**Default Template String:**

```
{albumartist}/{album} ({year})/%{?is_multidisc,Disc {media_number}/|%}{tracknumber} - {tracktitle}.{ext}

```

**What it means:**

- **For a standard, single-disc album**, it creates a clean folder structure:
  ```
  Artist Name/
  └── Album Title (2023)/
      ├── 01 - Track One.flac
      └── 02 - Track Two.flac
  ```
- **For a multi-disc album**, it automatically creates subfolders for each disc:
  ```
  Artist Name/
  └── Album Title (2023)/
      ├── Disc 01/
      │   ├── 01 - Track One.flac
      │   └── 02 - Track Two.flac
      └── Disc 02/
          ├── 01 - Track One.flac
          └── 02 - Track Two.flac
  ```

### Available Template Variables

You can use any combination of the following variables to build your path.

| Variable          | Description                                                | Example                      |
| :---------------- | :--------------------------------------------------------- | :--------------------------- |
| **Track**         |
| `{tracknumber}`   | Track number, zero-padded.                                 | `01`                         |
| `{tracktitle}`    | The title of the track.                                    | `One Step Closer`            |
| `{artist}`        | The track's primary artist.                                | `Linkin Park`                |
| `{isrc}`          | The track's ISRC code.                                     | `USRE10001014`               |
| `{composer}`      | The track's composer.                                      | `Wolfgang Amadeus Mozart`    |
| `{work}`          | The larger classical work.                                 | `The Magic Flute`            |
| **Album**         |
| `{album}`         | The title of the album.                                    | `Hybrid Theory`              |
| `{albumartist}`   | The album's primary artist.                                | `Linkin Park`                |
| `{year}`          | Four-digit year of release.                                | `2000`                       |
| `{release_date}`  | The full release date.                                     | `2000-10-24`                 |
| `{version}`       | The album's version info.                                  | `20th Anniversary Edition`   |
| `{label}`         | The record label.                                          | `Warner Records`             |
| `{upc}`           | The album's UPC/barcode.                                   | `093624893661`               |
| `{genre}`         | The primary genre of the album.                            | `Rock`                       |
| `{release_type}`  | The type of release.                                       | `album`, `single`, or `ep`   |
| `{copyright}`     | Copyright information.                                     | `© 2020 Warner Records Inc.` |
| **Disc**          |
| `{media_number}`  | The disc number, zero-padded.                              | `02`                         |
| `{media_count}`   | Total number of discs.                                     | `5`                          |
| **Format**        |
| `{bit_depth}`     | Bit depth of the audio.                                    | `16` or `24`                 |
| `{sampling_rate}` | Sampling rate in kHz.                                      | `44` or `96`                 |
| `{ext}`           | The file extension.                                        | `flac` or `mp3`              |
| **Special**       |
| `{is_multidisc}`  | A helper flag (1 or 0). For use in conditional formatting. | `1` (if media_count > 1)     |

### Conditional Formatting

To avoid empty parentheses or stray hyphens when a piece of metadata is missing, you can use conditional logic directly in your template.

**Syntax:** `%{?variable,text_if_present|text_if_absent%}`

- `?variable`: The name of the variable to check (must be from the table above).
- `text_if_present`: The text to insert if the variable exists and is not empty. You can use other variables inside this text.
- `text_if_absent`: The text to insert if the variable is missing. This can be left empty.

**Example 1: The Default Disc Logic**
This is how the default template works.

```
%{?is_multidisc,Disc {media_number}/|%}
```

- **If `is_multidisc` is true (1):** It inserts `Disc 02/` into the path.
- **If `is_multidisc` is false (0):** It inserts nothing (`|%}`).

**Example 2: Safely adding the album version**
This template will add the version in parentheses, but only if the album has one.

```
-o "{albumartist}/{album}%{?version, ({version})|%}/{tracknumber} - {tracktitle}.{ext}"
```

- **Result if version exists:** `.../Hybrid Theory (20th Anniversary Edition)/01 - Papercut.flac`
- **Result if version is missing:** `.../Meteora/01 - Foreword.flac` (no empty `()` are created)

---

## Command-Line Reference

### `qobuz-dl --help`

```
 Usage: python -m qobuz_dl.cli [OPTIONS] COMMAND [ARGS]...

 A command-line tool to download high-quality music from Qobuz.

╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --show-config                 Display the current configuration and exit.                                  │
│ --version                     Show the application's version and exit.                                     │
│ --install-completion          Install completion for the current shell.                                    │
│ --show-completion             Show completion for the current shell, to copy it or customize the           │
│                               installation.                                                                │
│ --help                        Show this message and exit.                                                  │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ─────────────────────────────────────────────────────────────────────────────────────────────────╮
│ init   Initialize and configure your Qobuz credentials.                                                    │
│ dl     Download music from Qobuz by URL (album, track, artist, playlist, label).                           │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

```

### `qobuz-dl init --help`

```
  Usage: python -m qobuz_dl.cli init [OPTIONS] CREDENTIALS

 Initialize and configure your Qobuz credentials.

 This command will create a configuration file with your authentication
 details and default settings. It will also fetch the necessary app secrets
 from Qobuz.

╭─ Arguments ────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    credentials      TEXT  Your auth token, OR your email and password. [required]                        │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### `qobuz-dl dl --help`

```
 Usage: python -m qobuz_dl.cli dl [OPTIONS] URL_OR_FILE

 Download music from Qobuz by URL (album, track, artist, playlist, label).

╭─ Arguments ────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    source      URL_OR_FILE  One or more Qobuz URLs or a path to a text file containing URLs. [required]  │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --output             -o      TEMPLATE  Output path and filename template. See docs for available           │
│                                        variables.                                                          │
│ --quality            -q      ID        Audio quality: 5=MP3, 6=CD-Lossless, 7=Hi-Res <96kHz, 27=Hi-Res     │
│                                        >96kHz.                                                             │
│ --max-workers        -w      INT       Maximum number of concurrent download threads. [default: 8]         │
│ --embed-art          -e                Embed cover art into audio files.                                   │
│ --no-cover                             Do not download any cover art.                                      │
│ --og-cover                             Download cover art in its original quality.                         │
│ --albums-only                          Skip singles/EPs when downloading an artist's discography.          │
│ --no-m3u                               Disable creation of .m3u playlist files.                            │
│ --no-fallback                          Do not download if the selected quality is unavailable.             │
│ --smart-discography  -s                Filter out deluxe, live, and compilation albums.                    │
│ --dry-run                              Simulate downloads without writing any files to disk.               │
│ --download-archive                     Enable and use the download archive to skip already downloaded      │
│                                        tracks.                                                             │
│ --help                                 Show this message and exit.                                         │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## A note about Qo-DL

`qobuz-dl` is inspired by the discontinued Qo-DL-Reborn. This tool uses some modules originally written by Sorrow446 and DashLt.

## Disclaimer

- This tool is for educational purposes. By using it, you are accepting the [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf). The developers are not responsible for misuse of this program.
- `qobuz-dl` is not affiliated with Qobuz.

