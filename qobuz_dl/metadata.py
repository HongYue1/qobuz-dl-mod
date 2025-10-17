"""
Handles writing metadata tags to FLAC and MP3 files using the Mutagen library.
"""

import logging
import os
import re

from mutagen.flac import FLAC, Picture
import mutagen.id3 as id3
from mutagen.id3 import ID3NoHeaderError

log = logging.getLogger(__name__)

# --- Constants ---

# Unicode symbols for copyright characters.
COPYRIGHT, PHON_COPYRIGHT = "\u00a9", "\u2117"

# FLAC metadata blocks have a maximum size. Very large cover images can exceed this.
FLAC_MAX_BLOCKSIZE = 16777215

# Mapping of our internal metadata keys to Mutagen's ID3 frame classes.
# This makes it easy to add or change which tags are written.
ID3_LEGEND = {
    "album": id3.TALB,
    "albumartist": id3.TPE2,
    "artist": id3.TPE1,
    "comment": id3.COMM,
    "composer": id3.TCOM,
    "copyright": id3.TCOP,
    "date": id3.TDAT,
    "genre": id3.TCON,
    "isrc": id3.TSRC,
    "label": id3.TPUB,
    "performer": id3.TOPE,
    "title": id3.TIT2,
    "year": id3.TYER,
    "upc": (id3.TXXX, {"desc": "BARCODE"}),  # Custom TXXX frame for barcode/UPC
    "compilation": (id3.TCMP, {}),  # Flag for compilations
}


# --- Helper Functions ---


def _get_title(track_dict):
    """Constructs a full, descriptive title for a track, including version or work."""
    title = track_dict["title"]
    if version := track_dict.get("version"):
        title = f"{title} ({version})"
    if work := track_dict.get("work"):
        title = f"{work}: {title}"
    return title


def _format_copyright(s: str) -> str:
    """Replaces (P) and (C) with their proper Unicode symbols."""
    if s:
        s = s.replace("(P)", PHON_COPYRIGHT)
        s = s.replace("(C)", COPYRIGHT)
    return s


def _get_genres(genres_list: list) -> list:
    """Parses Qobuz's sometimes messy genre strings into a clean list."""
    if not genres_list:
        return []
    # Qobuz genres can be like "Rock/Pop -> Indie Rock". This extracts distinct genres.
    genres = re.findall(r"([^\u2192\/]+)", "/".join(genres_list))
    # Remove duplicates while preserving order.
    return list(dict.fromkeys(g.strip() for g in genres))


def _embed_flac_img(root_dir: str, audio: FLAC):
    """Finds a 'cover.jpg' in the given directory and embeds it into a FLAC file."""
    cover_image_path = os.path.join(root_dir, "cover.jpg")
    if not os.path.isfile(cover_image_path):
        return

    try:
        if os.path.getsize(cover_image_path) > FLAC_MAX_BLOCKSIZE:
            raise ValueError(
                "Cover size is too large to embed in FLAC. "
                "Disable og_cover or embed_art to avoid this."
            )

        image = Picture()
        image.type = 3  # 3 indicates front cover art.
        image.mime = "image/jpeg"
        image.desc = "cover"
        with open(cover_image_path, "rb") as img:
            image.data = img.read()

        audio.clear_pictures()
        audio.add_picture(image)
    except Exception as e:
        log.error(f"Failed to embed cover image: {e}", exc_info=True)


def _embed_id3_img(root_dir: str, audio: id3.ID3):
    """Finds a 'cover.jpg' and embeds it into an MP3 file's ID3 tags."""
    cover_image_path = os.path.join(root_dir, "cover.jpg")
    if not os.path.isfile(cover_image_path):
        return

    with open(cover_image_path, "rb") as cover:
        # APIC: is the frame for Attached Picture.
        if "APIC:" in audio:
            del audio["APIC:"]
        audio.add(
            id3.APIC(
                encoding=3,  # 3 is UTF-8.
                mime="image/jpeg",
                type=3,  # 3 is front cover.
                desc="Cover",
                data=cover.read(),
            )
        )


