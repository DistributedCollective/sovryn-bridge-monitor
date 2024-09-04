drop table if exists ledger_entry;
drop table if exists ledger_entry_queue;
drop table if exists ledger_account;

create unlogged table ledger_account
(
    id       int primary key,
    name     text not null,
    is_debit bool not null,
    unique (name)
);


create unlogged table ledger_entry
(
    id         serial primary key,
    tx_hash    text            not null,
    timestamp  timestamptz     not null,
    account_id int             not null references ledger_account (id),
    value      numeric(40, 18) not null,
    description text
);

create index ledger_entry_tx_hash_idx on ledger_entry (tx_hash);
create index ledger_entry_account_timestamp_idx on ledger_entry (account_id, timestamp);
create index ledger_entry_timestamp_id_idx on ledger_entry (timestamp, id);

drop function if exists get_account_id(text);
drop function if exists get_btc_wallet_id(text);
drop function if exists get_rsk_addr_by_name(text);


create function get_rsk_addr_by_name(addr_name text) returns text as
$$
declare
    addr text;
begin
    select address into addr from rsk_address where name = addr_name;
    if addr is null then
        raise exception 'address not found for name %', addr_name;
    end if;
    return addr;
end;
$$ language plpgsql stable;

create function get_account_id(acc_name text) returns int as
$$
declare
    acc_id int;
begin
    select id into acc_id from ledger_account where name = acc_name;
    if acc_id is null then
        raise exception 'account not found for name %', acc_name;
    end if;
    return acc_id;
end;
$$ language plpgsql stable;

create function get_btc_wallet_id(wallet_name text) returns int as
$$
declare
    wallet_id int;
begin
    select id into wallet_id from btc_wallet where name = wallet_name;
    if wallet_id is null then
        raise exception 'wallet not found for name %', wallet_name;
    end if;
    return wallet_id;
end;
$$ language plpgsql stable;

insert into ledger_account (id, name, is_debit)
values (1910, 'fastbtc in btc wallet', true),
       (1911, 'fastbtc out btc wallet', true),
       (1913, 'fastbtc in rsk wallet', true),
       (1914, 'fastbtc out rsk wallet', true),
       (1915, 'btc backup wallet', true);

insert into ledger_account (id, name, is_debit)
values (-1910, 'fastbtc in btc wallet credit', true),
       (-1911, 'fastbtc out btc wallet credit', true),
       (-1913, 'fastbtc in rsk wallet credit', true),
       (-1914, 'fastbtc out rsk wallet credit', true),
       (-1915, 'btc backup wallet credit', true);

/*changing these numbers might break things*/
insert into ledger_account (id, name, is_debit)
values (10, 'fastbtc in rsk manual withdrawal', false),
       (11, 'fastbtc in rsk manual deposit', false),
       (-11, 'fastbtc in rsk manual deposit credit', false),
       (20, 'fastbtc out rsk manual withdrawal', false),
       (30, 'fastbtc in btc manual withdrawal', false),
       (40, 'fastbtc out btc manual withdrawal', false),
       (41, 'fastbtc out btc manual deposit', false),
       (-41, 'fastbtc out btc manual deposit credit', false),
       (50, 'btc backup manual withdrawal', false),
       (51, 'btc backup manual deposit', false),
       (-51, 'btc backup manual deposit credit', false);


insert into ledger_account (id, name, is_debit)
values (-100, 'fastbtc user prepayments credit', false),
       (100, 'fastbtc user prepayments', false),
       (-110, 'fastbtc btc self prepayments credit', false),
       (110, 'fastbtc btc self prepayments', false),
       (111, 'fastbtc in self deposit', false),
       (-111, 'fastbtc in self deposit credit', false),
       (-120, 'fastbtc user donations credit', false),
       (120, 'fastbtc user donations', false);


insert into ledger_account (id, name, is_debit)
values (-200, 'fastbtc in processed withdrawals credit', false),
       (200, 'fastbtc in processed withdrawals', false);

