"""Proposal persistence."""

from __future__ import annotations

from app.db.database import Database
from app.repositories.base import dumps, iso, loads, parse_iso
from app.schemas.actions import ActionProposal


class ProposalRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, proposal: ActionProposal, simulated: bool = False) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO proposals
                (proposal_id, source, action, parameters, reason, context_ref,
                 simulated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.proposal_id,
                proposal.source,
                proposal.action.value,
                dumps(proposal.parameters),
                proposal.reason,
                None,
                1 if simulated else 0,
                iso(proposal.created_at),
            ),
        )

    def get(self, proposal_id: str) -> ActionProposal | None:
        row = self.db.query_one(
            "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
        )
        return self._row_to_model(row) if row else None

    def list(self, limit: int = 50) -> list[ActionProposal]:
        rows = self.db.query(
            "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row) -> ActionProposal:
        return ActionProposal(
            proposal_id=row["proposal_id"],
            action=row["action"],
            parameters=loads(row["parameters"], {}) or {},
            reason=row["reason"] or "",
            source=row["source"],
            created_at=parse_iso(row["created_at"]),
        )
