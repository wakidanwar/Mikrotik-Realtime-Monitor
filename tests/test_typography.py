"""The whole application shares one monospace type stack."""

import app.ui as ui


def test_monospace_is_the_application_default():
    assert ui.FONT_UI == ui.FONT_MONO
    assert "monospace" in ui.FONT_UI
    assert "font-family: " + ui.FONT_UI in ui.QSS
