"""
Handles fetching and parsing of the Qobuz web player's JavaScript bundle
to extract the application ID and secrets required for API authentication.
"""

import base64
import logging
import re
from collections import OrderedDict

import aiohttp

logger = logging.getLogger(__name__)

# --- Constants and Regular Expressions ---

_BASE_URL = "https://play.qobuz.com"

# Regex to find the URL of the main JavaScript bundle file from the login page HTML.
_BUNDLE_URL_REGEX = re.compile(
    r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>'
)

# Regex to find the production App ID within the JavaScript bundle.
_APP_ID_REGEX = re.compile(
    r'production:{api:{appId:"(?P<app_id>\d{9})",appSecret:"\w{32}"'
)

# Regex to find the initial seed and timezone used for generating secrets.
_SEED_TIMEZONE_REGEX = re.compile(
    r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.utimezone\.(?P<timezone>[a-z]+)\)'
)

# Regex to find the 'info' and 'extras' parts of the secrets, associated with a timezone.
_INFO_EXTRAS_REGEX = r'name:"\w+/(?P<timezone>{timezones})",info:"(?P<info>[\w=]+)",extras:"(?P<extras>[\w=]+)"'


class Bundle:
    """A class to fetch and parse the Qobuz JavaScript bundle."""

    def __init__(self, bundle_text):
        """Initializes with the text content of the bundle.js file."""
        self._bundle = bundle_text

    @classmethod
    async def create(cls):
        """
        Fetches the Qobuz login page to find the bundle URL, then downloads the bundle.

        Returns:
            Bundle: An instance of the Bundle class.
        """
        async with aiohttp.ClientSession() as session:
            logger.debug("Getting login page to find bundle URL")
            async with session.get(f"{_BASE_URL}/login") as response:
                response.raise_for_status()
                text = await response.text()

            bundle_url_match = _BUNDLE_URL_REGEX.search(text)
            if not bundle_url_match:
                raise RuntimeError("Could not find bundle URL in login page HTML.")

            bundle_url = _BASE_URL + bundle_url_match.group(1)
            logger.debug(f"Getting bundle from: {bundle_url}")

            async with session.get(bundle_url) as response:
                response.raise_for_status()
                bundle_text = await response.text()

        return cls(bundle_text)

    def get_app_id(self):
        """
        Extracts the 9-digit application ID from the bundle.

        Returns:
            str: The extracted App ID.
        """
        match = _APP_ID_REGEX.search(self._bundle)
        if not match:
            raise RuntimeError("Failed to find App ID in the JavaScript bundle.")
        return match.group("app_id")

    def get_secrets(self):
        """
        Extracts and decodes the API secrets from the bundle.

        The secrets are constructed by combining a 'seed', 'info', and 'extras' string
        found in the JavaScript, which are then base64 decoded.

        Returns:
            OrderedDict: A dictionary of decoded secrets, keyed by timezone.
        """
        logger.debug("Extracting secrets from bundle")
        seed_matches = _SEED_TIMEZONE_REGEX.finditer(self._bundle)
        secrets = OrderedDict()

        # 1. Find all initial seeds and their corresponding timezones.
        for match in seed_matches:
            seed, timezone = match.group("seed", "timezone")
            secrets[timezone] = [seed]

        # 2. Reorder secrets to match the structure in the bundle file.
        # This seems to be a specific requirement for the decoding to work.
        if len(secrets) > 1:
            keypairs = list(secrets.items())
            secrets.move_to_end(keypairs[1][0], last=False)

        # 3. Find the 'info' and 'extras' strings for each timezone.
        info_extras_regex = _INFO_EXTRAS_REGEX.format(
            timezones="|".join([timezone.capitalize() for timezone in secrets])
        )
        info_extras_matches = re.finditer(info_extras_regex, self._bundle)
        for match in info_extras_matches:
            timezone, info, extras = match.group("timezone", "info", "extras")
            secrets[timezone.lower()] += [info, extras]

        # 4. Concatenate the parts, decode from base64, and clean up.
        for secret_key in secrets:
            # The full secret is the concatenation of seed, info, and extras.
            full_secret_encoded = "".join(secrets[secret_key])
            # The last 44 characters are a checksum/salt and must be removed before decoding.
            trimmed_secret = full_secret_encoded[:-44]
            secrets[secret_key] = base64.standard_b64decode(trimmed_secret).decode(
                "utf-8"
            )

        return secrets