insert into ledger_account (id, name, is_debit)
values (-210, 'fastbtc in processed deposits credit', false),
       (210, 'fastbtc in processed deposits', false);

insert into ledger_account (id, name, is_debit)
values (-300, 'fastbtc out processed withdrawals credit', false),
       (300, 'fastbtc out processed withdrawals', false);

insert into ledger_account (id, name, is_debit)
values (-310, 'fastbtc out processed deposits credit', false),
       (310, 'fastbtc out processed deposits', false);

insert into ledger_account (id, name, is_debit)
values (402, 'fastbtc out btc fees', false),
       (403, 'fastbtc in btc fees', false),
       (404, 'btc backup wallet fees', false),
       (-402, 'fastbtc out btc fees credit', false),
       (-403, 'fastbtc in btc fees credit', false),
       (-404, 'btc backup wallet fees credit', false);

insert into ledger_account (id, name, is_debit)
values (500, 'fastbtc out refunds', false),
       (-500, 'fastbtc out refunds credit', false);



drop view if exists fastbtc_in_transfer_sane;
create view fastbtc_in_transfer_sane as
select *, to_timestamp(executed_block_timestamp) executed_block_time
from fastbtc_in_transfer;

drop view if exists bidi_fastbtc_transfer_sane;
create view bidi_fastbtc_transfer_sane as
select *, to_timestamp(marked_as_mined_block_timestamp) marked_as_mined_block_time
from bidi_fastbtc_transfer;

drop view if exists btc_wallet_full_transaction;
create view btc_wallet_full_transaction as
select tx_hash,
       max(timestamp)                                             as timestamp,
       wallet_id,
       sum(amount_received) - sum(amount_sent) - max(amount_fees) as net_change,
       sum(amount_received)                                       as amount_received,
       sum(amount_sent)                                           as amount_sent,
       max(amount_fees)                                           as amount_fees
from btc_wallet_transaction
group by tx_hash, wallet_id;

drop view if exists rsk_tx_trace_no_error;
create view rsk_tx_trace_no_error as
select *
from rsk_tx_trace
where error is null;

/*
main
*/
do
$$
    declare
        /*
        minimum allowed transfer over the bridge
        */
        min_transfer_rsk numeric(40, 18) := (select min(total_amount_satoshi::numeric(40, 18) / 1e8)
                                             from bidi_fastbtc_transfer_sane
                                             where status = 'MINED');
        min_transfer_btc numeric(40, 18) := (select min((net_amount_wei + fee_wei)::numeric(40, 18) / 1e18)
                                             from fastbtc_in_transfer_sane
                                             where status = 'EXECUTED');
    begin

        /*
        fastbtcin deposit
        */

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    timestamp,
                    get_account_id('fastbtc in btc wallet'),
                    amount_received,
                    'Fastbtc user bridge deposit'
             from btc_wallet_transaction
             where wallet_id = get_btc_wallet_id('fastbtc-in')
               and amount_received >= min_transfer_btc);

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    timestamp,
                    get_account_id('fastbtc user prepayments credit'),
                    -amount_received,
                    'Fastbtc user bridge deposit'
             from btc_wallet_transaction
             where wallet_id = get_btc_wallet_id('fastbtc-in')
               and amount_received >= min_transfer_btc);

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    timestamp,
                    get_account_id('fastbtc user donations credit'),
                    -amount_received,
                    'User donation'
             from btc_wallet_transaction
             where wallet_id = get_btc_wallet_id('fastbtc-in')
               and amount_received < min_transfer_btc
               and amount_received != 0);

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    timestamp,
                    get_account_id('fastbtc in btc wallet'),
                    amount_received,
                    'User donation'
             from btc_wallet_transaction
             where wallet_id = get_btc_wallet_id('fastbtc-in')
               and amount_received < min_transfer_btc
               and amount_received != 0);


