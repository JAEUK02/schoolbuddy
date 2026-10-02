"""Notice validation and injected I/O helpers; importing this module has no I/O."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import json


class NoticeValidationError(ValueError):
    """A model response is not a renderable notice object."""


class DatabaseUnavailableError(RuntimeError):
    """The configured connection factory could not return a connection."""


def validate_notice(payload):
    """Validate known fields, retain unknown fields, and never supply a date."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise NoticeValidationError("Notice must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise NoticeValidationError("Notice must be a JSON object")
    notice = deepcopy(payload)
    for field in ("title", "summary"):
        if not isinstance(notice.get(field), str) or not notice[field].strip():
            raise NoticeValidationError(f"Notice {field} must be nonempty text")
    if notice.get("details") is None:
        notice["details"] = {}
    if not isinstance(notice["details"], dict):
        raise NoticeValidationError("Notice details must be an object or null")
    date = notice["details"].get("date")
    if date is not None and not isinstance(date, str):
        raise NoticeValidationError("Notice date must be text or null")
    return notice


def _same_shape(original, translated):
    if isinstance(original, dict):
        return (
            isinstance(translated, dict)
            and original.keys() == translated.keys()
            and all(_same_shape(value, translated[key]) for key, value in original.items())
        )
    if isinstance(original, list):
        return (
            isinstance(translated, list)
            and len(original) == len(translated)
            and all(_same_shape(a, b) for a, b in zip(original, translated))
        )
    if isinstance(original, str):
        return isinstance(translated, str)
    return type(original) is type(translated) and original == translated


def translated_notice_or_original(original, translated):
    """Accept translated strings only when the original structure is preserved."""
    original = validate_notice(original)
    try:
        # Check the model's shape before normalizing details=null.
        candidate = json.loads(translated) if isinstance(translated, str) else translated
        if not _same_shape(original, candidate):
            return original
        return validate_notice(candidate)
    except (NoticeValidationError, ValueError, TypeError):
        return original


def chunk_text(text):
    """Keep the experiment's 1,000-character windows and 800-character stride."""
    return [text[i:i + 1000] for i in range(0, len(text), 800)]


def recent_analysis_objects(response, limit=3):
    """Handle S3's missing/empty Contents without indexing a missing UI key."""
    objects = [
        obj for obj in (response.get("Contents") or [])
        if isinstance(obj.get("Key"), str) and obj["Key"].endswith(".json")
    ]
    return sorted(objects, key=lambda obj: str(obj.get("LastModified", "")), reverse=True)[:limit]


@contextmanager
def database_cursor(connection, *, commit=False):
    """Close both resources on all paths; roll back work after any failure."""
    cursor = None
    try:
        cursor = connection.cursor()
        yield cursor
        if commit:
            connection.commit()
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        try:
            connection.close()
        except Exception:
            pass


def index_notice(text, file_name, file_ext, connect, embeddings_factory):
    connection = connect()
    if connection is None:
        raise DatabaseUnavailableError("Notice indexing requires a database connection")
    chunks = chunk_text(text)
    with database_cursor(connection, commit=True) as cursor:
        embeddings = embeddings_factory()
        for chunk in chunks:
            vector = embeddings.embed_query(chunk)
            cursor.execute(
                "INSERT INTO documents (content, embedding, metadata) VALUES (%s, %s, %s)",
                (chunk, vector, json.dumps({"source": file_name, "type": file_ext})),
            )
    return len(chunks)


@dataclass
class IngestionResult:
    raw_saved: bool = False
    summary_saved: bool = False
    indexed: bool = False
    indexed_chunks: int = 0
    failed_stage: str | None = None
    error_code: str | None = None


def ingest_notice(*, s3, bucket, file_bytes, file_name, extract_text, analyze_text,
                  connect, embeddings_factory):
    """Record partial progress; never delete already stored S3 objects on failure."""
    result = IngestionResult()
    stage = "raw_upload"
    try:
        s3.put_object(Bucket=bucket, Key=f"raw/{file_name}", Body=file_bytes)
        result.raw_saved = True
        stage = "extract_text"
        text = extract_text(file_bytes, file_name)
        if not isinstance(text, str) or not text.strip():
            result.failed_stage = stage
            result.error_code = "no_text"
            return result
        stage = "summary"
        notice = validate_notice(analyze_text(text))
        s3.put_object(
            Bucket=bucket, Key=f"analysis/{file_name}.json",
            Body=json.dumps(notice, ensure_ascii=False),
        )
        result.summary_saved = True
        stage = "index"
        result.indexed_chunks = index_notice(
            text, file_name, file_name.rsplit(".", 1)[-1].lower(),
            connect, embeddings_factory,
        )
        result.indexed = True
    except Exception as exc:
        result.failed_stage = stage
        if isinstance(exc, NoticeValidationError):
            result.error_code = "invalid_notice"
        elif isinstance(exc, DatabaseUnavailableError):
            result.error_code = "db_unavailable"
        else:
            result.error_code = "operation_failed"
    return result
