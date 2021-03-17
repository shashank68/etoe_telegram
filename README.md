# etoe_telegram

## Running (After getting the api id & hash)

```bash
pip3 install -r requirements.txt
python3 sym_enc_telegram.py
```

## Working

* Uses Elliptic Curve Diffie-Hellman for getting a shared key
* Messages are encryted using AES
* Initially, public key is uploaded to a [server](https://pub-keys.herokuapp.com/)
* A client willing to chat will fetch this public public key
