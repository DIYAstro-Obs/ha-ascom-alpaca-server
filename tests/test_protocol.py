"""Protocol rules of the server: Connected per client and the HTTP status of errors."""

import asyncio
import importlib
import types

import pytest

common = importlib.import_module("ascom_alpaca_server.alpaca.handlers._common")
server_module = importlib.import_module("ascom_alpaca_server.alpaca.server")
registry_module = importlib.import_module("ascom_alpaca_server.alpaca.device_registry")


# ---- Connected is kept per client ---------------------------------------------------------------------
def connected(clients, method, params=None, client_id=1):
    return common.handle_connected(clients, method, params or {}, client_id)


def test_a_client_is_not_connected_until_it_connects():
    clients = set()
    assert connected(clients, "GET")["Value"] is False
    assert connected(clients, "PUT", {"Connected": "True"})["Value"] is True
    assert connected(clients, "GET")["Value"] is True
    assert connected(clients, "PUT", {"Connected": "False"})["Value"] is False
    assert connected(clients, "GET")["Value"] is False


def test_clients_do_not_disconnect_each_other():
    clients = set()
    connected(clients, "PUT", {"Connected": "true"}, client_id=1)
    connected(clients, "PUT", {"Connected": "true"}, client_id=2)

    connected(clients, "PUT", {"Connected": "false"}, client_id=2)
    assert connected(clients, "GET", client_id=1)["Value"] is True
    assert connected(clients, "GET", client_id=2)["Value"] is False


def test_connecting_twice_and_disconnecting_when_not_connected_are_harmless():
    clients = set()
    connected(clients, "PUT", {"Connected": "true"})
    assert connected(clients, "PUT", {"Connected": "true"})["Value"] is True
    connected(clients, "PUT", {"Connected": "false"})
    assert connected(clients, "PUT", {"Connected": "false"})["Value"] is False


def test_a_get_ignores_a_connected_parameter():
    clients = set()
    assert connected(clients, "GET", {"Connected": "true"})["Value"] is False


@pytest.mark.parametrize(
    "params",
    [{}, {"connected": "true"}, {"CONNECTED": "true"}, {"Connected": "maybe"}, {"Connected": ""}],
)
def test_a_put_with_a_missing_or_bad_parameter_is_a_bad_request(params):
    clients = set()
    result = connected(clients, "PUT", params)
    assert result["HttpStatus"] == 400
    assert clients == set()


# ---- HTTP status ------------------------------------------------------------------------------------------
class FakeRequest:
    def __init__(self, path, method="GET", query=None, form=None):
        device_type, number, action = path.strip("/").split("/")[-3:]
        self.match_info = {"device_type": device_type, "device_number": number, "action": action}
        self.method = method
        self.query = query or {}
        self._form = form or {}

    async def post(self):
        return self._form


@pytest.fixture
def alpaca(monkeypatch):
    """A server with a registry and fake responses; ``send`` returns (status, body or text)."""
    monkeypatch.setattr(
        server_module,
        "web",
        types.SimpleNamespace(
            Response=lambda status, text, content_type: types.SimpleNamespace(
                status=status, text=text, content_type=content_type, json=None
            ),
            json_response=lambda body, status=200: types.SimpleNamespace(
                status=status, text=None, content_type="application/json", json=body
            ),
        ),
    )
    registry = registry_module.AlpacaDeviceRegistry()
    server = server_module.AlpacaServer(registry, 11111, discovery_enabled=False)

    def register(result=None, error=None, device_type="safetymonitor"):
        calls = []

        async def handler(action, params):
            calls.append(action)
            if error:
                raise error
            return result

        registry.register_device(device_type, "Test", handler)
        return calls

    def send(*args, **kwargs):
        return asyncio.run(server._handle_device_request(FakeRequest(*args, **kwargs)))

    return types.SimpleNamespace(register=register, send=send)


def test_a_result_without_an_error_is_http_200(alpaca):
    alpaca.register({"Value": True})
    response = alpaca.send("/api/v1/safetymonitor/0/issafe")
    assert response.status == 200
    assert response.json["Value"] is True
    assert response.json["ErrorNumber"] == 0


def test_an_ascom_exception_of_the_device_is_http_200_with_the_error_number(alpaca):
    """Not implemented, invalid value: the request was understood, the client raises the ASCOM exception."""
    alpaca.register({"Value": None, "ErrorNumber": 0x400, "ErrorMessage": "not implemented"})
    response = alpaca.send("/api/v1/safetymonitor/0/azimuth", query={"ClientTransactionID": "7"})
    assert response.status == 200
    assert response.json["ErrorNumber"] == 0x400
    assert response.json["ErrorMessage"] == "not implemented"
    assert response.json["ClientTransactionID"] == 7


