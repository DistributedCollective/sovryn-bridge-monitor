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

Run your project.

    env/bin/pserve development.ini