/*
fastbtcin withdrawal
 */

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select executed_transaction_hash,
                    executed_block_time,
                    get_account_id('fastbtc in rsk wallet credit'),
                    -net_amount_wei::numeric(40, 18) / 1e18,
                    'Fastbtc bridge withdrawal'
             from fastbtc_in_transfer_sane
             where status = 'EXECUTED');

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select executed_transaction_hash,
                    executed_block_time,
                    get_account_id('fastbtc in processed withdrawals'),
                    net_amount_wei::numeric(40, 18) / 1e18,
                    'Fastbtc bridge withdrawal'
             from fastbtc_in_transfer_sane
             where status = 'EXECUTED');

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select bwt.tx_hash,
                    fit.executed_block_time,
                    get_account_id('fastbtc user prepayments'),
                    bwt.amount_received,
                    'Fastbtc user bridge deposit'

             from fastbtc_in_transfer_sane fit
                      join btc_wallet_transaction bwt
                           on fit.bitcoin_tx_hash = bwt.tx_hash and fit.bitcoin_tx_vout = bwt.vout
             where fit.status = 'EXECUTED'
               and bwt.wallet_id = get_btc_wallet_id('fastbtc-in')
               and bwt.amount_received > 0);

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select bwt.tx_hash,
                    fit.executed_block_time,
                    get_account_id('fastbtc in processed deposits credit'),
                    -bwt.amount_received,
                    'Fastbtc user bridge deposit'

             from fastbtc_in_transfer_sane fit
                      join btc_wallet_transaction bwt
                           on fit.bitcoin_tx_hash = bwt.tx_hash and fit.bitcoin_tx_vout = bwt.vout
             where fit.status = 'EXECUTED'
               and bwt.wallet_id = get_btc_wallet_id('fastbtc-in')
               and bwt.amount_received > 0);


/*
Fastbtc out deposits
*/

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    block_time,
                    get_account_id('fastbtc out rsk wallet'),
                    value,
                    'Fastbtc user bridge deposit'
             from rsk_tx_trace_no_error
             where to_address = get_rsk_addr_by_name('fastbtc-out')
               and value >= min_transfer_rsk);

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    block_time,
                    get_account_id('fastbtc user prepayments credit'),
                    -value,
                    'Fastbtc user bridge deposit'
             from rsk_tx_trace_no_error
             where to_address = get_rsk_addr_by_name('fastbtc-out')
               and from_address != get_rsk_addr_by_name('fastbtc-in')
               and value >= min_transfer_rsk);

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    block_time,
                    get_account_id('fastbtc user donations credit'),
                    -value,
                    'User donation'
             from rsk_tx_trace_no_error
             where to_address = get_rsk_addr_by_name('fastbtc-out')
               and from_address != get_rsk_addr_by_name('fastbtc-in')
               and value < min_transfer_rsk
               and value != 0);


        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    block_time,
                    get_account_id('fastbtc out rsk wallet'),
                    value,
                    'User donation'
             from rsk_tx_trace_no_error
             where to_address = get_rsk_addr_by_name('fastbtc-out')
               and from_address != get_rsk_addr_by_name('fastbtc-in')
               and value < min_transfer_rsk
               and value != 0);

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select tx_hash,
                    block_time,
                    get_account_id('fastbtc in rsk wallet credit'),
                    -value,
                    'Deposit from fastbtc in to fastbtc out'
             from rsk_tx_trace_no_error
             where to_address = get_rsk_addr_by_name('fastbtc-out')
               and from_address = get_rsk_addr_by_name('fastbtc-in')
               and value > 0);

