import logging
import os
import re
import shutil
import subprocess
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Dict, List

import yaml
from packaging.version import Version, InvalidVersion

from cluster import TestCluster
from processjunit import ProcessJUnit


class Run:
    def __init__(self, gocql_driver_git, driver_type, scylla_install_dir, tag, tests, scylla_version, protocol):
        self.driver_version = tag
        self._full_driver_version = tag
        self._gocql_driver_git = Path(gocql_driver_git)
        self._scylla_version = scylla_version
        self._scylla_install_dir = scylla_install_dir
        self._protocol = int(protocol)
        self._driver_type = driver_type
        self._cversion = "3.11.4"
        self._test_tags = tests

    @cached_property
    def version_folder(self) -> Path:
        version_pattern = re.compile(r"([\d]+.[\d]+.[\d]+)$")
        target_version_folder = Path(os.path.dirname(__file__)) / "versions" / self._driver_type
        try:
            target_version = Version(self.driver_version)
        except InvalidVersion:
            target_dir = target_version_folder / self.driver_version
            if target_dir.is_dir():
                return target_dir
            return target_version_folder / "master"

        tags_defined = sorted(
            (
                Version(folder_path.name)
                for folder_path in target_version_folder.iterdir() if version_pattern.match(folder_path.name)
            ),
            reverse=True
        )
        for tag in tags_defined:
            if tag <= target_version:
                return target_version_folder / str(tag)
        else:
            raise ValueError("Not found directory for python-driver version '%s'", self.driver_version)

    @cached_property
    def ignore_tests(self) -> Dict[str, List[str]]:
        ignore_file = self.version_folder / "ignore.yaml"
        print(ignore_file)
        if not ignore_file.exists():
            logging.info("Cannot find ignore file for version '%s'", self.driver_version)
            return {}

        with ignore_file.open(mode="r", encoding="utf-8") as file:
            content = yaml.safe_load(file)
        ignore_tests = content.get("tests" if self._protocol == 3 else f"v{self._protocol}_tests", []) or {'ignore': None, 'flaky': None}
        if not ignore_tests.get("ignore", None):
            logging.info("The file '%s' for version tag '%s' doesn't contain any test to ignore for protocol"
                         " '%d'", ignore_file, self.driver_version, self._protocol)
        return ignore_tests

    @cached_property
    def xunit_file(self) -> Path:
        xunit_dir = Path(os.path.dirname(__file__)) / "xunit" / self.driver_version
        if not xunit_dir.exists():
            xunit_dir.mkdir(parents=True)

        file_path = xunit_dir / f'pytest.{self._driver_type}.v{self._protocol}.{self.driver_version}.xml'
        if file_path.exists():
            file_path.unlink()
        return file_path

    @cached_property
    def environment(self) -> Dict:
        result = {}
        result.update(os.environ)
        result["PROTOCOL_VERSION"] = str(self._protocol)
        result["SCYLLA_VERSION"] = self._scylla_version
        return result

    def _run_command_in_shell(self, cmd: str):
        logging.debug("Execute the cmd '%s'", cmd)
        with subprocess.Popen(cmd, shell=True, executable="/bin/bash", env=self.environment,
                              cwd=self._gocql_driver_git, stderr=subprocess.PIPE) as proc:
            stderr = proc.communicate()
            status_code = proc.returncode
        assert status_code == 0, stderr

    def _apply_patch_files(self) -> bool:
        for file_path in self.version_folder.iterdir():
            if file_path.name.startswith("patch"):
                try:
                    logging.info("Show patch's statistics for file '%s'", file_path)
                    self._run_command_in_shell(f"git apply --stat {file_path}")
                    logging.info("Detect patch's errors for file '%s'", file_path)
                    try:
                        self._run_command_in_shell(f"git apply --check {file_path}")
                    except AssertionError as exc:
                        if 'tests/integration/conftest.py' in str(exc):
                            self._run_command_in_shell(f"rm tests/integration/conftest.py")
                        else:
                            raise
                    logging.info("Applying patch file '%s'", file_path)
                    self._run_command_in_shell(f"patch -p1 -i {file_path}")
                except Exception:
                    logging.exception("Failed to apply patch '%s' to version '%s'",
                                      file_path, self.driver_version)
                    raise
        return True

    def _checkout_branch(self):
        try:
            self._run_command_in_shell("git checkout .")
            logging.info("git checkout to '%s' tag branch", self._full_driver_version)
            self._run_command_in_shell(f"git checkout tags/{self._full_driver_version}")
            return True
        except Exception as exc:
            logging.error("Failed to branch for version '%s', with: '%s'", self.driver_version, str(exc))
            return False

    def run(self) -> ProcessJUnit:
        junit = ProcessJUnit(self.xunit_file, self.ignore_tests)
        cluster = TestCluster(self._gocql_driver_git, self._scylla_version)
        cluster.start()
        logging.info("Changing the current working directory to the '%s' path", self._gocql_driver_git)
        os.chdir(self._gocql_driver_git)
        if self._checkout_branch() and self._apply_patch_files():
            args = f"-gocql.timeout=60s -proto={self._protocol} -rf=1 -clusterSize=1 -autowait=2000ms -compressor=snappy -gocql.cversion={self._cversion} -cluster={cluster.ip_addresses}"
            go_test_cmd = f'go test -v -timeout=1m -race -tags="{self._test_tags}" {args} ./...  2>&1 | go-junit-report -iocopy -out {self.xunit_file}'

            print("Running the command '%s'", go_test_cmd)

            subprocess.call(f"{go_test_cmd}", shell=True, executable="/bin/bash",
                            env=self.environment, cwd=self._gocql_driver_git)
            cluster.remove()
            junit.save_after_analysis(driver_version=self.driver_version, protocol=self._protocol,
                                      python_driver_type=self._driver_type)
        return junit

