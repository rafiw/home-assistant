"""Test the Yale Access Bluetooth switch and lock availability in privacy mode."""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from yalexs_ble import (
    ConnectionInfo,
    DoorStatus,
    LockInfo,
    LockState,
    LockStatus,
    YaleXSBLEError,
)

from homeassistant.components.lock import LockState as HALockState
from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.components.yalexs_ble.const import (
    CONF_KEY,
    CONF_LOCAL_NAME,
    CONF_SLOT,
    DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ADDRESS,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from . import YALE_ACCESS_LOCK_DISCOVERY_INFO

from tests.common import MockConfigEntry, mock_restore_cache


def _get_mock_push_lock(
    initial_privacy_mode: bool = False,
) -> tuple[Mock, list[Callable[[LockState, LockInfo, ConnectionInfo], None]]]:
    """Return a mock PushLock and its registered state callbacks."""
    callbacks: list[Callable[[LockState, LockInfo, ConnectionInfo], None]] = []
    mock_push_lock = Mock()
    mock_push_lock.name = "Front Door (EEFF)"
    mock_push_lock.address = YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    mock_push_lock.start = AsyncMock(return_value=MagicMock())
    mock_push_lock.wait_for_first_update = AsyncMock()
    mock_push_lock.stop = AsyncMock()
    mock_push_lock.update = AsyncMock()
    mock_push_lock.lock = AsyncMock()
    mock_push_lock.unlock = AsyncMock()
    mock_push_lock.securemode = AsyncMock()
    mock_push_lock.get_privacy_mode = AsyncMock(return_value=initial_privacy_mode)
    mock_push_lock.set_privacy_mode = AsyncMock()
    mock_push_lock.lock_state = LockState(
        LockStatus.UNLOCKED, DoorStatus.CLOSED, None, None, None, None
    )
    mock_push_lock.lock_status = LockStatus.UNLOCKED
    mock_push_lock.door_status = DoorStatus.CLOSED
    mock_push_lock.lock_info = LockInfo("Front Door", "M1XXX012LU", "1.0.0", "1.0.0")
    mock_push_lock.connection_info = ConnectionInfo(-60)

    def _register_callback(
        cb: Callable[[LockState, LockInfo, ConnectionInfo], None],
    ) -> Callable[[], None]:
        callbacks.append(cb)

        def _unregister() -> None:
            callbacks.remove(cb)

        return _unregister

    mock_push_lock.register_callback = Mock(side_effect=_register_callback)
    return mock_push_lock, callbacks


def _create_entry() -> MockConfigEntry:
    """Create a MockConfigEntry for yalexs_ble."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Front Door",
        data={
            CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
            CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 66,
        },
        unique_id=YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
    )


async def test_privacy_mode_switch_and_lock_availability(
    hass: HomeAssistant,
) -> None:
    """Test turning privacy mode on and off updates switch and lock availability."""
    entry = _create_entry()
    entry.add_to_hass(hass)
    mock_push_lock, _ = _get_mock_push_lock(initial_privacy_mode=False)

    with patch(
        "homeassistant.components.yalexs_ble.PushLock",
        return_value=mock_push_lock,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    switch_state = hass.states.get("switch.front_door_privacy_mode")
    assert switch_state is not None
    assert switch_state.state == STATE_OFF

    lock_state = hass.states.get("lock.front_door")
    assert lock_state is not None
    assert lock_state.state == HALockState.UNLOCKED

    # Turn on privacy mode -> switch becomes ON and lock becomes UNAVAILABLE
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.front_door_privacy_mode"},
        blocking=True,
    )
    mock_push_lock.set_privacy_mode.assert_awaited_once_with(True)

    switch_state = hass.states.get("switch.front_door_privacy_mode")
    assert switch_state is not None
    assert switch_state.state == STATE_ON

    lock_state = hass.states.get("lock.front_door")
    assert lock_state is not None
    assert lock_state.state == STATE_UNAVAILABLE

    # Turn off privacy mode -> switch becomes OFF and lock becomes UNLOCKED again
    mock_push_lock.set_privacy_mode.reset_mock()
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.front_door_privacy_mode"},
        blocking=True,
    )
    mock_push_lock.set_privacy_mode.assert_awaited_once_with(False)

    switch_state = hass.states.get("switch.front_door_privacy_mode")
    assert switch_state is not None
    assert switch_state.state == STATE_OFF

    lock_state = hass.states.get("lock.front_door")
    assert lock_state is not None
    assert lock_state.state == HALockState.UNLOCKED


async def test_privacy_mode_from_lock_status_push_update(
    hass: HomeAssistant,
) -> None:
    """Test LockStatus.PRIVACY_MODE push update sets switch on and lock unavailable."""
    entry = _create_entry()
    entry.add_to_hass(hass)
    mock_push_lock, callbacks = _get_mock_push_lock(initial_privacy_mode=False)

    with patch(
        "homeassistant.components.yalexs_ble.PushLock",
        return_value=mock_push_lock,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("switch.front_door_privacy_mode").state == STATE_OFF
    assert hass.states.get("lock.front_door").state == HALockState.UNLOCKED

    # Simulate push notification with LockStatus.PRIVACY_MODE
    new_state = LockState(
        LockStatus.PRIVACY_MODE, DoorStatus.CLOSED, None, None, None, None
    )
    mock_push_lock.lock_state = new_state
    mock_push_lock.lock_status = LockStatus.PRIVACY_MODE
    for cb in list(callbacks):
        cb(new_state, mock_push_lock.lock_info, mock_push_lock.connection_info)
    await hass.async_block_till_done()

    assert hass.states.get("switch.front_door_privacy_mode").state == STATE_ON
    assert hass.states.get("lock.front_door").state == STATE_UNAVAILABLE


async def test_privacy_mode_restore_state_and_initial_fetch_failure(
    hass: HomeAssistant,
) -> None:
    """Test restoring previous switch state when initial BLE read fails."""
    mock_restore_cache(
        hass,
        [State("switch.front_door_privacy_mode", STATE_ON)],
    )
    entry = _create_entry()
    entry.add_to_hass(hass)
    mock_push_lock, _ = _get_mock_push_lock()
    mock_push_lock.get_privacy_mode = AsyncMock(
        side_effect=YaleXSBLEError("BLE timeout")
    )

    with patch(
        "homeassistant.components.yalexs_ble.PushLock",
        return_value=mock_push_lock,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("switch.front_door_privacy_mode").state == STATE_ON
    assert hass.states.get("lock.front_door").state == STATE_UNAVAILABLE


async def test_privacy_mode_errors_and_manual_update(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test error handling when toggling privacy mode and manual entity update."""
    await async_setup_component(hass, "homeassistant", {})
    entry = _create_entry()
    entry.add_to_hass(hass)
    mock_push_lock, _ = _get_mock_push_lock(initial_privacy_mode=False)

    with patch(
        "homeassistant.components.yalexs_ble.PushLock",
        return_value=mock_push_lock,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Turn on error raises HomeAssistantError
    mock_push_lock.set_privacy_mode.side_effect = YaleXSBLEError("Disconnection")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "switch.front_door_privacy_mode"},
            blocking=True,
        )
    assert hass.states.get("switch.front_door_privacy_mode").state == STATE_OFF
    assert hass.states.get("lock.front_door").state == HALockState.UNLOCKED

    # Turn off error raises HomeAssistantError
    mock_push_lock.set_privacy_mode.side_effect = TimeoutError("Timed out")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.front_door_privacy_mode"},
            blocking=True,
        )

    # Manual update via homeassistant.update_entity
    mock_push_lock.get_privacy_mode.return_value = True
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: "switch.front_door_privacy_mode"},
        blocking=True,
    )
    mock_push_lock.update.assert_awaited_once()
    assert hass.states.get("switch.front_door_privacy_mode").state == STATE_ON
    assert hass.states.get("lock.front_door").state == STATE_UNAVAILABLE
