"""Provision the Atlas database: collections and the search indexes.

Run this once after MONGODB_URI is set in .env (see .env.example). It is idempotent,
so running it again only fills in whatever is missing.

    python server/setup_db.py          # create collections + indexes
    python server/setup_db.py --seed   # also insert one example term and song

Creates:
  - collections: terms, songs, show_memory
  - vector_index on terms.embedding   (Atlas Vector Search, for glossary lookup)
  - song_name   on songs.name         (Atlas Search, for selecting a song by announced name)

Search indexes need an Atlas cluster (they do not exist on a plain local mongod) and take a
minute or two to build after creation. Check what landed with:  python server/db.py
"""

import argparse

from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from db import db

COLLECTIONS = ["terms", "songs", "show_memory"]

# gemini-embedding-2 / gemini-embedding-001 default to 3072 dimensions. Change this if the
# glossary is embedded at a different output dimension (both models support 768 / 1536 / 3072),
# or drop the vector index entirely if Atlas Automated Embedding is used instead.
EMBED_DIM = 3072

VECTOR_INDEX = SearchIndexModel(
    name="vector_index",
    type="vectorSearch",
    definition={
        "fields": [
            {"type": "vector", "path": "embedding", "numDimensions": EMBED_DIM, "similarity": "cosine"},
            {"type": "filter", "path": "style"},
        ]
    },
)

SONG_NAME_INDEX = SearchIndexModel(
    name="song_name",
    type="search",
    definition={"mappings": {"dynamic": False, "fields": {"name": {"type": "string"}}}},
)


def ensure_collections(database):
    existing = set(database.list_collection_names())
    for name in COLLECTIONS:
        if name in existing:
            print(f"collection '{name}': already there")
        else:
            database.create_collection(name)
            print(f"collection '{name}': created")


def ensure_standard_indexes(database):
    name = database.terms.create_index(
        [("style", 1), ("term", 1)], unique=True, name="term_style_unique"
    )
    print(f"terms.{name}: ready")


def ensure_search_index(collection, model):
    have = {idx["name"] for idx in collection.list_search_indexes()}
    if model.document["name"] in have:
        print(f"{collection.name}.{model.document['name']}: already there")
        return
    collection.create_search_index(model)
    print(f"{collection.name}.{model.document['name']}: created (building, ~1-2 min)")


def seed(database):
    """One example document per collection, matching the shapes in SPEC.md section 4."""
    if database.terms.count_documents({}) == 0:
        database.terms.insert_one({
            "term": "natural turn", "style": "ballroom",
            "description": "a couple rotates clockwise while travelling, rising through the turn",
            "names": {"en": "natural turn", "uk": "", "de": "Rechtsdrehung", "hi": ""},
            "sources": [], "embedding": None,
        })
        print("seeded terms: 1 example")
    if database.songs.count_documents({}) == 0:
        database.songs.insert_one({
            "name": "Sugar Plum Fairy", "style": "ballet", "bpm": None,
            "beats_per_bar": 2, "beats": [], "phrases": [], "clean_spaces": [],
        })
        print("seeded songs: 1 example")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="insert one example term and song")
    args = parser.parse_args()

    database = db()
    database.client.admin.command("ping")
    print(f"connected to '{database.name}'")

    ensure_collections(database)
    ensure_standard_indexes(database)
    try:
        ensure_search_index(database.terms, VECTOR_INDEX)
        ensure_search_index(database.songs, SONG_NAME_INDEX)
    except OperationFailure as e:
        print(f"\nsearch index step failed: {e}\n"
              "(search indexes need an Atlas cluster; a plain local mongod can't build them.)")

    if args.seed:
        seed(database)

    print("\ndone. Verify with: python server/db.py")


if __name__ == "__main__":
    main()
