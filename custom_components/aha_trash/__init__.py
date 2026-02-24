"""The AHA Trash Pickup integration."""
import logging
from datetime import datetime, timedelta

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.const import Platform
from homeassistant.helpers.event import async_track_point_in_time

from .const import DOMAIN, CONF_GEMEINDE, CONF_STRASSE, CONF_HAUSNR, CONF_HAUSNRADDON, CONF_LADEORT, ABFALLARTEN, BASE_URL

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.CALENDAR]

async def async_setup_entry(hass, entry):
    """Set up AHA Trash Pickup from a config entry."""
    session = async_get_clientsession(hass)
    coordinator = AHATrashCoordinator(hass, session, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Schedule daily update at 7 AM local time
    def async_schedule_daily_update():
        now = dt_util.now()
        next_update = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if next_update < now:
            next_update += timedelta(days=1)

        async def async_daily_refresh(_):
            """Refresh data and reschedule."""
            await coordinator.async_request_refresh()
            async_schedule_daily_update()

        async_track_point_in_time(hass, async_daily_refresh, next_update)

    async_schedule_daily_update()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    #await hass.config_entries.async_forward_entry_unload(entry, "binary_sensor")
    hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class AHATrashCoordinator(DataUpdateCoordinator):
    """AHA Trash data update coordinator."""

    def __init__(self, hass, session, entry):
        """Initialize coordinator."""
        self.session = session
        self.config = entry.data
        self.entry = entry
        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def _async_update_data(self):
        """Fetch data from API."""
        data = {
            "gemeinde": self.config[CONF_GEMEINDE],
            "strasse": self.config[CONF_STRASSE],
            "hausnr": self.config[CONF_HAUSNR],
            "hausnraddon": self.config.get(CONF_HAUSNRADDON, ""),
            "ladeort": self.config.get(CONF_LADEORT, ""),
        }
        try:
            async with self.session.post(BASE_URL, data=data, timeout=10) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Error response {resp.status}")
                text = await resp.text()
        except Exception as err:
            raise UpdateFailed(f"Fetch failed: {err}")

        tomorrow = (datetime.today() + timedelta(days=1)).strftime("%d.%m.%Y")
        result = {}
        import re
        for abfallart in ABFALLARTEN:
            try:
                beg = text.index(f'<strong>{abfallart}')
                end = text.index('colspan="3"', beg)
                slice_text = text[beg:end]
                termine = re.findall(r"\w{2}, (\d{2}\.\d{2}\.\d{4})", slice_text)
                if not termine:
                    continue
                next_date = termine[0]
                result[abfallart] = {
                    "next_date": next_date,
                    "is_tomorrow": next_date == tomorrow,
                    "all_dates": termine,
                }
            except ValueError:
                _LOGGER.debug(f"Trash type {abfallart} not found")
        if not result:
            raise UpdateFailed("No trash data parsed")
        return result
