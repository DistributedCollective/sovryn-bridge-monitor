bridge_monitor
==============

Getting Started
---------------

Create a Python virtual environment, if not already created.

    python3 -m venv env

Upgrade packaging tools, if necessary.

    env/bin/pip install --upgrade pip setuptools

Install the project in editable mode with its testing requirements.

    env/bin/pip install -e ".[testing]"

Initialize DB and run migrations using Alembic.

    createdb bridge_monitor_dev
    env/bin/alembic -c development.ini upgrade head

Run your project's tests.

    env/bin/pytest

Monitor bridge transfers

    INFURA_API_KEY=KEYGOESHERE env/bin/monitor_bridge development.ini

Fetch block times and rsk transfers

    trace_block development.ini -chain_env rsk_mainnet

If block chain meta is missing run

    import_block_meta development.ini --empty

To add wallets for btc fetching

    initialize_btc_wallet development.ini -wallet WALLET_1 WALLET_2

Run your project.

    env/bin/pserve development.ini
