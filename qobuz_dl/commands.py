import argparse


def init_args(subparsers):
    init = subparsers.add_parser(
        "init",
        description=(
            "Initializes the configuration file with your Qobuz credentials.\n"
            "This command must be run before you can download anything.\n\n"
            "Usage Examples:\n"
            "  # Using a token\n"
            "  qobuz-dl init YOUR_AUTH_TOKEN\n\n"
            "  # Using an email and password\n"
            "  qobuz-dl init your.email@example.com your_password"
        ),
        help="Configure credentials (run this first).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    init.add_argument(
        "credentials",
        metavar="CREDENTIALS",
        nargs="+",
        help="Your authentication token, or your email and password separated by a space.",
    )
    return init


def dl_args(subparsers):
    download = subparsers.add_parser(
        "dl",
        description="Download music from Qobuz by URL (album, track, artist, playlist, label).",
        help="Download music from a URL.",
    )
    download.add_argument(
        "SOURCE",
        metavar="URL_OR_FILE",
        nargs="+",
        help=(
            "One or more Qobuz URLs (space-separated) or a path to a text file containing URLs."
        ),
    )
    return download


def add_common_arg(custom_parser, default_folder, default_quality):
    custom_parser.add_argument(
        "-d",
        "--directory",
        metavar="PATH",
        default=default_folder,
        help='Directory to save downloads (default: "%(default)s").',
    )
    custom_parser.add_argument(
        "-q",
        "--quality",
        metavar="ID",
        default=default_quality,
        help=(
            "Audio quality for downloads. 5=MP3, 6=CD-Lossless, "
            "7=Hi-Res <96kHz, 27=Hi-Res >96kHz (default: %(default)s)."
        ),
    )
    custom_parser.add_argument(
        "-w",
        "--max-workers",
        metavar="INT",
        type=int,
        default=8,
        help="Maximum number of concurrent download threads (default: %(default)s).",
    )
    custom_parser.add_argument(
        "--albums-only",
        action="store_true",
        help="Skip downloading singles, EPs, and VA releases when downloading an artist's discography.",
    )
    custom_parser.add_argument(
        "--no-m3u",
        action="store_true",
        help="Disable the creation of .m3u playlist files when downloading playlists.",
    )
    custom_parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not download a release if it's unavailable in the selected quality.",
    )
    custom_parser.add_argument(
        "-e",
        "--embed-art",
        action="store_true",
        help="Embed cover art into audio files.",
    )
    custom_parser.add_argument(
        "--og-cover",
        action="store_true",
        help="Download cover art in its original, uncompressed quality.",
    )
    custom_parser.add_argument(
        "--no-cover", action="store_true", help="Do not download any cover art."
    )
    custom_parser.add_argument(
        "-ff",
        "--folder-format",
        metavar="PATTERN",
        help='Pattern for formatting download folders (e.g., "{artist}/{album}").',
    )
    custom_parser.add_argument(
        "-tf",
        "--track-format",
        metavar="PATTERN",
        help='Pattern for formatting track filenames (e.g., "{tracknumber} - {tracktitle}").',
    )
    custom_parser.add_argument(
        "-s",
        "--smart-discography",
        action="store_true",
        help="Filter out deluxe, live, and compilation albums when downloading an artist's discography.",
    )


def qobuz_dl_args(
    default_quality=6, default_limit=20, default_folder="Qobuz Downloads"
):
    parser = argparse.ArgumentParser(
        prog="qobuz-dl",
        description="A command-line tool to download high-quality music from Qobuz.",
        epilog="",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-r",
        "--reset",
        action="store_true",
        help="Alias for the 'init' command to configure credentials.",
    )
    parser.add_argument(
        "-sc",
        "--show-config",
        action="store_true",
        help="Display the current configuration and exit.",
    )

    subparsers = parser.add_subparsers(
        title="Available Commands",
        description="Run `qobuz-dl <command> --help` for more information on a specific command.",
        dest="command",
    )

    init_args(subparsers)
    download = dl_args(subparsers)

    add_common_arg(download, default_folder, default_quality)

    return parser
