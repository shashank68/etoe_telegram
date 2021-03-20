# etoe_telegram

An end to end encryption layer on Telegram chats for individual and group conversations.

## Usage (After getting the api id & hash)

```bash

pip3 install -r requirements.txt -U
python3 telegram_client.py

```

## Features

* Uses Elliptic Curve Diffie-Hellman to get a shared key
* Messages are encryted using AES
* Initially, public key is uploaded to a [server](https://pub-keys.herokuapp.com/)
* A client willing to chat will fetch this public key and derives a shared secret
