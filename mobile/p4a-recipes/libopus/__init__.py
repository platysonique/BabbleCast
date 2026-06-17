"""Build libopus for opuslib on Android."""

from __future__ import annotations

from multiprocessing import cpu_count

import sh

from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class LibopusRecipe(Recipe):
    name = "libopus"
    version = "1.3.1"
    url = "https://downloads.xiph.org/releases/opus/opus-{version}.tar.gz"
    built_libraries = {"libopus.so": ".libs"}

    def build_arch(self, arch):
        env = self.get_recipe_env(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            bash = sh.Command("bash")
            shprint(
                bash,
                "./configure",
                "--host=" + arch.command_prefix,
                "--prefix=" + self.ctx.get_python_install_dir(arch.arch),
                "--enable-shared",
                "--disable-static",
                _env=env,
            )
            shprint(sh.make, "-j", str(cpu_count()), _env=env)


recipe = LibopusRecipe()