def tag_flac(**kwargs):
    """Tags a FLAC file with metadata, embeds art, and renames it."""
    filename = kwargs["filename"]
    final_name = kwargs["final_name"]
    track_meta = kwargs["track_meta"]
    album_meta = kwargs["album_meta"]
    is_track = kwargs["is_track"]
    embed_art = kwargs["embed_art"]

    audio = FLAC(filename)
    final_dir = os.path.dirname(final_name)
    effective_album_meta = (
        track_meta.get("album", album_meta) if is_track else album_meta
    )

    # Write tags using Vorbis Comment keys.
    audio["TITLE"] = _get_title(track_meta)
    audio["TRACKNUMBER"] = str(track_meta.get("track_number"))
    audio["TRACKTOTAL"] = str(effective_album_meta.get("tracks_count"))
    if track_meta.get("media_number", 0) > 1:
        audio["DISCNUMBER"] = str(track_meta.get("media_number"))
        if effective_album_meta.get("media_count"):
            audio["DISCTOTAL"] = str(effective_album_meta.get("media_count"))
    if track_meta.get("isrc"):
        audio["ISRC"] = track_meta["isrc"]
    if track_meta.get("composer"):
        audio["COMPOSER"] = track_meta["composer"]["name"]

    track_artist = track_meta.get("performer", {}).get("name")
    album_artist = effective_album_meta["artist"]["name"]
    audio["ARTIST"] = track_artist or album_artist
    audio["ALBUMARTIST"] = album_artist

    audio["ALBUM"] = effective_album_meta["title"]
    audio["GENRE"] = _get_genres(effective_album_meta.get("genres_list", []))
    audio["DATE"] = effective_album_meta.get("release_date_original")
    if label := effective_album_meta.get("label", {}).get("name"):
        audio["ORGANIZATION"] = label
    if upc := effective_album_meta.get("upc"):
        audio["BARCODE"] = upc
    if album_artist.lower() == "various artists":
        audio["COMPILATION"] = "1"

    copyright_info = track_meta.get("copyright") or effective_album_meta.get(
        "copyright"
    )
    if copyright_info:
        audio["COPYRIGHT"] = _format_copyright(copyright_info)

    if embed_art:
        _embed_flac_img(final_dir, audio)

    audio.save()
    os.rename(filename, final_name)


def tag_mp3(**kwargs):
    """Tags an MP3 file with metadata, embeds art, and renames it."""
    filename = kwargs["filename"]
    final_name = kwargs["final_name"]
    track_meta = kwargs["track_meta"]
    album_meta = kwargs["album_meta"]
    is_track = kwargs["is_track"]
    embed_art = kwargs["embed_art"]

    try:
        audio = id3.ID3(filename)
    except ID3NoHeaderError:
        audio = id3.ID3()

    final_dir = os.path.dirname(final_name)
    effective_album_meta = (
        track_meta.get("album", album_meta) if is_track else album_meta
    )

    # Prepare a dictionary of tags to be written.
    tags = {
        "title": _get_title(track_meta),
        "isrc": track_meta.get("isrc"),
        "composer": track_meta.get("composer", {}).get("name"),
        "artist": track_meta.get("performer", {}).get("name")
        or effective_album_meta["artist"]["name"],
        "albumartist": effective_album_meta["artist"]["name"],
        "album": effective_album_meta["title"],
        "genre": "/".join(_get_genres(effective_album_meta.get("genres_list", []))),
        "date": effective_album_meta.get("release_date_original"),
        "year": str(effective_album_meta.get("release_date_original", "0"))[:4],
        "label": effective_album_meta.get("label", {}).get("name"),
        "upc": effective_album_meta.get("upc"),
        "compilation": "1"
        if effective_album_meta["artist"]["name"].lower() == "various artists"
        else None,
        "copyright": _format_copyright(
            track_meta.get("copyright") or effective_album_meta.get("copyright")
        ),
    }

    # Handle special frames like track/disc numbers.
    track_total = str(effective_album_meta.get("tracks_count", ""))
    audio["TRCK"] = id3.TRCK(
        encoding=3, text=f"{track_meta.get('track_number')}/{track_total}"
    )
    if track_meta.get("media_number", 0) > 1:
        disc_total = str(effective_album_meta.get("media_count", ""))
        audio["TPOS"] = id3.TPOS(
            encoding=3, text=f"{track_meta.get('media_number')}/{disc_total}"
        )

    # Write tags from the dictionary using the ID3_LEGEND map.
    for key, value in tags.items():
        if not value:
            continue
        frame_info = ID3_LEGEND[key]
        kwargs = {"encoding": 3, "text": value}
        if isinstance(frame_info, tuple):
            frame_class, custom_args = frame_info
            kwargs.update(custom_args)
            audio.add(frame_class(**kwargs))
        else:
            audio.add(frame_info(**kwargs))

    if embed_art:
        _embed_id3_img(final_dir, audio)

    audio.save(filename, v2_version=3)
    os.rename(filename, final_name)