/*
Fastbtc out withdrawals
 */

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('fastbtc out processed withdrawals'),
               amount_sent,
                'Fastbtc bridge withdrawal'
        from btc_wallet_transaction
        where amount_sent > 0
          and wallet_id = get_btc_wallet_id('fastbtc-out')
          and tx_hash in (select bitcoin_tx_id from bidi_fastbtc_transfer_sane where status = 'MINED')
          and (tx_hash, vout) not in
              (select tx_hash, vout from btc_wallet_transaction where wallet_id = get_btc_wallet_id('fastbtc-in'));


        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('fastbtc out btc wallet credit'),
               -amount_sent,
                'Fastbtc bridge withdrawal'
        from btc_wallet_transaction
        where amount_sent > 0
          and wallet_id = get_btc_wallet_id('fastbtc-out')
          and tx_hash in (select bitcoin_tx_id from bidi_fastbtc_transfer_sane where status = 'MINED')
          and (tx_hash, vout) not in
              (select tx_hash, vout from btc_wallet_transaction where wallet_id = get_btc_wallet_id('fastbtc-in'));


        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    bft.marked_as_mined_block_time,
                    get_account_id('fastbtc user prepayments'),
                    rtt.value,
                    'Fastbtc user bridge deposit'
             from bidi_fastbtc_transfer_sane bft
                      join rsk_tx_trace_no_error rtt on bft.event_transaction_hash = rtt.tx_hash
             where bft.status = 'MINED'
               and rtt.to_address = get_rsk_addr_by_name('fastbtc-out')
               and rtt.value > 0);


        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    bft.marked_as_mined_block_time,
                    get_account_id('fastbtc out processed deposits credit'),
                    -rtt.value,
                    'Fastbtc user bridge deposit'
             from bidi_fastbtc_transfer_sane bft
                      join rsk_tx_trace_no_error rtt on bft.event_transaction_hash = rtt.tx_hash
             where bft.status = 'MINED'
               and rtt.to_address = get_rsk_addr_by_name('fastbtc-out')
               and rtt.value > 0);


        /*
        rsk manual transfers
        */

/*
create a table with the same columns as ledger entry and name it ledger entry queue
*/
        create unlogged table ledger_entry_queue
        (
            id         serial primary key,
            tx_hash    text            not null,
            timestamp  timestamptz     not null,
            account_id int             not null references ledger_account (id),
            value      numeric(40, 18) not null,
            description text
        );

/*
fastbtc in manual in
*/

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc in rsk wallet'),
                    rtt.value,
                    'Rsk fastbtc in manual transfer'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.to_address = get_rsk_addr_by_name('fastbtc-in')
               and le.tx_hash is null
               and rtt.to_address = get_rsk_addr_by_name('fastbtc-in')
               and rtt.from_address != get_rsk_addr_by_name('fastbtc-out')
               and rtt.value > 0
             order by timestamp, rtt.tx_hash, rtt.trace_index);

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc in rsk manual deposit credit'),
                    -rtt.value,
                    'Rsk fastbtc in manual transfer'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.to_address = get_rsk_addr_by_name('fastbtc-in')
               and le.tx_hash is null
               and rtt.to_address = get_rsk_addr_by_name('fastbtc-in')
               and rtt.from_address != get_rsk_addr_by_name('fastbtc-out')
               and rtt.value > 0
             order by timestamp, rtt.tx_hash, rtt.trace_index);

/*
fastbtc in manual out
*/

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc in rsk wallet credit'),
                    -rtt.value,
                    'Rsk fastbtc in manual transfer'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.from_address = get_rsk_addr_by_name('fastbtc-in')
               and le.tx_hash is null
               and rtt.to_address != get_rsk_addr_by_name('fastbtc-out')
               and rtt.value > 0);

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc in rsk manual withdrawal'),
                    rtt.value,
                    'Rsk fastbtc in manual transfer'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.from_address = get_rsk_addr_by_name('fastbtc-in')
               and le.tx_hash is null
               and rtt.to_address != get_rsk_addr_by_name('fastbtc-out')
               and rtt.value > 0);

