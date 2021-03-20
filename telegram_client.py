"""Telgram client with end to end encryption layer"""

import os
import sys
import asyncio
import base64
from secrets import token_bytes
from getpass import getpass
from datetime import datetime, timezone
import requests_cache
import requests

# Crypto
from cryptography.hazmat.primitives import hashes, serialization, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend

# Telethon
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.network import ConnectionTcpAbridged
from telethon.utils import get_display_name
from telethon.tl.types import Chat

from helpers import print_title, get_public_key, get_env, sprint, BUCKET_URL
from db import Dialog, BLOBS_DIR

requests_cache.install_cache(
    cache_name="blobs/http_requests_cache",
    allowable_codes=(
        200,
        404,
    ),
)

loop = asyncio.get_event_loop()


async def async_input(prompt):
    """
    Python's ``input()`` is blocking, which means the event loop we set
    above can't be running while we're blocking there. This method will
    let the loop run while we wait for input.
    """
    print(prompt, end="", flush=True)
    return (await loop.run_in_executor(None, sys.stdin.readline)).rstrip()


class InteractiveTelegramClient(TelegramClient):
    """Interactive end to end encrypted messaging"""

    def __init__(self, session_user_id, api_id, api_hash, proxy=None):

        print_title("Initialization")

        super().__init__(
            session_user_id,
            api_id,
            api_hash,
            connection=ConnectionTcpAbridged,
            proxy=proxy,
        )

        print("Connecting to Telegram servers...")
        try:
            loop.run_until_complete(self.connect())
        except IOError:
            # We handle IOError and not ConnectionError because
            # PySocks' errors do not subclass ConnectionError
            # (so this will work with and without proxies).
            print("Initial connection failed. Retrying...")
            loop.run_until_complete(self.connect())

        if not loop.run_until_complete(self.is_user_authorized()):
            print("First run. Sending code request...")
            user_phone = input("Enter your phone: ")
            loop.run_until_complete(self.sign_in(user_phone))

            self_user = None
            while self_user is None:
                code = input("Enter the code you just received: ")
                try:
                    self_user = loop.run_until_complete(self.sign_in(code=code))

                except SessionPasswordNeededError:
                    passwd = getpass(
                        "Two step verification is enabled. "
                        "Please enter your password: "
                    )

                    self_user = loop.run_until_complete(self.sign_in(password=passwd))

    async def run(self):
        """Main loop of the TelegramClient, will wait for user action"""

        self.add_event_handler(self.message_handler, events.NewMessage(incoming=True))

        # Enter a while loop to chat as long as the user wants
        while True:
            dialog_count = 15
            dialogs = await self.get_dialogs(limit=dialog_count)

            i = None
            while i is None:
                print_title("Dialogs window")

                # Display them so the user can choose
                for i, dialog in enumerate(dialogs, start=1):
                    sprint("{}. {}".format(i, get_display_name(dialog.entity)))

                # Let the user decide who they want to talk to
                print()
                print("> Who do you want to send messages to?")
                print("> Available commands:")
                print("  !q: Quits the dialogs window and exits.")
                print("  !l: Logs out, terminating this session.")
                print()
                i = await async_input("Enter dialog ID or a command: ")
                if i == "!q":
                    return
                if i == "!l":
                    await self.log_out()
                    return

                try:
                    i = int(i if i else 0) - 1
                    # Ensure it is inside the bounds, otherwise retry
                    if not 0 <= i < dialog_count:
                        i = None
                except ValueError:
                    i = None

            # Retrieve the selected user (or chat, or channel)
            entity = dialogs[i].entity

            print_title('Chat with "{}"'.format(get_display_name(entity)))
            print("Available commands:")
            print("  !q:  Quits the current chat.")
            print("  !Q:  Quits the current chat and exits.")
            print()

            while True:
                msg = await async_input("Enter a message: ")
                if msg == "!q":
                    break
                if msg == "!Q":
                    return
                if msg:
                    if isinstance(entity, Chat):
                        # group chat
                        async for person in self.iter_participants(entity):
                            if not person.is_self:
                                enc_msg_bytes = encrypt_msg(person.id, msg)
                                if enc_msg_bytes == -1:
                                    continue

                                id_str = str(person.id)
                                id_str = "0" * (20 - len(id_str)) + id_str
                                # Append receivers id to msg (20 chars)
                                enc_msg_bytes += id_str.encode("utf-8")
                                b64_enc_txt = base64.b64encode(enc_msg_bytes).decode(
                                    "utf-8"
                                )
                                await self.send_message(
                                    entity, b64_enc_txt, link_preview=False
                                )
                    else:
                        # individual chat
                        enc_msg_bytes = encrypt_msg(entity.id, msg)
                        if enc_msg_bytes == -1:
                            return
                        b64_enc_txt = base64.b64encode(enc_msg_bytes).decode("utf-8")
                        await self.send_message(entity, b64_enc_txt, link_preview=False)

    async def message_handler(self, event):
        """Callback method for received events.NewMessage"""

        if event.text:
            b64_enc_text_bytes = event.text.encode("utf-8")
            encr_msg_bytes = base64.b64decode(b64_enc_text_bytes)
            sender_id = event.sender_id
            if event.is_group:
                receiver_id = encr_msg_bytes[-20:].decode("utf-8")
                if int(receiver_id) != int(MY_ENTITY_ID):
                    # Not my message :(
                    return
                # Remove the received id
                encr_msg_bytes = encr_msg_bytes[:-20]

            aes_shared_key = get_aes_key(sender_id)
            init_vector = encr_msg_bytes[:16]
            aes = Cipher(
                algorithms.AES(aes_shared_key),
                modes.CBC(init_vector),
                backend=default_backend(),
            )
            decryptor = aes.decryptor()
            temp_bytes = decryptor.update(encr_msg_bytes[16:]) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            temp_bytes = unpadder.update(temp_bytes) + unpadder.finalize()
            event.text = temp_bytes.decode("utf-8")

            chat = await event.get_chat()

            if event.is_group:
                sprint(
                    '<< {} @ {} sent "{}"'.format(
                        get_display_name(await event.get_sender()),
                        get_display_name(chat),
                        event.text,
                    )
                )
            else:
                sprint('<< {} sent "{}"'.format(get_display_name(chat), event.text))


