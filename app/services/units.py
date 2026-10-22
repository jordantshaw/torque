"""Measurement units for a bike's schedule and odometer.

A bike model declares the unit its manual uses (`hours` for engine-hour
schedules, `km` for distance-based ones). Every stored value (current
reading, ride lengths, service points) is kept in that native unit. A
distance bike also has a display preference (km or mi); `Unit` converts
between stored and displayed values so the rest of the app never has to.
"""

from dataclasses import dataclass

KM_PER_MILE = 1.609344


def _trim(value: float, decimals: int) -> str:
    """Fixed-point text with trailing zeros dropped ("7.0" -> "7"), never in
    exponent form."""
    text = f"{round(value, decimals) + 0.0:.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class Unit:
    key: str  # "hours", "km" or "mi"
    factor: float  # displayed value = stored value * factor
    suffix: str  # appended to a displayed value: "h", " km", " mi"
    short: str  # compact label: "hrs", "km", "mi"
    reading: str  # name of the bike's running total
    ride_label: str  # label for a ride's length field
    meter_label: str  # caption under the big number in the page header
    decimals: int = 1  # precision shown; trailing zeros are dropped

    def show(self, stored) -> str:
        """Format a stored value for display in this unit."""
        if stored is None:
            return ""
        return _trim(stored * self.factor, self.decimals)

    def edit_value(self, stored) -> str:
        """The value to prefill an input with. It keeps more precision than
        `show`, so saving an untouched field doesn't nudge the stored value
        (100 km shown as 62.1 mi would otherwise save back as 99.94 km)."""
        if stored is None:
            return ""
        return _trim(stored * self.factor, 4)

    def to_stored(self, displayed: float) -> float:
        """Convert a value the user typed in this unit to the stored unit."""
        return displayed / self.factor

    def service_label(self, point) -> str:
        if self.key == "hours":
            return f"{self.show(point)}-hour service"
        return f"{self.show(point)}{self.suffix} service"


HOURS = Unit("hours", 1.0, "h", "hrs", "Engine hours", "Hours", "engine hours", decimals=2)
KM = Unit("km", 1.0, " km", "km", "Odometer", "Distance", "kilometres")
MILES = Unit("mi", 1 / KM_PER_MILE, " mi", "mi", "Odometer", "Distance", "miles")

MODEL_UNITS = ("hours", "km")
DISPLAY_PREFERENCES = ("km", "mi")


def unit_for(model_unit: str, preference: str | None) -> Unit:
    """The unit to show for a bike: hours bikes always use hours; distance
    bikes use the owner's km/mi preference (km if unset)."""
    if model_unit == "hours":
        return HOURS
    return MILES if preference == "mi" else KM
