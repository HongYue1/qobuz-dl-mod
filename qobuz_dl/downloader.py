import logging
import os

import requests
from pathvalidate import sanitize_filename, sanitize_filepath

import qobuz_dl.metadata as metadata
from qobuz_dl.color import OFF, GREEN, RED, YELLOW
from qobuz_dl.exceptions import NonStreamable

QL_DOWNGRADE = "FormatRestrictedByFormatAvailability"
# used in case of error
DEFAULT_FORMATS = {
    "MP3": [
        "{artist} - {album} ({year}) [MP3]",
        "{tracknumber}. {tracktitle}",
    ],
    "Unknown": [
        "{artist} - {album}",
        "{tracknumber}. {tracktitle}",
    ],
}

DEFAULT_FOLDER = "{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]"
DEFAULT_TRACK = "{tracknumber}. {tracktitle}"

logger = logging.getLogger(__name__)


class Download:
    def __init__(
        self,
        client,
        item_id: str,
        path: str,
        quality: int,
        embed_art: bool = False,
        albums_only: bool = False,
        downgrade_quality: bool = False,
        cover_og_quality: bool = False,
        no_cover: bool = False,
        folder_format=None,
        track_format=None,
    ):
        self.client = client
        self.item_id = item_id
        self.path = path
        self.quality = quality
        self.albums_only = albums_only
        self.embed_art = embed_art
        self.downgrade_quality = downgrade_quality
        self.cover_og_quality = cover_og_quality
        self.no_cover = no_cover
        self.folder_format = folder_format or DEFAULT_FOLDER
        self.track_format = track_format or DEFAULT_TRACK

    def download_id_by_type(self, track=True):
        if not track:
            return self.get_album_tracks()
        else:
            self.download_track()
            return []

    def get_album_tracks(self):
        """Gathers all track data for an album, but does not download. Returns a list of jobs for the executor."""
        meta = self.client.get_album_meta(self.item_id)

        if not meta.get("streamable"):
            raise NonStreamable("This release is not streamable")

        if self.albums_only and (
            meta.get("release_type") != "album"
            or meta.get("artist").get("name") == "Various Artists"
        ):
            logger.info(f"{OFF}Ignoring Single/EP/VA: {meta.get('title', 'n/a')}")
            return []

        album_title = _get_title(meta)
        format_info = self._get_format(meta)
        file_format, quality_met, bit_depth, sampling_rate = format_info

        if not self.downgrade_quality and not quality_met:
            logger.info(
                f"{OFF}Skipping {album_title} as it doesn't meet quality requirement"
            )
            return []

        logger.info(
            f"\n{YELLOW}Downloading: {album_title}\nQuality: {file_format} ({bit_depth or 'N/A'}/{sampling_rate or 'N/A'})\n"
        )
        album_attr = self._get_album_attr(
            meta, album_title, file_format, bit_depth, sampling_rate
        )

        # Use a safe format string for MP3s if the default is used
        current_folder_format = self.folder_format
        if file_format == "MP3" and (
            "bit_depth" in current_folder_format
            or "sampling_rate" in current_folder_format
        ):
            current_folder_format = DEFAULT_FORMATS["MP3"][0]
            logger.info(
                f"{YELLOW}Using MP3-safe folder format: {current_folder_format}"
            )

        sanitized_title = sanitize_filepath(current_folder_format.format(**album_attr))
        dirn = os.path.join(self.path, sanitized_title)
        os.makedirs(dirn, exist_ok=True)

        if not self.no_cover:
            _download_file(
                meta["image"]["large"],
                os.path.join(dirn, "cover.jpg"),
                "cover.jpg",
                self.cover_og_quality,
            )

        if "goodies" in meta:
            try:
                _download_file(
                    meta["goodies"][0]["url"],
                    os.path.join(dirn, "booklet.pdf"),
                    "booklet.pdf",
                )
            except Exception:
                pass

        track_jobs = []
        media_numbers = [track["media_number"] for track in meta["tracks"]["items"]]
        is_multiple = len(set(media_numbers)) > 1

        for i, track_meta in enumerate(meta["tracks"]["items"]):
            parse = self.client.get_track_url(track_meta["id"], fmt_id=self.quality)
            if "sample" in parse or not parse.get("sampling_rate"):
                logger.info(f"{OFF}Skipping demo track: {track_meta.get('title')}")
                continue

            is_mp3 = int(self.quality) == 5
            job = {
                "root_dir": dirn,
                "tmp_count": i,
                "track_url_dict": parse,
                "track_metadata": track_meta,
                "album_or_track_metadata": meta,
                "is_track": False,
                "is_mp3": is_mp3,
                "multiple": track_meta["media_number"] if is_multiple else None,
            }
            track_jobs.append(job)

        return track_jobs

    def download_track(self):
        parse = self.client.get_track_url(self.item_id, self.quality)

        if "sample" in parse or not parse.get("sampling_rate"):
            logger.info(f"{OFF}Demo. Skipping")
            return

        meta = self.client.get_track_meta(self.item_id)
        track_title = _get_title(meta)
        artist = _safe_get(meta, "performer", "name")
        logger.info(f"\n{YELLOW}Downloading: {artist} - {track_title}")
        format_info = self._get_format(meta, is_track_id=True, track_url_dict=parse)
        _, quality_met, bit_depth, sampling_rate = format_info

        if not self.downgrade_quality and not quality_met:
            logger.info(
                f"{OFF}Skipping {track_title} as it doesn't meet quality requirement"
            )
            return

        track_attr = self._get_track_attr(meta, track_title, bit_depth, sampling_rate)

        current_folder_format = self.folder_format
        if bit_depth is None and (
            "bit_depth" in current_folder_format
            or "sampling_rate" in current_folder_format
        ):
            current_folder_format = DEFAULT_FORMATS["MP3"][0]

        sanitized_title = sanitize_filepath(current_folder_format.format(**track_attr))
        dirn = os.path.join(self.path, sanitized_title)
        os.makedirs(dirn, exist_ok=True)

        if not self.no_cover:
            _download_file(
                meta["album"]["image"]["large"],
                os.path.join(dirn, "cover.jpg"),
                "cover.jpg",
                self.cover_og_quality,
            )

        is_mp3 = int(self.quality) == 5
        self._download_and_tag(dirn, 1, parse, meta, meta, True, is_mp3, False)
        logger.info(f"{GREEN}Completed")

    def _download_and_tag(
        self,
        root_dir,
        tmp_count,
        track_url_dict,
        track_metadata,
        album_or_track_metadata,
        is_track,
        is_mp3,
        multiple=None,
    ):
        extension = ".mp3" if is_mp3 else ".flac"
        try:
            url = track_url_dict["url"]
        except KeyError:
            logger.info(f"{OFF}Track not available for download")
            return

        if multiple:
            root_dir = os.path.join(root_dir, f"Disc {multiple}")
            os.makedirs(root_dir, exist_ok=True)

        filename = os.path.join(root_dir, f".{tmp_count:02}.tmp")
        track_title = track_metadata.get("title")
        artist = _safe_get(track_metadata, "performer", "name")
        filename_attr = self._get_filename_attr(artist, track_metadata, track_title)

        formatted_path = sanitize_filename(self.track_format.format(**filename_attr))
        final_file = os.path.join(root_dir, formatted_path)[:250] + extension

        if os.path.isfile(final_file):
            return

        _download_file(url, filename)
        tag_function = metadata.tag_mp3 if is_mp3 else metadata.tag_flac
        try:
            tag_function(
                filename,
                root_dir,
                final_file,
                track_metadata,
                album_or_track_metadata,
                is_track,
                self.embed_art,
            )
        except Exception as e:
            logger.error(f"{RED}Error tagging the file: {e}", exc_info=True)

    @staticmethod
    def _get_filename_attr(artist, track_metadata, track_title):
        return {
            "artist": artist,
            "albumartist": _safe_get(
                track_metadata, "album", "artist", "name", default=artist
            ),
            "bit_depth": track_metadata.get("maximum_bit_depth"),
            "sampling_rate": track_metadata.get("maximum_sampling_rate"),
            "tracktitle": track_title,
            "version": track_metadata.get("version"),
            "tracknumber": f"{track_metadata['track_number']:02}",
        }

    @staticmethod
    def _get_track_attr(meta, track_title, bit_depth, sampling_rate):
        return {
            "album": sanitize_filename(meta["album"]["title"]),
            "artist": sanitize_filename(meta["album"]["artist"]["name"]),
            "tracktitle": track_title,
            "year": meta["album"]["release_date_original"].split("-")[0],
            "bit_depth": bit_depth,
            "sampling_rate": sampling_rate,
        }

    @staticmethod
    def _get_album_attr(meta, album_title, file_format, bit_depth, sampling_rate):
        return {
            "artist": sanitize_filename(meta["artist"]["name"]),
            "album": sanitize_filename(album_title),
            "year": meta["release_date_original"].split("-")[0],
            "format": file_format,
            "bit_depth": bit_depth,
            "sampling_rate": sampling_rate,
        }

    def _get_format(self, item_dict, is_track_id=False, track_url_dict=None):
        quality_met = True
        if int(self.quality) == 5:
            return ("MP3", quality_met, None, None)
        track_dict = item_dict if is_track_id else item_dict["tracks"]["items"][0]
        try:
            new_track_dict = track_url_dict or self.client.get_track_url(
                track_dict["id"], fmt_id=self.quality
            )
            if any(
                r.get("code") == QL_DOWNGRADE
                for r in new_track_dict.get("restrictions", [])
            ):
                quality_met = False
            return (
                "FLAC",
                quality_met,
                new_track_dict["bit_depth"],
                new_track_dict["sampling_rate"],
            )
        except (KeyError, requests.exceptions.HTTPError):
            return "Unknown", quality_met, None, None


def _download_file(url, fname, desc=None, og_quality=False):
    if og_quality:
        url = url.replace("_600.", "_org.")
    if os.path.isfile(fname):
        if desc:
            logger.info(f"{OFF}{desc} was already downloaded")
        return
    try:
        r = requests.get(url, allow_redirects=True, stream=True)
        r.raise_for_status()
        _ = int(r.headers.get("content-length", 0))
        with open(fname, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    except requests.exceptions.RequestException as e:
        logger.error(f"{RED}Error downloading {fname}: {e}")


def _get_title(item_dict):
    album_title = item_dict["title"]
    version = item_dict.get("version")
    if version and version.lower() not in album_title.lower():
        album_title = f"{album_title} ({version})"
    return album_title


def _safe_get(d: dict, *keys, default=None):
    curr = d
    for key in keys:
        res = curr.get(key)
        if res is None:
            return default
        curr = res
    return res
