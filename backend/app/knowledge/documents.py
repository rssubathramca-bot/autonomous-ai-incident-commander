from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .schemas import KnowledgeFile


class KnowledgeLoadError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedDocument:
    path: Path
    data: KnowledgeFile


def default_knowledge_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "knowledge"


def load_knowledge_documents(directory: Path | None = None) -> list[LoadedDocument]:
    root = directory or default_knowledge_directory()
    if not root.is_dir():
        raise KnowledgeLoadError(f"Knowledge directory does not exist: {root}")

    paths = sorted(root.rglob("*.json"))
    if not paths:
        raise KnowledgeLoadError(f"No JSON knowledge documents found in {root}")

    documents: list[LoadedDocument] = []
    seen_ids: set[str] = set()
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            document = KnowledgeFile.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise KnowledgeLoadError(f"Invalid knowledge document {path.name}: {error}") from error

        document_id = document.metadata.document_id
        if document_id in seen_ids:
            raise KnowledgeLoadError(f"Duplicate knowledge document ID: {document_id}")
        seen_ids.add(document_id)
        documents.append(LoadedDocument(path=path, data=document))
    return documents
