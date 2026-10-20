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

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.services.schedule import ActionsSchedule, EveryHoursSchedule, ItemSchedule

VALID_ACTIONS = {"C", "S", "P", "T", "R", "C/P"}


class BikeModelError(Exception):
    """Raised when a bike model YAML file fails to parse or validate."""


@dataclass(frozen=True)
class Item:
    key: str
    category: str
    name: str
    schedule: ItemSchedule


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
        return EveryHoursSchedule(every_hours=every_hours, action=action)

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


def load_bike_model(path: Path) -> BikeModel:
    """Parse and validate a single bike model YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise BikeModelError(f"failed to parse {path}: {e}") from e

    items = _build_items(data.get("items", []), path)
    suspension = _build_suspension(data.get("suspension", {}), path)

    return BikeModel(
        key=_require(data, "key", path),
        display_name=_require(data, "display_name", path),
        engine=_require(data, "engine", path),
        items=items,
        notes=data.get("notes", []),
        suspension=suspension,
    )


def load_bike_models(directory: Path) -> dict[str, BikeModel]:
    """Load all bike model YAML files in `directory`, keyed by `BikeModel.key`.

    Raises `BikeModelError` if two files declare the same model key.
    """
    models: dict[str, BikeModel] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        model = load_bike_model(path)
        if model.key in models:
            raise BikeModelError(
                f"duplicate bike model key '{model.key}' in {path}"
            )
        models[model.key] = model
    return models
