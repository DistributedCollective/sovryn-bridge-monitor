from pyramid.view import view_config


@view_config(route_name='home', renderer='bridge_monitor:templates/mytemplate.jinja2')
def my_view(request):
    return {'one': {}, 'project': 'bridge_monitor'}