def test_a_request_the_device_does_not_understand_is_http_400_with_a_text(alpaca):
    alpaca.register(common.bad_request("Action 'foo' not supported"))
    response = alpaca.send("/api/v1/safetymonitor/0/foo")
    assert response.status == 400
    assert response.text == "Action 'foo' not supported"
    assert response.content_type == "text/plain"
    assert response.json is None


def test_an_unknown_device_is_http_400(alpaca):
    alpaca.register({"Value": True})
    response = alpaca.send("/api/v1/safetymonitor/5/issafe")
    assert response.status == 400
    assert "not found" in response.text


def test_a_device_type_with_capital_letters_is_http_400(alpaca):
    alpaca.register({"Value": True})
    assert alpaca.send("/api/v1/SafetyMonitor/0/issafe").status == 400


def test_a_device_that_crashes_is_http_500(alpaca):
    alpaca.register(error=RuntimeError("boom"))
    response = alpaca.send("/api/v1/safetymonitor/0/issafe")
    assert response.status == 500
    assert "boom" in response.text


# ---- Connected through the server -----------------------------------------------------------------------
def test_the_server_keeps_connected_and_the_device_never_sees_it(alpaca):
    calls = alpaca.register({"Value": True})

    put = alpaca.send(
        "/api/v1/safetymonitor/0/connected", "PUT", form={"Connected": "True", "ClientID": "42"}
    )
    assert put.status == 200
    assert put.json["Value"] is True

    assert alpaca.send("/api/v1/safetymonitor/0/connected", query={"ClientID": "42"}).json["Value"] is True
    assert alpaca.send("/api/v1/safetymonitor/0/connected", query={"ClientID": "43"}).json["Value"] is False
    assert calls == []


def test_a_bad_connected_put_is_http_400(alpaca):
    alpaca.register({"Value": True})
    response = alpaca.send("/api/v1/safetymonitor/0/connected", "PUT", form={"connected": "true"})
    assert response.status == 400
    assert "Connected" in response.text


def test_every_client_without_a_client_id_counts_as_client_0(alpaca):
    alpaca.register({"Value": True})
    alpaca.send("/api/v1/safetymonitor/0/connected", "PUT", form={"Connected": "true"})
    assert alpaca.send("/api/v1/safetymonitor/0/connected").json["Value"] is True


# ---- Commands only as PUT ----------------------------------------------------------------------------------
COMMANDS = {
    "dome": ["openshutter", "closeshutter", "abortslew", "findhome", "park", "setpark",
             "slewtoaltitude", "slewtoazimuth", "synctoazimuth"],
    "switch": ["setswitch", "setswitchvalue", "setswitchname"],
    "covercalibrator": ["calibratoron", "calibratoroff", "opencover", "closecover", "haltcover"],
    "observingconditions": ["refresh"],
}
ALL_COMMANDS = [(t, a) for t, actions in COMMANDS.items() for a in actions]


@pytest.mark.parametrize("device_type, action", ALL_COMMANDS)
@pytest.mark.parametrize("method", ["GET", "POST", "HEAD", "DELETE"])
def test_a_command_is_refused_unless_it_is_a_put(alpaca, device_type, action, method):
    """A link, an <img> or a form on any web page can send a GET or POST; only a PUT needs a preflight."""
    calls = alpaca.register({"Value": None}, device_type=device_type)
    response = alpaca.send(f"/api/v1/{device_type}/0/{action}", method)
    assert response.status == 400
    assert "PUT" in response.text
    assert calls == []


@pytest.mark.parametrize("device_type, action", ALL_COMMANDS)
def test_a_command_as_a_put_reaches_the_device(alpaca, device_type, action):
    calls = alpaca.register({"Value": None}, device_type=device_type)
    response = alpaca.send(f"/api/v1/{device_type}/0/{action}", "PUT")
    assert response.status == 200
    assert calls == [action]


@pytest.mark.parametrize("action", ["shutterstatus", "issafe", "getswitch", "calibratorstate", "temperature", "averageperiod"])
def test_properties_can_still_be_read_with_a_get(alpaca, action):
    calls = alpaca.register({"Value": 0}, device_type="dome")
    assert alpaca.send(f"/api/v1/dome/0/{action}").status == 200
    assert calls == [action]


def test_the_action_name_is_not_case_sensitive_for_the_command_check(alpaca):
    alpaca.register({"Value": None}, device_type="dome")
    assert alpaca.send("/api/v1/dome/0/OpenShutter", "GET").status == 400


# ---- the version exists twice and has to match ------------------------------------------------------------------
def test_the_server_version_matches_the_manifest():
    import json
    import pathlib

    from ascom_alpaca_server.alpaca.const import SERVER_VERSION

    manifest = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ascom_alpaca_server" / "manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == SERVER_VERSION
