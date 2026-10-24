"""MongoDB Atlas: the dance glossary, song maps and show memory.

Connection details come from .env (see .env.example): MONGODB_URI and MONGODB_DB.

Check the connection and see what's in the database:
    python server/db.py
"""

from urllib.parse import quote_plus

from pymongo import MongoClient

try:
    from .settings import first_env, mongodb_uri, mongodb_user
except ImportError:  # Running as ``python server/db.py``.
    from settings import first_env, mongodb_uri, mongodb_user

_db = None


def db():
    global _db
    if _db is None:
        uri = mongodb_uri()
        if not uri:  # or build it from parts, so the password sits on its own line in .env
            user = mongodb_user()
            password = first_env("MONGODB_PASSWORD")
            host = first_env("MONGODB_HOST")
            if not (user and password and host):
                raise RuntimeError("Set MONGODB_URI, or MONGODB_USER + MONGODB_PASSWORD + MONGODB_HOST, in .env")
            uri = f"mongodb+srv://{quote_plus(user)}:{quote_plus(password)}@{host}/?appName=unseen-steps"
        _db = MongoClient(uri, serverSelectionTimeoutMS=8000)[first_env("MONGODB_DB") or "unseen_steps"]
    return _db


if __name__ == "__main__":
    database = db()
    database.client.admin.command("ping")
    print(f"connected to '{database.name}'")
    for name in database.list_collection_names():
        coll = database[name]
        sample = coll.find_one({}, {"embedding": 0})
        print(f"- {name}: {coll.estimated_document_count()} documents; fields: {sorted(sample) if sample else []}")
