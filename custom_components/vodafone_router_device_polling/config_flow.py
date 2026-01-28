import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, ENTRY_DATA_HOST, OPTION_PASSWORD, OPTION_USERNAME, OPTION_MAC_FILTER, OPTION_ENABLE_BINARY_SENSOR, OPTION_ENABLE_DEVICE_TRACKER
from .vodafone_box import VodafoneBox

_LOGGER = logging.getLogger(__name__)

class VodafoneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vodafone Station."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return VodafoneOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        _LOGGER.debug("Starting config flow step: user")
        errors = {}

        if user_input is not None:
            _LOGGER.info("Processing user input for Vodafone Station configuration")
            host = user_input[ENTRY_DATA_HOST]
            username = user_input[OPTION_USERNAME]
            password = user_input[OPTION_PASSWORD]
            mac_filter = user_input.get(OPTION_MAC_FILTER, "")
            enable_binary_sensor = user_input.get(OPTION_ENABLE_BINARY_SENSOR, True)
            enable_device_tracker = user_input.get(OPTION_ENABLE_DEVICE_TRACKER, True)
            
            _LOGGER.debug("Testing connection to Vodafone Station at %s with username %s", host, username)

            box = VodafoneBox(host)
            try:
                await self.hass.async_add_executor_job(box.login, username, password)
                _LOGGER.info("Connection test successful for %s", host)
            except Exception as e:
                _LOGGER.error("Connection test failed for %s: %s", host, e, exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                _LOGGER.info("Creating config entry for Vodafone Station at %s", host)
                return self.async_create_entry(
                    title=f"Vodafone Station ({host})",
                    data={ENTRY_DATA_HOST: host},  # non-sensitive
                    options={
                        OPTION_USERNAME: username,
                        OPTION_PASSWORD: password,
                        OPTION_MAC_FILTER: mac_filter,
                        OPTION_ENABLE_BINARY_SENSOR: enable_binary_sensor,
                        OPTION_ENABLE_DEVICE_TRACKER: enable_device_tracker,
                    }
                )

        schema = vol.Schema({
            vol.Required(ENTRY_DATA_HOST): str,
            vol.Required(OPTION_USERNAME): str,
            vol.Required(OPTION_PASSWORD): str,
            vol.Optional(OPTION_MAC_FILTER, default=""): str,
            vol.Optional(OPTION_ENABLE_BINARY_SENSOR, default=True): bool,
            vol.Optional(OPTION_ENABLE_DEVICE_TRACKER, default=True): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, user_input=None):
        """Handle re-authentication when login fails."""
        return await self.async_step_user(user_input)


class VodafoneOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Vodafone Station."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        _LOGGER.debug("Starting options flow")
        errors = {}

        if user_input is not None:
            _LOGGER.info("Processing options update")
            host = self.config_entry.data[ENTRY_DATA_HOST]
            username = user_input[OPTION_USERNAME]
            password = user_input[OPTION_PASSWORD]
            
            box = VodafoneBox(host)
            try:
                await self.hass.async_add_executor_job(box.login, username, password)
                _LOGGER.info("Options connection test successful")
                
                return self.async_create_entry(
                    title="",
                    data={
                        OPTION_USERNAME: username,
                        OPTION_PASSWORD: password,
                        OPTION_MAC_FILTER: user_input[OPTION_MAC_FILTER],
                        OPTION_ENABLE_BINARY_SENSOR: user_input[OPTION_ENABLE_BINARY_SENSOR],
                        OPTION_ENABLE_DEVICE_TRACKER: user_input[OPTION_ENABLE_DEVICE_TRACKER],
                    }
                )
            except Exception as e:
                _LOGGER.error("Options connection test failed: %s", e, exc_info=True)
                errors["base"] = "cannot_connect"

        current_options = self.config_entry.options
        
        schema = vol.Schema({
            vol.Required(OPTION_USERNAME, default=current_options.get(OPTION_USERNAME, "")): str,
            vol.Required(OPTION_PASSWORD, default=current_options.get(OPTION_PASSWORD, "")): str,
            vol.Optional(OPTION_MAC_FILTER, default=current_options.get(OPTION_MAC_FILTER, "")): str,
            vol.Optional(OPTION_ENABLE_BINARY_SENSOR, default=current_options.get(OPTION_ENABLE_BINARY_SENSOR, True)): bool,
            vol.Optional(OPTION_ENABLE_DEVICE_TRACKER, default=current_options.get(OPTION_ENABLE_DEVICE_TRACKER, True)): bool,
        })
        
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "host": self.config_entry.data[ENTRY_DATA_HOST]
            }
        )