/*
rsk replenishments
*/
        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc in rsk wallet'),
                    rtt.value,
                    'Rsk replenishment'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.from_address = get_rsk_addr_by_name('fastbtc-out')
               and le.tx_hash is null
               and rtt.to_address = get_rsk_addr_by_name('fastbtc-in')
               and rtt.value > 0);

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc out rsk wallet credit'),
                    -rtt.value,
                    'Rsk replenishment'

             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.from_address = get_rsk_addr_by_name('fastbtc-out')
               and le.tx_hash is null
               and rtt.to_address = get_rsk_addr_by_name('fastbtc-in')
               and rtt.value > 0);

/*
fastbtc out manual out
*/

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc out rsk wallet credit'),
                    -rtt.value,
                    'Rsk fastbtc out manual transfer'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.from_address = get_rsk_addr_by_name('fastbtc-out')
               and le.tx_hash is null
               and rtt.to_address != get_rsk_addr_by_name('fastbtc-in')
               and rtt.value > 0);

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc out rsk manual withdrawal'),
                    rtt.value,
                    'Rsk fastbtc out manual transfer'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.from_address = get_rsk_addr_by_name('fastbtc-out')
               and le.tx_hash is null
               and rtt.to_address != get_rsk_addr_by_name('fastbtc-in')
               and rtt.value > 0
               and rtt.tx_hash not in
                   (select refunded_or_reclaimed_transaction_hash
                    from bidi_fastbtc_transfer_sane
                    where status != 'MINED'));

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select rtt.tx_hash,
                    rtt.block_time,
                    get_account_id('fastbtc out refunds'),
                    rtt.value,
                    'Rsk refund'
             from rsk_tx_trace_no_error rtt
                      left join ledger_entry le on rtt.tx_hash = le.tx_hash
             where rtt.from_address = get_rsk_addr_by_name('fastbtc-out')
               and le.tx_hash is null
               and rtt.to_address != get_rsk_addr_by_name('fastbtc-in')
               and rtt.value > 0
               and rtt.tx_hash in
                   (select refunded_or_reclaimed_transaction_hash
                    from bidi_fastbtc_transfer_sane
                    where status != 'MINED'));

        update ledger_entry_queue set description = 'rsk refund' where account_id = get_account_id('fastbtc out rsk wallet credit')
        and tx_hash in (select tx_hash from ledger_entry_queue where account_id = get_account_id('fastbtc out refunds'));

        /*
        btc manual transfers
        */

