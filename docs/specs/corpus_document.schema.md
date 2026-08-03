# corpus_document

Canonical module: `backend/src/starmap/contracts/corpus_document.py`.

Registry metadata for one corpus document, per tech reference 1.1 with the Foothold deltas: `track_tags` is dropped entirely.
Document text is deliberately not a field; text lives in the registry beside the record so the metadata schema stays small and exportable.

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `doc_id` | str | Pattern `^doc_[0-9a-f]{16}$`; must equal its derivation (below). |
| `source_url` | str | Non-empty. |
| `source_type` | literal | One of `bulletin_course`, `bulletin_requirement`. |
| `license_note` | str | Non-empty; no license basis means no registration. |
| `date_collected` | date | ISO date. |
| `source_published_date` | date or null | Must not be after `date_collected`; defaults to null. |
| `content_hash` | str | Pattern `^[0-9a-f]{64}$`; sha256 of the normalized document text. |
| `title` | str | Non-empty. |

## Validators

| Validator | Rule |
| --- | --- |
| Id derivation | `doc_id == "doc_" + sha256_hex(f"{source_url}\n{date_collected.isoformat()}")[:16]`, re-implemented inline via `sha256_hex`; the message quotes actual and derived ids. |
| Date ordering | `source_published_date <= date_collected`; the message names both fields and quotes both values. |

## Example

```json
{
  "doc_id": "doc_1bd714332f93cc04",
  "source_url": "https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/",
  "source_type": "bulletin_course",
  "license_note": "Columbia University bulletin, quoted for course discovery with source attribution.",
  "date_collected": "2026-07-31",
  "source_published_date": null,
  "content_hash": "f6b252c4db65a2ec92a928afe8d1be716a1c82b7f9654704eb50bab8fe8bd204",
  "title": "COMS W4701 Artificial Intelligence"
}
```
