"""Config flow for AHA Trash Pickup integration."""
import logging
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_GEMEINDE, CONF_STRASSE, CONF_HAUSNR, CONF_HAUSNRADDON, CONF_LADEORT, ABFALLARTEN, BASE_URL

_LOGGER = logging.getLogger(__name__)

async def fetch_form_options_gemeinde(hass):
    """Fetch muncipial options from the form page."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(BASE_URL, timeout=10) as resp:
            if resp.status != 200:
                return None
            text = await resp.text()
    except Exception as err:
        _LOGGER.error(f"Failed to fetch form page: {err}")
        return None

    gemeinde_match = re.search(r'<select[^>]+name="gemeinde"[^>]*>(.*?)</select>', text, re.DOTALL)
    if not gemeinde_match:
        return None
    gemeinden = {}
    for gemeinde in re.finditer(r'<option\s+value="([^"]*)"\s*(selected="selected")?\s*>(.*?)</option>', gemeinde_match.group(1)):
        value = gemeinde.group(1).strip()
        text_opt = gemeinde.group(3).strip()
        if value:
            gemeinden[value] = text_opt
    return gemeinden

async def fetch_form_options_strasse(hass, gemeinde):
    """Fetch street options from the form page."""
    session = async_get_clientsession(hass)
    strassen = {}
    for c in range(ord('A'), ord('Z')+1):
        data = {
            "gemeinde": gemeinde,
            "von": chr(c)
        }
        try:
            async with session.post(BASE_URL, data=data, timeout=10) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
        except Exception as err:
            _LOGGER.error(f"Failed to fetch form page: {err}")
            return None

        strasse_match = re.search(r'<select[^>]+name="strasse"[^>]*>(.*?)</select>', text, re.DOTALL)
        if not strasse_match:
            continue
        for strasse in re.finditer(r'<option\s+value=["\'](.*?)["\']\s*>(.*?)</option>', strasse_match.group(1)):
            value = strasse.group(1).strip()
            text_opt = strasse.group(2).strip()
            strassen[value] = text_opt
    return strassen

async def fetch_form_options_ladeort(hass, gemeinde, strasse, hausnr, hausnraddon):
    """Fetch ladeort options from the form page."""
    session = async_get_clientsession(hass)
    ladeorte = {}
    data = {
        "gemeinde": gemeinde,
        "strasse": strasse,
        "hausnr": hausnr,
        "hausnraddon": hausnraddon,
    }
    try:
        async with session.post(BASE_URL, data=data, timeout=10) as resp:
            if resp.status != 200:
                return None
            text = await resp.text()
    except Exception as err:
        _LOGGER.error(f"Failed to fetch form page: {err}")
        return None
    ladeort_match = re.search(r'<select[^>]+name="ladeort"[^>]*>(.*?)</select>', text, re.DOTALL)
    if not ladeort_match:
        return None
    for ladeort in re.finditer(r'<option\s+value=["\'](.*?)["\']\s*>(.*?)</option>', ladeort_match.group(1)):
        value = ladeort.group(1).strip()
        text_opt = ladeort.group(2).strip()
        ladeorte[value] = text_opt
    return ladeorte

class AHATrashConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AHA Trash Pickup."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self._gemeinden = {}
        self._strassen = {}
        self._selected_gemeinde_value = None
        self._selected_gemeinde_text = None
        self._selected_strasse_value = None
        self._selected_strasse_text = None
        self._strassenr = None
        self._strassenraddon = None
        self._selected_ladeort_value = None
        self._selected_ladeort_text = None

    async def create_entry(self):
        """Try to return entry, if data is valid, raise LookupError in case of required ladeort, return None if no data available"""
        data = {
            "gemeinde": self._selected_gemeinde_value,
            "strasse": self._selected_strasse_value,
            "hausnr": self._hausnr,
            "hausnraddon": self._hausnraddon,
            "ladeort": self._selected_ladeort_value,
        }
        session = async_get_clientsession(self.hass)
        async with session.post(BASE_URL, data=data, timeout=10) as resp:
            if resp.status != 200:
                raise SystemError("Bad status")
            text = await resp.text()
            has_data = any("<strong>"+abf+"</strong>" in text for abf in ABFALLARTEN)
            needs_ladeort = 'id="ladeort" name="ladeort"' in text
            if needs_ladeort and not has_data:
                raise LookupError("Needs ladeort")
            if not has_data:
                return None
        unique_id = f"{data[CONF_GEMEINDE]}_{data[CONF_STRASSE]}_{data[CONF_HAUSNR]}{data[CONF_HAUSNRADDON]}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"{self._selected_strasse_text} {data[CONF_HAUSNR]}{data[CONF_HAUSNRADDON]}",
            data=data,
        )

    async def async_step_user(self, user_input=None):
        """Initial step: load options and show gemeinde selector."""
        errors = {}
        if not self._gemeinden:
            self._gemeinden = await fetch_form_options_gemeinde(self.hass)
            if not self._gemeinden:
                errors["base"] = "fetch_failed"

        if user_input is not None and not errors:
            self._selected_gemeinde_value = user_input[CONF_GEMEINDE]
            self._selected_gemeinde_text = self._selected_gemeinde_value
            if self._gemeinden:
                self._selected_gemeinde_text = self._gemeinden.get(self._selected_gemeinde_value)
            return await self.async_step_strasse()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_GEMEINDE, default="Hannover"): vol.In(self._gemeinden) if not errors else str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_strasse(self, user_input=None):
        """Step: select strasse based on gemeinde."""
        errors = {}
        self._strassen = await fetch_form_options_strasse(self.hass, self._selected_gemeinde_value)

        if user_input is not None and not errors:
            self._selected_strasse_value = user_input[CONF_STRASSE]
            self._selected_strasse_text = user_input[CONF_STRASSE]
            if self._strassen:
                self._selected_strasse_text = self._strassen.get(user_input[CONF_STRASSE])
            self._hausnr = user_input[CONF_HAUSNR]
            self._hausnraddon = user_input[CONF_HAUSNRADDON]
            try:
                entry = await self.create_entry()
                if entry is not None:
                    return entry
                errors["base"] = "invalid_address"
            except SystemError:
                errors["base"] = "cannot_connect"
            except LookupError:
                return await self.async_step_ladeort()

        strasse_schema = vol.Schema(
            {
                vol.Required(CONF_STRASSE): vol.In(self._strassen) if self._strassen else str,
                vol.Required(CONF_HAUSNR, default=1): int,
                vol.Optional(CONF_HAUSNRADDON, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="strasse",
            data_schema=strasse_schema,
            description_placeholders={"gemeinde":self._selected_gemeinde_text},
            errors=errors,
        )

    async def async_step_ladeort(self, user_input=None):
        """Step: select ladeort based on address."""
        errors = {}
        self._ladeorte = await fetch_form_options_ladeort(self.hass, self._selected_gemeinde_value, self._selected_strasse_value, self._hausnr, self._hausnraddon)

        if user_input is not None and not errors:
            self._selected_ladeort_value = user_input[CONF_LADEORT]
            self._selected_ladeort_text = user_input[CONF_LADEORT]
            if self._ladeorte:
                self._selected_ladeorte_text = self._ladeorte.get(user_input[CONF_LADEORT])
            try:
                entry = await self.create_entry()
                if entry is not None:
                    return entry
                # Should not happen, as a ladeort is required, it should raise a LookupError
                errors["base"] = "invalid_address2"
            except SystemError:
                errors["base"] = "cannot_connect"
            except LookupError:
                errors["base"] = "invalid_address2"

        ladeort_schema = vol.Schema(
            {
                vol.Required(CONF_LADEORT, default=""): vol.In(self._ladeorte) if self._ladeorte else str,
            }
        )

        return self.async_show_form(
            step_id="ladeort",
            data_schema=ladeort_schema,
            errors=errors,
        )
