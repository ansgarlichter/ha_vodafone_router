import logging
import json
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from custom_components.vodafone_router_device_polling.const import DEFAULT_SCAN_INTERVAL
from .vodafone_box import VodafoneBox

_LOGGER = logging.getLogger(__name__)


class VodafoneDeviceCoordinator(DataUpdateCoordinator):
    """Coordinator to poll Vodafone Station devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        username: str,
        password: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        mac_filter: str = "",
    ):
        """Initialize."""
        _LOGGER.info(
            "Initializing VodafoneDeviceCoordinator for host: %s with scan interval: %s seconds",
            host,
            scan_interval,
        )
        self.box = VodafoneBox(host)
        self.username = username
        self.password = password
        self._update_count = 0  # Track update cycles

        if mac_filter.strip():
            self.mac_filter = {
                mac.strip().lower().replace("-", ":")
                for mac in mac_filter.split(",")
                if mac.strip()
            }
            _LOGGER.info(
                "MAC filter enabled for %s devices: %s",
                len(self.mac_filter),
                list(self.mac_filter),
            )
        else:
            self.mac_filter = None
            _LOGGER.info("No MAC filter - all devices will be included")

        _LOGGER.debug(
            "Setting up coordinator with update interval: %s seconds", scan_interval
        )

        super().__init__(
            hass,
            _LOGGER,
            name="Vodafone Devices",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def async_login(self):
        """Login to Vodafone Station."""
        _LOGGER.info(
            "Attempting to login to Vodafone Station for user: %s", self.username
        )
        try:
            await self.hass.async_add_executor_job(
                self.box.login, self.username, self.password
            )
            _LOGGER.info("Successfully logged in to Vodafone Station")
        except Exception as e:
            _LOGGER.error("Failed to login to Vodafone Station: %s", e)
            raise

    async def async_logout(self):
        """Logout from Vodafone Station."""
        _LOGGER.info("Attempting to logout from Vodafone Station")
        try:
            await self.hass.async_add_executor_job(self.box.logout)
            _LOGGER.info("Successfully logged out from Vodafone Station")
        except Exception as e:
            _LOGGER.error("Failed to logout from Vodafone Station: %s", e)
            raise

    async def _async_update_data(self):
        """Fetch connected devices."""
        _LOGGER.debug("Starting device data update (cycle %s)", self._update_count)
        self._update_count += 1

        try:
            raw_device_data = await self.hass.async_add_executor_job(
                self.box.get_connected_devices
            )

            return self._process_device_data(raw_device_data)
        except Exception as err:
            if "Session lost" in str(err):
                _LOGGER.warning("Session lost, attempting re-authentication ...")
                try:
                    await self.async_login()
                    raw_data = await self.hass.async_add_executor_job(
                        self.box.get_connected_devices
                    )
                    return self._process_device_data(raw_data)
                except Exception as retry_err:
                    _LOGGER.error("Re-authentication failed: %s", retry_err)
                    raise UpdateFailed(f"Auth failure: {retry_err}") from retry_err
            
            _LOGGER.error("Unexpected update failure: %s", err)
            raise UpdateFailed(f"Communication error: {err}") from err    

    def _process_device_data(self, data):
        """Normalize MACs and apply filtering to the raw data."""
        if not data:
            return self.data or {"lanDevices": [], "wlanDevices": []}

        for device in data.get("lanDevices", []):
            if device.get("MAC"):
                device["MAC"] = device["MAC"].lower()

        if self.mac_filter:
            original_lan_count = len(data.get("lanDevices", []))
            original_wlan_count = len(data.get("wlanDevices", []))

            filtered_lan = [
                d
                for d in data.get("lanDevices", [])
                if d.get("MAC", "") in self.mac_filter
            ]
            filtered_wifi = [
                d
                for d in data.get("wlanDevices", [])
                if d.get("MAC", "") in self.mac_filter
            ]

            data["lanDevices"] = filtered_lan
            data["wlanDevices"] = filtered_wifi

            _LOGGER.debug(
                "MAC filtering applied: LAN %s->%s, WIFI %s->%s",
                original_lan_count,
                len(filtered_lan),
                original_wlan_count,
                len(filtered_wifi),
            )

        lan_count = len(data.get("lanDevices", []))
        wifi_count = len(data.get("wlanDevices", []))
        _LOGGER.info(
            "Device update successful: %s LAN devices, %s WIFI devices",
            lan_count,
            wifi_count,
        )
        _LOGGER.debug("Updated device data: %s", data)
        
        return data