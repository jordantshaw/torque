"""Bike model YAML loader and validation.

A "bike model" is a motorcycle's maintenance manual transcribed into YAML:
its maintenance items (each with a schedule), free-text notes, and its
suspension settings table. This module is the authoring contract every
such YAML file must follow -- it parses the file into a `BikeModel` and
rejects anything that doesn't fit, with error messages that name the
offending item key and source file so a human hand-transcribing a manual
can find and fix the mistake.

Item schedules are built as `ActionsSchedule`/`EveryHoursSchedule` from
`app.services.schedule`, reused as-is rather than redefined here.
"""

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from app.services.units import MODEL_UNITS
from app.services.schedule import ActionsSchedule, EveryHoursSchedule, ItemSchedule

VALID_ACTIONS = {"C", "S", "P", "T", "R", "C/P", "C/S", "C/R"}

# A model's schedule is written in one unit, and "upcoming" means due within
# this many of them. Defaults per unit; a model file may override.
DEFAULT_UPCOMING_WINDOW = {"hours": 5, "km": 50}


class BikeModelError(Exception):
    """Raised when a bike model YAML file fails to parse or validate."""


@dataclass(frozen=True)
class Item:
    key: str
    category: str
    name: str
    schedule: ItemSchedule
    description: str = ""
    page: str = ""
    schedule_page: str = ""


@dataclass(frozen=True)
class SuspensionSetting:
    name: str
    factory: str
    racing: str
    comfort: str
    soft: str


@dataclass(frozen=True)
class Suspension:
    settings: list[SuspensionSetting]
    fixed_values: dict[str, str]
    source: str


@dataclass(frozen=True)
class BikeModel:
    key: str
    display_name: str
    engine: str
    items: list[Item]
    notes: list[str]
    suspension: Suspension
    unit: str = "hours"
    upcoming_window: float = 5


def _require(data: dict, field: str, path: Path, context: str | None = None) -> object:
    """Return `data[field]`, raising `BikeModelError` naming the missing
    field (and `context`, if given) and the source file.

    Used in place of plain dict indexing for every required field, so a
    typo'd or omitted field in a hand-transcribed manual produces a
    `BikeModelError` pointing at the exact problem rather than a raw
    `KeyError`.
    """
    if field not in data:
        where = f"{context} in {path}" if context else str(path)
        raise BikeModelError(f"{where}: missing required field '{field}'")
    return data[field]


def _build_schedule(item_data: dict, item_key: str, path: Path) -> ItemSchedule:
    has_every_hours = "every_hours" in item_data
    has_actions = "actions" in item_data

    if has_every_hours and has_actions:
        raise BikeModelError(
            f"item '{item_key}' in {path}: has both 'every_hours' and 'actions'; "
            "it must have exactly one"
        )
    if not has_every_hours and not has_actions:
        raise BikeModelError(
            f"item '{item_key}' in {path}: has neither 'every_hours' nor 'actions'; "
            "it must have exactly one"
        )

    if has_every_hours:
        every_hours = item_data["every_hours"]
        action = item_data.get("action")
        if not isinstance(every_hours, int) or every_hours <= 0:
            raise BikeModelError(
                f"item '{item_key}' in {path}: 'every_hours' must be a positive "
                f"integer, got {every_hours!r}"
            )
        if action not in VALID_ACTIONS:
            raise BikeModelError(
                f"item '{item_key}' in {path}: 'action' {action!r} is not a "
                f"valid action; expected one of {sorted(VALID_ACTIONS)}"
            )
        once_at = item_data.get("once_at", [])
        if (
            not isinstance(once_at, list)
            or any(isinstance(h, bool) or not isinstance(h, int) or h <= 0 for h in once_at)
            or once_at != sorted(set(once_at))
        ):
            raise BikeModelError(
                f"item '{item_key}' in {path}: 'once_at' must be an increasing list "
                f"of positive integers, got {once_at!r}"
            )
        return EveryHoursSchedule(
            every_hours=every_hours, action=action, once_at=tuple(once_at)
        )
    if "once_at" in item_data:
        raise BikeModelError(
            f"item '{item_key}' in {path}: 'once_at' only applies with 'every_hours'"
        )

    actions_data = item_data["actions"]
    actions: dict[int, str] = {}
    for hour, action in actions_data.items():
        if not isinstance(hour, int) or hour <= 0:
            raise BikeModelError(
                f"item '{item_key}' in {path}: action hour {hour!r} must be a "
                "positive integer"
            )
        if action not in VALID_ACTIONS:
            raise BikeModelError(
                f"item '{item_key}' in {path}: action {action!r} at hour {hour} "
                f"is not a valid action; expected one of {sorted(VALID_ACTIONS)}"
            )
        actions[int(hour)] = action
    return ActionsSchedule(actions=actions)


