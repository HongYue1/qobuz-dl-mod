"""
Defines the command-line interface (CLI) for the application using Typer.
Handles user commands, configuration file management, and orchestrates the
downloading process.
"""

import asyncio
import configparser
import hashlib
import logging
import glob
import os
import sys
from typing import List

import typer
from rich.console import Console
from rich.logging import RichHandler

from qobuz_dl.bundle import Bundle
from qobuz_dl.core import QobuzDL

from qobuz_dl.downloader import DEFAULT_OUTPUT_TEMPLATE
from qobuz_dl.exceptions import AuthenticationError

# --- Rich and Typer setup ---
console = Console()
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(console=console, rich_tracebacks=True, show_path=False, markup=True)
    ],
)
log = logging.getLogger(__name__)

app = typer.Typer(
    name="qobuz-dl",
    help="A command-line tool to download high-quality music from Qobuz.",
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

# --- Configuration File Handling ---

if os.name == "nt":
    OS_CONFIG = os.environ.get("APPDATA")
else:
    OS_CONFIG = os.path.join(os.environ["HOME"], ".config")

CONFIG_PATH = os.path.join(OS_CONFIG, "qobuz-dl")
CONFIG_FILE = os.path.join(CONFIG_PATH, "config.ini")


# --- Helper Functions ---
def _remove_leftovers(directory: str):
    """
    Recursively finds and removes temporary download files ('.*.tmp')
    from the given directory.
    """
    leftover_pattern = os.path.join(directory, "**", ".*.tmp")
    for item in glob.glob(leftover_pattern, recursive=True):
        try:
            os.remove(item)
            log.debug(f"Removed leftover file: {item}")
        except OSError as e:
            log.warning(f"Could not remove leftover file: {item}. Reason: {e}")


# --- Typer Callback ---
@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    show_config: bool = typer.Option(
        False, "--show-config", help="Display the current configuration and exit."
    ),
    version: bool = typer.Option(
        False, "--version", help="Show the application's version and exit."
    ),
):
    """
    A tool to download music from Qobuz.
    Run qobuz-dl [COMMAND] --help for more information on a specific command.
    """
    if ctx.invoked_subcommand is None and not show_config and not version:
        console.print(ctx.get_help())
        raise typer.Exit()

    if show_config:
        if not os.path.isfile(CONFIG_FILE):
            log.error("Config file not found. Run qobuz-dl init to create one.")
            raise typer.Exit(code=1)
        console.print(f"[bold cyan]Configuration: {CONFIG_FILE}[/bold cyan]\n---")
        with open(CONFIG_FILE, "r") as f:
            console.print(f.read())
        raise typer.Exit()

    if version:
        console.print("qobuz-dl version 3.0.4")
        raise typer.Exit()


# --- Typer Commands ---
@app.command()
def init(
    credentials: List[str] = typer.Argument(
        ...,
        help="Your auth token, OR your email and password.",
        metavar="CREDENTIALS",
    ),
):
    """
    Initialize and configure your Qobuz credentials.

    This command will create a configuration file with your authentication
    details and default settings. It will also fetch the necessary app secrets
    from Qobuz.
    """
    os.makedirs(CONFIG_PATH, exist_ok=True)
    asyncio.run(_create_or_update_config(CONFIG_FILE, credentials))


async def _create_or_update_config(config_file: str, credentials: List[str]):
    """
    Creates or updates the config.ini file with credentials and default settings.
    """
    log.info(f"Creating or updating config file: {config_file}")
    config = configparser.ConfigParser()
    config["DEFAULT"] = {}

    if len(credentials) == 1:
        config["DEFAULT"]["token"] = credentials[0]
        config["DEFAULT"]["email"] = ""
        config["DEFAULT"]["password"] = ""
        log.info("[green]Authentication method set to token.[/green]")
    elif len(credentials) == 2:
        email, password = credentials
        config["DEFAULT"]["email"] = email
        config["DEFAULT"]["password"] = hashlib.md5(
            password.encode("utf-8")
        ).hexdigest()
        config["DEFAULT"]["token"] = ""
        log.info("[green]Authentication method set to email/password.[/green]")
    else:
        log.error(
            "Invalid arguments for init. Use 'qobuz-dl init <token>' or 'qobuz-dl init <email> <password>'."
        )
        raise typer.Exit(code=1)

    # Set sensible defaults for other options.
    config["DEFAULT"]["default_quality"] = "6"

    escaped_template = DEFAULT_OUTPUT_TEMPLATE.replace("%", "%%")
    config["DEFAULT"]["output_template"] = escaped_template

    config["DEFAULT"]["no_m3u"] = "false"
    config["DEFAULT"]["albums_only"] = "false"
    config["DEFAULT"]["no_fallback"] = "false"
    config["DEFAULT"]["og_cover"] = "false"
    config["DEFAULT"]["embed_art"] = "false"
    config["DEFAULT"]["no_cover"] = "false"
    config["DEFAULT"]["smart_discography"] = "false"

    log.info("Fetching app secrets from Qobuz. This may take a moment...")
    try:
        bundle = await Bundle.create()
        config["DEFAULT"]["app_id"] = str(bundle.get_app_id())
        config["DEFAULT"]["secrets"] = ",".join(bundle.get_secrets().values())
    except Exception as e:
        log.error(f"Failed to fetch app secrets: {e}")
        raise typer.Exit(code=1)

    with open(config_file, "w") as configfile:
        config.write(configfile)
    log.info(
        f"[green]Config file saved. You can edit it at {config_file} to change default options.[/green]"
    )


