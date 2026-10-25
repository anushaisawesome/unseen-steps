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


if __name__ == "__main__" and len(__import__("sys").argv) == 1:
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


def save_song(name: str, song: dict, style: str | None = None, file: str | None = None) -> None:
    """Store a song's music map (beats, phrases, the gaps where a line fits) under its name, so it can be found again
    by name with Atlas Search (find_song) instead of being re-analysed."""
    import json
    plain = json.loads(json.dumps({k: song[k] for k in ("bpm", "beats", "phrases", "clean_spaces", "beats_per_bar",
                                                         "energy", "hits") if k in song}, default=float))
    doc = {"name": name, "style": style, "file": file, **plain}
    db()["songs"].update_one({"name": name}, {"$set": doc}, upsert=True)


def find_song(name: str, beats_per_bar: int | None = None) -> dict | None:
    """The stored song whose name best matches what was typed or announced ("viennese waltz", a misspelling, part of
    the title): Atlas Search over songs.name with fuzzy matching (index song_name). None if nothing matches."""
    pipeline = [
        {"$search": {"index": "song_name", "text": {"query": name, "path": "name", "fuzzy": {"maxEdits": 2}}}},
        {"$limit": 5},
        {"$addFields": {"score": {"$meta": "searchScore"}}},
    ]
    if beats_per_bar:
        pipeline.insert(2, {"$match": {"beats_per_bar": beats_per_bar}})
    return next(db()["songs"].aggregate(pipeline), None)


def _text_terms(text: str, style: str, statuses: list[str], limit: int = 10) -> list[dict]:
    """Atlas Search over the glossary's words: a term's name and aliases (boosted) and its description."""
    pipeline = [
        {"$search": {"index": "term_text", "compound": {
            "should": [{"text": {"query": text, "path": ["term", "aliases"], "score": {"boost": {"value": 3}}}},
                       {"text": {"query": text, "path": "description"}}],
            "minimumShouldMatch": 1,
            "filter": [{"equals": {"path": "style", "value": style}}]}}},
        {"$match": {"status": {"$in": statuses}}},
        {"$limit": limit},
        {"$project": {"_id": 0, "term": 1, "description": 1, "status": 1, "aliases": 1, "display_names": 1,
                      "score": {"$meta": "searchScore"}}},
    ]
    return list(db()["terms"].aggregate(pipeline))


def match_terms_hybrid(text: str, style: str, k: int = 4, include_drafts: bool = False,
                       explain: bool = False):
    """Hybrid Search over the glossary: Atlas Vector Search (what the described movement means) and Atlas Search
    (the words: a term's name, aliases, description), fused by reciprocal rank fusion (1 / (60 + rank)) in our code,
    since the cluster is MongoDB 8.0 and $rankFusion needs 8.1. A line that names the step ranks it first even when
    the description alone is vague; a description with no name still finds it by meaning. Vetted terms only unless
    include_drafts. With explain=True, also returns both rankings."""
    statuses = list(SPOKEN_STATUSES) + (["draft"] if include_drafts else [])
    vector = match_terms(text, style, k=10, include_drafts=include_drafts)
    words = _text_terms(text, style, statuses)
    fused, docs = {}, {}
    for ranking in (vector, words):
        for rank, d in enumerate(ranking, 1):
            fused[d["term"]] = fused.get(d["term"], 0.0) + 1 / (60 + rank)
            docs.setdefault(d["term"], d)
    best = [{**docs[t], "score": round(fused[t], 5)} for t in sorted(fused, key=fused.get, reverse=True)[:k]]
    return (best, vector, words) if explain else best


def find_show(query: str) -> dict:
    """The show a studio means by a partial name ("andrii waltz" for "Spring showcase: Andrii, waltz"): an exact name
    first, else the one show whose name, studio, song or style contains every typed word. A plain query, not Atlas
    Search: the free cluster's three search indexes are taken. Stops and lists the candidates rather than guess when
    several match."""
    import re
    shows = db()["shows"]
    exact = shows.find_one({"name": {"$regex": f"^{re.escape(query.strip())}$", "$options": "i"}})
    if exact:
        return exact
    fields = ("name", "studio", "song", "style")
    words = query.split()
    # Each word must start a word somewhere ("andri" finds Andrii; "3" isn't found inside "mp3")
    found = list(shows.find({"$and": [{"$or": [{f: {"$regex": f"(^|[^a-z0-9]){re.escape(w)}", "$options": "i"}}
                                               for f in fields]} for w in words]})) if words else []
    if len(found) == 1:
        print(f"show found: {found[0]['name']}")
        return found[0]
    if not found:
        raise SystemExit(f"no show matches {query!r}; prepare it with scripts/prepare_show.py")
    raise SystemExit(f"{len(found)} shows match {query!r}; use more of the name:\n"
                     + "\n".join(f"  {s['name']}  ({s.get('studio') or 'no studio'}, {s.get('song')})" for s in found))


if __name__ == "__main__" and len(__import__("sys").argv) > 2:
    import sys
    if sys.argv[1] == "song":       # python server/db.py song "andrii waltz"
        hit = find_song(sys.argv[2])
        print({k: hit[k] for k in ("name", "file", "bpm", "beats_per_bar", "score")} if hit else "no match")
    elif sys.argv[1] == "terms":    # python server/db.py terms waltz "turning right as a couple, a natural turn"
        best, vector, words = match_terms_hybrid(sys.argv[3], sys.argv[2], explain=True)
        print("vector: ", [d["term"] for d in vector[:5]])
        print("text:   ", [d["term"] for d in words[:5]])
        print("hybrid: ", [(d["term"], d["score"]) for d in best])
    elif sys.argv[1] == "show":     # python server/db.py show "andrii waltz"
        hit = find_show(sys.argv[2])
        print({k: hit.get(k) for k in ("name", "studio", "song", "style")})
