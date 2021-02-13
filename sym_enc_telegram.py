from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from peewee import IntegerField, BlobField, SqliteDatabase, Model
from getpass import getpass
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.network import ConnectionTcpAbridged
from telethon.utils import get_display_name
import asyncio
import os
import sys
import time
import base64
import logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)


if len(sys.argv) > 1:
    db_file = str(sys.argv[1])
else:
    db_file = 'key_store.db'
db = SqliteDatabase(db_file)


class BaseModel(Model):
    class Meta:
        database = db


class Dialog(BaseModel):
    dialog_id = IntegerField(primary_key=True)
    peer_pub_key = BlobField()


db.create_tables([Dialog])

# Create a global variable to hold the loop we will be using
loop = asyncio.get_event_loop()


def sprint(string, *args, **kwargs):
    """Safe Print (handle UnicodeEncodeErrors on some terminals)"""
    try:
        print(string, *args, **kwargs)
    except UnicodeEncodeError:
        string = string.encode('utf-8', errors='ignore')\
                       .decode('ascii', errors='ignore')
        print(string, *args, **kwargs)


def print_title(title):
    """Helper function to print titles to the console more nicely"""
    sprint('\n')
    sprint('=={}=='.format('=' * len(title)))
    sprint('= {} ='.format(title))
    sprint('=={}=='.format('=' * len(title)))


def bytes_to_string(byte_count):
    """Converts a byte count to a string (in KB, MB...)"""
    suffix_index = 0
    while byte_count >= 1024:
        byte_count /= 1024
        suffix_index += 1

    return '{:.2f}{}'.format(
        byte_count, [' bytes', 'KB', 'MB', 'GB', 'TB'][suffix_index]
    )


async def async_input(prompt):
    """
    Python's ``input()`` is blocking, which means the event loop we set
    above can't be running while we're blocking there. This method will
    let the loop run while we wait for input.
    """
    print(prompt, end='', flush=True)
    return (await loop.run_in_executor(None, sys.stdin.readline)).rstrip()


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
            time.sleep(1)


