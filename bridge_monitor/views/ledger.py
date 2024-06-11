from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from logging import getLogger
from tempfile import NamedTemporaryFile

from pyramid.view import view_config
from pyramid.response import Response
from sqlalchemy.orm import Session
from sqlalchemy.sql import select
from sqlalchemy.sql.expression import func
from sqlalchemy.sql.expression import text
from openpyxl import Workbook

from .pnl import _parse_time_range, ParsedTimeRange
from bridge_monitor.models.ledger_entry import LedgerEntry, LedgerAccount

logger = getLogger(__name__)

@dataclass
class AccountBalance:
    account_id: int
    account_name: str
    balance: Decimal
    credit: Decimal
    debit: Decimal

@dataclass
class EntryDisplay:
    account_name: str
    value: Decimal
    timestamp: datetime
    tx_hash: str

@view_config(
    route_name="ledger",
    renderer="bridge_monitor:templates/ledger.jinja2",
)
def ledger(request):

    def get_account_name(account_id: int, account_list: list[AccountBalance]) -> str:
        for acc in account_list:
            if acc.account_id == abs(account_id):
                return acc.account_name + (" credit" if account_id < 0 else " debit")
        return f"Unknown account {account_id}"

    dbsession: Session = request.dbsession
    chain_env = request.registry.get("chain_env", "mainnet")
    chain = f"rsk_{chain_env}"

    start, end, errors, time_filter = _parse_time_range(request)

    amount_in_page = 100
    first_entry_number = request.params.get("first_entry", 1)
    first_entry_number = max(1, int(first_entry_number))
    last_entry_number = first_entry_number + amount_in_page - 1

    accounts = dbsession.execute(select(LedgerAccount)
                                 .where(LedgerAccount.is_debit==True)
                                 .order_by(LedgerAccount.id)).scalars().all()

    account_balances = []
    ledger_entries = []

    if start and end:
        for account in accounts:

            credit = dbsession.execute(select(func.sum(LedgerEntry.value))
                                        .where(LedgerEntry.account_id == -account.id,
                                               LedgerEntry.timestamp >= start,
                                               LedgerEntry.timestamp <= end)).scalar()
            credit = Decimal(0) if credit is None else credit.normalize()

            debit = dbsession.execute(select(func.sum(LedgerEntry.value))
                                       .where(LedgerEntry.account_id == account.id,
                                              LedgerEntry.timestamp >= start,
                                              LedgerEntry.timestamp <= end)).scalar()
            debit = Decimal(0) if debit is None else debit.normalize()

            balance = debit + credit

            account_balances.append(AccountBalance(account.id, account.name, balance, credit, debit))

        ledger_entries = dbsession.execute(
            select(LedgerEntry)
            .where(LedgerEntry.timestamp >= start,
                   LedgerEntry.timestamp <= end)
            .order_by(LedgerEntry.timestamp, LedgerEntry.id)
        ).scalars().all()

        # if request type is post then download all the data in excel format
        if request.method == "POST":
            wb = Workbook()
            curr_sheet = wb.active
            curr_sheet.title = 'Accounts'
            curr_sheet.append(['Account Name', 'Balance', 'Credit', 'Debit'])
            for account in account_balances:
                curr_sheet.append([account.account_name, account.balance, account.credit, account.debit])
            curr_sheet = wb.create_sheet(title='Ledger Entries')
            curr_sheet.append(['Account Name', 'Value', 'Timestamp', 'Tx Hash'])
            for entry in ledger_entries:
                curr_sheet.append([get_account_name(entry.account_id, account_balances),
                                   entry.value, entry.timestamp.replace(tzinfo=None), entry.tx_hash])
            response = Response(content_type='application/vnd.ms-excel')
            response.content_disposition = 'attachment;filename=ledger.xlsx'
            with NamedTemporaryFile() as tmp:
                wb.save(tmp.name)
                tmp.seek(0)
                response.body = tmp.read()
                return response

        ledger_entries = ledger_entries[first_entry_number - 1:last_entry_number]
        ledger_entries = [EntryDisplay(get_account_name(entry.account_id, account_balances),
                                       entry.value, entry.timestamp, entry.tx_hash) for entry in ledger_entries]

        last_entry_number = len(ledger_entries) + first_entry_number - 1
        if first_entry_number > last_entry_number:
            first_entry_number -= amount_in_page
    return {
        "first_entry": first_entry_number,
        "last_entry": last_entry_number,
        "amount_in_page": amount_in_page,
        "accounts": accounts,
        "account_balances": account_balances,
        "ledger_entries": ledger_entries,
    }