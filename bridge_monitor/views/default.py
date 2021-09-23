from types import SimpleNamespace

from pyramid.view import view_config
from pyramid.response import Response
from sqlalchemy.exc import SQLAlchemyError

from .. import models


@view_config(route_name='home', renderer='bridge_monitor:templates/mytemplate.jinja2')
def my_view(request):
    try:
        query = request.dbsession.query(models.KeyValuePair)
        query.filter(models.KeyValuePair.key == 'test').one()
    except SQLAlchemyError:
        return Response(db_err_msg, content_type='text/plain', status=500)
    one = SimpleNamespace(name='one')
    return {'one': one, 'project': 'bridge_monitor'}


db_err_msg = """\
Pyramid is having a problem using your SQL database.  The problem
might be caused by one of the following things:

1.  You may need to initialize your database tables with `alembic`.
    Check your README.txt for descriptions and try to run it.

2.  Your database server may not be running.  Check that the
    database server referred to by the "sqlalchemy.url" setting in
    your "development.ini" file is running.

After you fix the problem, please restart the Pyramid application to
try it again.
"""
