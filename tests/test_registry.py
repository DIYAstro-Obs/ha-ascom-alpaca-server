"""The device registry: numbers, registering again, unregistering."""

import asyncio
import importlib
import uuid

registry_module = importlib.import_module("ascom_alpaca_server.alpaca.device_registry")
models = importlib.import_module("ascom_alpaca_server.alpaca.models")


def answering(value):
    async def handler(action, params):
        return {"Value": value}

    return handler


def answer(registry, device_type="safetymonitor", number=0):
    return asyncio.run(registry.get_device(device_type, number).handler("x", {}))["Value"]


def test_devices_get_numbers_per_type():
    registry = registry_module.AlpacaDeviceRegistry()
    registry.register_device("SafetyMonitor", "A", answering("a"))
    registry.register_device("SafetyMonitor", "B", answering("b"))
    registry.register_device("Dome", "C", answering("c"))

    assert [(d.device_type, d.device_number) for d in registry.get_all_devices()] == [
        ("safetymonitor", 0),
        ("safetymonitor", 1),
        ("dome", 0),
    ]


def test_registering_again_under_the_same_name_replaces_the_old_device():
    """Safety that could not unregister must not stay behind with a dead handler."""
    registry = registry_module.AlpacaDeviceRegistry()
    registry.register_device("SafetyMonitor", "Safety", answering("old"))
    registry.register_device("SafetyMonitor", "Safety", answering("new"))

    assert len(registry.get_all_devices()) == 1
    assert answer(registry) == "new"
    assert registry.get_all_devices()[0].device_number == 0


def test_a_late_unregister_of_the_replaced_device_leaves_the_new_one():
    registry = registry_module.AlpacaDeviceRegistry()
    unregister_old = registry.register_device("SafetyMonitor", "Safety", answering("old"))
    registry.register_device("SafetyMonitor", "Safety", answering("new"))

    unregister_old()
    assert answer(registry) == "new"


def test_another_name_is_another_device():
    registry = registry_module.AlpacaDeviceRegistry()
    registry.register_device("SafetyMonitor", "Safety", answering("a"))
    registry.register_device("SafetyMonitor", "Other", answering("b"))
    assert len(registry.get_all_devices()) == 2


def test_the_same_name_gets_its_number_back_after_unregistering():
    registry = registry_module.AlpacaDeviceRegistry()
    registry.register_device("SafetyMonitor", "A", answering("a"))
    unregister = registry.register_device("SafetyMonitor", "B", answering("b"))

    unregister()
    assert registry.get_device("safetymonitor", 1) is None

    registry.register_device("SafetyMonitor", "B", answering("b2"))
    assert answer(registry, number=1) == "b2"


def test_a_freed_number_goes_to_the_next_new_device():
    registry = registry_module.AlpacaDeviceRegistry()
    unregister = registry.register_device("SafetyMonitor", "A", answering("a"))
    registry.register_device("SafetyMonitor", "B", answering("b"))
    unregister()

    registry.register_device("SafetyMonitor", "C", answering("c"))
    assert answer(registry, number=0) == "c"


def test_rebuilding_the_internal_devices_keeps_the_external_ones():
    registry = registry_module.AlpacaDeviceRegistry()
    registry.register_device("SafetyMonitor", "Safety", answering("s"))
    registry.add_device(
        models.AlpacaDevice("dome", registry.allocate_number("dome"), "HA Dome", "int_dome", answering("d"))
    )

    registry.remove_internal_devices()
    assert [d.device_name for d in registry.get_all_devices()] == ["Safety"]

    assert registry.allocate_number("dome") == 0  # the numbers of the internal devices start again
    assert answer(registry) == "s"


def test_every_device_has_its_own_connected_clients():
    registry = registry_module.AlpacaDeviceRegistry()
    registry.register_device("SafetyMonitor", "A", answering("a"))
    registry.register_device("SafetyMonitor", "B", answering("b"))
    first, second = registry.get_all_devices()

    first.connected_clients.add(7)
    assert second.connected_clients == set()


# ---- the UniqueID: a GUID that does not depend on the device number -----------------------------------------------------
def ids_of(registry):
    return {d.device_name: d.unique_id for d in registry.get_all_devices()}


def test_a_unique_id_is_a_guid_and_independent_of_the_registration_order():
    first = registry_module.AlpacaDeviceRegistry()
    first.register_device("SafetyMonitor", "A", answering("a"))
    first.register_device("SafetyMonitor", "B", answering("b"))

    other_order = registry_module.AlpacaDeviceRegistry()
    other_order.register_device("SafetyMonitor", "B", answering("b"))
    other_order.register_device("SafetyMonitor", "A", answering("a"))

    for unique_id in ids_of(first).values():
        uuid.UUID(unique_id)  # a GUID
    assert ids_of(first)["A"] != ids_of(first)["B"]
    assert ids_of(first) == ids_of(other_order)  # whatever the numbers are
    numbers = lambda registry: {d.device_name: d.device_number for d in registry.get_all_devices()}  # noqa: E731
    assert numbers(first) != numbers(other_order)


def test_the_unique_id_survives_unregistering_and_registering_again():
    registry = registry_module.AlpacaDeviceRegistry()
    unregister = registry.register_device("SafetyMonitor", "Safety", answering("s"))
    before = ids_of(registry)["Safety"]

    unregister()
    registry.register_device("SafetyMonitor", "Safety", answering("s"))
    assert ids_of(registry)["Safety"] == before


def test_the_type_and_the_name_make_the_id():
    registry = registry_module.AlpacaDeviceRegistry()
    registry.register_device("SafetyMonitor", "X", answering("a"))
    registry.register_device("Dome", "X", answering("b"))
    registry.register_device("Dome", "Y", answering("c"))
    assert len({d.unique_id for d in registry.get_all_devices()}) == 3


def test_two_servers_do_not_share_ids():
    one = registry_module.AlpacaDeviceRegistry("server-one")
    two = registry_module.AlpacaDeviceRegistry("server-two")
    one.register_device("SafetyMonitor", "Safety", answering("s"))
    two.register_device("SafetyMonitor", "Safety", answering("s"))
    assert ids_of(one)["Safety"] != ids_of(two)["Safety"]


def test_the_internal_devices_keep_their_ids_when_they_are_built_again():
    from ha_stubs import FakeHass

    ha_bridge = importlib.import_module("ascom_alpaca_server.ha_bridge")
    registry = registry_module.AlpacaDeviceRegistry("server-one")
    options = {"dome_cover_entity": "cover.roof", "calibrator_onoff_entity": "switch.panel"}

    ha_bridge.rebuild_devices(registry, FakeHass(), options)
    first = ids_of(registry)
    ha_bridge.rebuild_devices(registry, FakeHass(), options)

    assert ids_of(registry) == first
    assert len(set(first.values())) == 2
    for unique_id in first.values():
        uuid.UUID(unique_id)
