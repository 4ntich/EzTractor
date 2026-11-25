import math

from sqlalchemy.orm import Session

from .models import CreditLedger


class InsufficientCredits(Exception):
    def __init__(self, needed: int, balance: int):
        super().__init__(f"Créditos insuficientes: precisa de {needed}, saldo {balance}")
        self.needed = needed
        self.balance = balance


def cost_for_duration(duration_s: float) -> int:
    """1 crédito por minuto de vídeo, mínimo 1."""
    return max(1, math.ceil(duration_s / 60))


def grant(db: Session, user_id: str, amount: int, reason: str, ref_id: str | None = None) -> None:
    db.add(CreditLedger(user_id=user_id, delta=amount, reason=reason, ref_id=ref_id))


def charge(db: Session, user_id: str, amount: int, ref_id: str) -> None:
    balance = CreditLedger.balance(db, user_id)
    if balance < amount:
        raise InsufficientCredits(amount, balance)
    db.add(CreditLedger(user_id=user_id, delta=-amount, reason="processing", ref_id=ref_id))
