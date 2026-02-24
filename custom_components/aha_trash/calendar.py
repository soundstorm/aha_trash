"""Calendar platform for AHA Trash Pickup."""
from datetime import date as dt_date, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, ABFALLARTEN, MANUFACTURER


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the calendar platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        AHATrashCalendar(coordinator, abfallart)
        for abfallart in ABFALLARTEN
    ]
    async_add_entities(entities)


class AHATrashCalendar(CalendarEntity):
    """Calendar entity for a single trash type at an address."""

    def __init__(self, coordinator, abfallart):
        """Initialize the calendar."""
        self.coordinator = coordinator
        self.abfallart = abfallart
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{abfallart.lower().replace(' ', '_')}_calendar"
        self._attr_name = abfallart

    @property
    def device_info(self):
        """Return device info to group entities under the address device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _get_dates(self):
        """Parse all stored pickup dates into date objects."""
        data = self.coordinator.data.get(self.abfallart, {})
        dates = []
        for date_str in data.get("all_dates", []):
            try:
                day, month, year = map(int, date_str.split("."))
                dates.append(dt_date(year, month, day))
            except ValueError:
                pass
        return dates

    @property
    def event(self):
        """Return the next upcoming calendar event."""
        today = dt_date.today()
        upcoming = [d for d in self._get_dates() if d >= today]
        if not upcoming:
            return None
        d = upcoming[0]
        return CalendarEvent(start=d, end=d + timedelta(days=1), summary=self.abfallart)

    async def async_get_events(self, hass, start_date, end_date):
        """Return all calendar events in the given time range."""
        start = start_date.date()
        end = end_date.date()
        events = []
        for d in self._get_dates():
            if start <= d < end:
                events.append(CalendarEvent(start=d, end=d + timedelta(days=1), summary=self.abfallart))
        return events

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.abfallart in self.coordinator.data

    async def async_added_to_hass(self):
        """Connect to coordinator."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
