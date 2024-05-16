import logging
import argparse
import sys
from datetime import datetime, timezone
from tempfile import TemporaryFile
import json
import configparser
from typing import List

from pyramid.paster import setup_logging
import zstandard as zstd
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
import pandas as pd


from bridge_monitor.models.chain_info import BlockInfo, BlockChain

logger = logging.getLogger(__name__)


def parse_args(argv: List[str]):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config_uri",
        help="Configuration file, e.g., development.ini",
    )
    parser.add_argument(
        "-file",
        help="file to import, can be zstd compressed",
        required=False,
    )
    parser.add_argument("--empty", action="store_true", help="Initialize empty")

    return parser.parse_args(argv[1:])


def get_blockchain_meta(dbsession: Session, name, expected_safe_limit=12):
    block_chain_meta = (
        dbsession.query(BlockChain).filter(BlockChain.name == name).scalar()
    )
    if block_chain_meta is None:
        logger.info("Creating new blockchain meta for %s", name)
        dbsession.add(BlockChain(name=name, safe_limit=expected_safe_limit))
        block_chain_meta = (
            dbsession.query(BlockChain).filter(BlockChain.name == name).one()
        )
    return block_chain_meta


def write_from_file_to_db(
    dbsession: Session, file
):  # file must be formatted as: [123123, 545343]\n[123124, 545344]\n...
    block_chain_meta = get_blockchain_meta(dbsession, "rsk")
    dbsession.query(BlockInfo).filter(
        BlockInfo.block_chain_id == block_chain_meta.id
    ).delete()

    for count, line in enumerate(file):
        try:
            block_n, ts = json.loads(line.decode("utf-8"))
        except (
            ValueError
        ):  # in a properly formatted file an empty last line would trigger this
            break
        dbsession.add(
            BlockInfo(
                block_chain_id=block_chain_meta.id,
                block_number=block_n,
                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
            )
        )
        if count % 1000 == 0:
            dbsession.flush()


def write_from_parquet_to_db(dbsession: Session, path: str):
    block_chain_meta = get_blockchain_meta(dbsession, "rsk")
    dbsession.query(BlockInfo).filter(
        BlockInfo.block_chain_id == block_chain_meta.id
    ).delete()

    df = pd.read_parquet(path)
    df.drop_duplicates(subset=["block_number"], inplace=True)
    df.insert(0, "block_chain_id", block_chain_meta.id, allow_duplicates=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, unit="s")
    df.to_sql("block_info", dbsession.bind, if_exists="append", index=False)
    del df  # df will likely be large, so del it just to be sure it's gone


def main(argv=None):
    if argv is None:
        argv = sys.argv
    args = parse_args(argv)
    if not args.empty and not args.file:
        logger.error("Either --empty or a file must be provided")
        return
    setup_logging(args.config_uri)

    config = configparser.ConfigParser()
    config.read(args.config_uri)
    db_url = config["app:main"]["sqlalchemy.url"]
    engine = create_engine(db_url)
    dbsession = Session(engine)

    chain_env = "rsk_mainnet"  # hardcoded for now

    logger.info("chain_env: %s", chain_env)

    if args.empty:
        with dbsession.begin():
            get_blockchain_meta(dbsession, "rsk")
        return
    if args.file.endswith(".parquet"):
        logger.info("Writing from parquet file %s to db", args.file)
        with dbsession.begin():
            write_from_parquet_to_db(dbsession, args.file)
        logger.info("Done writing from parquet file %s to db", args.file)
        return
    with open(args.file, "rb") as source_file:
        if args.file.endswith(".zst"):
            logger.info("Decompressing zstd compressed file")
            with TemporaryFile() as temp_file:
                decomp = zstd.ZstdDecompressor()
                decomp.copy_stream(source_file, temp_file)
                with dbsession.begin():
                    temp_file.seek(0)
                    write_from_file_to_db(dbsession, temp_file)
        else:
            with dbsession.begin():
                write_from_file_to_db(dbsession, source_file)
    logger.info("Done writing from file %s to db", args.file)


if __name__ == "__main__":
    main()
