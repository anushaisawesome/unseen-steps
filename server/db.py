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


EMBED_MODEL = "gemini-embedding-2"  # same model and size the glossary was embedded with
EMBED_DIM = 3072
SPOKEN_STATUSES = ("vetted", "translated")  # nothing unvetted is spoken
_gemini = None


def _embed_query(text: str) -> list[float]:
    from google import genai
    from google.genai import types
    try:
        from .settings import gemini_api_key
    except ImportError:
        from settings import gemini_api_key
    global _gemini
    if _gemini is None:
        _gemini = genai.Client(api_key=gemini_api_key())
    result = _gemini.models.embed_content(
        model=EMBED_MODEL, contents=f"task: search result | query: {text}",
        config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM))
    return list(result.embeddings[0].values)


def match_terms(movement: str, style: str, k: int = 4, include_drafts: bool = False) -> list[dict]:
    """Glossary terms whose body-language description best matches a plain description of the movement.

    Uses the Atlas vector index on terms.embedding, filtered to the style. Only vetted terms are returned
    unless include_drafts is set (for previews, never for the demo).
    """
    statuses = list(SPOKEN_STATUSES) + (["draft"] if include_drafts else [])
    pipeline = [
        {"$vectorSearch": {"index": "vector_index", "path": "embedding", "queryVector": _embed_query(movement),
                           "numCandidates": 50, "limit": k * 3, "filter": {"style": style}}},
        {"$match": {"status": {"$in": statuses}}},
        {"$limit": k},
        {"$project": {"_id": 0, "term": 1, "description": 1, "status": 1, "aliases": 1, "display_names": 1,
                      "score": {"$meta": "vectorSearchScore"}}},
    ]
    return list(db()["terms"].aggregate(pipeline))


def spoken_name(term: dict, level: str = "beginner") -> str | None:
    """The name to say for this listener (SPEC.md 5b). Professional: the canonical term. Beginner: the confirmed
    beginner name, or None so the writer falls back to plain body language."""
    if level == "professional":
        return term["term"]
    return (term.get("display_names") or {}).get("beginner")
