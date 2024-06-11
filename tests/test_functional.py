import base64

from bridge_monitor import models


def test_my_view_auth_Failure(testapp, dbsession):
    model = models.KeyValuePair(key="test", value=12)
    dbsession.add(model)
    dbsession.flush()

    res = testapp.get("/", status=401)
    assert res.status_code == 401


def test_my_view_success(testapp, dbsession):
    model = models.KeyValuePair(key="test", value=55)
    dbsession.add(model)
    dbsession.flush()

    registry = testapp.app.registry
    auth_plaintext = registry["auth.username"] + ":" + registry["auth.password"]
    auth_header_value = "Basic " + base64.b64encode(auth_plaintext.encode()).decode()

    res = testapp.get(
        "/",
        status=200,
        headers={
            "Authorization": auth_header_value,
        },
    )
    assert res.body


def test_notfound(testapp):
    res = testapp.get("/badurl", status=404)
    assert res.status_code == 404
