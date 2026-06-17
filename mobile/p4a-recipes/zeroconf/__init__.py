"""Newer zeroconf (p4a default 0.24.5 is too old for our discovery API)."""

from pythonforandroid.recipe import PythonRecipe


class ZeroconfRecipe(PythonRecipe):
    name = "zeroconf"
    version = "0.132.2"
    url = "https://files.pythonhosted.org/packages/source/z/zeroconf/zeroconf-{version}.tar.gz"
    depends = ["setuptools", "ifaddr"]
    call_hostpython_via_targetpython = False


recipe = ZeroconfRecipe()
