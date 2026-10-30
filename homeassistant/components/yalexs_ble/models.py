"""The yalexs_ble integration models."""

from dataclasses import dataclass, field

from yalexs_ble import PushLock

from homeassistant.core import CALLBACK_TYPE, callback


@dataclass
class YaleXSBLEData:
    """Data for the yale xs ble integration."""

    title: str
    lock: PushLock
    always_connected: bool
    privacy_mode: bool = False
    _privacy_mode_callbacks: list[CALLBACK_TYPE] = field(default_factory=list)

    @callback
    def async_set_privacy_mode(self, enabled: bool) -> None:
        """Update privacy mode state and notify listeners."""
        self.privacy_mode = enabled
        for listener in self._privacy_mode_callbacks:
            listener()

    @callback
    def async_register_privacy_mode_callback(
        self, listener: CALLBACK_TYPE
    ) -> CALLBACK_TYPE:
        """Register a callback to be notified when privacy mode changes."""
        self._privacy_mode_callbacks.append(listener)

        @callback
        def _remove() -> None:
            self._privacy_mode_callbacks.remove(listener)

        return _remove