/*
 fastbtc out manual in
 */
        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select l.tx_hash,
                    l.timestamp,
                    get_account_id('fastbtc out btc wallet'),
                    l.amount_received,
                    'Btc fastbtc out manual transfer'
             from (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-out')) l
                      left join
                  (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-in')) r
                  on l.tx_hash = r.tx_hash
             where r.tx_hash is null
               and l.amount_received > 0
               and l.amount_sent = 0);

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select l.tx_hash,
                    l.timestamp,
                    get_account_id('fastbtc out btc manual deposit credit'),
                    -l.amount_received,
                    'Btc fastbtc out manual transfer'

             from (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-out')) l
                      left join
                  (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-in')) r
                  on l.tx_hash = r.tx_hash
             where r.tx_hash is null
               and l.amount_received > 0
               and l.amount_sent = 0);

/*
 fastbtc in manual out
 */
        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select l.tx_hash,
                    l.timestamp,
                    get_account_id('fastbtc in btc wallet credit'),
                    -l.amount_sent,
                    'Btc fastbtc in manual transfer'
             from (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-in')) l
                      left join
                  (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-out')) r
                  on l.tx_hash = r.tx_hash
             where r.tx_hash is null
               and l.amount_sent > 0);

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
            (select l.tx_hash,
                    l.timestamp,
                    get_account_id('fastbtc in btc manual withdrawal'),
                    l.amount_sent,
                    'Btc fastbtc in manual transfer'
             from (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-in')) l
                      left join
                  (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-out')) r
                  on l.tx_hash = r.tx_hash
             where r.tx_hash is null
               and l.amount_sent > 0);

/*
 fastbtc out manual out
 */
        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select wallet_tx.tx_hash,
               wallet_tx.timestamp,
               get_account_id('fastbtc out btc wallet credit'),
               -wallet_tx.amount_sent,
                'Btc fastbtc out manual transfer'
        from (select l.tx_hash, l.net_change, l.timestamp, l.amount_sent
              from ((select *
                     from btc_wallet_full_transaction
                     where wallet_id = get_btc_wallet_id('fastbtc-out')) l left join
                  (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-in')) r
                    on l.tx_hash = r.tx_hash)
              where r.tx_hash is null
                and l.amount_sent > 0) wallet_tx
                 left join bidi_fastbtc_transfer_sane bft on wallet_tx.tx_hash = bft.bitcoin_tx_id
        where bft.bitcoin_tx_id is null
          and wallet_tx.amount_sent > 0;

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select wallet_tx.tx_hash,
               wallet_tx.timestamp,
               get_account_id('fastbtc out btc manual withdrawal'),
               wallet_tx.amount_sent,
                'Btc fastbtc out manual transfer'
        from (select l.tx_hash, l.net_change, l.timestamp, l.amount_sent
              from ((select *
                     from btc_wallet_full_transaction
                     where wallet_id = get_btc_wallet_id('fastbtc-out')) l left join
                  (select * from btc_wallet_full_transaction where wallet_id = get_btc_wallet_id('fastbtc-in')) r
                    on l.tx_hash = r.tx_hash)
              where r.tx_hash is null
                and l.amount_sent > 0) wallet_tx
                 left join bidi_fastbtc_transfer_sane bft on wallet_tx.tx_hash = bft.bitcoin_tx_id
        where bft.bitcoin_tx_id is null
          and wallet_tx.amount_sent > 0;

/*
btc replenishments fastbtc in -> fastbtc out
*/

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select l.tx_hash,
               l.timestamp,
               get_account_id('fastbtc out btc wallet'),
               r.amount_received,
                'Btc replenishment'
        from btc_wallet_full_transaction l
                 join
             btc_wallet_full_transaction r
             on l.tx_hash = r.tx_hash and
                l.wallet_id = get_btc_wallet_id('fastbtc-in') and
                r.wallet_id = get_btc_wallet_id('fastbtc-out')
        where l.amount_sent > 0
          and r.amount_received > 0;

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select l.tx_hash,
               l.timestamp,
               get_account_id('fastbtc in btc wallet credit'),
               -l.amount_sent,
                'Btc replenishment'
        from btc_wallet_full_transaction l
                 join
             btc_wallet_full_transaction r
             on l.tx_hash = r.tx_hash and
                l.wallet_id = get_btc_wallet_id('fastbtc-in') and
                r.wallet_id = get_btc_wallet_id('fastbtc-out')
        where l.amount_sent > 0
          and r.amount_received > 0;

/*
Fastbtc out -> in deposit
*/

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select l.tx_hash,
               l.timestamp,
               get_account_id('fastbtc in btc wallet'),
               r.amount_received,
                'Fastbtc out to in deposit'
        from btc_wallet_transaction l
                 join
             btc_wallet_transaction r
             on l.tx_hash = r.tx_hash and l.vout = r.vout and
                l.wallet_id = get_btc_wallet_id('fastbtc-out') and
                r.wallet_id = get_btc_wallet_id('fastbtc-in')
        where l.amount_sent > 0
          and r.amount_received > 0;


        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select l.tx_hash,
               l.timestamp,
               get_account_id('fastbtc out btc wallet credit'),
               -l.amount_sent,
                'Fastbtc out to in deposit'
        from btc_wallet_transaction l
                 join
             btc_wallet_transaction r
             on l.tx_hash = r.tx_hash and l.vout = r.vout and
                l.wallet_id = get_btc_wallet_id('fastbtc-out') and
                r.wallet_id = get_btc_wallet_id('fastbtc-in')
        where l.amount_sent > 0
          and r.amount_received > 0;

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select l.tx_hash,
               l.timestamp,
               get_account_id('fastbtc btc self prepayments credit'),
               -l.amount_sent,
                'Fastbtc out to in deposit'
        from btc_wallet_transaction l
                 join
             btc_wallet_transaction r
             on l.tx_hash = r.tx_hash and l.vout = r.vout and
                l.wallet_id = get_btc_wallet_id('fastbtc-out') and
                r.wallet_id = get_btc_wallet_id('fastbtc-in')
        where l.amount_sent > 0
          and r.amount_received > 0
          and l.tx_hash in (select bitcoin_tx_hash from fastbtc_in_transfer_sane);

        insert into ledger_entry_queue(tx_hash, timestamp, account_id, value, description)
        select l.tx_hash,
               l.timestamp,
               get_account_id('fastbtc in self deposit'),
               l.amount_sent,
                'Fastbtc out to in deposit'
        from btc_wallet_transaction l
                 join
             btc_wallet_transaction r
             on l.tx_hash = r.tx_hash and l.vout = r.vout and
                l.wallet_id = get_btc_wallet_id('fastbtc-out') and
                r.wallet_id = get_btc_wallet_id('fastbtc-in')
        where l.amount_sent > 0
          and r.amount_received > 0
          and l.tx_hash in (select bitcoin_tx_hash from fastbtc_in_transfer_sane);


        delete
        from ledger_entry
        where (abs(account_id) = get_account_id('fastbtc in btc wallet') or
               account_id = get_account_id('fastbtc user prepayments credit') or
               account_id = get_account_id('fastbtc user donations credit'))
          and tx_hash in (select l.tx_hash
                          from btc_wallet_full_transaction l
                                   join
                               btc_wallet_full_transaction r
                               on l.tx_hash = r.tx_hash and
                                  l.wallet_id = get_btc_wallet_id('fastbtc-out') and
                                  r.wallet_id = get_btc_wallet_id('fastbtc-in')
                          where l.amount_sent > 0
                            and r.amount_received > 0);

        update ledger_entry
        set account_id = get_account_id('fastbtc btc self prepayments'), description = 'Fastbtc out to in deposit'
        where account_id = get_account_id('fastbtc user prepayments')
          and tx_hash in
              (select tx_hash
               from ledger_entry_queue
               where account_id = get_account_id('fastbtc btc self prepayments credit'));

        update ledger_entry
        set description = 'Fastbtc out to in deposit'
        where tx_hash in
              (select tx_hash
               from ledger_entry_queue
               where account_id = get_account_id('fastbtc btc self prepayments credit'));


/*
re-insert queue
*/
        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash, timestamp, account_id, value, description
        from ledger_entry_queue;


/*
btc backup wallet
*/

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('btc backup wallet'),
               amount_received,
               'Btc backup wallet manual transfer'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('btc-backup')
          and amount_received > 0;

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('btc backup manual deposit credit'),
               -amount_received,
                'Btc backup wallet manual transfer'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('btc-backup')
          and amount_received > 0;

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('btc backup wallet credit'),
               -amount_sent,
               'Btc backup wallet manual transfer'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('btc-backup')
          and amount_sent > 0;

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('btc backup manual withdrawal'),
               amount_sent,
                'Btc backup wallet manual transfer'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('btc-backup')
          and amount_sent > 0;

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('btc backup wallet fees'),
               amount_fees,
               'Fees'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('btc-backup')
          and amount_sent > 0;

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('btc backup wallet credit'),
               -amount_fees,
               'Fees'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('btc-backup')
          and amount_sent > 0;


/*fastbtc out fees*/

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('fastbtc out btc fees'),
               amount_fees,
                'Fees'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('fastbtc-out')
          and amount_fees > 0;

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('fastbtc out btc wallet credit'),
               -amount_fees,
                'Fees'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('fastbtc-out')
          and amount_fees > 0;
/*
fastbtc in fees
*/

        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('fastbtc in btc fees'),
               amount_fees,
                'Fees'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('fastbtc-in')
          and amount_fees > 0;
        insert into ledger_entry(tx_hash, timestamp, account_id, value, description)
        select tx_hash,
               timestamp,
               get_account_id('fastbtc in btc wallet credit'),
               -amount_fees,
                'Fees'
        from btc_wallet_full_transaction
        where wallet_id = get_btc_wallet_id('fastbtc-in')
          and amount_fees > 0;

/*
descriptions
*/
        update btc_wallet_transaction set notes = 'Fastbtc manual transfer' where tx_hash in
            (select tx_hash from ledger_entry where abs(account_id) >= get_account_id('fastbtc in btc manual withdrawal') and
             abs(account_id) <= get_account_id('btc backup manual deposit'));

        update rsk_tx_trace set notes = 'Fastbtc manual transfer' where tx_hash in
            (select tx_hash from ledger_entry where abs(account_id) >= get_account_id('fastbtc in rsk manual withdrawal') and
             abs(account_id) <= get_account_id('fastbtc out rsk manual withdrawal'));


        update btc_wallet_transaction set notes = 'Fastbtc user bridge deposit' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc user prepayments credit'));

        update rsk_tx_trace set notes = 'Fastbtc user bridge deposit' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc user prepayments credit'));


        update btc_wallet_transaction set notes = 'User donation' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc user donations credit'));

        update rsk_tx_trace set notes = 'User donation' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc user donations credit'));


        update btc_wallet_transaction set notes = 'Fastbtc bridge withdrawal' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc out processed withdrawals'));

        update rsk_tx_trace set notes = 'Fastbtc bridge withdrawal' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc in processed withdrawals'));


        update rsk_tx_trace set notes = 'Replenishment' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc out rsk wallet credit')) and
            tx_hash in (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc in rsk wallet'));

        update rsk_tx_trace set notes = 'Refunded' where  tx_hash in
            (select tx_hash from ledger_entry where abs(account_id) = get_account_id('fastbtc out refunds'));

        update btc_wallet_transaction set notes = 'Replenishment' where tx_hash in
            (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc in btc wallet credit')) and
            tx_hash in (select tx_hash from ledger_entry where account_id = get_account_id('fastbtc out btc wallet'));

        update btc_wallet_transaction set notes = 'Deposit from fastbtc out to fastbtc in' where tx_hash in
            (select tx_hash from ledger_entry where abs(account_id ) = get_account_id('fastbtc in self deposit'));


        /*
        override descriptions for ledger_entry table using content of ledger_description_override table
        */
        update ledger_entry set description = ldo.description_override
                            from ledger_description_override ldo where ldo.tx_hash = ledger_entry.tx_hash;

        update rsk_tx_trace set notes = ldo.description_override
                            from ledger_description_override ldo where ldo.tx_hash = rsk_tx_trace.tx_hash;

        update btc_wallet_transaction set notes = ldo.description_override
                            from ledger_description_override ldo where ldo.tx_hash = btc_wallet_transaction.tx_hash;


    end

$$;
/*
check valid output
*/

do
$$
    declare
        total int;
    begin
        select count(*)
        into total
        from ledger_entry
        where account_id > 0
          and value < 0;
        if total != 0 then
            raise exception 'ledger_entry has negative debit entries: %', total;
        end if;
    end
$$;

do
$$
    declare
        total int;
    begin
        select count(*)
        into total
        from ledger_entry
        where account_id < 0
          and value > 0;
        if total != 0 then
            raise exception 'ledger_entry has positive credit entries: %', total;
        end if;
    end
$$;

do
$$
    declare
        total numeric(40, 18);
    begin
        select sum(value) into total from ledger_entry;
        if total != 0 then
            raise exception 'ledger_entry total is not zero: %', total;
        end if;
    end
$$;
