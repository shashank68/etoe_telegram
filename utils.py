import os
import sys
from base64 import b64decode
import requests

from cryptography.hazmat.primitives import serialization

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


def bytes_to_string(byte_count):
    """Converts a byte count to a string (in KB, MB...)"""
    suffix_index = 0
    while byte_count >= 1024:
        byte_count /= 1024
        suffix_index += 1

    return "{:.2f}{}".format(
        byte_count, [" bytes", "KB", "MB", "GB", "TB"][suffix_index]
    )


def get_env(name, message, cast=str):
    """Helper to get environment variables interactively"""
    if name in os.environ:
        return os.environ[name]
    while True:
        value = input(message)
        try:
            return cast(value)
        except ValueError as e:
            print(e, file=sys.stderr)


def print_progress(progress_type, downloaded_bytes, total_bytes):
    print(
        "{} {} out of {} ({:.2%})".format(
            progress_type,
            bytes_to_string(downloaded_bytes),
            bytes_to_string(total_bytes),
            downloaded_bytes / total_bytes,
        )
    )


def get_public_key(telegram_id):
    telegram_id = str(telegram_id)
    r = requests.get(url=BUCKET_URL + telegram_id)
    if r.status_code == 404:
        return -1
    serialized_pub_key = b64decode(r.text.encode("utf-8"))

    return serialization.load_pem_public_key(serialized_pub_key)