def _build_items(items_data: list[dict], path: Path) -> list[Item]:
    items: list[Item] = []
    seen_keys: set[str] = set()
    for index, item_data in enumerate(items_data):
        item_key = _require(item_data, "key", path, context=f"item at index {index}")
        if item_key in seen_keys:
            raise BikeModelError(
                f"duplicate item key '{item_key}' in {path}"
            )
        seen_keys.add(item_key)

        item_context = f"item '{item_key}'"
        category = _require(item_data, "category", path, context=item_context)
        name = _require(item_data, "name", path, context=item_context)

        schedule = _build_schedule(item_data, item_key, path)
        items.append(
            Item(
                key=item_key,
                category=category,
                name=name,
                schedule=schedule,
                description=str(item_data.get("description", "") or ""),
                page=str(item_data.get("page", "") or ""),
                schedule_page=str(item_data.get("schedule_page", "") or ""),
            )
        )
    return items


def _build_suspension(suspension_data: dict, path: Path) -> Suspension:
    settings = []
    for index, setting in enumerate(suspension_data.get("settings", [])):
        setting_context = f"suspension setting at index {index}"
        settings.append(
            SuspensionSetting(
                name=_require(setting, "name", path, context=setting_context),
                factory=_require(setting, "factory", path, context=setting_context),
                racing=_require(setting, "racing", path, context=setting_context),
                comfort=_require(setting, "comfort", path, context=setting_context),
                soft=_require(setting, "soft", path, context=setting_context),
            )
        )
    return Suspension(
        settings=settings,
        fixed_values=suspension_data.get("fixed_values", {}),
        source=suspension_data.get("source", ""),
    )


def _read_yaml(path: Path) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise BikeModelError(f"failed to parse {path}: {e}") from e


def _build_base_model(data: dict, path: Path) -> BikeModel:
    items = _build_items(data.get("items", []), path)
    suspension = _build_suspension(data.get("suspension", {}), path)

    unit = data.get("unit", "hours")
    if unit not in MODEL_UNITS:
        raise BikeModelError(
            f"{path}: 'unit' {unit!r} is not valid; expected one of {list(MODEL_UNITS)}"
        )
    window = data.get("upcoming_window", DEFAULT_UPCOMING_WINDOW[unit])
    if isinstance(window, bool) or not isinstance(window, (int, float)) or window <= 0:
        raise BikeModelError(
            f"{path}: 'upcoming_window' must be a positive number, got {window!r}"
        )

    return BikeModel(
        unit=unit,
        upcoming_window=window,
        key=_require(data, "key", path),
        display_name=_require(data, "display_name", path),
        engine=_require(data, "engine", path),
        items=items,
        notes=data.get("notes", []),
        suspension=suspension,
    )


def _build_variant(variant: dict, base: BikeModel, path: Path) -> BikeModel:
    """A closely related bike that shares the base model's items, notes and
    unit. It may `omit` items it doesn't have, `overrides` the schedule of
    items that differ (a full replacement schedule per item), and replace the
    `suspension` block; anything it doesn't mention is inherited."""
    key = _require(variant, "key", path, context="variant")
    context = f"variant '{key}'"
    item_keys = {item.key for item in base.items}

    omit = set(variant.get("omit", []))
    overrides = variant.get("overrides", {})
    for ref in (*omit, *overrides):
        if ref not in item_keys:
            raise BikeModelError(f"{context} in {path}: refers to unknown item '{ref}'")

    items = []
    for item in base.items:
        if item.key in omit:
            continue
        if item.key in overrides:
            schedule = _build_schedule(overrides[item.key], item.key, path)
            item = replace(item, schedule=schedule)
        items.append(item)

    suspension = base.suspension
    if "suspension" in variant:
        suspension = _build_suspension(variant["suspension"] or {}, path)

    return replace(
        base,
        key=key,
        display_name=_require(variant, "display_name", path, context=context),
        engine=_require(variant, "engine", path, context=context),
        items=items,
        suspension=suspension,
    )


def load_bike_model_file(path: Path) -> list[BikeModel]:
    """Parse and validate one model file: its base bike followed by each of
    its `variants`."""
    data = _read_yaml(path)
    base = _build_base_model(data, path)
    return [base, *(_build_variant(v, base, path) for v in data.get("variants", []))]


def load_bike_model(path: Path) -> BikeModel:
    """Parse and validate a single bike model YAML file (its base bike)."""
    return load_bike_model_file(path)[0]


def load_bike_models(directory: Path) -> dict[str, BikeModel]:
    """Load all bike model YAML files in `directory`, keyed by `BikeModel.key`.

    Raises `BikeModelError` if two files declare the same model key.
    """
    models: dict[str, BikeModel] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        for model in load_bike_model_file(path):
            if model.key in models:
                raise BikeModelError(
                    f"duplicate bike model key '{model.key}' in {path}"
                )
            models[model.key] = model
    return models
