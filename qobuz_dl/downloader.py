"""
Handles the lower-level download logic for individual tracks and albums.

The Download class fetches metadata, determines the correct file format and quality,
manages the download of audio files and associated assets (covers, booklets),
and orchestrates the final metadata tagging process.
"""

import asyncio
import logging
import os
import re

import aiohttp
import aiofiles
from pathvalidate import sanitize_filename, sanitize_filepath

import qobuz_dl.metadata as metadata
from qobuz_dl.exceptions import NonStreamable
from qobuz_dl.progress import get_rich_bytes_progress, get_rich_files_progress

log = logging.getLogger(__name__)

# --- Constants ---

QL_DOWNGRADE = "FormatRestrictedByFormatAvailability"

# NEW: The default template now intelligently handles multi-disc albums.
DEFAULT_OUTPUT_TEMPLATE = os.path.join(
    "{albumartist}",
    "{album} ({year})",
    "%{?is_multidisc,Disc {media_number}/|%}{tracknumber} - {tracktitle}.{ext}",
)


async def _get_content_length(session, url):
    """
    Performs an efficient HEAD request to get the size of a remote file.
    """
    try:
        async with session.head(url, allow_redirects=True, timeout=10) as response:
            response.raise_for_status()
            return int(response.headers.get("Content-Length", 0))
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError):
        return 0


