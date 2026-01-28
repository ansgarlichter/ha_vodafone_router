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

    def __init__(self, hass: HomeAssistant, host: str, username: str, password: str, 
                 scan_interval: int = DEFAULT_SCAN_INTERVAL, mac_filter: str = ""):
        """Initialize."""
        _LOGGER.info("Initializing VodafoneDeviceCoordinator for host: %s with scan interval: %s seconds", host, scan_interval)
        self.box = VodafoneBox(host)
        self.username = username
        self.password = password
        self._update_count = 0  # Track update cycles
        
        # Process MAC filter
        if mac_filter.strip():
            self.mac_filter = {mac.strip().lower().replace("-", ":") for mac in mac_filter.split(",") if mac.strip()}
            _LOGGER.info("MAC filter enabled for %s devices: %s", len(self.mac_filter), list(self.mac_filter))
        else:
            self.mac_filter = None
            _LOGGER.info("No MAC filter - all devices will be included")
        
        _LOGGER.debug("Setting up coordinator with update interval: %s seconds", scan_interval)

        super().__init__(
            hass,
            _LOGGER,
            name="Vodafone Devices",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def async_login(self):
        """Login to Vodafone Station."""
        _LOGGER.info("Attempting to login to Vodafone Station for user: %s", self.username)
        try:
            await self.hass.async_add_executor_job(self.box.login, self.username, self.password)
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
        
        # Force fresh login every N cycles (e.g., every 10 minutes)
        force_fresh_login = self._update_count % 20 == 0  # Every 20 cycles = 10 mins if 30s interval
        
        if force_fresh_login:
            _LOGGER.debug("Performing periodic session refresh (cycle %s)", self._update_count)
            try:
                await self.async_logout()
                await self.async_login()
            except Exception as refresh_err:
                _LOGGER.warning("Periodic session refresh failed, continuing with existing session: %s", refresh_err)
        
        try:
            devices = await self.hass.async_add_executor_job(self.box.get_connected_devices)
            
            if devices:
                # Normalize all MAC addresses to lowercase for consistency
                for device in devices.get('lanDevices', []):
                    if device.get('MAC'):
                        device['MAC'] = device['MAC'].lower()
                
                for device in devices.get('wlanDevices', []):
                    if device.get('MAC'):
                        device['MAC'] = device['MAC'].lower()
                
                # Apply MAC filtering if configured
                if self.mac_filter:
                    original_lan_count = len(devices.get('lanDevices', []))
                    original_wlan_count = len(devices.get('wlanDevices', []))
                    
                    filtered_lan = [d for d in devices.get('lanDevices', []) 
                                   if d.get('MAC', '') in self.mac_filter]
                    filtered_wlan = [d for d in devices.get('wlanDevices', []) 
                                    if d.get('MAC', '') in self.mac_filter]
                    
                    devices['lanDevices'] = filtered_lan
                    devices['wlanDevices'] = filtered_wlan
                    
                    _LOGGER.debug("MAC filtering applied: LAN %s->%s, WLAN %s->%s", 
                                 original_lan_count, len(filtered_lan), 
                                 original_wlan_count, len(filtered_wlan))
                
                lan_count = len(devices.get('lanDevices', []))
                wlan_count = len(devices.get('wlanDevices', []))
                _LOGGER.info("Device update successful: %s LAN devices, %s WLAN devices", lan_count, wlan_count)
                _LOGGER.debug("Updated device data: %s", devices)
            else:
                _LOGGER.warning("No device data returned from router")
                
            return devices
        except (ValueError, json.JSONDecodeError) as err:
            # Likely session expired - try to re-login once
            _LOGGER.warning("Device fetch failed, attempting re-login: %s", err)
            try:
                await self.async_login()
                devices = await self.hass.async_add_executor_job(self.box.get_connected_devices)
                _LOGGER.info("Re-login successful, device data retrieved")
                return devices
            except Exception as retry_err:
                _LOGGER.error("Re-login failed: %s", retry_err, exc_info=True)
                raise UpdateFailed(f"Error fetching devices after re-login: {retry_err}") from retry_err
        except Exception as err:
            _LOGGER.error("Error fetching devices from Vodafone Station: %s", err, exc_info=True)
            raise UpdateFailed(f"Error fetching devices: {err}") from err
