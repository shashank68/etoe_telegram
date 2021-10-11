"""Database schema for AES keys storage"""

import os

from peewee import BlobField, CharField, IntegerField, Model, SqliteDatabase

BLOBS_DIR = "blobs/"

if not os.path.exists(BLOBS_DIR):
    os.makedirs(BLOBS_DIR)

db = SqliteDatabase(BLOBS_DIR + "keystore.db")


class BaseModel(Model):
    class Meta:
        database = db


class Dialog(BaseModel):
    dialog_id = IntegerField(primary_key=True)
    aes_shared_key = BlobField()
    creation_datetime = CharField()


db.create_tables([Dialog])
