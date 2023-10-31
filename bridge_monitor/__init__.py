from pyramid.config import Configurator
import logging


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    with Configurator(settings=settings) as config:
        config.include('pyramid_jinja2')
        config.include('.routes')
        config.include('.models')
        config.include('.auth')
        config.include('.jinja2_filters')

        config.registry['chain_env'] = settings.get('monitor.chain_env', 'mainnet')
        logging.info("Chain env: %s", config.registry['chain_env'])

        config.scan()

    return config.make_wsgi_app()
