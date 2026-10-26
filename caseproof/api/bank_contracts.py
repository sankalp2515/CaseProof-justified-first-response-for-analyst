"""Bounded, explicitly synthetic bank-side data; never a customer-upload contract."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from caseproof.graph.contracts import Account


def aware(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("bank timestamps require an offset")
    return parsed.isoformat()


class BankRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Customer(BankRecord):
    account: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=120)


class Transaction(BankRecord):
    txn_id: str = Field(min_length=1, max_length=120)
    account: str = Field(min_length=1, max_length=100)
    counterparty_account: str = Field(min_length=1, max_length=100)
    amount_minor: StrictInt = Field(gt=0)
    payee: str = Field(min_length=1, max_length=160)
    ts: str
    reference: str = Field(min_length=1, max_length=120)
    direction: Literal["debit"] = "debit"
    channel: Literal["UPI", "IMPS", "NEFT", "CARD"] = "UPI"
    _time = field_validator("ts")(aware)


class Coverage(BankRecord):
    account: str
    start: str
    end: str
    as_of: str
    _time = field_validator("start", "end", "as_of")(aware)

    @model_validator(mode="after")
    def interval(self):
        if (
            not datetime.fromisoformat(self.start)
            <= datetime.fromisoformat(self.end)
            <= datetime.fromisoformat(self.as_of)
        ):
            raise ValueError("invalid debit coverage interval")
        return self


class BankBatch(BankRecord):
    batch_id: str = Field(min_length=1, max_length=120)
    synthetic: Literal[True]
    bank: str = Field(min_length=1, max_length=120)
    customers: list[Customer] = Field(default_factory=list, max_length=100)
    accounts: list[Account] = Field(min_length=1, max_length=300)
    transactions: list[Transaction] = Field(default_factory=list, max_length=500)
    coverage: list[Coverage] = Field(default_factory=list, max_length=100)

    @field_validator("accounts", mode="before")
    @classmethod
    def strict_accounts(cls, values):
        return [Account.model_validate(v, strict=True) for v in values]

    @model_validator(mode="after")
    def references(self):
        accounts = {a.id: a for a in self.accounts}
        if len(accounts) != len(self.accounts) or len({t.txn_id for t in self.transactions}) != len(
            self.transactions
        ):
            raise ValueError("duplicate bank record identity")
        if len({c.account for c in self.customers}) != len(self.customers):
            raise ValueError("duplicate customer")
        for row in [*self.customers, *self.coverage, *self.transactions]:
            if (
                row.account not in accounts
                or accounts[row.account].bank != self.bank
                or accounts[row.account].kind != "customer"
            ):
                raise ValueError("bank does not own customer account")
        for tx in self.transactions:
            if tx.counterparty_account not in accounts:
                raise ValueError("unknown receiver")
            if not any(
                c.account == tx.account
                and datetime.fromisoformat(c.start)
                <= datetime.fromisoformat(tx.ts)
                <= datetime.fromisoformat(c.end)
                for c in self.coverage
            ):
                raise ValueError("transaction outside asserted debit coverage")
        return self
