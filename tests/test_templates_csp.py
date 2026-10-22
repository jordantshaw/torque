"""The Content-Security-Policy forbids inline scripts and styles, so no template
may rely on them. These guards keep it that way, and keep unsafe escaping out."""

import re
from pathlib import Path

import pytest

TEMPLATES = sorted((Path(__file__).parent.parent / "app" / "templates").glob("*.html"))
STATIC = Path(__file__).parent.parent / "app" / "static"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_have_no_inline_script_handler_or_style(template):
    text = template.read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)", text), "inline <script>"
    assert not re.search(r"\son[a-z]+\s*=", text, flags=re.I), "inline event handler"
    assert not re.search(r"\sstyle\s*=", text, flags=re.I), "inline style attribute"
    assert not re.search(r"<style", text, flags=re.I), "inline <style>"
    assert "javascript:" not in text.lower()


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_never_turn_off_escaping(template):
    text = template.read_text()
    assert "|safe" not in text and "| safe" not in text
    assert "autoescape" not in text and "Markup" not in text


def test_pages_load_their_scripts_from_static_only(client, db_session):
    from app.models import Bike

    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    for path in ("/", f"/bikes/{bike.id}", f"/bikes/{bike.id}/rides", f"/bikes/{bike.id}/edit"):
        scripts = re.findall(r"<script[^>]*>", client.get(path).text)
        assert scripts, path
        assert all('src="/static/' in tag for tag in scripts), (path, scripts)


def test_the_garage_script_is_only_on_the_garage(client, db_session):
    from app.models import Bike

    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    assert "/static/garage.js" in client.get("/").text
    assert "/static/garage.js" not in client.get(f"/bikes/{bike.id}").text


def test_static_scripts_exist_and_are_served(client):
    for name in ("htmx.min.js", "app.js", "garage.js"):
        assert (STATIC / name).exists()
        assert client.get(f"/static/{name}").status_code == 200


def test_static_files_cannot_escape_their_folder(client):
    for path in ("/static/../main.py", "/static/..%2fmain.py", "/static/%2e%2e/main.py", "/static//etc/passwd"):
        assert client.get(path).status_code in (400, 404), path
