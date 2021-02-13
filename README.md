# etoe_telegram

## Running (After getting the api id & hash)

```bash
pip3 install -r requirements.txt
python3 sym_enc_telegram.py
```

## Working

* RSA public key encryption/decryption
* For sending a msg, we need the public key. (sends `_SEND_PUB_KEY`)
* Decryption is done through private key.
