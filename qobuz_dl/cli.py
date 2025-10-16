import configparser
import hashlib
import logging
import glob
import os
import sys

from qobuz_dl.bundle import Bundle
from qobuz_dl.color import GREEN, RED, YELLOW
from qobuz_dl.commands import qobuz_dl_args
from qobuz_dl.core import QobuzDL
from qobuz_dl.downloader import DEFAULT_FOLDER, DEFAULT_TRACK

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

if os.name == "nt":
    OS_CONFIG = os.environ.get("APPDATA")
else:
    OS_CONFIG = os.path.join(os.environ["HOME"], ".config")

CONFIG_PATH = os.path.join(OS_CONFIG, "qobuz-dl")
CONFIG_FILE = os.path.join(CONFIG_PATH, "config.ini")


def _create_or_update_config(config_file, credentials):
    logging.info(f"{YELLOW}Creating or updating config file: {config_file}")
    config = configparser.ConfigParser()
    config["DEFAULT"] = {}

    if len(credentials) == 1:
        config["DEFAULT"]["token"] = credentials[0]
        config["DEFAULT"]["email"] = ""
        config["DEFAULT"]["password"] = ""
        logging.info(f"{GREEN}Authentication method set to token.")
    elif len(credentials) == 2:
        email, password = credentials
        config["DEFAULT"]["email"] = email
        config["DEFAULT"]["password"] = hashlib.md5(
            password.encode("utf-8")
        ).hexdigest()
        config["DEFAULT"]["token"] = ""
        logging.info(f"{GREEN}Authentication method set to email/password.")
    else:
        sys.exit(
            f"{RED}Invalid arguments for init. Use 'qobuz-dl init <token>' or 'qobuz-dl init <email> <password>'."
        )

    config["DEFAULT"]["default_folder"] = "Qobuz Downloads"
    config["DEFAULT"]["default_quality"] = "6"
    config["DEFAULT"]["default_limit"] = "20"
    config["DEFAULT"]["no_m3u"] = "false"
    config["DEFAULT"]["albums_only"] = "false"
    config["DEFAULT"]["no_fallback"] = "false"
    config["DEFAULT"]["og_cover"] = "false"
    config["DEFAULT"]["embed_art"] = "false"
    config["DEFAULT"]["no_cover"] = "false"

    logging.info(f"{YELLOW}Getting tokens. Please wait...")
    bundle = Bundle()
    config["DEFAULT"]["app_id"] = str(bundle.get_app_id())
    config["DEFAULT"]["secrets"] = ",".join(bundle.get_secrets().values())
    config["DEFAULT"]["folder_format"] = DEFAULT_FOLDER
    config["DEFAULT"]["track_format"] = DEFAULT_TRACK
    config["DEFAULT"]["smart_discography"] = "false"

    with open(config_file, "w") as configfile:
        config.write(configfile)
    logging.info(
        f"{GREEN}Config file saved. You can edit it at {config_file} to change default options."
    )


def _remove_leftovers(directory):
    directory = os.path.join(directory, "**", ".*.tmp")
    for i in glob.glob(directory, recursive=True):
        try:
            os.remove(i)
        except:  # noqa
            pass


def _handle_commands(qobuz, arguments):
    try:
        if arguments.command == "dl":
            qobuz.download_list_of_urls(arguments.SOURCE)
    except KeyboardInterrupt:
        logging.info(f"{RED}Interrupted by user.")
    finally:
        _remove_leftovers(qobuz.directory)


def main():
    parser = qobuz_dl_args()
    arguments = parser.parse_args()

    # Handle top-level flags that should execute and exit immediately
    if arguments.show_config:
        if not os.path.isfile(CONFIG_FILE):
            sys.exit(
                f"{RED}Config file not found. Run 'qobuz-dl init ...' to create one."
            )
        print(f"Configuration: {CONFIG_FILE}\n---")
        with open(CONFIG_FILE, "r") as f:
            print(f.read())
        sys.exit()

    if arguments.reset:
        sys.exit(
            f"{YELLOW}The '-r' or '--reset' flag is an alias for the 'init' command.\n"
            "Please use 'qobuz-dl init' to configure your credentials."
        )

    # If no command is given, print help and exit
    if not arguments.command:
        parser.print_help()
        sys.exit(f"\n{RED}Error: A command (e.g., 'init', 'dl') is required.")

    # Handle commands
    if arguments.command == "init":
        os.makedirs(CONFIG_PATH, exist_ok=True)
        _create_or_update_config(CONFIG_FILE, arguments.credentials)
        sys.exit()

    # For the 'dl' command, a config file is required.
    if not os.path.isfile(CONFIG_FILE):
        sys.exit(
            f"{RED}Configuration file not found. Please run 'qobuz-dl init ...' to create it."
        )

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    try:
        email = config["DEFAULT"]["email"]
        password = config["DEFAULT"]["password"]
        token = config["DEFAULT"]["token"]
        app_id = config["DEFAULT"]["app_id"]
        secrets = [
            secret for secret in config["DEFAULT"]["secrets"].split(",") if secret
        ]

        # Re-parse arguments to ensure we have them all, using config for defaults
        parser = qobuz_dl_args(
            default_quality=config["DEFAULT"]["default_quality"],
            default_folder=config["DEFAULT"]["default_folder"],
        )
        arguments = parser.parse_args()

    except (KeyError, configparser.Error) as error:
        sys.exit(
            f"{RED}Your config file is corrupted: {error}! "
            "Run 'qobuz-dl init ...' to fix this."
        )

    qobuz = QobuzDL(
        directory=arguments.directory,
        quality=arguments.quality,
        max_workers=arguments.max_workers,
        embed_art=arguments.embed_art or config.getboolean("DEFAULT", "embed_art"),
        ignore_singles_eps=arguments.albums_only
        or config.getboolean("DEFAULT", "albums_only"),
        no_m3u_for_playlists=arguments.no_m3u or config.getboolean("DEFAULT", "no_m3u"),
        quality_fallback=not arguments.no_fallback
        or not config.getboolean("DEFAULT", "no_fallback"),
        cover_og_quality=arguments.og_cover or config.getboolean("DEFAULT", "og_cover"),
        no_cover=arguments.no_cover or config.getboolean("DEFAULT", "no_cover"),
        folder_format=arguments.folder_format or config["DEFAULT"]["folder_format"],
        track_format=arguments.track_format or config["DEFAULT"]["track_format"],
        smart_discography=arguments.smart_discography
        or config.getboolean("DEFAULT", "smart_discography"),
    )

    if token:
        qobuz.initialize_client_via_token(token, app_id, secrets)
    elif email and password:
        qobuz.initialize_client(email, password, app_id, secrets)
    else:
        sys.exit(
            f"{RED}No valid credentials found in config file. "
            "Run 'qobuz-dl init ...' to set them."
        )

    _handle_commands(qobuz, arguments)


if __name__ == "__main__":
    sys.exit(main())
