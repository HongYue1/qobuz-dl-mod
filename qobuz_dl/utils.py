"""
A collection of miscellaneous utility functions for file handling,
data filtering, and URL parsing.
"""

import logging
import os
import re

import mutagen
from mutagen.flac import FLAC
from mutagen.mp3 import EasyMP3

logger = logging.getLogger(__name__)

EXTENSIONS = (".mp3", ".flac")


def make_m3u(pl_directory: str):
    """
    Generates an M3U playlist file for all audio files found in a directory.
    """
    track_list = ["#EXTM3U"]
    pl_name = f"{os.path.basename(os.path.normpath(pl_directory))}.m3u"

    for local, _, files in os.walk(pl_directory):
        # Sort files to ensure a consistent track order, attempting a natural sort.
        files.sort(
            key=lambda f: [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", f)]
        )

        for file_ in files:
            if not file_.endswith(EXTENSIONS):
                continue

            audio_file_abs = os.path.join(local, file_)
            # Use relative paths in the M3U file.
            audio_file_rel = os.path.relpath(audio_file_abs, pl_directory)

            try:
                # Read metadata from the audio file to populate M3U info.
                audio = (
                    EasyMP3(audio_file_abs)
                    if file_.endswith(".mp3")
                    else FLAC(audio_file_abs)
                )
                title = audio.get("title", [os.path.splitext(file_)[0]])[0]
                artist = audio.get("artist", ["Unknown Artist"])[0]
                length = int(audio.info.length)
                track_list.append(f"#EXTINF:{length},{artist} - {title}")
                track_list.append(audio_file_rel)
            except (mutagen.MutagenError, KeyError, AttributeError) as e:
                logger.warning(
                    f"Could not read tags from '{audio_file_abs}' for M3U entry. Reason: {e}"
                )
                continue

    if len(track_list) > 1:
        m3u_path = os.path.join(pl_directory, pl_name)
        with open(m3u_path, "w", encoding="utf-8") as pl:
            pl.write("\n".join(track_list))
        logger.info(f"Created playlist file: {m3u_path}")


def smart_discography_filter(items: list, **kwargs) -> list:
    """
    Filters an artist's discography to remove duplicates, spam, and unwanted releases.

    This function intelligently groups albums by their base title, selects the
    highest quality version, and optionally removes deluxe/live editions.

    Args:
        items (list): A list of album dictionaries from the Qobuz API.
        **kwargs:
            save_space (bool): If true, prefers lower sampling rates at the highest bit depth.
            skip_extras (bool): If true, removes releases like deluxe, live, or collector's editions.

    Returns:
        list: The filtered list of album dictionaries.
    """
    save_space = kwargs.get("save_space", False)
    skip_extras = kwargs.get("skip_extras", False)

    if not items:
        return []

    requested_artist = items[0]["artist"]["name"]

    # This regex helps identify different types of releases.
    TYPE_REGEXES = {
        "remaster": r"(?i)(re)?master(ed)?",
        "extra": r"(?i)(anniversary|deluxe|live|collector|demo|expanded|remix|acoustic|instrumental)",
    }

    def is_type(album: dict, album_type: str) -> bool:
        """Checks if an album's title or version matches a given release type regex."""
        text = f"{album.get('title', '')} {album.get('version', '')}"
        return re.search(TYPE_REGEXES[album_type], text) is not None

    def get_base_title(album: dict) -> str:
        """
        Extracts a 'base' title by removing text in parentheses or brackets.
        This helps group different versions of the same album (e.g., "Album" and "Album (Deluxe)").
        """
        match = re.match(r"([^\(]+)(?:\s*[\(\[][^)]*[\)\]])*", album["title"])
        return match.group(1).strip().lower() if match else album["title"].lower()

    # 1. Group albums by their base title.
    title_grouped = {}
    for item in items:
        # Ignore albums where the main artist doesn't match (e.g., features).
        if item.get("artist", {}).get("name") != requested_artist:
            continue
        base_title = get_base_title(item)
        if base_title not in title_grouped:
            title_grouped[base_title] = []
        title_grouped[base_title].append(item)

    # 2. Process each group to find the best version.
    filtered_items = []
    for base_title, albums in title_grouped.items():
        # Find the best available quality within the group.
        best_bit_depth = max(a["maximum_bit_depth"] for a in albums)

        # Prefer higher sampling rate unless saving space.
        relevant_albums = [
            a for a in albums if a["maximum_bit_depth"] == best_bit_depth
        ]
        best_sampling_rate = (min if save_space else max)(
            a["maximum_sampling_rate"] for a in relevant_albums
        )

        # Prefer remasters if they exist.
        remaster_exists = any(is_type(a, "remaster") for a in albums)

        # Apply all filters to find the final candidate(s).
        candidates = []
        for album in albums:
            if (
                album["maximum_bit_depth"] == best_bit_depth
                and album["maximum_sampling_rate"] == best_sampling_rate
                and not (remaster_exists and not is_type(album, "remaster"))
                and not (skip_extras and is_type(album, "extra"))
            ):
                candidates.append(album)

        # If multiple candidates remain, they are likely identical; pick the first one.
        if candidates:
            filtered_items.append(candidates[0])

    return filtered_items


def create_and_return_dir(directory: str) -> str:
    """Creates a directory if it doesn't exist and returns the normalized path."""
    norm_path = os.path.normpath(directory)
    os.makedirs(norm_path, exist_ok=True)
    return norm_path


def get_url_info(url: str):
    """
    Parses a Qobuz URL to extract its type (album, track, etc.) and ID.
    Supports various Qobuz URL formats.
    """
    # Regex designed to match play.qobuz.com, open.qobuz.com, and www.qobuz.com URLs.
    match = re.search(
        r"/(album|artist|track|playlist|label)/"  # The content type
        r"[^/]+/"  # The slug/name (can be anything)
        r"([\w\d]+)",  # The ID
        url,
    )
    if match:
        return match.groups()

    # Fallback for simpler open.qobuz.com/{type}/{id} format
    match_simple = re.search(
        r"qobuz\.com/(album|artist|track|playlist|label)/([\w\d]+)", url
    )
    if match_simple:
        return match_simple.groups()

    return None