class Download:
    """
    Manages the download and processing of a single Qobuz item (album or track).
    """

    def __init__(self, **kwargs):
        """Initializes a Download instance with specific settings."""
        self.client = kwargs["client"]
        self.item_id = kwargs["item_id"]
        self.path = kwargs["path"]
        self.quality = kwargs["quality"]
        self.output_template = kwargs.get("output_template") or DEFAULT_OUTPUT_TEMPLATE
        self.albums_only = kwargs.get("albums_only", False)
        self.embed_art = kwargs.get("embed_art", False)
        self.downgrade_quality = kwargs.get("downgrade_quality", False)
        self.cover_og_quality = kwargs.get("cover_og_quality", False)
        self.no_cover = kwargs.get("no_cover", False)
        self.dry_run = kwargs.get("dry_run", False)
        self.archive_checker = kwargs.get("archive_checker")
        self.archive_adder = kwargs.get("archive_adder")
        self.output_dirs = kwargs.get("output_dirs", set())
        self.stats = kwargs.get("stats")

    def _format_template_string(self, variables):
        """
        Formats the output template, supporting advanced conditional logic.
        Syntax: %{?key,value_if_true|value_if_false%}
        """
        template = self.output_template
        conditional_pattern = re.compile(r"%\{\?(\w+),([^|]*?)\|([^}]*?)\}")

        def replacer(match):
            key, true_val, false_val = match.groups()
            if variables.get(key):
                return true_val
            else:
                return false_val

        processed_template = conditional_pattern.sub(replacer, template)
        return processed_template.format(**variables)

    async def _get_format(self, item_dict, is_track_id=False, track_url_dict=None):
        """
        Determines the audio format and verifies if the desired quality is met.
        """
        quality_met = True
        if int(self.quality) == 5:
            return "MP3", quality_met, None, None

        track_dict = item_dict if is_track_id else item_dict["tracks"]["items"][0]
        try:
            new_track_dict = track_url_dict or await self.client.get_track_url(
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
                new_track_dict.get("bit_depth"),
                new_track_dict.get("sampling_rate"),
            )
        except (KeyError, aiohttp.ClientError):
            return "Unknown", False, None, None

    async def get_album_tracks(self):
        """
        Fetches metadata for all tracks in an album and prepares them for download.
        """
        meta = await self.client.get_album_meta(self.item_id)

        if not meta.get("streamable", False):
            raise NonStreamable("This release is not streamable on Qobuz.")

        if self.albums_only and (
            meta.get("release_type") != "album"
            or meta.get("artist", {}).get("name") == "Various Artists"
        ):
            log.info(f"Skipping non-album release: {meta.get('title', 'N/A')}")
            return []

        album_title = _get_title(meta)
        format_info = await self._get_format(meta)
        file_format, quality_met, bit_depth, sampling_rate = format_info

        if not self.downgrade_quality and not quality_met:
            log.info(
                f"Skipping '{album_title}' as it does not meet the quality requirement."
            )
            return []

        log.info(
            f"\n[bold]Album:[/] {album_title}\n[bold]Quality:[/] {file_format} "
            f"({bit_depth or 'N/A'}-bit / {sampling_rate or 'N/A'}kHz)"
        )

        track_metas = meta["tracks"]["items"]

        if self.archive_checker:
            track_metas_to_skip = {
                str(tm["id"])
                for tm in track_metas
                if self.archive_checker(tm.get("id"))
            }
            skipped_count = len(track_metas_to_skip)
            if skipped_count > 0:
                self.stats.tracks_skipped_archive += skipped_count
                log.info(f"Skipping {skipped_count} tracks (already in archive).")
            track_metas = [
                tm for tm in track_metas if str(tm.get("id")) not in track_metas_to_skip
            ]

        if not track_metas:
            return []

        track_ids_to_fetch = [tm.get("id") for tm in track_metas]

        parses = await asyncio.gather(
            *(
                self.client.get_track_url(tid, fmt_id=self.quality)
                for tid in track_ids_to_fetch
            )
        )

        if not any(p.get("size") or p.get("url_size") for p in parses):
            log.info("API did not provide file sizes, fetching them manually...")
            async with aiohttp.ClientSession() as session:
                sizes = await asyncio.gather(
                    *(
                        _get_content_length(session, p["url"])
                        for p in parses
                        if "url" in p
                    )
                )
                for i, size in enumerate(sizes):
                    if i < len(parses):
                        parses[i]["size"] = size

        track_meta_map = {tm["id"]: tm for tm in track_metas}

        track_jobs = []
        for parse in parses:
            track_id = parse.get("track_id")
            if "sample" in parse or not parse.get("sampling_rate") or not track_id:
                continue

            track_meta = track_meta_map.get(track_id)
            if not track_meta:
                continue

            parse["size"] = parse.get("size") or parse.get("url_size", 0)

            job = {
                "track_url_dict": parse,
                "track_metadata": track_meta,
                "album_or_track_metadata": meta,
                "is_track": False,
            }
            track_jobs.append(job)

        return track_jobs

    async def download_track(self, progress=None, task_id=None, update_by_chunk=True):
        """Manages the download of a single track."""
        meta = await self.client.get_track_meta(self.item_id)

        if self.archive_checker and self.archive_checker(meta["id"]):
            self.stats.tracks_skipped_archive += 1
            log.info(f"Skipping track (already in archive): {_get_title(meta)}")
            return

        parse = await self.client.get_track_url(self.item_id, self.quality)

        if "sample" in parse or not parse.get("sampling_rate"):
            log.info("Demo or sample track detected. Skipping.")
            return

        track_title = _get_title(meta)
        artist = _safe_get(meta, "performer", "name") or _safe_get(
            meta, "album", "artist", "name"
        )
        log.info(f"Downloading: {artist} - {track_title}")

        _, quality_met, _, _ = await self._get_format(
            meta, is_track_id=True, track_url_dict=parse
        )

        if not self.downgrade_quality and not quality_met:
            log.info(
                f"Skipping '{track_title}' as it does not meet the quality requirement."
            )
            return

        if not progress:
            total_size = parse.get("size") or parse.get("url_size", 0)
            if total_size == 0 and "url" in parse:
                async with aiohttp.ClientSession() as session:
                    total_size = await _get_content_length(session, parse["url"])
                parse["size"] = total_size

            prog = (
                get_rich_bytes_progress()
                if total_size > 0
                else get_rich_files_progress()
            )
            update_by_chunk = total_size > 0

            with prog as single_progress:
                single_task_id = single_progress.add_task(
                    f"Downloading {track_title}", total=total_size or 1
                )
                await self._download_and_tag(
                    track_url_dict=parse,
                    track_metadata=meta,
                    album_or_track_metadata=meta,
                    is_track=True,
                    progress=single_progress,
                    task_id=single_task_id,
                    update_by_chunk=update_by_chunk,
                )
                if not update_by_chunk:
                    single_progress.update(single_task_id, advance=1)
        else:
            await self._download_and_tag(
                track_url_dict=parse,
                track_metadata=meta,
                album_or_track_metadata=meta,
                is_track=True,
                progress=progress,
                task_id=task_id,
                update_by_chunk=update_by_chunk,
            )

        if not self.dry_run and not progress:
            log.info(f"Completed: {artist} - {track_title}")

    def _get_template_vars(self, track_meta, album_meta, track_url_dict):
        """
        Creates a dictionary of all available variables for formatting the output path.
        """
        effective_album_meta = album_meta.get("album", album_meta)
        artist = _safe_get(track_meta, "performer", "name") or _safe_get(
            effective_album_meta, "artist", "name"
        )
        album_artist = _safe_get(effective_album_meta, "artist", "name", default="")
        media_count = effective_album_meta.get("media_count", 1)

        return {
            "tracknumber": f"{track_meta.get('track_number', 0):02}",
            "tracktitle": sanitize_filename(_get_title(track_meta)),
            "artist": sanitize_filename(artist),
            "albumartist": sanitize_filename(album_artist),
            "album": sanitize_filename(effective_album_meta.get("title", "")),
            "year": str(
                _safe_get(effective_album_meta, "release_date_original", default="0")
            ).split("-")[0],
            "release_date": effective_album_meta.get("release_date_original", ""),
            "label": sanitize_filename(
                _safe_get(effective_album_meta, "label", "name", default="")
            ),
            "upc": effective_album_meta.get("upc", ""),
            "isrc": track_meta.get("isrc", ""),
            "bit_depth": track_url_dict.get("bit_depth", 0),
            "sampling_rate": int(track_url_dict.get("sampling_rate", 0) / 1000),
            "ext": "mp3" if int(self.quality) == 5 else "flac",
            "composer": sanitize_filename(
                _safe_get(track_meta, "composer", "name", default="")
            ),
            "release_type": effective_album_meta.get("release_type", "album"),
            "media_number": f"{track_meta.get('media_number', 1):02}",
            "media_count": media_count,
            "work": sanitize_filename(
                _safe_get(track_meta, "work", "name", default="")
            ),
            "version": sanitize_filename(effective_album_meta.get("version", "")),
            "copyright": effective_album_meta.get("copyright", ""),
            "genre": _safe_get(effective_album_meta, "genre", "name", default=""),
            "is_multidisc": 1 if media_count > 1 else 0,
        }

    async def _download_and_tag(self, **kwargs):
        """
        The core function that downloads a file, tags it, and renames it.
        """
        track_metadata = kwargs["track_metadata"]
        track_url_dict = kwargs["track_url_dict"]
        album_or_track_metadata = kwargs["album_or_track_metadata"]
        track_size = track_url_dict.get("size", 0)

        track_id = track_metadata.get("id")
        if self.archive_checker and self.archive_checker(track_id):
            return

        template_vars = self._get_template_vars(
            track_metadata, album_or_track_metadata, track_url_dict
        )
        final_file_path = self._format_template_string(template_vars)
        final_file = sanitize_filepath(final_file_path, platform="auto")
        final_dir = os.path.dirname(final_file) or self.path
        self.output_dirs.add(final_dir)

        if self.dry_run:
            self.stats.tracks_downloaded += 1
            log.info(f"[cyan]DRY RUN[/cyan]: Would save track to: {final_file}")
            return

        if os.path.isfile(final_file):
            self.stats.tracks_skipped_exists += 1
            log.info(f"Track already exists: {os.path.basename(final_file)}")
            if self.archive_adder:
                self.archive_adder(track_id)
            return

        os.makedirs(final_dir, exist_ok=True)

        try:
            url = track_url_dict["url"]
        except KeyError:
            log.warning(
                f"Track '{_get_title(track_metadata)}' not available for download. Skipping."
            )
            self.stats.tracks_failed += 1
            return

        effective_album_meta = album_or_track_metadata.get(
            "album", album_or_track_metadata
        )
        if not self.no_cover:
            image_url = _safe_get(effective_album_meta, "image", "large")
            if image_url:
                cover_path = os.path.join(final_dir, "cover.jpg")
                await _download_file(
                    image_url, cover_path, "cover art", self.cover_og_quality
                )
        if "goodies" in effective_album_meta:
            booklet_url = _safe_get(effective_album_meta, "goodies", 0, "url")
            if booklet_url and booklet_url.endswith(".pdf"):
                booklet_path = os.path.join(final_dir, "booklet.pdf")
                await _download_file(booklet_path, booklet_path, "booklet")

        temp_file = os.path.join(final_dir, f".{track_id}.tmp")

        download_successful = await _download_file(
            url,
            temp_file,
            progress=kwargs.get("progress"),
            task_id=kwargs.get("task_id"),
            update_by_chunk=kwargs.get("update_by_chunk", True),
        )

        if not download_successful:
            self.stats.tracks_failed += 1
            log.error(
                f"Skipping tagging for '{_get_title(track_metadata)}' because its download failed."
            )
            return

        is_mp3 = int(self.quality) == 5
        tag_function = metadata.tag_mp3 if is_mp3 else metadata.tag_flac
        try:
            await asyncio.to_thread(
                tag_function,
                filename=temp_file,
                final_name=final_file,
                track_meta=track_metadata,
                album_meta=album_or_track_metadata,
                is_track=kwargs["is_track"],
                embed_art=self.embed_art,
            )
            if self.archive_adder:
                self.archive_adder(track_id)
            self.stats.tracks_downloaded += 1
            self.stats.total_size_downloaded += track_size
        except Exception as e:
            self.stats.tracks_failed += 1
            log.error(f"Error tagging '{final_file}': {e}", exc_info=True)


