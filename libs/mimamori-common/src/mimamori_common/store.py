"""Storage behind small repository classes, one per Firestore database.

    DocumentStore  (InMemoryStore | FirestoreStore)      generic collections of JSON documents
    CaseRepo       case-db   (Scoring and the case service ONLY)
    IntelRepo      intel-db  (playbooks, question banks)
    RefRepo        ref-db    (watchlist snapshots)

Services import the repos, never the Firestore SDK. The in-memory implementation is shared per
database ID within a process (so two repos opened in one test see the same data); call
`reset_memory_stores()` between tests. Documents are plain JSON dicts: pass `model.model_dump(mode="json")`.
"""

from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Any, Protocol

from .config import Settings
from .models.baseline import WatchlistSnapshot

# Defence in depth for the data boundary (DA 16): these services must never open case-db, even by mistake.
CASE_DB_FORBIDDEN_SERVICES = {
    "conversation-svc", "watchlist-loader", "intel-job", "sim-job", "web-ui", "core-bank-mock",
}


class DocumentStore(Protocol):
    def get(self, collection: str, doc_id: str) -> dict | None: ...
    def set(self, collection: str, doc_id: str, doc: dict) -> None: ...
    def update(self, collection: str, doc_id: str, patch: dict) -> dict: ...
    def delete(self, collection: str, doc_id: str) -> None: ...
    def list(self, collection: str, *, where: dict[str, Any] | None = None, order_by: str | None = None,
             descending: bool = False, limit: int | None = None) -> list[dict]: ...


class InMemoryStore:
    _named: dict[str, "InMemoryStore"] = {}
    _named_lock = threading.Lock()

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = {}
        self._lock = threading.RLock()

    @classmethod
    def named(cls, db_id: str) -> "InMemoryStore":
        with cls._named_lock:
            return cls._named.setdefault(db_id, cls())

    def get(self, collection, doc_id):
        with self._lock:
            doc = self._data.get(collection, {}).get(doc_id)
            return copy.deepcopy(doc) if doc is not None else None

    def set(self, collection, doc_id, doc):
        with self._lock:
            self._data.setdefault(collection, {})[doc_id] = copy.deepcopy(doc)

    def update(self, collection, doc_id, patch):
        with self._lock:
            current = self._data.setdefault(collection, {}).setdefault(doc_id, {})
            current.update(copy.deepcopy(patch))
            return copy.deepcopy(current)

    def delete(self, collection, doc_id):
        with self._lock:
            self._data.get(collection, {}).pop(doc_id, None)

    def list(self, collection, *, where=None, order_by=None, descending=False, limit=None):
        with self._lock:
            docs = [copy.deepcopy(d) for d in self._data.get(collection, {}).values()]
        for key, value in (where or {}).items():
            docs = [d for d in docs if d.get(key) == value]
        if order_by:
            docs.sort(key=lambda d: (d.get(order_by) is None, d.get(order_by)), reverse=descending)
        return docs[:limit] if limit else docs

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class FirestoreStore:
    """Firestore Native, one named database per instance. Uses the emulator when
    FIRESTORE_EMULATOR_HOST is set. Needs the `cloud` extra. Verified against the emulator (named
    databases, filters, ordering); not yet against real Firestore, see infra/README.md."""

    def __init__(self, database_id: str, project: str | None = None) -> None:
        from google.cloud import firestore  # lazy: not needed locally or in tests

        self._client = firestore.Client(project=project, database=database_id)

    def get(self, collection, doc_id):
        snap = self._client.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def set(self, collection, doc_id, doc):
        self._client.collection(collection).document(doc_id).set(doc)

    def update(self, collection, doc_id, patch):
        ref = self._client.collection(collection).document(doc_id)
        ref.set(patch, merge=True)
        return ref.get().to_dict()

    def delete(self, collection, doc_id):
        self._client.collection(collection).document(doc_id).delete()

    def list(self, collection, *, where=None, order_by=None, descending=False, limit=None):
        # Equality filters only; sorting and limiting happen here so no composite indexes are needed.
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self._client.collection(collection)
        for key, value in (where or {}).items():
            query = query.where(filter=FieldFilter(key, "==", value))
        docs = [snap.to_dict() for snap in query.stream()]
        if order_by:
            docs.sort(key=lambda d: (d.get(order_by) is None, d.get(order_by)), reverse=descending)
        return docs[:limit] if limit else docs


