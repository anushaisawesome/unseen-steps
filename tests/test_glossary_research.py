import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import glossary_research as glossary  # noqa: E402
import settings  # noqa: E402


class GlossaryResearchTests(unittest.TestCase):
    def test_extracts_single_fenced_json_object(self):
        report = "Research notes.\n```json\n{\"terms\": [{\"term\": \"natural turn\"}]}\n```"
        self.assertEqual(glossary.extract_json_report(report)["terms"][0]["term"], "natural turn")

    def test_validates_sourced_skeleton_and_sets_review_state(self):
        payload = {
            "terms": [
                {
                    "term": "natural turn",
                    "category": "figure",
                    "description": "The couple rotates while travelling.",
                    "signature": "Two people in hold rotate and travel.",
                    "aliases": ["right turn"],
                    "names": {"en": "Natural Turn"},
                    "sources": {"en": ["https://www.wdsf.org/a", "https://www.istd.org/b"]},
                    "status": "vetted",
                }
            ]
        }
        documents, warnings = glossary.validate_skeleton(payload, "waltz")
        self.assertEqual(warnings, [])
        self.assertEqual(documents[0]["style"], "waltz")
        self.assertEqual(documents[0]["status"], "draft")
        self.assertEqual(documents[0]["trust"], "pending")
        self.assertIsNone(documents[0]["vetted_by"])

    def test_unsourced_skeleton_term_is_dropped(self):
        payload = {
            "terms": [
                {
                    "term": "mystery move",
                    "description": "Unknown.",
                    "signature": "Unknown.",
                    "sources": {"en": []},
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "No valid sourced terms"):
            glossary.validate_skeleton(payload, "waltz")

    def test_translations_are_limited_to_vetted_terms(self):
        payload = {
            "translations": [
                {
                    "term": "natural turn",
                    "name": "Rechtsdrehung",
                    "sources": ["https://www.tanzsport.de/a"],
                },
                {
                    "term": "invented term",
                    "name": "Erfunden",
                    "sources": ["https://www.dtv.de/b"],
                },
            ]
        }
        updates, warnings = glossary.validate_translations(payload, ["natural turn"])
        self.assertEqual([item["term"] for item in updates], ["natural turn"])
        self.assertTrue(any("not in the vetted glossary" in warning for warning in warnings))

    def test_translation_prompt_preserves_exact_english_terms(self):
        prompt = glossary.translation_prompt("waltz", "uk", ["natural turn", "closed change"])
        self.assertIn("1. natural turn", prompt)
        self.assertIn("2. closed change", prompt)
        self.assertIn("Ukrainian", prompt)

    def test_legacy_local_env_names_are_supported(self):
        with patch.dict(
            settings.os.environ,
            {
                "GEMINI_API_KEY": "",
                "GOOGLE_API_KEY": "",
                "Google_Gemini_API_Key": "local-key",
                "MONGODB_URI": "",
                "MongoDB_URI": "mongodb://local",
            },
            clear=False,
        ):
            self.assertEqual(settings.gemini_api_key(), "local-key")
            self.assertEqual(settings.mongodb_uri(), "mongodb://local")

    def test_draft_json_is_serializable(self):
        payload = {
            "terms": [
                {
                    "term": "natural turn",
                    "description": "The couple rotates.",
                    "signature": "Two people rotate.",
                    "sources": {"en": ["https://www.wdsf.org/a"]},
                }
            ]
        }
        documents, _ = glossary.validate_skeleton(payload, "waltz")
        json.dumps(documents)

    def test_start_explicitly_stores_background_interaction(self):
        class FakeInteractions:
            def __init__(self):
                self.arguments = None

            def create(self, **kwargs):
                self.arguments = kwargs
                return SimpleNamespace(id="v1_validInteraction123", status="in_progress")

        interactions = FakeInteractions()
        client = SimpleNamespace(interactions=interactions)
        with patch.object(glossary, "_save_job"):
            glossary.start_research(client, style="waltz")
        arguments = interactions.arguments
        self.assertIsNotNone(arguments)
        assert arguments is not None
        self.assertTrue(arguments["background"])
        self.assertTrue(arguments["store"])
        self.assertEqual(arguments["agent"], glossary.AGENT)

    def test_output_fallback_ignores_user_prompt_json(self):
        user = SimpleNamespace(
            type="user_input",
            content=[SimpleNamespace(text='```json\n{"terms": [{"term": "placeholder"}]}\n```')],
        )
        final_text = 'Final report\n```json\n{"terms": [{"term": "closed change"}]}\n```'
        model = SimpleNamespace(type="model_output", content=[SimpleNamespace(text=final_text)])
        interaction = SimpleNamespace(output_text=None, steps=[user, model])
        self.assertEqual(glossary._output_text(interaction), final_text)

    def test_placeholder_and_search_urls_are_rejected(self):
        self.assertEqual(
            glossary._urls(
                [
                    "https://...",
                    "https://example.com/source",
                    "https://www.google.com/search?q=waltz",
                    "https://www.scribd.com/document/123/uploaded-copy",
                    "https://www.wdsf.org/source",
                ]
            ),
            ["https://www.wdsf.org/source"],
        )

    def test_max_terms_is_enforced(self):
        term = {
            "term": "natural turn",
            "description": "The couple rotates.",
            "signature": "Two people rotate.",
            "sources": {"en": ["https://www.wdsf.org/a"]},
        }
        with self.assertRaisesRegex(ValueError, "limit is 1"):
            glossary.validate_skeleton({"terms": [term, {**term, "term": "closed change"}]}, "waltz", 1)

    def test_translation_import_does_not_overwrite_vetted_local_name(self):
        class FakeTerms:
            def __init__(self):
                self.query = None

            def update_one(self, query, update):
                self.query = query
                return SimpleNamespace(matched_count=0, modified_count=0)

        terms = FakeTerms()
        database = SimpleNamespace(terms=terms)
        result = glossary.import_translations(
            database,
            style="waltz",
            language="de",
            translations=[{"term": "natural turn", "name": "Rechtsdrehung", "sources": []}],
            interaction_id="v1_validInteraction123",
        )
        query = terms.query
        self.assertIsNotNone(query)
        assert query is not None
        self.assertEqual(query["translations.de.status"], {"$ne": "vetted"})
        self.assertEqual(result["skipped"], 1)

    def test_skeleton_import_atomically_excludes_reviewed_terms(self):
        class FakeTerms:
            def __init__(self):
                self.query = None
                self.update = None
                self.inserted = False

            def create_index(self, *args, **kwargs):
                return "term_style_unique"

            def update_one(self, query, update, upsert=False):
                self.query = query
                self.update = update
                return SimpleNamespace(matched_count=0, modified_count=0)

            def find_one(self, query, projection):
                return {"_id": "reviewed"}

            def insert_one(self, value):
                self.inserted = True

        terms = FakeTerms()
        database = SimpleNamespace(terms=terms)
        result = glossary.import_skeleton(
            database,
            [
                {
                    "term": "natural turn",
                    "style": "waltz",
                    "description": "The couple rotates.",
                    "status": "draft",
                }
            ],
            embed=False,
        )
        assert terms.query is not None
        assert terms.update is not None
        self.assertEqual(terms.query["status"], {"$nin": ["vetted", "translated"]})
        self.assertEqual(terms.update["$unset"], {"embedding": ""})
        self.assertFalse(terms.inserted)
        self.assertEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
