"""Include the reviewed rule and holiday files in wheels without duplicating sources."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithData(build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        target = Path(self.build_lib) / "sg_deadline" / "_data"
        self.copy_tree(str(root / "rules"), str(target / "rules"))
        self.copy_tree(str(root / "data" / "holidays"), str(target / "holidays"))


setup(cmdclass={"build_py": BuildWithData})
