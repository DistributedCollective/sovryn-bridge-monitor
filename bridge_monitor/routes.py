def includeme(config):
    config.add_static_view('static', 'static', cache_max_age=3600)
    config.add_route('bridge_transfers', '/')
    config.add_route('bidirectional_fastbtc', '/bidirectional-fastbtc/')
    config.add_route('fastbtc_in', '/fastbtc-in/')
    config.add_route('replenisher', '/replenisher/')
    config.add_route('pnl', '/pnl/')
    config.add_route('sanity_check', '/sanity-check/')
    config.add_route('pnl_details_csv', '/pnl/details.csv')
