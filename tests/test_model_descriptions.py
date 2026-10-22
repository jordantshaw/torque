"""Every shipped bike model explains each of its items, so no row in the
maintenance list is left as an unexplained one-liner."""

from pathlib import Path

import pytest

from app.bike_models import load_bike_model_file

MODELS = sorted((Path(__file__).parent.parent / "bike_models").glob("*.yaml"))


@pytest.mark.parametrize("path", MODELS, ids=lambda p: p.stem)
def test_every_item_has_a_description(path):
    for model in load_bike_model_file(path):  # the base bike and each variant
        missing = [i.name for i in model.items if not i.description.strip()]
        assert not missing, f"{model.key}: items without a description: {missing}"
        unpaged = [i.name for i in model.items if not i.schedule_page.strip()]
        assert not unpaged, f"{model.key}: items without a schedule page: {unpaged}"
