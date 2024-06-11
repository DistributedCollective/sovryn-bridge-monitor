import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "README.md")) as f:
    README = f.read()
with open(os.path.join(here, "CHANGES.txt")) as f:
    CHANGES = f.read()

requires = [
    "plaster_pastedeploy",
    "pyramid>=1.10,<2.0",  # TODO: fix, should port to 2.0
    "pyramid_jinja2",
    "pyramid_debugtoolbar",
    "waitress",
    "alembic",
    "pyramid_retry",
    "pyramid_tm",
    "psycopg2",
    "SQLAlchemy",
    "transaction",
    "zope.sqlalchemy",
    "eth-utils",
    "web3",
    "requests",
    "python-dateutil",
    "pandas",
    "pyarrow",
    "openpyxl",
    "zstandard",
    "dotenv",
]

tests_require = [
    "WebTest",
    "pytest",
    "pytest-cov",
]

setup(
    name="bridge_monitor",
    version="0.0",
    description="bridge_monitor",
    long_description=README + "\n\n" + CHANGES,
    classifiers=[
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
    ],
    author="",
    author_email="",
    url="",
    keywords="web pyramid pylons",
    packages=find_packages(exclude=["tests"]),
    include_package_data=True,
    zip_safe=False,
    extras_require={
        "testing": tests_require,
    },
    install_requires=requires,
    entry_points={
        "paste.app_factory": [
            "main = bridge_monitor:main",
        ],
        "console_scripts": [
            "monitor_bridge=bridge_monitor.scripts.monitor_bridge:main",
            "import_block_meta_rsk=bridge_monitor.scripts.import_block_meta_rsk:main",
            "initialize_btc_wallet_txs=bridge_monitor.scripts.initialize_btc_wallet_txs:main",
            "trace_block=bridge_monitor.scripts.trace_block:main",
        ],
    },
)