async def get_my_id(client):
    """Get my entity id"""
    my_entity = await client.get_me()
    return my_entity.id


def encrypt_msg(entity_id, msg):
    """Encrypts message with peer entity's aes key"""
    aes_shared_key = get_aes_key(entity_id)
    if aes_shared_key == -1:
        return -1
    init_vector = token_bytes(16)
    aes = Cipher(
        algorithms.AES(aes_shared_key),
        modes.CBC(init_vector),
        backend=default_backend(),
    )
    encryptor = aes.encryptor()

    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(msg.encode("utf-8")) + padder.finalize()
    enc_msg_bytes = encryptor.update(padded_data) + encryptor.finalize()
    enc_msg_bytes = init_vector + enc_msg_bytes

    return enc_msg_bytes


def get_aes_key(entity_id):
    """Get the aes key of peer entity"""
    aes_shared_key = None
    for dlg in Dialog.select():
        if dlg.dialog_id == entity_id:
            # found a entry of aes shared key.
            response_date = requests.get(
                url=BUCKET_URL + MY_ENTITY_ID + "/date", expire_after=120
            )
            if response_date.status_code != 200:
                raise "Peer public key not found!!!"
            if float(response_date.text) <= float(dlg.creation_datetime):
                # Public has not been modified.
                aes_shared_key = dlg.aes_shared_key
            break

    if aes_shared_key is None:
        # If the receiver's aes key is not present,
        # fetch his public key from server and derive a aes key
        peer_pub_key = get_public_key(entity_id)
        if isinstance(peer_pub_key, int):
            print("Public key for ", entity_id, " not found", file=sys.stderr)
            return -1
        shared_key = my_ecdh_private_key.exchange(ec.ECDH(), peer_pub_key)
        aes_shared_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=None,
            backend=default_backend(),
        ).derive(shared_key)
        Dialog.replace(
            dialog_id=entity_id,
            aes_shared_key=aes_shared_key,
            creation_datetime=datetime.now(timezone.utc).timestamp(),
        ).execute()
    return aes_shared_key


if __name__ == "__main__":
    SESSION = os.environ.get("TG_SESSION", "interactive")
    API_ID = get_env("TG_API_ID", "Enter your API ID: ", int)
    API_HASH = get_env("TG_API_HASH", "Enter your API hash: ")

    try:
        with open(BLOBS_DIR + "my_ecdh_private_key.pem", "rb") as f:
            my_ecdh_private_key = serialization.load_pem_private_key(
                f.read(), password=None
            )
        with open(BLOBS_DIR + "my_ecdh_public_key.pem", "rb") as f:
            serialized_public_key = f.read()
            my_ecdh_public_key = serialization.load_pem_public_key(
                serialized_public_key
            )
    except FileNotFoundError:
        print("Generting a new ecdh key pair!!")
        my_ecdh_private_key = ec.generate_private_key(ec.SECP384R1())
        my_ecdh_public_key = my_ecdh_private_key.public_key()

        serialized_private_key = my_ecdh_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        serialized_public_key = my_ecdh_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with open(BLOBS_DIR + "my_ecdh_private_key.pem", "wb") as f:
            f.write(serialized_private_key)
        with open(BLOBS_DIR + "my_ecdh_public_key.pem", "wb") as f:
            f.write(serialized_public_key)

    client = InteractiveTelegramClient(SESSION, API_ID, API_HASH)

    MY_ENTITY_ID = str(loop.run_until_complete(get_my_id(client)))
    pub_key_text = base64.b64encode(serialized_public_key).decode("utf-8")
    resp = requests.get(url=BUCKET_URL + MY_ENTITY_ID, expire_after=1)
    if resp.status_code == 404 or resp.text != pub_key_text:
        print("Uploading public key to server!!")
        data = {"pub_key": pub_key_text}
        requests.post(url=BUCKET_URL + "update/" + MY_ENTITY_ID, data=data)

    loop.run_until_complete(client.run())
