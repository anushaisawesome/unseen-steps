"""Build the dance glossary with Gemini Deep Research.

Deep Research is asynchronous. Jobs are saved locally so they can be resumed after a
terminal closes, and nothing reaches MongoDB until a completed report passes validation.

Examples:
    python server/glossary_research.py start --style waltz
    python server/glossary_research.py collect INTERACTION_ID --wait
    python server/glossary_research.py run --style waltz --import-mongo --embed

After Andrii vets the English terms in MongoDB and marks them ``vetted``:
    python server/glossary_research.py run --style waltz --language uk --import-mongo
    python server/glossary_research.py run --style waltz --language de --import-mongo
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google import genai
from google.genai import types
from pymongo.errors import DuplicateKeyError

try:
    from .db import db
    from .settings import ROOT, gemini_api_key
except ImportError:  # Running as ``python server/glossary_research.py``.
    from db import db
    from settings import ROOT, gemini_api_key

AGENT = "deep-research-preview-04-2026"
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 3072
LANGUAGES = {"en": "English", "uk": "Ukrainian", "de": "German", "hi": "Hindi"}
ACTIVE_STATUSES = {"queued", "in_progress"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "incomplete", "budget_exceeded"}
ARTIFACTS = ROOT / "data" / "glossary-research"
JOBS = ARTIFACTS / "jobs"
REPORTS = ARTIFACTS / "reports"
DRAFTS = ARTIFACTS / "drafts"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def api_client() -> genai.Client:
    return genai.Client(api_key=gemini_api_key())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("Style must contain at least one letter or number")
    return slug


def _safe_interaction_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,512}", value):
        raise ValueError("Invalid Deep Research interaction ID")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _save_job(job: dict[str, Any]) -> Path:
    job["updated_at"] = utc_now()
    interaction_id = _safe_interaction_id(job["interaction_id"])
    path = JOBS / f"{interaction_id}.json"
    _write_json(path, job)
    return path


def load_job(identifier: str) -> dict[str, Any]:
    interaction_id = _safe_interaction_id(identifier)
    path = JOBS / f"{interaction_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No local Deep Research job found for {identifier}")
    return json.loads(path.read_text(encoding="utf-8"))


def skeleton_prompt(style: str, max_terms: int) -> str:
    return f"""Research an English skeleton glossary for {style} dance, for an accessibility system that
writes live audio description for blind and partially sighted audiences.

Scope and quality rules:
- Return at most {max_terms} common, visually identifiable {style} figures, actions, positions, or movement terms.
- Prefer governing-body or federation syllabi and reputable material by qualified dance teachers.
- Do not use forums, social posts, document-upload mirrors such as Scribd, or search-result pages as sources.
- Do not infer emotion, intention, music, or hidden footwork from sources or camera pose data.
- A term is useful only when a fixed camera and body keypoints could plausibly verify it.
- If sources disagree, say so in the description or omit the term. Do not guess.
- Use at least two independent direct HTTPS source URLs per term where possible. Do not cite search-result pages.

For every term provide:
- term: canonical English name
- category: short grouping such as figure, hold, action, alignment, or timing
- description: plain body-language description of what an audience can observe, with no unexplained dance jargon
- signature: concise measurable cues for a future pose/vision check (people count, hold, direction of travel,
  rotation, rise/fall, limb shape, timing, and any important limitation)
- aliases: established English alternatives only
- names.en: canonical English name
- sources.en: direct URLs that support the name and movement description

End the report with exactly one fenced JSON block matching this shape:
```json
{{
  "terms": [
    {{
      "term": "natural turn",
      "category": "figure",
      "description": "...",
      "signature": "...",
      "aliases": [],
      "names": {{"en": "natural turn"}},
      "sources": {{"en": ["https://...", "https://..."]}}
    }}
  ]
}}
```
The JSON must be valid: double quotes, no comments, no trailing commas. Do not put any other JSON block in the report."""


def translation_prompt(style: str, language: str, terms: list[str]) -> str:
    language_name = LANGUAGES[language]
    numbered = "\n".join(f"{i + 1}. {term}" for i, term in enumerate(terms))
    return f"""Research the names that {language_name}-speaking dancers actually use for this vetted English
{style} glossary. This is terminology research, not machine translation.