@app.command()
def dl(
    source: List[str] = typer.Argument(
        ...,
        help="One or more Qobuz URLs or a path to a text file containing URLs.",
        metavar="URL_OR_FILE",
    ),
    output: str = typer.Option(
        None,
        "-o",
        "--output",
        metavar="TEMPLATE",
        help="Output path and filename template. See docs for available variables.",
    ),
    quality: int = typer.Option(
        None,
        "-q",
        "--quality",
        metavar="ID",
        help="Audio quality: 5=MP3, 6=CD-Lossless, 7=Hi-Res <96kHz, 27=Hi-Res >96kHz.",
    ),
    max_workers: int = typer.Option(
        8,
        "-w",
        "--max-workers",
        metavar="INT",
        help="Maximum number of concurrent download threads.",
    ),
    embed_art: bool = typer.Option(
        False, "-e", "--embed-art", help="Embed cover art into audio files."
    ),
    no_cover: bool = typer.Option(
        False, "--no-cover", help="Do not download any cover art."
    ),
    og_cover: bool = typer.Option(
        False, "--og-cover", help="Download cover art in its original quality."
    ),
    albums_only: bool = typer.Option(
        False,
        "--albums-only",
        help="Skip singles/EPs when downloading an artist's discography.",
    ),
    no_m3u: bool = typer.Option(
        False, "--no-m3u", help="Disable creation of .m3u playlist files."
    ),
    no_fallback: bool = typer.Option(
        False,
        "--no-fallback",
        help="Do not download if the selected quality is unavailable.",
    ),
    smart_discography: bool = typer.Option(
        False,
        "-s",
        "--smart-discography",
        help="Filter out deluxe, live, and compilation albums.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulate downloads without writing any files to disk.",
    ),
    download_archive: bool = typer.Option(
        False,
        "--download-archive",
        help="Enable and use the download archive to skip already downloaded tracks.",
    ),
):
    """
    Download music from Qobuz by URL (album, track, artist, playlist, label).
    """
    asyncio.run(
        _dl_async(
            source=source,
            output=output,
            quality=quality,
            max_workers=max_workers,
            embed_art=embed_art,
            no_cover=no_cover,
            og_cover=og_cover,
            albums_only=albums_only,
            no_m3u=no_m3u,
            no_fallback=no_fallback,
            smart_discography=smart_discography,
            dry_run=dry_run,
            download_archive=download_archive,
        )
    )


async def _dl_async(**kwargs):
    """Asynchronous core logic for the 'dl' command."""
    if not os.path.isfile(CONFIG_FILE):
        log.error(
            "Configuration file not found. Please run qobuz-dl init to create it."
        )
        raise typer.Exit(code=1)

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    default = config["DEFAULT"]

    qobuz = None
    try:
        qobuz = QobuzDL(
            quality=kwargs["quality"] or default["default_quality"],
            max_workers=kwargs["max_workers"],
            output_template=kwargs["output"]
            or default.get("output_template", DEFAULT_OUTPUT_TEMPLATE),
            embed_art=kwargs["embed_art"] or config.getboolean("DEFAULT", "embed_art"),
            ignore_singles_eps=kwargs["albums_only"]
            or config.getboolean("DEFAULT", "albums_only"),
            no_m3u_for_playlists=kwargs["no_m3u"]
            or config.getboolean("DEFAULT", "no_m3u"),
            quality_fallback=not (
                kwargs["no_fallback"] or config.getboolean("DEFAULT", "no_fallback")
            ),
            cover_og_quality=kwargs["og_cover"]
            or config.getboolean("DEFAULT", "og_cover"),
            no_cover=kwargs["no_cover"] or config.getboolean("DEFAULT", "no_cover"),
            smart_discography=kwargs["smart_discography"]
            or config.getboolean("DEFAULT", "smart_discography"),
            dry_run=kwargs["dry_run"],
            download_archive=kwargs["download_archive"],
            config_path=CONFIG_PATH,
        )

        token = default.get("token")
        email = default.get("email")
        password = default.get("password")
        app_id = default["app_id"]
        secrets = [secret for secret in default["secrets"].split(",") if secret]

        if token:
            await qobuz.initialize_client_via_token(token, app_id, secrets)
        elif email and password:
            await qobuz.initialize_client(email, password, app_id, secrets)
        else:
            log.error(
                "No valid credentials found. Please run qobuz-dl init to set them."
            )
            raise typer.Exit(code=1)

        await qobuz.download_list_of_urls(kwargs["source"])

    except (KeyError, configparser.Error) as error:
        log.error(
            f"Your config file is corrupted: {error}! Please run qobuz-dl init to fix it."
        )
        raise typer.Exit(code=1)
    except AuthenticationError as e:
        log.error(
            f"Authentication failed: {e}. Please run qobuz-dl init again with valid credentials."
        )
        raise typer.Exit(code=1)
    except Exception as e:
        log.error(f"An unexpected error occurred: {e}", exc_info=True)
        raise typer.Exit(code=1)
    finally:
        if qobuz:
            if not qobuz.dry_run:
                for directory in qobuz.output_dirs:
                    _remove_leftovers(directory)
                if not qobuz.output_dirs:
                    _remove_leftovers(".")
            if qobuz.client:
                await qobuz.client.close()
            qobuz.print_summary()


# --- Main Entry Point ---
def main():
    """Main function to run the Typer application."""
    try:
        app()
    except (typer.Exit, typer.Abort):
        pass
    except KeyboardInterrupt:
        log.warning("\nInterrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
