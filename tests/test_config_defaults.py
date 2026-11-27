"""Defaults must be vendor-neutral, never a copy of a real router's credentials."""

from app.config import ApiConfig, RouterConfig, SnmpConfig


def test_defaults_contain_no_site_specific_credentials():
    assert SnmpConfig().community == "public"

    api = ApiConfig()
    assert api.username == ""
    assert api.password == ""

    router = RouterConfig()
    assert router.name == "MikroTik Router"
    assert router.host == "192.168.88.1"
