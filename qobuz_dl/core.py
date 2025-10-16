import logging
import os
import concurrent.futures

import requests
from bs4 import BeautifulSoup as bso
from pathvalidate import sanitize_filename
from tqdm import tqdm

from qobuz_dl import downloader, qopy
from qobuz_dl.color import OFF, RED, YELLOW, GREEN
from qobuz_dl.utils import (
    get_url_info,
    make_m3u,
    smart_discography_filter,
    create_and_return_dir,
)

WEB_URL = "https://play.qobuz.com/"
ARTISTS_SELECTOR = "td.chartlist-artist > a"
TITLE_SELECTOR = "td.chartlist-name > a"
QUALITIES = {
    5: "5 - MP3",
    6: "6 - 16 bit, 44.1kHz",
    7: "7 - 24 bit, <96kHz",
    27: "27 - 24 bit, >96kHz",
}

logger = logging.getLogger(__name__)


class QobuzDL:
    def __init__(
        self,
        directory="Qobuz Downloads",
        quality=6,
        max_workers=8,
        embed_art=False,
        ignore_singles_eps=False,
        no_m3u_for_playlists=False,
        quality_fallback=True,
        cover_og_quality=False,
        no_cover=False,
        folder_format="{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]",
        track_format="{tracknumber}. {tracktitle}",
        smart_discography=False,
    ):
        self.directory = create_and_return_dir(directory)
        self.quality = quality
        self.max_workers = max_workers
        self.embed_art = embed_art
        self.ignore_singles_eps = ignore_singles_eps
        self.no_m3u_for_playlists = no_m3u_for_playlists
        self.quality_fallback = quality_fallback
        self.cover_og_quality = cover_og_quality
        self.no_cover = no_cover
        self.folder_format = folder_format
        self.track_format = track_format
        self.smart_discography = smart_discography

    # --- MODIFIED: Client creation and authentication are now separate steps ---
    def initialize_client_via_token(self, token, app_id, secrets):
        self.client = qopy.Client(app_id, secrets)
        self.client.auth_via_token(token)
        logger.info(f"{YELLOW}Set max quality: {QUALITIES[int(self.quality)]}\n")

    def initialize_client(self, email, pwd, app_id, secrets):
        self.client = qopy.Client(app_id, secrets)
        self.client.auth(email, pwd)
        logger.info(f"{YELLOW}Set max quality: {QUALITIES[int(self.quality)]}\n")

    def _get_downloader(self, item_id, path=None):
        return downloader.Download(
            self.client,
            item_id,
            path or self.directory,
            int(self.quality),
            self.embed_art,
            self.ignore_singles_eps,
            self.quality_fallback,
            self.cover_og_quality,
            self.no_cover,
            self.folder_format,
            self.track_format,
        )

    def _download_track_concurrent(self, **kwargs):
        """Wrapper to be used in the executor for downloading and tagging a single track from an album job."""
        dloader = self._get_downloader(
            kwargs.get("album_or_track_metadata", {}).get("id")
        )
        dloader._download_and_tag(**kwargs)

    def _download_album(self, album_id, path=None):
        """Gets all track jobs for an album and downloads them concurrently."""
        dloader = self._get_downloader(album_id, path)
        track_jobs = dloader.get_album_tracks()

        if not track_jobs:
            return

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            futures = [
                executor.submit(self._download_track_concurrent, **job)
                for job in track_jobs
            ]
            album_title = track_jobs[0]["album_or_track_metadata"]["title"]
            for future in tqdm(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                desc=f"Downloading {album_title}",
            ):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"{RED}A track download failed: {e}")
        logger.info(f"{GREEN}Completed")

    def handle_url(self, url):
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
        except (KeyError, IndexError):
            logger.info(
                f'{RED}Invalid url: "{url}". Use urls from https://play.qobuz.com!'
            )
            return

        # If func is None, it's a single item (album or track)
        if type_dict["func"] is None:
            if url_type == "album":
                self._download_album(item_id)
            else:  # Single track
                self._get_downloader(item_id).download_track()
        # Otherwise, it's a multi-item collection (playlist, artist, label)
        else:
            content = [item for item in type_dict["func"](item_id)]
            content_name = content[0]["name"]
            logger.info(
                f"{YELLOW}Downloading all music from {content_name} ({url_type})!"
            )
            new_path = create_and_return_dir(
                os.path.join(self.directory, sanitize_filename(content_name))
            )
            items = self._get_items_from_content(content, url_type, type_dict)

            if type_dict["iterable_key"] == "albums":  # Artist or Label
                for item in items:
                    self._download_album(item["id"], new_path)
            else:  # Playlist
                track_ids = [item["id"] for item in items]
                self._download_playlist_tracks(track_ids, new_path, content_name)

            if url_type == "playlist" and not self.no_m3u_for_playlists:
                make_m3u(new_path)

    def _get_items_from_content(self, content, url_type, type_dict):
        if self.smart_discography and url_type == "artist":
            return smart_discography_filter(content, save_space=True, skip_extras=True)
        return [item[type_dict["iterable_key"]]["items"] for item in content][0]

    def download_list_of_urls(self, urls):
        if not urls or not isinstance(urls, list):
            logger.info(f"{OFF}Nothing to download")
            return
        for url in urls:
            if "last.fm" in url:
                self.download_lastfm_pl(url)
            elif os.path.isfile(url):
                self.download_from_txt_file(url)
            else:
                self.handle_url(url)

    def download_from_txt_file(self, txt_file):
        with open(txt_file, "r") as txt:
            try:
                urls = [
                    line.replace("\n", "").strip()
                    for line in txt.readlines()
                    if not line.strip().startswith("#")
                ]
            except Exception as e:
                logger.error(f"{RED}Invalid text file: {e}")
                return
            logger.info(
                f"{YELLOW}qobuz-dl will download {len(urls)} urls from file: {txt_file}"
            )
            self.download_list_of_urls(urls)

    def _search_track_id(self, query):
        try:
            results = self.client.search_tracks(query=query, limit=1)
            return results["tracks"]["items"][0]["id"]
        except (KeyError, IndexError):
            logger.warning(
                f"{YELLOW}Could not find a match for '{query}' on Qobuz. Skipping."
            )
            return None

    def _download_playlist_tracks(self, track_ids, path, name):
        """Downloads a list of track IDs concurrently. Used for playlists."""
        if not track_ids:
            return

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            futures = [
                executor.submit(self._get_downloader(track_id, path).download_track)
                for track_id in track_ids
            ]
            for future in tqdm(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                desc=f"Downloading {name}",
            ):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"{RED}A track download failed: {e}")

    def download_lastfm_pl(self, playlist_url):
        try:
            r = requests.get(playlist_url, timeout=10)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"{RED}Playlist download failed: {e}")
            return

        soup = bso(r.content, "html.parser")
        artists = [artist.text for artist in soup.select(ARTISTS_SELECTOR)]
        titles = [title.text for title in soup.select(TITLE_SELECTOR)]
        track_list = [f"{artist} {title}" for artist, title in zip(artists, titles)]

        if not track_list:
            logger.info(f"{OFF}No tracks found on Last.fm page.")
            return

        pl_title = sanitize_filename(soup.select_one("h1").text)
        pl_directory = os.path.join(self.directory, pl_title)

        track_ids = []
        logger.info(f"{YELLOW}Searching for {len(track_list)} tracks on Qobuz...")
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_query = {
                executor.submit(self._search_track_id, query): query
                for query in track_list
            }
            for future in tqdm(
                concurrent.futures.as_completed(future_to_query),
                total=len(track_list),
                desc="Searching for tracks",
            ):
                track_id = future.result()
                if track_id:
                    track_ids.append(track_id)

        if not track_ids:
            logger.info(
                f"{OFF}Could not find any matching tracks on Qobuz for this playlist."
            )
            return

        logger.info(f"{YELLOW}Found {len(track_ids)} tracks. Starting download...")
        self._download_playlist_tracks(track_ids, pl_directory, pl_title)

        if not self.no_m3u_for_playlists:
            make_m3u(pl_directory)
