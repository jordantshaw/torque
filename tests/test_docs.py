"""Keep the docs honest.

- The guide's worked example must be a valid model.
- Every relative link, and every `#anchor`, must point somewhere real.
- Each doc's "Contents" must list exactly its sections.
- The code files and names the guides tell people to touch must still exist.
"""

import re
from pathlib import Path

import pytest

from app.bike_models import load_bike_model_file

ROOT = Path(__file__).parent.parent
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
GUIDE = ROOT / "docs" / "adding-a-bike-model.md"


def _without_code(text: str) -> str:
    """The text with fenced code blocks removed (their `#` lines aren't headings)."""
    return re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)


def _slug(heading: str) -> str:
    """The anchor GitHub makes for a heading."""
    heading = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", heading))


def _headings(doc: Path, level: int) -> list[str]:
    return re.findall(rf"^{'#' * level} (.+)$", _without_code(doc.read_text()), flags=re.M)


def _anchors(doc: Path) -> set[str]:
    return {_slug(h) for level in (1, 2, 3) for h in _headings(doc, level)}


def test_the_guides_worked_example_loads_and_is_fully_described(tmp_path):
    examples = [
        block
        for block in re.findall(r"```yaml\n(.*?)```", GUIDE.read_text(), flags=re.S)
        if block.startswith("# example: valid")
    ]
    assert examples, "the guide should contain a '# example: valid' YAML block"
    for n, example in enumerate(examples):
        path = tmp_path / f"example{n}.yaml"
        path.write_text(example)
        models = load_bike_model_file(path)
        assert len(models) >= 2  # the example shows a variant too
        for model in models:
            for item in model.items:
                assert item.description and item.schedule_page, f"{model.key}/{item.key}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_links_and_anchors_resolve(doc):
    text = _without_code(doc.read_text())
    for target, anchor in re.findall(r"\]\(([^)#\s]*)(?:#([^)\s]*))?\)", text):
        if re.match(r"[a-z]+:", target):  # http:, mailto:, ...
            continue
        linked = doc if not target else doc.parent / target
        assert linked.exists(), f"{doc.name} links to missing {target}"
        if anchor:
            assert anchor in _anchors(linked), f"{doc.name} links to missing anchor {target}#{anchor}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_contents_lists_exactly_the_sections(doc):
    text = _without_code(doc.read_text())
    contents = re.search(r"^## Contents\n(.*?)(?=^## )", text, flags=re.S | re.M)
    assert contents, f"{doc.name} needs a '## Contents' section"
    listed = re.findall(r"\(#([^)]+)\)", contents.group(1))
    sections = [_slug(h) for h in _headings(doc, 2) if h != "Contents"]
    assert listed == sections, f"{doc.name}: contents and sections differ"


# Things the guides tell people to open or edit.
REFERENCED = {
    "app/bike_models.py": ["VALID_ACTIONS"],
    "app/routes/bikes.py": ["ACTION_LABELS"],
    "app/routes/rides.py": ["SUSPENSION_FIELD_BY_SETTING_NAME"],
    "app/templates/_icons.html": ["category_icon"],
    "bike_models/beta-300-rr-race-2026.yaml": ["variants", "&small_bore_schedule"],
    "bike_models/ktm-300-xcw-2017.yaml": ["once_at"],
    "bike_models/surron-ultra-bee-2026.yaml": ["unit: km"],
    "tests/test_ultra_bee_model.py": [],
    "tests/test_ktm_model.py": [],
    "tests/test_model_descriptions.py": [],
    "tests/test_bike_models.py": [],
    "docker-compose.yml": ["./data:/data"],
}


@pytest.mark.parametrize("path", REFERENCED)
def test_files_and_names_the_docs_mention_exist(path):
    file = ROOT / path
    assert file.exists(), f"docs mention {path}"
    text = file.read_text()
    for name in REFERENCED[path]:
        assert name in text, f"docs mention {name} in {path}"
    mentioned = "".join(d.read_text() for d in DOCS)
    assert Path(path).name in mentioned, f"{path} is no longer mentioned in the docs"
