"""A refund a person declined ends in its own state, including cases declined before that state existed."""

from __future__ import annotations

from types import SimpleNamespace

from versoml.zone_client.service import ClientService


class _Cases:
    def __init__(self, docs: list[dict]):
        self.docs = {d["case_id"]: d for d in docs}

    def all(self) -> list[dict]:
        return list(self.docs.values())

    def update(self, case_id: str, patch: dict) -> None:
        self.docs[case_id].update(patch)


def _doc(case_id: str, **kw) -> dict:
    return {"case_id": case_id, "status": "IN_ANALIZA", "verdict": "RAMBURSEAZA_CU_APROBARE",
            "finished_at": "2026-10-29T02:30:00+00:00",
            "interrupt": {"pending": False, "answer": {"action": "reject", "approver": "OPERATOR-01"}}, **kw}


def test_old_declined_cases_are_repaired_and_others_left_alone():
    cases = _Cases([
        _doc("CT-DECLINED"),
        _doc("CT-RUNNING", finished_at=None),  # still running: not ours to touch
        _doc("CT-APPROVED", interrupt={"pending": False, "answer": {"action": "approve"}}),
        _doc("CT-MISSING", verdict="INFORMATII_SUPLIMENTARE", interrupt={}),
    ])
    ClientService(SimpleNamespace(cases=cases))
    assert cases.docs["CT-DECLINED"]["status"] == "REFUZAT"
    assert cases.docs["CT-DECLINED"]["rejected_by"] == "OPERATOR-01"
    assert [cases.docs[i]["status"] for i in ("CT-RUNNING", "CT-APPROVED", "CT-MISSING")] == ["IN_ANALIZA"] * 3
