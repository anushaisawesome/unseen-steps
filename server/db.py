"""MongoDB Atlas: the dance glossary, song maps and show memory.

Connection details come from .env (see .env.example): MONGODB_URI and MONGODB_DB.

Check the connection and see what's in the database:
    python server/db.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_db = None


def db():
    global _db
    if _db is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI isn't set: add Andrii's Atlas connection string to .env")
        _db = MongoClient(uri, serverSelectionTimeoutMS=8000)[os.environ.get("MONGODB_DB", "unseen_steps")]
    return _db


if __name__ == "__main__":
    database = db()
    database.client.admin.command("ping")
    print(f"connected to '{database.name}'")
    for name in database.list_collection_names():
        coll = database[name]
        sample = coll.find_one({}, {"embedding": 0})
        print(f"- {name}: {coll.estimated_document_count()} documents; fields: {sorted(sample) if sample else []}")