class InteractiveTelegramClient(TelegramClient):

    def __init__(self, session_user_id, api_id, api_hash,
                 proxy=None):

        print_title('Initialization')

        # The first step is to initialize the TelegramClient, as we are
        # subclassing it, we need to call super().__init__(). On a more
        # normal case you would want 'client = TelegramClient(...)'
        super().__init__(
            # These parameters should be passed always, session name and API
            session_user_id, api_id, api_hash,

            # You can optionally change the connection mode by passing a
            # type or an instance of it. This changes how the sent packets
            # look (low-level concept you normally shouldn't worry about).
            # Default is ConnectionTcpFull, smallest is ConnectionTcpAbridged.
            connection=ConnectionTcpAbridged,

            # If you're using a proxy, set it here.
            proxy=proxy
        )

        # Store {message.id: message} map here so that we can download
        # media known the message ID, for every message having media.
        self.found_media = {}

        # Calling .connect() may raise a connection error False, so you need
        # to except those before continuing. Otherwise you may want to retry
        # as done here.
        print('Connecting to Telegram servers...')
        try:
            loop.run_until_complete(self.connect())
        except IOError:
            # We handle IOError and not ConnectionError because
            # PySocks' errors do not subclass ConnectionError
            # (so this will work with and without proxies).
            print('Initial connection failed. Retrying...')
            loop.run_until_complete(self.connect())

        # If the user hasn't called .sign_in() or .sign_up() yet, they won't
        # be authorized. The first thing you must do is authorize. Calling
        # .sign_in() should only be done once as the information is saved on
        # the *.session file so you don't need to enter the code every time.
        if not loop.run_until_complete(self.is_user_authorized()):
            print('First run. Sending code request...')
            user_phone = input('Enter your phone: ')
            loop.run_until_complete(self.sign_in(user_phone))

            self_user = None
            while self_user is None:
                code = input('Enter the code you just received: ')
                try:
                    self_user =\
                        loop.run_until_complete(self.sign_in(code=code))

                # Two-step verification may be enabled, and .sign_in will
                # raise this error. If that's the case ask for the password.
                # Note that getpass() may not work on PyCharm due to a bug,
                # if that's the case simply change it for input().
                except SessionPasswordNeededError:
                    pw = getpass('Two step verification is enabled. '
                                 'Please enter your password: ')

                    self_user = loop.run_until_complete(
                        self.sign_in(password=pw))

    async def run(self):
        """Main loop of the TelegramClient, will wait for user action"""

        # Once everything is ready, we can add an event handler.
        #
        # Events are an abstraction over Telegram's "Updates" and
        # are much easier to use.
        self.add_event_handler(self.message_handler,
                               events.NewMessage(incoming=True))

        # Enter a while loop to chat as long as the user wants
        while True:
            # Retrieve the top dialogs. You can set the limit to None to
            # retrieve all of them if you wish, but beware that may take
            # a long time if you have hundreds of them.
            dialog_count = 15

            # Entities represent the user, chat or channel
            # corresponding to the dialog on the same index.
            dialogs = await self.get_dialogs(limit=dialog_count)

            i = None
            while i is None:
                print_title('Dialogs window')

                # Display them so the user can choose
                for i, dialog in enumerate(dialogs, start=1):
                    sprint('{}. {}'.format(i, get_display_name(dialog.entity)))

                # Let the user decide who they want to talk to
                print()
                print('> Who do you want to send messages to?')
                print('> Available commands:')
                print('  !q: Quits the dialogs window and exits.')
                print('  !l: Logs out, terminating this session.')
                print()
                i = await async_input('Enter dialog ID or a command: ')
                if i == '!q':
                    return
                if i == '!l':
                    # Logging out will cause the user to need to reenter the
                    # code next time they want to use the library, and will
                    # also delete the *.session file off the filesystem.
                    #
                    # This is not the same as simply calling .disconnect(),
                    # which simply shuts down everything gracefully.
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

            # Show some information
            print_title('Chat with "{}"'.format(get_display_name(entity)))
            print('Available commands:')
            print('  !q:  Quits the current chat.')
            print('  !Q:  Quits the current chat and exits.')

            print()

            # And start a while loop to chat
            while True:
                msg = await async_input('Enter a message: ')
                # Quit
                if msg == '!q':
                    break
                elif msg == '!Q':
                    return

                # Send chat message (if any)
                elif msg:
                    # If the receivers public key is not present
                    # Then send the _SEND_PUB_KEY txt to request for public key

                    print("SENDING MESSAGE TO ENTITTY: ", entity.id)
                    b64_enc_txt = '_SEND_PUB_KEY'
                    for dlg in Dialog.select():
                        if dlg.dialog_id == entity.id:
                            cipher = PKCS1_OAEP.new(
                                RSA.import_key(dlg.peer_pub_key))
                            enc_msg_bytes = cipher.encrypt(msg.encode('utf-8'))
                            b64_enc_txt = base64.b64encode(
                                enc_msg_bytes).decode('utf-8')
                            print("found public key!!")
                            break
                    await self.send_message(entity, b64_enc_txt, link_preview=False)

    @staticmethod
    def print_progress(progress_type, downloaded_bytes, total_bytes):
        print('{} {} out of {} ({:.2%})'.format(
            progress_type, bytes_to_string(downloaded_bytes),
            bytes_to_string(total_bytes), downloaded_bytes / total_bytes)
        )

    async def message_handler(self, event):
        """Callback method for received events.NewMessage"""

        # Note that message_handler is called when a Telegram update occurs
        # and an event is created. Telegram may not always send information
        # about the ``.sender`` or the ``.chat``, so if you *really* want it
        # you should use ``get_chat()`` and ``get_sender()`` while working
        # with events. Since they are methods, you know they may make an API
        # call, which can be expensive.

        if event.text == '_SEND_PUB_KEY':
            # Request for public key
            my_pub_key_bytes = my_key.public_key().export_key()
            b64_enc_txt = "__REC_KEY" + \
                base64.b64encode(my_pub_key_bytes).decode('utf-8')
            await event.reply(b64_enc_txt)
        elif len(event.text) > 9 and event.text[:9] == "__REC_KEY":
            # Recieved a public key. Add to DB.
            print("RECIEVED PUBLIC KEY", event.text)
            b64_enc_text_bytes = event.text[9:].encode('utf-8')
            pub_bytes = base64.b64decode(b64_enc_text_bytes)
            peer = Dialog(dialog_id=event.sender_id, peer_pub_key=pub_bytes)
            peer.save(force_insert=True)
        else:
            # Decrypt the msg and print.
            b64_enc_text_bytes = event.text.encode('utf-8')
            encr_msg_bytes = base64.b64decode(b64_enc_text_bytes)
            cipher = PKCS1_OAEP.new(my_key)
            event.text = cipher.decrypt(encr_msg_bytes).decode('utf-8')

            chat = await event.get_chat()
            if event.is_group:
                sprint('<< {} @ {} sent "{}"'.format(
                    get_display_name(await event.get_sender()),
                    get_display_name(chat),
                    event.text
                ))
            else:
                sprint('<< {} sent "{}"'.format(
                    get_display_name(chat), event.text
                ))


if __name__ == '__main__':
    SESSION = os.environ.get('TG_SESSION', 'interactive')
    API_ID = get_env('TG_API_ID', 'Enter your API ID: ', int)
    API_HASH = get_env('TG_API_HASH', 'Enter your API hash: ')
    # my_key will be our private-public RSA key.
    try:
        with open('my_key.pem') as f:
            my_key = RSA.import_key(f.read())
    except FileNotFoundError:
        # Limiting factor for lenght of messages.
        # can msg length should be less than key lenght
        my_key = RSA.generate(1024)
        with open('my_key.pem', 'wb') as f:
            f.write(my_key.export_key('PEM'))

    client = InteractiveTelegramClient(SESSION, API_ID, API_HASH)
    loop.run_until_complete(client.run())
