"""Helpers for telegram client"""

import os
import sys
from base64 import b64decode
import requests
import requests_cache
from cryptography.hazmat.primitives import serialization

requests_cache.install_cache(
    cache_name="blobs/pub_keys_cache",
    allowable_codes=(
        200,
        404,
    ),
)

BUCKET_URL = "https://pub-keys.herokuapp.com/"


def sprint(string, *args, **kwargs):
    """Safe Print (handle UnicodeEncodeErrors on some terminals)"""
    try:
        print(string, *args, **kwargs)
    except UnicodeEncodeError:
        string = string.encode("utf-8", errors="ignore").decode(
            "ascii", errors="ignore"
        )
        print(string, *args, **kwargs)


def print_title(title):
    """Helper function to print titles to the console more nicely"""
    sprint("\n")
    sprint("=={}==".format("=" * len(title)))
    sprint("= {} =".format(title))
    sprint("=={}==".format("=" * len(title)))


def get_env(name, message, cast=str):
    """Helper to get environment variables interactively"""
    if name in os.environ:
        return os.environ[name]
    while True:
        value = input(message)
        try:
            return cast(value)
        except ValueError as err:
            print(err, file=sys.stderr)


def get_public_key(telegram_id):
    """Fetch public key of the telegram entity"""
    telegram_id = str(telegram_id)
    resp = requests.get(url=BUCKET_URL + telegram_id, expire_after=100)
    if resp.status_code == 404:
        return -1
    serialized_pub_key = b64decode(resp.text.encode("utf-8"))

    return serialization.load_pem_public_key(serialized_pub_key)
