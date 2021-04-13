# etoe_telegram

An end to end encryption layer on Telegram chats for individual and group conversations.

## Usage

Clone the repo

```bash
git clone https://github.com/shashank68/etoe_telegram.git
cd etoe_telgram
```

Get the Telegram API credentials using [these steps](https://core.telegram.org/api/obtaining_api_id#obtaining-api-id)

Install the requirements and run

```bash
pip3 install -r requirements.txt -U
python3 telegram_client.py

```

## Features

* Uses Elliptic Curve Diffie-Hellman to get a shared key
* Messages are encrypted using AES
* Initially, ECDH public key is uploaded to a [server](https://pub-keys.herokuapp.com/)
* A client willing to chat will fetch this public key and derives a shared secret
* This shared secret will be used to encrypt the conversations
