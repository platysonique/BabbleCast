"""opuslib Python bindings (needs libopus.so from libopus recipe)."""

from pythonforandroid.recipe import PythonRecipe


class OpuslibRecipe(PythonRecipe):
    name = "opuslib"
    version = "3.0.1"
    url = "https://files.pythonhosted.org/packages/source/o/opuslib/opuslib-{version}.tar.gz"
    depends = ["libopus", "setuptools"]
    call_hostpython_via_targetpython = False


recipe = OpuslibRecipe()
