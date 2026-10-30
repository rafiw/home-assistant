"""Support for Yale Access Bluetooth switches."""

import logging
from typing import Any, override

from yalexs_ble import ConnectionInfo, LockInfo, LockState, LockStatus, YaleXSBLEError

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import YALEXSBLEConfigEntry
from .entity import YALEXSBLEEntity
from .models import YaleXSBLEData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YALEXSBLEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Yale Access Bluetooth switches."""
    async_add_entities([YaleXSBLEPrivacyModeSwitch(entry.runtime_data)])


class YaleXSBLEPrivacyModeSwitch(YALEXSBLEEntity, RestoreEntity, SwitchEntity):
    """Switch to enable or disable Privacy Mode (BLE setting 0xBC)."""

    _attr_translation_key = "privacy_mode"

    def __init__(self, data: YaleXSBLEData) -> None:
        """Initialize the Privacy Mode switch."""
        self._attr_is_on: bool | None = None
        super().__init__(data)
        self._attr_unique_id = f"{self._device.address}_privacy_mode"

    @callback
    @override
    def _async_update_state(
        self, new_state: LockState, lock_info: LockInfo, connection_info: ConnectionInfo
    ) -> None:
        """Update the switch state from lock push state."""
        if new_state.lock is LockStatus.PRIVACY_MODE:
            self._attr_is_on = True
            self._data.async_set_privacy_mode(True)
        super()._async_update_state(new_state, lock_info, connection_info)

    @override
    async def async_added_to_hass(self) -> None:
        """Restore previous state and fetch actual setting from the lock."""
        await super().async_added_to_hass()
        if (
            self._attr_is_on is None
            and (last_state := await self.async_get_last_state()) is not None
            and last_state.state in (STATE_ON, STATE_OFF)
        ):
            is_on = last_state.state == STATE_ON
            self._attr_is_on = is_on
            self._data.async_set_privacy_mode(is_on)
        self.hass.async_create_background_task(
            self._async_fetch_initial_state(),
            f"yalexs_ble_privacy_mode_{self._device.address}",
        )

    async def _async_fetch_initial_state(self) -> None:
        """Read setting 0xBC from the lock once after startup."""
        try:
            is_on = await self._device.get_privacy_mode()
        except (YaleXSBLEError, TimeoutError, RuntimeError) as err:
            _LOGGER.debug(
                "%s: Could not read initial privacy mode state: %s",
                self._device.name,
                err,
            )
            return
        self._attr_is_on = is_on
        self._data.async_set_privacy_mode(is_on)
        self.async_write_ha_state()

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable privacy mode on the lock."""
        try:
            await self._device.set_privacy_mode(True)
        except (YaleXSBLEError, TimeoutError) as err:
            raise HomeAssistantError(
                f"Failed to enable privacy mode on {self._device.name}: {err}"
            ) from err
        self._attr_is_on = True
        self._data.async_set_privacy_mode(True)
        self.async_write_ha_state()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable privacy mode on the lock."""
        try:
            await self._device.set_privacy_mode(False)
        except (YaleXSBLEError, TimeoutError) as err:
            raise HomeAssistantError(
                f"Failed to disable privacy mode on {self._device.name}: {err}"
            ) from err
        self._attr_is_on = False
        self._data.async_set_privacy_mode(False)
        self.async_write_ha_state()

    @override
    async def async_update(self) -> None:
        """Request a manual update of lock state and privacy mode."""
        await super().async_update()
        is_on = await self._device.get_privacy_mode()
        self._attr_is_on = is_on
        self._data.async_set_privacy_mode(is_on)