Use {language_name}-language dance federation syllabi, dance-school teaching material, and reputable
{language_name}-language dancer or teacher sources. Preserve borrowed English, French, or German terms when
that is what dancers actually say. If a term has no well-supported local name, return null rather than inventing one.
Use direct HTTPS URLs, not search-result pages.

Vetted English terms (return these exact English strings in the `term` field):
{numbered}

End the report with exactly one fenced JSON block matching this shape:
```json
{{
  "translations": [
    {{
      "term": "natural turn",
      "name": "locally used term or null",
      "sources": ["https://...", "https://..."]
    }}
  ]
}}
```
The JSON must be valid: double quotes, no comments, no trailing commas. Do not put any other JSON block in the report."""


def vetted_terms(style: str) -> list[str]:
    cursor = db().terms.find(
        {"style": style, "status": {"$in": ["vetted", "translated"]}},
        {"term": 1, "_id": 0},
    ).sort("term", 1)
    terms = [row["term"] for row in cursor if row.get("term")]
    if not terms:
        raise RuntimeError(
            f"No vetted {style} terms found. Vet the English draft in MongoDB before researching translations."
        )
    return terms


def start_research(
    client: genai.Client,
    *,
    style: str,
    language: str = "en",
    max_terms: int = 20,
) -> dict[str, Any]:
    style = style.strip().lower()
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    mode = "skeleton" if language == "en" else "translation"
    if mode == "translation":
        terms = vetted_terms(style)
        prompt = translation_prompt(style, language, terms)
    else:
        terms = []
        prompt = skeleton_prompt(style, max_terms)

    interaction = client.interactions.create(
        agent=AGENT,
        input=prompt,
        agent_config={
            "type": "deep-research",
            "thinking_summaries": "none",
            "visualization": "off",
            "collaborative_planning": False,
        },
        background=True,
        store=True,
    )
    interaction_id = getattr(interaction, "id", None)
    if not interaction_id:
        raise RuntimeError("Deep Research did not return an interaction ID")

    job = {
        "version": 1,
        "interaction_id": interaction_id,
        "agent": AGENT,
        "mode": mode,
        "style": style,
        "language": language,
        "max_terms": max_terms,
        "terms": terms,
        "prompt": prompt,
        "status": getattr(interaction, "status", None) or "in_progress",
        "created_at": utc_now(),
    }
    _save_job(job)
    return job


def _output_text(interaction: Any) -> str:
    text = getattr(interaction, "output_text", None)
    if text:
        return text
    # Never include user_input steps: the prompt contains illustrative JSON which must
    # not be mistaken for researched output. Use only the final model-output run.
    blocks: list[str] = []
    for step in reversed(getattr(interaction, "steps", None) or []):
        if getattr(step, "type", None) != "model_output":
            if blocks:
                break
            continue
        step_text = [
            value
            for content in (getattr(step, "content", None) or [])
            if (value := getattr(content, "text", None))
        ]
        if not step_text:
            if blocks:
                break
            continue
        blocks.insert(0, "".join(step_text))
    return "".join(blocks)


def wait_for_result(
    client: genai.Client,
    job: dict[str, Any],
    *,
    wait: bool,
    poll_seconds: float = 10,
    timeout_seconds: float = 3600,
) -> Any:
    started = time.monotonic()
    while True:
        interaction = client.interactions.get(id=job["interaction_id"])
        status = getattr(interaction, "status", None) or "unknown"
        job["status"] = status
        _save_job(job)
        if status == "completed":
            return interaction
        if status == "requires_action":
            raise RuntimeError("Deep Research requires unsupported client action; start a new job")
        if status in TERMINAL_STATUSES:
            errors = getattr(interaction, "errors", None) or getattr(interaction, "error", None)
            raise RuntimeError(f"Deep Research ended with status {status}: {errors or 'no error details'}")
        if not wait:
            return interaction
        if status not in ACTIVE_STATUSES:
            raise RuntimeError(f"Unexpected Deep Research status: {status}")
        if time.monotonic() - started >= timeout_seconds:
            raise TimeoutError(
                f"Deep Research is still {status}; resume with: "
                f"python server/glossary_research.py collect {job['interaction_id']} --wait"
            )
        time.sleep(poll_seconds)


def extract_json_report(report: str) -> dict[str, Any]:
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", report, flags=re.DOTALL | re.IGNORECASE)
    if len(fenced) != 1:
        raise ValueError(f"The completed report must contain exactly one fenced JSON object; found {len(fenced)}")
    try:
        value = json.loads(fenced[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"The completed report's JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("The completed report's JSON must be an object")
    return value


def _text(value: Any, field: str, *, required: bool = True, max_length: int = 2000) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > max_length:
        raise ValueError(f"{field} is longer than {max_length} characters")
    return cleaned


def _urls(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    clean: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        url = item.strip()
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        valid_host = bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", hostname))
        search_result = (
            hostname in {"google.com", "www.google.com", "bing.com", "www.bing.com", "search.yahoo.com"}
            and parsed.path.rstrip("/") in {"/search", "/search/"}
        ) or hostname in {"duckduckgo.com", "www.duckduckgo.com"}
        placeholder = hostname in {"example.com", "example.org", "example.net"}
        weak_source = hostname in {
            "scribd.com",
            "www.scribd.com",
            "dance-forums.com",
            "www.dance-forums.com",
        }
        if (
            parsed.scheme == "https"
            and valid_host
            and not parsed.username
            and not parsed.password
            and not search_result
            and not placeholder
            and not weak_source
            and url not in clean
        ):
            clean.append(url)
    return clean


def validate_skeleton(
    payload: dict[str, Any], style: str, max_terms: int = 20
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_terms = payload.get("terms")
    if not isinstance(raw_terms, list):
        raise ValueError("JSON must contain a terms array")
    if len(raw_terms) > max_terms:
        raise ValueError(f"Report returned {len(raw_terms)} terms; limit is {max_terms}")

    documents: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_terms, 1):
        try:
            if not isinstance(raw, dict):
                raise ValueError("entry must be an object")
            term = _text(raw.get("term"), "term", max_length=120)
            key = term.casefold()
            if key in seen:
                warnings.append(f"Skipped duplicate term: {term}")
                continue
            description = _text(raw.get("description"), f"{term}.description")
            signature = _text(raw.get("signature"), f"{term}.signature")
            category = _text(raw.get("category"), f"{term}.category", required=False, max_length=80)
            aliases = raw.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            aliases = [
                cleaned
                for alias in aliases
                if isinstance(alias, str) and (cleaned := " ".join(alias.split())) and cleaned.casefold() != key
            ]
            sources = raw.get("sources", {})
            source_urls = _urls(sources.get("en") if isinstance(sources, dict) else sources)
            if not source_urls:
                raise ValueError("at least one direct HTTPS source is required")
            if len(source_urls) < 2:
                warnings.append(f"{term}: only one source; verify carefully before vetting")

            names = raw.get("names", {})
            english_name = term
            if isinstance(names, dict) and names.get("en"):
                english_name = _text(names["en"], f"{term}.names.en", max_length=120)

            documents.append(
                {
                    "term": term,
                    "style": style,
                    "category": category,
                    "description": description,
                    "signature": signature,
                    "aliases": sorted(set(aliases), key=str.casefold),
                    "names": {"en": english_name},
                    "sources": {"en": source_urls},
                    "status": "draft",
                    "trust": "pending",
                    "vetted_by": None,
                }
            )
            seen.add(key)
        except ValueError as exc:
            warnings.append(f"Skipped term {index}: {exc}")

    if not documents:
        raise ValueError("No valid sourced terms remained after validation")
    return documents, warnings


def validate_translations(
    payload: dict[str, Any], expected_terms: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_items = payload.get("translations")
    if not isinstance(raw_items, list):
        raise ValueError("JSON must contain a translations array")

    expected = {term.casefold(): term for term in expected_terms}
    updates: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped translation {index}: entry must be an object")
            continue
        term_value = raw.get("term")
        name_value = raw.get("name")
        if not isinstance(term_value, str) or term_value.casefold() not in expected:
            warnings.append(f"Skipped translation {index}: term is not in the vetted glossary")
            continue
        canonical = expected[term_value.casefold()]
        if canonical.casefold() in seen:
            warnings.append(f"Skipped duplicate translation: {canonical}")
            continue
        if name_value is None:
            warnings.append(f"{canonical}: no supported local name found")
            seen.add(canonical.casefold())
            continue
        try:
            name = _text(name_value, f"{canonical}.name", max_length=160)
        except ValueError as exc:
            warnings.append(f"Skipped {canonical}: {exc}")
            continue
        source_urls = _urls(raw.get("sources"))
        if not source_urls:
            warnings.append(f"Skipped {canonical}: no direct HTTPS source")
            continue
        if len(source_urls) < 2:
            warnings.append(f"{canonical}: only one translation source; review carefully")
        updates.append({"term": canonical, "name": name, "sources": source_urls})
        seen.add(canonical.casefold())

    if not updates:
        raise ValueError("No valid sourced translations remained after validation")
    return updates, warnings


def collect_job(
    client: genai.Client,
    job: dict[str, Any],
    *,
    wait: bool,
    poll_seconds: float = 10,
    timeout_seconds: float = 3600,
) -> tuple[dict[str, Any] | None, list[str]]:
    interaction = wait_for_result(
        client,
        job,
        wait=wait,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
    )
    if getattr(interaction, "status", None) != "completed":
        return None, []

    report = _output_text(interaction)
    if not report.strip():
        raise RuntimeError("Deep Research completed without text output")
    report_path = REPORTS / f"{job['interaction_id']}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    payload = extract_json_report(report)
    if job["mode"] == "skeleton":
        records, warnings = validate_skeleton(payload, job["style"], job["max_terms"])
        key = "terms"
    else:
        records, warnings = validate_translations(payload, job["terms"])
        key = "translations"

    research = {
        "agent": job["agent"],
        "interaction_id": job["interaction_id"],
        "completed_at": utc_now(),
        "report": str(report_path.relative_to(ROOT)),
    }
    if key == "terms":
        for record in records:
            record["research"] = research

    draft = {
        "version": 1,
        "interaction_id": job["interaction_id"],
        "mode": job["mode"],
        "style": job["style"],
        "language": job["language"],
        key: records,
        "warnings": warnings,
    }
    draft_path = DRAFTS / f"{job['interaction_id']}.json"
    _write_json(draft_path, draft)
    job.update(
        {
            "status": "completed",
            "report_path": str(report_path.relative_to(ROOT)),
            "draft_path": str(draft_path.relative_to(ROOT)),
            "record_count": len(records),
            "warnings": warnings,
        }
    )
    _save_job(job)
    return draft, warnings


def add_embeddings(client: genai.Client, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    embedded = copy.deepcopy(documents)
    for document in embedded:
        content = f"title: {document['term']} | text: {document['description']}"
        result = client.models.embed_content(
            model=EMBED_MODEL,
            contents=content,
            config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
        )
        embeddings = getattr(result, "embeddings", None) or []
        values = getattr(embeddings[0], "values", None) if embeddings else None
        if not values or len(values) != EMBED_DIM:
            raise RuntimeError(f"Embedding failed for {document['term']}: expected {EMBED_DIM} values")
        document["embedding"] = list(values)
    return embedded


def import_skeleton(
    database: Any,
    documents: list[dict[str, Any]],
    *,
    client: genai.Client | None = None,
    embed: bool = False,
) -> dict[str, int]:
    if embed:
        if client is None:
            raise ValueError("A Gemini client is required to create embeddings")
        documents = add_embeddings(client, documents)

    database.terms.create_index([("style", 1), ("term", 1)], unique=True, name="term_style_unique")
    counts = {"matched": 0, "modified": 0, "upserted": 0, "skipped": 0}
    now = utc_now()
    for document in documents:
        query = {"style": document["style"], "term": document["term"]}
        value = copy.deepcopy(document)
        value["updated_at"] = now
        update: dict[str, Any] = {"$set": value}
        if not embed:
            update["$unset"] = {"embedding": ""}
        result = database.terms.update_one(
            {**query, "status": {"$nin": ["vetted", "translated"]}},
            update,
            upsert=False,
        )
        if result.matched_count:
            counts["matched"] += result.matched_count
            counts["modified"] += result.modified_count
            continue
        if database.terms.find_one(query, {"_id": 1}):
            counts["skipped"] += 1
            continue
        value["created_at"] = now
        try:
            database.terms.insert_one(value)
            counts["upserted"] += 1
        except DuplicateKeyError:
            # Another writer inserted or protected the same term after our check.
            counts["skipped"] += 1
    return counts


def import_translations(
    database: Any,
    *,
    style: str,
    language: str,
    translations: list[dict[str, Any]],
    interaction_id: str,
) -> dict[str, int]:
    counts = {"matched": 0, "modified": 0, "upserted": 0, "skipped": 0}
    now = utc_now()
    for item in translations:
        result = database.terms.update_one(
            {
                "style": style,
                "term": item["term"],
                "status": {"$in": ["vetted", "translated"]},
                f"translations.{language}.status": {"$ne": "vetted"},
            },
            {
                "$set": {
                    f"names.{language}": item["name"],
                    f"sources.{language}": item["sources"],
                    f"translations.{language}": {
                        "status": "researched",
                        "interaction_id": interaction_id,
                        "updated_at": now,
                    },
                    "status": "translated",
                    "updated_at": now,
                }
            },
        )
        counts["matched"] += result.matched_count
        counts["modified"] += result.modified_count
        if not result.matched_count:
            counts["skipped"] += 1
    return counts


def import_draft(
    draft: dict[str, Any], *, client: genai.Client, embed: bool
) -> dict[str, int]:
    database = db()
    database.client.admin.command("ping")
    if draft["mode"] == "skeleton":
        if not embed:
            raise ValueError("English glossary imports require --embed so vectors cannot become stale")
        return import_skeleton(database, draft["terms"], client=client, embed=True)
    return import_translations(
        database,
        style=draft["style"],
        language=draft["language"],
        translations=draft["translations"],
        interaction_id=draft["interaction_id"],
    )


def _print_summary(job: dict[str, Any], draft: dict[str, Any] | None, warnings: list[str]) -> None:
    print(f"interaction: {job['interaction_id']}")
    print(f"status: {job['status']}")
    if draft:
        count = len(draft.get("terms", draft.get("translations", [])))
        print(f"validated records: {count}")
        print(f"report: {job['report_path']}")
        print(f"draft: {job['draft_path']}")
    for warning in warnings:
        print(f"warning: {warning}")


def _common_start_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--style", default="waltz", help="dance style (default: waltz)")
    parser.add_argument("--language", choices=sorted(LANGUAGES), default="en")
    parser.add_argument("--max-terms", type=int, default=20, choices=range(1, 51), metavar="1-50")


def _collect_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--poll-seconds", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=3600, help="maximum seconds to wait")
    parser.add_argument("--import-mongo", action="store_true", help="write validated records to MongoDB")
    parser.add_argument("--embed", action="store_true", help="embed English drafts before MongoDB import")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start a background Deep Research job")
    _common_start_arguments(start)

    collect = subparsers.add_parser("collect", help="check or collect an existing job")
    collect.add_argument("interaction_id")
    collect.add_argument("--wait", action="store_true")
    _collect_arguments(collect)

    run = subparsers.add_parser("run", help="start, wait, validate, and optionally import")
    _common_start_arguments(run)
    _collect_arguments(run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "embed", False) and not getattr(args, "import_mongo", False):
        raise ValueError("--embed requires --import-mongo")
    client = api_client()

    if args.command == "start":
        job = start_research(
            client,
            style=args.style,
            language=args.language,
            max_terms=args.max_terms,
        )
        _print_summary(job, None, [])
        print(f"resume: python server/glossary_research.py collect {job['interaction_id']} --wait")
        return 0

    if args.command == "collect":
        job = load_job(args.interaction_id)
        draft, warnings = collect_job(
            client,
            job,
            wait=args.wait,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout,
        )
    else:
        job = start_research(
            client,
            style=args.style,
            language=args.language,
            max_terms=args.max_terms,
        )
        print(f"started Deep Research: {job['interaction_id']}")
        draft, warnings = collect_job(
            client,
            job,
            wait=True,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout,
        )

    if draft and args.import_mongo:
        result = import_draft(draft, client=client, embed=args.embed)
        job["mongo_import"] = result
        _save_job(job)
        print("MongoDB: " + ", ".join(f"{key}={value}" for key, value in result.items()))
    _print_summary(job, draft, warnings)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
