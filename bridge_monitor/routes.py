from .views import sanity_check


def includeme(config):
    config.add_route("pnl_details", "/pnl/details/")
    config.add_static_view("static", "static", cache_max_age=3600)
    config.add_route("bridge_transfers", "/")
    config.add_route("bidirectional_fastbtc", "/bidirectional-fastbtc/")
    config.add_route("fastbtc_in", "/fastbtc-in/")
    config.add_route("replenisher", "/replenisher/")
    config.add_route("pnl", "/pnl/")
    config.include(sanity_check)
    config.add_route("pnl_details_csv", "/pnl/details.csv")
    config.add_route("balances", "/balances/")
    config.add_route("ledger", "/ledger/")