def _open(settings: Settings, db_id: str) -> DocumentStore:
    if settings.store_backend == "firestore":
        return FirestoreStore(db_id, settings.project_id)
    if settings.store_backend == "memory":
        return InMemoryStore.named(db_id)
    raise ValueError(f"unknown MIMAMORI_STORE {settings.store_backend!r} (memory | firestore)")


def reset_memory_stores() -> None:
    with InMemoryStore._named_lock:
        for store in InMemoryStore._named.values():
            store.clear()


def _iso(value: datetime | str | None = None) -> str:
    return value if isinstance(value, str) else (value or datetime.now().astimezone()).isoformat()


class CaseRepo:
    """`case-db`: baselines, scores, advance wishes (versioned), cases, cards, events, audit,
    freeze requests, learning-loop proposals. Only Scoring and the case service may open it."""

    def __init__(self, store: DocumentStore) -> None:
        self.store = store

    # baselines and scores (Scoring writes; case service reads baselines)
    def put_baseline(self, customer_ref: str, doc: dict) -> None:
        self.store.set("baselines", customer_ref, doc)

    def get_baseline(self, customer_ref: str) -> dict | None:
        return self.store.get("baselines", customer_ref)

    def put_score(self, transfer_id: str, doc: dict) -> None:
        self.store.set("scores", transfer_id, doc)

    def get_score(self, transfer_id: str) -> dict | None:
        return self.store.get("scores", transfer_id)

    # advance wishes: document id `<customer_ref>:v<version>`
    def put_wishes(self, wishes: dict) -> None:
        self.store.set("wishes", f"{wishes['customer_ref']}:v{wishes['version']}", wishes)

    def get_active_wishes(self, customer_ref: str) -> dict | None:
        docs = self.store.list("wishes", where={"customer_ref": customer_ref, "status": "active"}, order_by="version", descending=True, limit=1)
        return docs[0] if docs else None

    def list_wishes(self, customer_ref: str) -> list[dict]:
        return self.store.list("wishes", where={"customer_ref": customer_ref}, order_by="version")

    # cases and cards
    def put_case(self, case: dict) -> None:
        self.store.set("cases", case["case_id"], case)

    def get_case(self, case_id: str) -> dict | None:
        return self.store.get("cases", case_id)

    def list_cases(self, status: str | None = None) -> list[dict]:
        return self.store.list("cases", where={"status": status} if status else None, order_by="opened_at", descending=True)

    def put_card(self, card: dict) -> None:
        self.store.set("cards", card["case_id"], card)

    def get_card(self, case_id: str) -> dict | None:
        return self.store.get("cards", case_id)

    # per-case event log (replayed to SSE subscribers) and audit trail
    def append_event(self, case_id: str, event: dict) -> dict:
        event = {**event, "case_id": case_id, "seq": len(self.list_events(case_id)) + 1}
        self.store.set("events", f"{case_id}:{event['seq']:06d}", event)
        return event

    def list_events(self, case_id: str, after_seq: int = 0) -> list[dict]:
        docs = self.store.list("events", where={"case_id": case_id}, order_by="seq")
        return [d for d in docs if d["seq"] > after_seq]

    def append_audit(self, entry: dict) -> dict:
        """Who did what and why. Every pause, release, police summary, freeze and approval goes here."""
        entry = {"at": _iso(entry.get("at")), **entry}
        doc_id = f"{entry.get('case_id', 'none')}:{entry['at']}:{len(self.store.list('audit', where={'case_id': entry.get('case_id')})):04d}"
        entry["audit_id"] = doc_id
        self.store.set("audit", doc_id, entry)
        return entry

    def list_audit(self, case_id: str | None = None) -> list[dict]:
        return self.store.list("audit", where={"case_id": case_id} if case_id else None, order_by="at")

    def put_freeze_request(self, freeze: dict) -> None:
        self.store.set("freeze_requests", freeze["freeze_id"], freeze)

    def get_freeze_request(self, freeze_id: str) -> dict | None:
        return self.store.get("freeze_requests", freeze_id)

    def list_freeze_requests(self, status: str | None = None) -> list[dict]:
        return self.store.list("freeze_requests", where={"status": status} if status else None, order_by="requested_at")

    def put_proposal(self, proposal: dict) -> None:
        self.store.set("proposals", proposal["proposal_id"], proposal)


