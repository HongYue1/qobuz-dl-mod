"""
Core application logic for downloading from Qobuz.

The QobuzDL class orchestrates the entire process, from parsing URLs
to managing concurrent downloads and handling different content types
like albums, artists, and playlists.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

import aiohttp
from bs4 import BeautifulSoup as bso
from pathvalidate import sanitize_filename
from rich.console import Console
from rich.panel import Panel

from qobuz_dl import downloader, qopy
from qobuz_dl.downloader import _get_content_length
from qobuz_dl.progress import get_rich_bytes_progress, get_rich_files_progress
from qobuz_dl.utils import (
    create_and_return_dir,
    get_url_info,
    make_m3u,
    smart_discography_filter,
)

log = logging.getLogger(__name__)
console = Console()

# --- Constants ---

# CSS selectors for scraping Last.fm playlist pages.
ARTISTS_SELECTOR = "td.chartlist-artist > a"
TITLE_SELECTOR = "td.chartlist-name > a"

# Human-readable mapping for quality IDs.
QUALITIES = {
    5: "5 - MP3 (320 kbps)",
    6: "6 - CD-Lossless (16-bit / 44.1kHz)",
    7: "7 - Hi-Res (24-bit / up to 96kHz)",
    27: "27 - Hi-Res (24-bit / up to 192kHz)",
}


@dataclass
class DownloadStats:
    """A simple class to hold statistics for a download session."""

    tracks_downloaded: int = 0
    tracks_skipped_archive: int = 0
    tracks_skipped_exists: int = 0
    tracks_failed: int = 0
    total_size_downloaded: int = 0
    albums_processed: set = field(default_factory=set)


class QobuzDL:
    """
    Orchestrates the downloading process from Qobuz.
    """

    def __init__(self, **kwargs):
        """Initializes the QobuzDL client with user-defined settings."""
        self.quality = kwargs.get("quality", 6)
        self.max_workers = kwargs.get("max_workers", 8)
        self.output_template = kwargs.get("output_template")
        self.embed_art = kwargs.get("embed_art", False)
        self.ignore_singles_eps = kwargs.get("ignore_singles_eps", False)
        self.no_m3u_for_playlists = kwargs.get("no_m3u_for_playlists", False)
        self.quality_fallback = kwargs.get("quality_fallback", True)
        self.cover_og_quality = kwargs.get("cover_og_quality", False)
        self.no_cover = kwargs.get("no_cover", False)
        self.smart_discography = kwargs.get("smart_discography", False)
        self.dry_run = kwargs.get("dry_run", False)
        self.download_archive = kwargs.get("download_archive", False)
        self.client = None
        self.archive_ids = set()
        self.output_dirs = set()  # Track output directories for later cleanup.

        self.stats = DownloadStats()
        self.start_time = time.time()

        if self.download_archive:
            config_path = kwargs.get("config_path")
            if config_path:
                self.archive_file = os.path.join(config_path, "download_archive.txt")
                self._load_archive()

    def print_summary(self):
        """Prints a summary of the download session."""
        end_time = time.time()
        elapsed_seconds = end_time - self.start_time
        elapsed_time = time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))

        total_processed = (
            self.stats.tracks_downloaded
            + self.stats.tracks_skipped_archive
            + self.stats.tracks_skipped_exists
            + self.stats.tracks_failed
        )
        if total_processed == 0 and not self.dry_run:
            log.info("No tracks were processed in this session.")
            return

        size_mb = self.stats.total_size_downloaded / (1024 * 1024)
        size_str = f"{size_mb:.2f} MiB"

        summary_text = (
            f"[bold]Albums/Playlists Processed:[/] {len(self.stats.albums_processed)}\n"
            f"[green]Tracks Downloaded:[/] {self.stats.tracks_downloaded}\n"
            f"[yellow]Skipped (in archive):[/] {self.stats.tracks_skipped_archive}\n"
            f"[yellow]Skipped (already exists):[/] {self.stats.tracks_skipped_exists}\n"
            f"[red]Tracks Failed:[/] {self.stats.tracks_failed}\n\n"
            f"[bold]Total Size Downloaded:[/] {size_str}\n"
            f"[bold]Time Elapsed:[/] {elapsed_time}"
        )

        title = "Dry Run Summary" if self.dry_run else "Download Session Summary"
        console.print(
            Panel(summary_text, title=f"[bold cyan]{title}[/bold cyan]", expand=False)
        )

    def _load_archive(self):
        """Loads track IDs from the download archive file into a set for quick lookups."""
        try:
            with open(self.archive_file, "r") as f:
                self.archive_ids = {line.strip() for line in f}
            log.info(
                f"Loaded {len(self.archive_ids)} track IDs from the download archive."
            )
        except FileNotFoundError:
            log.info("Download archive not found. A new one will be created.")

    def is_in_archive(self, track_id):
        """Checks if a track ID is present in the download archive."""
        return str(track_id) in self.archive_ids

    def add_to_archive(self, track_id):
        """Adds a track ID to the archive file and the in-memory set."""
        if self.dry_run or not self.download_archive:
            return
        track_id_str = str(track_id)
        if track_id_str not in self.archive_ids:
            with open(self.archive_file, "a") as f:
                f.write(f"{track_id_str}\n")
            self.archive_ids.add(track_id_str)

    async def initialize_client_via_token(self, token, app_id, secrets):
        """Initializes the API client using an authentication token."""
        self.client = qopy.Client(app_id, secrets)
        await self.client.auth_via_token(token)
        log.info(f"Set max quality: {QUALITIES.get(int(self.quality), 'Unknown')}\n")

    async def initialize_client(self, email, pwd, app_id, secrets):
        """Initializes the API client using an email and password."""
        self.client = qopy.Client(app_id, secrets)
        await self.client.auth(email, pwd)
        log.info(f"Set max quality: {QUALITIES.get(int(self.quality), 'Unknown')}\n")

    def _get_downloader(self, item_id, path=None):
        """Factory method to create a downloader instance with current settings."""
        return downloader.Download(
            client=self.client,
            item_id=item_id,
            path=path or ".",
            quality=int(self.quality),
            output_template=self.output_template,
            embed_art=self.embed_art,
            albums_only=self.ignore_singles_eps,
            downgrade_quality=self.quality_fallback,
            cover_og_quality=self.cover_og_quality,
            no_cover=self.no_cover,
            dry_run=self.dry_run,
            archive_checker=self.is_in_archive if self.download_archive else None,
            archive_adder=self.add_to_archive if self.download_archive else None,
            output_dirs=self.output_dirs,
            stats=self.stats,
        )

    async def _download_album(self, album_id, path=None):
        """Coordinates the download of a full album."""
        dloader = self._get_downloader(album_id, path)
        track_jobs = await dloader.get_album_tracks()

        if not track_jobs:
            return

        album_title = track_jobs[0]["album_or_track_metadata"]["title"]
        self.stats.albums_processed.add(album_title)

        if self.dry_run:
            for job in track_jobs:
                await self._get_downloader(
                    job["track_metadata"]["id"]
                )._download_and_tag(**job)
            return

        total_size = sum(job["track_url_dict"].get("size", 0) for job in track_jobs)
        if total_size > 0:
            progress = get_rich_bytes_progress()
            update_by_chunk = True
        else:
            progress = get_rich_files_progress()
            update_by_chunk = False

        with progress:
            task_id = progress.add_task(
                f"Downloading {album_title}", total=total_size or len(track_jobs)
            )
            semaphore = asyncio.Semaphore(self.max_workers)

            async def download_with_semaphore(job):
                async with semaphore:
                    try:
                        await self._get_downloader(
                            job["track_metadata"]["id"]
                        )._download_and_tag(
                            **job,
                            progress=progress,
                            task_id=task_id,
                            update_by_chunk=update_by_chunk,
                        )
                    except Exception as e:
                        log.error(f"A track download failed: {e}")
                        self.stats.tracks_failed += 1
                    finally:
                        if not update_by_chunk:
                            progress.update(task_id, advance=1)

            await asyncio.gather(*(download_with_semaphore(job) for job in track_jobs))

        log.info(f"Completed download of {album_title}")

    async def handle_url(self, url):
        """
        Parses a Qobuz URL and triggers the appropriate download action based on its type.
        """
        possibles = {
            "playlist": {"func": self.client.get_plist_meta, "iterable_key": "tracks"},
            "artist": {"func": self.client.get_artist_meta, "iterable_key": "albums"},
            "label": {"func": self.client.get_label_meta, "iterable_key": "albums"},
            "album": {"album": True, "func": None, "iterable_key": None},
            "track": {"album": False, "func": None, "iterable_key": None},
        }
        try:
            url_type, item_id = get_url_info(url)
            type_dict = possibles[url_type]
        except (KeyError, IndexError, TypeError):
            log.error(f'Invalid or unsupported URL: "{url}"')
            return

        if type_dict["func"] is None:
            if url_type == "album":
                await self._download_album(item_id)
            else:
                await self._get_downloader(item_id).download_track()
        else:
            content_generator = type_dict["func"](item_id)
            content = [item async for item in content_generator]
            if not content:
                log.warning(f"No content found for {url_type} ID {item_id}.")
                return

            content_name = content[0].get("name") or content[0].get("title", "Unknown")
            log.info(f"Downloading all music from {content_name} ({url_type})!")
            self.stats.albums_processed.add(content_name)
            new_path = create_and_return_dir(sanitize_filename(content_name))
            items = self._get_items_from_content(content, url_type, type_dict)

            if type_dict["iterable_key"] == "albums":
                for item in items:
                    await self._download_album(item["id"], new_path)
            else:
                track_ids = [item["id"] for item in items]
                await self._download_playlist_tracks(track_ids, new_path, content_name)

            if (
                url_type == "playlist"
                and not self.no_m3u_for_playlists
                and not self.dry_run
            ):
                make_m3u(new_path)

    def _get_items_from_content(self, content, url_type, type_dict):
        """Extracts a list of items (tracks or albums) from API response content."""
        items = [item[type_dict["iterable_key"]]["items"] for item in content][0]
        if self.smart_discography and url_type == "artist":
            return smart_discography_filter(items, save_space=True, skip_extras=True)
        return items

    async def download_list_of_urls(self, urls):
        """
        Iterates through a list of sources and handles each one.
        """
        if not urls or not isinstance(urls, list):
            log.info("Nothing to download.")
            return
        if self.dry_run:
            log.info(
                "[bold cyan]Dry run mode is enabled. No files will be written.[/bold cyan]\n"
            )

        for url in urls:
            if "last.fm" in url:
                await self.download_lastfm_pl(url)
            elif os.path.isfile(url):
                await self.download_from_txt_file(url)
            else:
                await self.handle_url(url)

    async def download_from_txt_file(self, txt_file):
        """Reads a text file line by line and downloads from each URL."""
        log.info(f"Processing URLs from file: {txt_file}")
        with open(txt_file, "r") as txt:
            try:
                urls = [
                    line.strip()
                    for line in txt.readlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
            except Exception as e:
                log.error(f"Could not read the text file: {e}")
                return
            await self.download_list_of_urls(urls)

    async def _search_track_id(self, query):
        """Searches for a track on Qobuz and returns its ID."""
        try:
            results = await self.client.search_tracks(query=query, limit=1)
            return results["tracks"]["items"][0]["id"]
        except (KeyError, IndexError):
            log.warning(f"Could not find a match for '{query}' on Qobuz. Skipping.")
            return None

    async def _download_playlist_tracks(self, track_ids, path, name):
        """Manages the concurrent download of a list of track IDs."""
        if not track_ids:
            return

        if self.download_archive:
            track_ids_to_skip = {
                str(tid) for tid in track_ids if self.is_in_archive(tid)
            }
            skipped_count = len(track_ids_to_skip)
            if skipped_count > 0:
                self.stats.tracks_skipped_archive += skipped_count
                log.info(f"Skipping {skipped_count} tracks (already in archive).")
            track_ids = [tid for tid in track_ids if str(tid) not in track_ids_to_skip]

        if not track_ids:
            return

        if self.dry_run:
            for track_id in track_ids:
                await self._get_downloader(track_id, path).download_track()
            return

        log.info("Calculating total playlist size...")
        meta_tasks = [self.client.get_track_url(tid, self.quality) for tid in track_ids]
        track_metas = await asyncio.gather(*meta_tasks, return_exceptions=True)

        track_metas = [meta for meta in track_metas if isinstance(meta, dict)]

        total_size = sum(meta.get("size", 0) for meta in track_metas)

        if total_size == 0:
            log.info("API did not provide file sizes, fetching them manually...")
            async with aiohttp.ClientSession() as session:
                sizes = await asyncio.gather(
                    *(
                        _get_content_length(session, meta["url"])
                        for meta in track_metas
                        if "url" in meta
                    )
                )
                total_size = sum(sizes)

        if total_size > 0:
            progress = get_rich_bytes_progress()
            update_by_chunk = True
        else:
            progress = get_rich_files_progress()
            update_by_chunk = False

        with progress:
            task_id = progress.add_task(
                f"Downloading {name}", total=total_size or len(track_ids)
            )
            semaphore = asyncio.Semaphore(self.max_workers)

            async def download_with_semaphore(track_id):
                async with semaphore:
                    try:
                        await self._get_downloader(track_id, path).download_track(
                            progress=progress,
                            task_id=task_id,
                            update_by_chunk=update_by_chunk,
                        )
                    except Exception as e:
                        log.error(f"A track download failed: {e}")
                        self.stats.tracks_failed += 1
                    finally:
                        if not update_by_chunk:
                            progress.update(task_id, advance=1)

            await asyncio.gather(*(download_with_semaphore(tid) for tid in track_ids))

        log.info(f"Completed download of {name}")

    async def download_lastfm_pl(self, playlist_url):
        """Scrapes a Last.fm playlist, searches for tracks on Qobuz, and downloads them."""
        log.info(f"Fetching Last.fm playlist: {playlist_url}")
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(playlist_url, timeout=10) as r,
            ):
                r.raise_for_status()
                content = await r.text()
        except aiohttp.ClientError as e:
            log.error(f"Failed to fetch Last.fm playlist: {e}")
            return

        soup = bso(content, "html.parser")
        artists = [artist.text.strip() for artist in soup.select(ARTISTS_SELECTOR)]
        titles = [title.text.strip() for title in soup.select(TITLE_SELECTOR)]
        track_list = [f"{artist} {title}" for artist, title in zip(artists, titles)]

        if not track_list:
            log.info("No tracks found on the Last.fm page.")
            return

        pl_title = sanitize_filename(soup.select_one("h1").text.strip())
        pl_directory = create_and_return_dir(pl_title)
        self.stats.albums_processed.add(pl_title)

        log.info(
            f"Searching for {len(track_list)} tracks from '{pl_title}' on Qobuz..."
        )
        tasks = [self._search_track_id(query) for query in track_list]

        with get_rich_files_progress() as progress:
            search_task_id = progress.add_task("Searching...", total=len(tasks))
            results = []
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                progress.update(search_task_id, advance=1)

        track_ids = [tid for tid in results if tid]

        if not track_ids:
            log.info("Could not find any matching tracks on Qobuz for this playlist.")
            return

        log.info(f"Found {len(track_ids)} tracks. Starting download...")
        await self._download_playlist_tracks(track_ids, pl_directory, pl_title)

        if not self.no_m3u_for_playlists and not self.dry_run:
            make_m3u(pl_directory)
