"""One run of the intelligence job: fetch -> extract -> validate -> de-duplicate -> write `pending`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from mimamori_common.config import Settings
from mimamori_common.llm import ModelClient
from mimamori_common.store import IntelRepo

from .dedupe import duplicate_reason
from .extract import extract_playbook
from .fetcher import Alert, AlertFetcher, FetchError
from .validate import validate_playbook

log = logging.getLogger("intel_job")


class PendingWriter:
    """The job's only door to intel-db. It exposes no way to approve, reject or retire: it can read
    playbooks and add a new `pending` one, and refuses to overwrite an existing id."""

    def __init__(self, repo: IntelRepo) -> None:
        self._repo = repo

    def playbooks(self) -> list[dict]:
        return self._repo.list_playbooks()

    def wording_ids(self) -> set[str]:
        ids: set[str] = set()
        for pb in self._repo.list_playbooks():
            bank = pb["question_bank"]
            ids |= {i["id"] for i in bank["questions"] + bank["hold_lines"]}
        for bank in self._repo.list_question_banks():
            ids |= {i["id"] for i in bank["questions"] + bank["hold_lines"]}
        return ids

    def put_pending(self, playbook: dict) -> None:
        if playbook.get("status") != "pending" or playbook.get("approved_by") or playbook.get("approved_at"):
            raise PermissionError("intel-job may only write pending playbooks")
        if self._repo.get_playbook(playbook["id"]) is not None:
            raise FileExistsError(f"playbook {playbook['id']} already exists; the job never overwrites")
        self._repo.put_playbook(playbook)


@dataclass
class RunReport:
    written: list[str] = field(default_factory=list)
    duplicates: list[tuple[str, str]] = field(default_factory=list)  # (alert url, reason)
    rejected: list[tuple[str, list[str]]] = field(default_factory=list)  # (alert url, problems)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (alert url, error)

    @property
    def ok(self) -> bool:
        """Rejected model output is a normal outcome (logged, not stored); errors are not."""
        return not self.errors


async def run(fetcher: AlertFetcher, client: ModelClient, repo: IntelRepo, settings: Settings | None = None) -> RunReport:
    settings = settings or Settings.from_env()
    today = settings.now().date()
    writer = PendingWriter(repo)
    report = RunReport()
    alerts: list[Alert] = fetcher.fetch()  # FetchError fails the whole run
    log.info("fetched %d alerts", len(alerts))
    existing = writer.playbooks()
    taken = writer.wording_ids()

    for alert in alerts:
        try:
            candidate = await extract_playbook(client, alert)
        except Exception as err:  # model unreachable or unparseable: this alert is not stored
            log.error("extraction failed for %s: %s", alert.url, err)
            report.errors.append((alert.url, f"{type(err).__name__}: {err}"))
            continue
        problems = validate_playbook(candidate, today=today)
        if problems:
            log.warning("rejected model output for %s: %s", alert.url, "; ".join(problems))
            report.rejected.append((alert.url, problems))
            continue
        reason = duplicate_reason(candidate, existing)
        if reason:
            log.info("duplicate %s: %s", alert.url, reason)
            report.duplicates.append((alert.url, reason))
            continue
        problems = validate_playbook(candidate, taken_wording_ids=taken, today=today)  # ids used by other playbooks
        if problems:
            log.warning("rejected model output for %s: %s", alert.url, "; ".join(problems))
            report.rejected.append((alert.url, problems))
            continue
        try:
            writer.put_pending(candidate)
        except Exception as err:
            log.error("write failed for %s: %s", alert.url, err)
            report.errors.append((alert.url, f"{type(err).__name__}: {err}"))
            continue
        existing.append(candidate)
        taken |= {i["id"] for i in candidate["question_bank"]["questions"] + candidate["question_bank"]["hold_lines"]}
        report.written.append(candidate["id"])
        log.info("wrote pending playbook %s (published %s)", candidate["id"], alert.published_at)
    log.info("done: %d written, %d duplicate, %d rejected, %d errors",
             len(report.written), len(report.duplicates), len(report.rejected), len(report.errors))
    return report


__all__ = ["PendingWriter", "RunReport", "run", "FetchError"]
