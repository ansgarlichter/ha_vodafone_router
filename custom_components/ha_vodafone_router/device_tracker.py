from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import TrackerEntity, SourceType
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_PROPERTY_HOSTNAME,
    DEVICE_PROPERTY_MAC_ADDRESS,
    DEVICE_PROPERTY_NAME,
    DOMAIN,
    ROUTER_PROPERTY_LAN_DEVICES,
    ROUTER_PROPERTY_WLAN_DEVICES,
)
from .coordinator import VodafoneDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vodafone device tracker entities."""
    _LOGGER.info(
        "Setting up Vodafone device tracker entities for entry: %s", entry.entry_id
    )

    coordinator: VodafoneDeviceCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Coordinator is already logged in and has data from __init__.py
    _LOGGER.debug("Using coordinator data for device tracker setup (already logged in)")

    _LOGGER.debug("Creating device tracker entities from connected devices")
    entities: list[VodafoneDeviceTracker] = []
    total_devices = 0

    for dev_list_name in (ROUTER_PROPERTY_LAN_DEVICES, ROUTER_PROPERTY_WLAN_DEVICES):
        devices = coordinator.data.get(dev_list_name, [])
        _LOGGER.debug("Processing %s devices from %s", len(devices), dev_list_name)

        for device in devices:
            total_devices += 1
            if not device.get(DEVICE_PROPERTY_MAC_ADDRESS):
                _LOGGER.warning("Skipping device without MAC address: %s", device)
                continue

            _LOGGER.debug(
                "Creating tracker entity for device: %s (%s)",
                device.get(DEVICE_PROPERTY_HOSTNAME, "Unknown"),
                device.get(DEVICE_PROPERTY_MAC_ADDRESS),
            )
            entities.append(VodafoneDeviceTracker(coordinator, device))

    _LOGGER.info(
        "Created %s device tracker entities from %s total devices",
        len(entities),
        total_devices,
    )
    async_add_entities(entities)


class VodafoneDeviceTracker(TrackerEntity):
    """Device tracker for a Vodafone Station connected device."""

    _attr_source_type = SourceType.ROUTER

    def __init__(
        self,
        coordinator: VodafoneDeviceCoordinator,
        device: dict[str, Any],
    ) -> None:
        self.coordinator = coordinator
        self.device = device
        self.mac: str = device.get(DEVICE_PROPERTY_MAC_ADDRESS)
        # MAC is guaranteed here because we filtered earlier
        self._attr_name = f"{device.get(DEVICE_PROPERTY_HOSTNAME) or device.get(DEVICE_PROPERTY_NAME) or self.mac} Tracker"
        self._attr_unique_id = f"vodafone_{self.mac.replace(':', '').lower()}_tracker"

        _LOGGER.debug(
            "Initialized device tracker for %s (MAC: %s, unique_id: %s)",
            self._attr_name,
            self.mac,
            self._attr_unique_id,
        )

    @property
    def state(self) -> str:
        """Return the state of the device tracker."""
        if not self.coordinator.data:
            _LOGGER.debug("No coordinator data available for %s", self.mac)
            return STATE_NOT_HOME

        connected_lan_macs = [d.get(DEVICE_PROPERTY_MAC_ADDRESS, "").lower() 
                   for d in self.coordinator.data.get(ROUTER_PROPERTY_LAN_DEVICES, [])]
        connected_wifi_macs = [d.get(DEVICE_PROPERTY_MAC_ADDRESS, "").lower() 
                    for d in self.coordinator.data.get(ROUTER_PROPERTY_WLAN_DEVICES, [])]
        
        is_connected = self.mac.lower() in connected_lan_macs or self.mac.lower() in connected_wifi_macs

        state = STATE_HOME if is_connected else STATE_NOT_HOME
        _LOGGER.debug(
            "Device tracker %s (%s) state: %s", self._attr_name, self.mac, state
        )
        return state

    @property
    def location_name(self) -> str | None:
        """Return the location name of the device."""
        return STATE_HOME if self.state == STATE_HOME else None

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """Register for coordinator updates."""
        _LOGGER.debug(
            "Adding device tracker %s (%s) to Home Assistant", self._attr_name, self.mac
        )
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        _LOGGER.debug(
            "Registered device tracker %s for coordinator updates", self._attr_name
        )