class IntelRepo:
    """`intel-db`: playbooks (pending / approved) and question banks. Public, structured data only."""

    def __init__(self, store: DocumentStore) -> None:
        self.store = store

    def put_playbook(self, playbook: dict) -> None:
        self.store.set("playbooks", playbook["id"], playbook)

    def get_playbook(self, playbook_id: str) -> dict | None:
        return self.store.get("playbooks", playbook_id)

    def list_playbooks(self, status: str | None = None) -> list[dict]:
        return self.store.list("playbooks", where={"status": status} if status else None, order_by="id")

    def set_playbook_status(self, playbook_id: str, status: str, approved_by: str | None = None, approved_at: str | None = None) -> dict:
        patch = {"status": status}
        if status == "approved":
            patch |= {"approved_by": approved_by, "approved_at": approved_at}
        return self.store.update("playbooks", playbook_id, patch)

    def put_question_bank(self, bank: dict) -> None:
        self.store.set("question_banks", bank["bank_id"], bank)

    def get_question_bank(self, bank_id: str) -> dict | None:
        return self.store.get("question_banks", bank_id)

    def list_question_banks(self, status: str | None = None) -> list[dict]:
        return self.store.list("question_banks", where={"status": status} if status else None, order_by="bank_id")


class RefRepo:
    """`ref-db`: watchlist snapshots written by the loader, read by Scoring."""

    def __init__(self, store: DocumentStore) -> None:
        self.store = store

    def put_snapshot(self, snapshot: WatchlistSnapshot | dict) -> None:
        doc = snapshot.model_dump(mode="json") if isinstance(snapshot, WatchlistSnapshot) else snapshot
        self.store.set("watchlist_snapshots", doc["snapshot_id"], doc)
        self.store.set("watchlist_latest", "latest", {"snapshot_id": doc["snapshot_id"], "content_hash": doc["content_hash"], "created_at": doc["created_at"]})

    def latest_pointer(self) -> dict | None:
        return self.store.get("watchlist_latest", "latest")

    def get_latest_snapshot(self) -> dict | None:
        pointer = self.latest_pointer()
        return self.store.get("watchlist_snapshots", pointer["snapshot_id"]) if pointer else None


def open_case_repo(settings: Settings | None = None) -> CaseRepo:
    settings = settings or Settings.from_env()
    if settings.service_name in CASE_DB_FORBIDDEN_SERVICES:
        raise PermissionError(f"{settings.service_name} has no case-db access (data boundary, DA 16)")
    return CaseRepo(_open(settings, settings.case_db_id))


def open_intel_repo(settings: Settings | None = None) -> IntelRepo:
    settings = settings or Settings.from_env()
    return IntelRepo(_open(settings, settings.intel_db_id))


def open_ref_repo(settings: Settings | None = None) -> RefRepo:
    settings = settings or Settings.from_env()
    return RefRepo(_open(settings, settings.ref_db_id))
