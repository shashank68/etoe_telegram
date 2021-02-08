import logging
from telethon import TelegramClient, events, sync
from dotenv import dotenv_values

CURSOR_UP_ONE = '\x1b[1A'
ERASE_LINE = '\x1b[2K'

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.WARNING)

config = dotenv_values('.env')

api_id = config['api_id']
api_hash = config['api_hash']
client = TelegramClient('EtoE', api_id, api_hash)


@client.on(events.NewMessage(incoming=True))
async def handler(event):
    sender = await event.get_sender()
    print("\n[(", event.date.strftime("%c"), ')]', end=' ', sep='')
    print('{', sender.phone, "}: ", event.raw_text, sep='')
    reply = input("Enter your message: ")
    await event.reply(reply)
    print(CURSOR_UP_ONE, ERASE_LINE, sep='', end='')
    print("[(", event.date.strftime("%c"), ')]', end=' ', sep='')
    print('{ME}: ', reply)

    while True:
        snd = input("Send a msg?[y/n]: ")
        if snd == 'y':
            reply = input("Enter your message: ")
            await event.reply(reply)
            print(CURSOR_UP_ONE, ERASE_LINE, sep='', end='')
            print("[(", event.date.strftime("%c"), ')]', end=' ', sep='')
            print('{ME}: ', reply)
        else:
            break


with client:
    client.run_until_disconnected()