async def _download_file(
    url,
    fname,
    desc=None,
    og_quality=False,
    progress=None,
    task_id=None,
    update_by_chunk=True,
):
    """
    Asynchronously downloads a file from a URL, with progress reporting.
    Returns True on success, False on failure.
    """
    if og_quality:
        url = url.replace("_600.", "_org.")

    if os.path.isfile(fname):
        log.debug(
            f"{desc or 'File'} '{os.path.basename(fname)}' already exists. Skipping."
        )
        return True

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, allow_redirects=True) as r,
        ):
            r.raise_for_status()
            async with aiofiles.open(fname, "wb") as f:
                async for chunk in r.content.iter_chunked(8192):
                    await f.write(chunk)
                    if progress is not None and task_id is not None and update_by_chunk:
                        progress.update(task_id, advance=len(chunk))
        return True
    except aiohttp.ClientError as e:
        log.error(f"Error downloading {desc or fname}: {e}")
        if os.path.exists(fname):
            os.remove(fname)
        return False


def _get_title(item_dict):
    """Constructs a full title including the version, if available."""
    title = item_dict.get("title", "Unknown Title")
    version = item_dict.get("version")
    if version and version.lower() not in title.lower():
        title = f"{title} ({version})"
    return title


def _safe_get(d: dict, *keys, default=None):
    """
    Safely access nested dictionary keys without raising a KeyError.
    """
    for key in keys:
        try:
            d = d[key]
        except (KeyError, TypeError, IndexError, AttributeError):
            return default
    return d
