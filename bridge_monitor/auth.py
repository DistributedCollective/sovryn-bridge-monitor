import logging
import os
import secrets

from pyramid.authentication import BasicAuthAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPForbidden, HTTPUnauthorized
from pyramid.security import ALL_PERMISSIONS, Allow, Authenticated, forget
from pyramid.view import forbidden_view_config

logger = logging.getLogger(__name__)


def check_credentials(username, password, request):
    reg = request.registry
    if username == reg['auth.username'] and password == reg['auth.password']:
        return []  # logged in


class Root:
    __acl__ = (
        (Allow, Authenticated, ALL_PERMISSIONS),
    )


@forbidden_view_config()
def forbidden_view(request):
    if request.authenticated_userid is None:
        response = HTTPUnauthorized()
        response.headers.update(forget(request))
    # user is logged in but doesn't have permissions, reject wholesale
    else:
        response = HTTPForbidden()
    return response


def includeme(config: Configurator):
    username = config.registry['auth.username'] = os.getenv('AUTH_USERNAME', 'sov' + secrets.token_hex(2))
    password = config.registry['auth.password'] = os.getenv('AUTH_PASSWORD', secrets.token_hex(10))
    logger.info('HTTP Basic auth: %s / %s', username, password)

    # TODO: this is pyramid 1.x legacy stuff and should be replace with 2.0 security policy
    config.set_authentication_policy(BasicAuthAuthenticationPolicy(check_credentials))
    config.set_authorization_policy(ACLAuthorizationPolicy())
    config.set_root_factory(lambda request: Root)
    config.set_default_permission('view')
