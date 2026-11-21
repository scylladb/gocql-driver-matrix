import logging
import os
import re
import subprocess
import json
import time
from functools import cached_property
from pathlib import Path
from typing import Dict, List

import yaml
from packaging.version import Version, InvalidVersion

from cluster import TestCluster
from configurations import test_config_map, TestConfiguration
from processjunit import ProcessJUnit

# gocql v2 (module github.com/scylladb/gocql/v2) has its integration suite in this
# package, built for ScyllaDB on native protocol 4 (it refuses any other -proto).
V2_INTEGRATION_PACKAGE = "./tests/integration"
V2_PROTOCOLS = (4,)


class Run:
    def __init__(self, gocql_driver_git, driver_type, tag, tests, scylla_version, protocol, checkout_ref=None):
        self.driver_version = tag
        self._full_driver_version = tag
        self._gocql_driver_git = Path(gocql_driver_git)
        self._scylla_version = scylla_version
        self._protocol = int(protocol)
        self._driver_type = driver_type
        self._cversion = "3.11.4"
        self._test_tags = tests
        self._checkout_ref = checkout_ref

    @cached_property
    def version_folder(self) -> Path:
        target_version_folder = Path(os.path.dirname(__file__)) / "versions" / self._driver_type
        try:
            target_version = Version(self.driver_version)
        except InvalidVersion:
            target_dir = target_version_folder / self.driver_version
            if target_dir.is_dir():
                return target_dir
            return target_version_folder / "master"

        # A folder is named after a release ("1.19.0") or a pre-release ("2.0.0-rc.1").
        # Patches and ignore lists never carry over to another major version:
        # each major version is its own Go module.
        folders_defined = []
        for folder_path in target_version_folder.iterdir():
            try:
                folder_version = Version(folder_path.name)
            except InvalidVersion:
                continue
            if folder_version.major == target_version.major:
                folders_defined.append((folder_version, folder_path))
        folders_defined.sort(reverse=True)
        for tag, folder_path in folders_defined:
            if tag <= target_version:
                return folder_path
        else:
            raise ValueError("Not found directory for gocql-driver version '%s'", self.driver_version)

    @cached_property
    def xunit_dir(self) -> Path:
        return Path(os.path.dirname(__file__)) / "xunit" / self.driver_version
    @property
    def xunit_file_name(self) -> str:
        return f'xunit.{self._driver_type}.v{self._protocol}.{self.driver_version}.xml'
    @property
    def metadata_file_name(self) -> str:
        return f'metadata_{self._driver_type}_v{self._protocol}_{self.driver_version}.json'

    @cached_property
    def ignore_tests(self) -> Dict[str, List[str]]:
        ignore_file = self.version_folder / "ignore.yaml"
        if not ignore_file.exists():
            logging.info("Cannot find ignore file for version '%s'", self.driver_version)
            return {}

        with ignore_file.open(mode="r", encoding="utf-8") as file:
            content = yaml.safe_load(file)
        ignore_tests = content.get("tests" if self._protocol == 3 else f"v{self._protocol}_tests", []) or {'ignore': None, 'flaky': None, 'skip': None}
        if not ignore_tests.get("ignore", None):
            logging.info("The file '%s' for version tag '%s' doesn't contain any test to ignore for protocol"
                         " '%d'", ignore_file, self.driver_version, self._protocol)
        return ignore_tests

    @cached_property
    def xunit_file(self) -> Path:
        if not self.xunit_dir.exists():
            self.xunit_dir.mkdir(parents=True)

        file_path = self.xunit_dir / self.xunit_file_name
        for parts in self.xunit_dir.glob(f"{self.xunit_file_name}*"):
            parts.unlink()
        return file_path

    @cached_property
    def environment(self) -> Dict:
        result = {}
        result.update(os.environ)
        result["PROTOCOL_VERSION"] = str(self._protocol)
        result["SCYLLA_VERSION"] = self._scylla_version
        return result

    def _gocql_cversion(self) -> str:
        if not self._scylla_version:
            return self._cversion
        return self._scylla_version.split("~", maxsplit=1)[0].removeprefix("release:")

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
        self._run_command_in_shell("git checkout .")
        logging.info("git checkout to '%s'", self._ref)
        subprocess.run(["git", "checkout", "--detach", self._ref], cwd=self._gocql_driver_git,
                       env=self.environment, check=True, capture_output=True)
        return True

    def create_metadata_for_failure(self, reason: str) -> None:
        metadata_file = self.xunit_dir / self.metadata_file_name
        if not self.xunit_dir.exists():
            self.xunit_dir.mkdir(exist_ok=True, parents=True)
        metadata = {
            "driver_name": self.xunit_file_name.replace(".xml", ""),
            "driver_type": "gocql",
            "failure_reason": reason,
        }
        metadata_file.write_text(json.dumps(metadata))

    def run(self) -> ProcessJUnit:
        metadata_file = self.xunit_dir / self.metadata_file_name
        metadata = {
            "driver_name": self.xunit_file_name.replace(".xml", ""),
            "driver_type": "gocql",
            "junit_result": f"./{self.xunit_file.name}",
        }
        junit = ProcessJUnit(self.xunit_file, self.ignore_tests)
        logging.info("Changing the current working directory to the '%s' path", self._gocql_driver_git)
        os.chdir(self._gocql_driver_git)
        if self._checkout_branch() and self._apply_patch_files():
            driver_module = self._get_driver_module()
            # go-junit-report names a test suite after its package.
            test_suite = driver_module
            if self.is_scylla_v2:
                test_suite = f"{driver_module}/{V2_INTEGRATION_PACKAGE.removeprefix('./')}"
            for idx, test in enumerate(self._test_tags):
                test_config: TestConfiguration = test_config_map[test]
                skip_tests = f'-skip "{"|".join(self.ignore_tests["skip"]) if self.ignore_tests.get("skip") else ""}"'
                with TestCluster(self._gocql_driver_git, self._scylla_version, configuration=test_config.cluster_configuration) as cluster:
                    cluster_params = cluster.start()
                    if test_config.startup_delay_seconds:
                        logging.info(
                            "Waiting %d seconds before running tests for tag '%s'",
                            test_config.startup_delay_seconds,
                            test,
                        )
                        time.sleep(test_config.startup_delay_seconds)
                    if test == 'ccm':
                        # CCM-tagged Go tests manage the cluster lifecycle themselves via ccm start/stop.
                        # Stop the cluster so the Go test's ccm.StartAll() can start it successfully.
                        cluster.stop()
                        # Tell the ccm CLI where to find the cluster that Python created.
                        # Python ccmlib creates the cluster in driver_directory/ccm, but the ccm CLI
                        # defaults to ~/.ccm/. Setting CCM_CONFIG_DIR aligns them.
                        self.environment['CCM_CONFIG_DIR'] = str(self._gocql_driver_git / 'ccm')
                        # pip installs ccm to ${HOME}/.local/bin which may not be on PATH.
                        # Ensure the Go test subprocess can find the ccm binary.
                        home = os.path.expanduser('~')
                        local_bin = os.path.join(home, '.local', 'bin')
                        current_path = self.environment.get('PATH', os.environ.get('PATH', ''))
                        if local_bin not in current_path.split(os.pathsep):
                            self.environment['PATH'] = local_bin + os.pathsep + current_path
                    logging.info("Run tests for tag '%s'", test)
                    cversion = self._gocql_cversion()
                    args = f"-gocql.timeout=60s -proto={self._protocol} -autowait=2000ms -compressor=snappy -gocql.cversion={cversion}"
                    if self._driver_type == 'scylla' and Version(self.driver_version.lstrip('v')) >= Version('1.16.1'):
                        args += " -distribution=scylla"
                    if self.is_scylla_v2:
                        # gocql v2 keeps its integration suite in one package; the
                        # suite's flags are undefined in every other test binary.
                        # The package goes first: go test hands everything after
                        # the first flag it does not know (-runauth, -rf, ...) to
                        # the test binary and tests the current directory instead.
                        test_command_args = test_config.v2_test_command_args or test_config.test_command_args
                        go_test_cmd = (f'go test -v {V2_INTEGRATION_PACKAGE} {test_command_args} {skip_tests} '
                                       f'{cluster_params} {args}')
                    else:
                        go_test_cmd = f'go test -v {test_config.test_command_args} {cluster_params} {skip_tests} {args} ./...'
                    go_test_cmd += f'  2>&1 | go-junit-report -iocopy -out {self.xunit_file}_part_{idx}'
                    logging.info("Running the command '%s'", go_test_cmd)
                    subprocess.call(f"{go_test_cmd}", shell=True, executable="/bin/bash",
                                    env=self.environment, cwd=self._gocql_driver_git)
            junit.save_after_analysis(driver_version=self.driver_version, protocol=self._protocol,
                                      gocql_driver_type=self._driver_type, driver_module=test_suite)
            metadata_file.write_text(json.dumps(metadata))
        return junit
   
    
    @property
    def _ref(self) -> str:
        return self._checkout_ref or f"tags/{self._full_driver_version}"

    @cached_property
    def is_scylla_v2(self) -> bool:
        """
        Whether the ref to test is the Scylla driver's v2 module (github.com/scylladb/gocql/v2).

        Read from the ref's go.mod without checking it out, so that main.py can
        skip the protocols v2 does not run before the checkout.
        """
        if self._driver_type != "scylla":
            return False
        try:
            go_mod = subprocess.run(["git", "show", f"{self._ref}:go.mod"], cwd=self._gocql_driver_git,
                                    check=True, capture_output=True, text=True).stdout
        except subprocess.CalledProcessError:
            return False
        module = next((line[len("module "):].strip() for line in go_mod.splitlines()
                       if line.startswith("module ")), "")
        return module.endswith("/v2")

    def supports_protocol(self) -> bool:
        """gocql v2's integration suite runs against Scylla on native protocol 4 only."""
        return not self.is_scylla_v2 or self._protocol in V2_PROTOCOLS

    def _get_driver_module(self):
        """
        Extract the module name from the go.mod file in the gocql driver repository.
        
        :return: The module name as a string.
        """
        DEFAULT_GOCQL_MODULE = "github.com/gocql/gocql"
        go_mod_file = os.path.join(self._gocql_driver_git, "go.mod")
        if not os.path.isfile(go_mod_file):
            logging.error(f"go.mod file not found in the driver directory ({self._gocql_driver_git}), defaulting module name to '{DEFAULT_GOCQL_MODULE}'")
            return DEFAULT_GOCQL_MODULE
        with open(go_mod_file, "r") as f:
            for line in f:
                if line.startswith("module "):
                    module = line[7:].strip()
                    logging.info(f"Found module name in go.mod: {module}")
                    return module
        logging.error(f"Module name not found in go.mod file, defaulting module name to '{DEFAULT_GOCQL_MODULE}'")
        return DEFAULT_GOCQL_MODULE
