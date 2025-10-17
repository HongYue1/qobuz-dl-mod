"""
A lightweight, asynchronous API client for the private Qobuz API.
"""

import hashlib
import logging
import time

import aiohttp

from qobuz_dl.exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
)

log = logging.getLogger(__name__)


class Client:
    """
    An asynchronous client for interacting with the Qobuz JSON API (v0.2).
    """

    def __init__(self, app_id, secrets):
        """Initializes the API client."""
        self.secrets = secrets
        self.id = str(app_id)
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0",
                "X-App-Id": self.id,
            }
        )
        self.base = "https://www.qobuz.com/api.json/0.2/"
        self.sec = None  # The valid app secret, determined after testing.
        self.uat = None  # User authentication token.

    async def close(self):
        """Gracefully closes the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def _prepare_file_url_params(self, **kwargs):
        """
        Builds the parameters and request signature for the 'track/getFileUrl' endpoint.
        This is the most complex endpoint, requiring a timestamp and MD5 signature.
        """
        unix_ts = int(time.time())
        track_id = kwargs["id"]
        fmt_id = kwargs["fmt_id"]
        secret = kwargs.get("sec", self.sec)

        if int(fmt_id) not in (5, 6, 7, 27):
            raise InvalidQuality("Invalid quality ID: choose from 5, 6, 7, or 27.")

        # The signature is an MD5 hash of several concatenated request parameters and the secret.
        # The format is critical for the API to accept the request.
        sig_str = f"trackgetFileUrlformat_id{fmt_id}intentstreamtrack_id{track_id}{unix_ts}{secret}"
        request_sig = hashlib.md5(sig_str.encode("utf-8")).hexdigest()

        return {
            "request_ts": unix_ts,
            "request_sig": request_sig,
            "track_id": track_id,
            "format_id": fmt_id,
            "intent": "stream",
        }

    async def api_call(self, endpoint, **kwargs):
        """
        Makes a generic, authenticated call to a Qobuz API endpoint.
        """
        params = kwargs.copy()
        if endpoint == "track/getFileUrl":
            params = self._prepare_file_url_params(**kwargs)

        # The user auth token is added to every call after login.
        if self.uat:
            params["user_auth_token"] = self.uat

        async with self.session.get(self.base + endpoint, params=params) as r:
            if endpoint == "user/login":
                if r.status == 401:
                    raise AuthenticationError("Invalid email or password.")
                if r.status == 400:
                    raise InvalidAppIdError("Invalid App ID.")
            elif endpoint == "track/getFileUrl" and r.status == 400:
                raise InvalidAppSecretError("The app secret is invalid or has expired.")

            r.raise_for_status()
            return await r.json()

    async def auth_via_token(self, token):
        """Authenticates using a pre-existing user token."""
        log.info("Logging in with authentication token...")
        self.uat = token
        await self.cfg_setup()
        # Make a test call to verify the token is valid.
        try:
            user_info = await self.api_call("user/get")
            log.info(f"Successfully authenticated as {user_info['email']}.")
            if not user_info["credential"]["parameters"]:
                raise IneligibleError("This account is not eligible for streaming.")
        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise AuthenticationError(
                    "The provided token is invalid or has expired."
                )
            raise

    async def auth(self, email, password):
        """Authenticates using an email and MD5 hashed password."""
        log.info("Logging in with email/password...")
        await self.cfg_setup()
        login_payload = {
            "email": email,
            "password": password,  # Password should already be an MD5 hash.
            "app_id": self.id,
        }
        user_info = await self.api_call("user/login", **login_payload)
        if not user_info["user"]["credential"]["parameters"]:
            raise IneligibleError("This account is not eligible for streaming.")
        self.uat = user_info["user_auth_token"]
        log.info(
            f"Membership: {user_info['user']['credential']['parameters']['short_label']}"
        )

    async def _yield_paginated(self, endpoint, item_key, count_key, **kwargs):
        """Generator to handle paginated API endpoints."""
        offset = 0
        while True:
            response = await self.api_call(endpoint, offset=offset, limit=500, **kwargs)
            yield response

            total_items = response.get(count_key, 0)
            items_in_response = len(response.get(item_key, {}).get("items", []))

            if not items_in_response or (offset + items_in_response) >= total_items:
                break
            offset += items_in_response

    async def get_album_meta(self, id):
        return await self.api_call("album/get", album_id=id)

    async def get_track_meta(self, id):
        return await self.api_call("track/get", track_id=id)

    async def get_track_url(self, id, fmt_id):
        return await self.api_call("track/getFileUrl", id=id, fmt_id=fmt_id)

    def get_artist_meta(self, id):
        return self._yield_paginated(
            "artist/get",
            item_key="albums",
            count_key="albums_count",
            artist_id=id,
            extra="albums",
        )

    def get_plist_meta(self, id):
        return self._yield_paginated(
            "playlist/get",
            item_key="tracks",
            count_key="tracks_count",
            playlist_id=id,
            extra="tracks",
        )

    def get_label_meta(self, id):
        return self._yield_paginated(
            "label/get",
            item_key="albums",
            count_key="albums_count",
            label_id=id,
            extra="albums",
        )

    async def search_tracks(self, query, limit=50):
        return await self.api_call("track/search", query=query, limit=limit)

    async def test_secret(self, sec):
        """Tests if a secret is valid by making a dummy getFileUrl call."""
        try:
            # A known public domain track ID.
            await self.api_call("track/getFileUrl", id=5966783, fmt_id=5, sec=sec)
            return True
        except (InvalidAppSecretError, aiohttp.ClientError):
            return False

    async def cfg_setup(self):
        """
        Finds and sets a valid app secret from the list of scraped secrets.
        This is done once before the first authenticated API call.
        """
        if self.sec:
            return  # Already found a valid secret.

        for secret in self.secrets:
            if not secret:
                continue
            if await self.test_secret(secret):
                self.sec = secret
                log.debug(f"Found valid app secret: {secret[:4]}...")
                break

        if self.sec is None:
            raise InvalidAppSecretError(
                "None of the provided app secrets are valid. "
                "Try running qobuz-dl init again."
            )
