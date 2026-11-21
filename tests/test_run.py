import sys
import subprocess
import pytest

from configurations import test_config_map
from main import get_arguments
from run import Run


def test_default_tests_include_auth(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            ".",
            "--versions",
            "v1.18.3",
            "--protocols",
            "4",
            "--scylla-version",
            "release:2026.2.0",
        ],
    )

    arguments = get_arguments()

    assert arguments.tests == ["integration", "auth"]


def test_candidate_version_does_not_resolve_tags(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", ".", "--checkout-ref", "candidate-sha",
                                  "--driver-version", "1.20.1", "--scylla-version", "release:2026.2.0"])

    arguments = get_arguments()

    assert arguments.versions == ["1.20.1"]
    assert arguments.checkout_ref == "candidate-sha"


def test_untagged_ref_requires_version(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", ".", "--checkout-ref", "candidate-sha",
                                  "--scylla-version", "release:2026.2.0"])

    with pytest.raises(SystemExit) as error:
        get_arguments()
    assert error.value.code == 2


def test_candidate_checkout_uses_ref_and_report_version(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "go.mod").write_text("module example.com/gocql\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "go.mod"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c",
                    "user.email=test@example.com", "commit", "-qm", "Initial"], check=True)
    ref = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    runner = Run(gocql_driver_git=tmp_path, driver_type="scylla", tag="1.20.1",
                 checkout_ref=ref, tests=["integration"], scylla_version="release:2026.2.0", protocol="4")

    assert runner._checkout_branch()
    assert runner.driver_version == "1.20.1"
    assert "1.20.1" in runner.xunit_file_name


def test_auth_configuration_enables_cluster_auth_and_selects_auth_test():
    auth_config = test_config_map["auth"]

    assert auth_config.cluster_configuration == {
        "authenticator": "PasswordAuthenticator",
        "authorizer": "CassandraAuthorizer",
        "auth_superuser_name": "cassandra",
        "auth_superuser_salted_password": "$6$x7IFjiX5VCpvNiFk$2IfjTvSyGL7zerpV.wbY7mJjaRCrJ/68dtT3UpT.sSmNYz1bPjtn3mH.kJKFvaZ2T4SbVeBijjmwGjcb83LlV/",
    }
    assert "-run=TestAuthentication" in auth_config.test_command_args
    assert "-runauth" in auth_config.test_command_args
    assert auth_config.startup_delay_seconds == 30


def test_gocql_cversion_defaults_to_cassandra_version():
    runner = Run(
        gocql_driver_git=".",
        driver_type="scylla",
        tag="v1.18.3",
        tests=["integration"],
        scylla_version=None,
        protocol="4",
    )

    assert runner._gocql_cversion() == "3.11.4"


def test_gocql_cversion_strips_ccm_release_prefix():
    runner = Run(
        gocql_driver_git=".",
        driver_type="scylla",
        tag="v1.18.3",
        tests=["integration"],
        scylla_version="release:2026.2.0",
        protocol="4",
    )

    assert runner._gocql_cversion() == "2026.2.0"


def test_gocql_cversion_strips_build_metadata():
    runner = Run(
        gocql_driver_git=".",
        driver_type="scylla",
        tag="v1.18.3",
        tests=["integration"],
        scylla_version="release:2026.2.0~dev",
        protocol="4",
    )

    assert runner._gocql_cversion() == "2026.2.0"


def _driver_repo(tmp_path, module):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "go.mod").write_text(f"// License header.\n\nmodule {module}\n\ngo 1.25\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "go.mod"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c",
                    "user.email=test@example.com", "commit", "-qm", "Initial"], check=True)
    return subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()


@pytest.mark.parametrize("driver_type, module, protocols", [
    ("scylla", "github.com/scylladb/gocql/v2", {"4": True, "3": False, "5": False}),
    ("scylla", "github.com/scylladb/gocql", {"4": True, "3": True}),
    ("upstream", "github.com/apache/cassandra-gocql-driver/v2", {"4": True, "3": True}),
])
def test_v2_runs_protocol_4_only(tmp_path, driver_type, module, protocols):
    ref = _driver_repo(tmp_path, module)
    for protocol, supported in protocols.items():
        runner = Run(gocql_driver_git=tmp_path, driver_type=driver_type, tag="2.0.0-rc.1", checkout_ref=ref,
                     tests=["integration"], scylla_version="release:2026.1.0", protocol=protocol)
        assert runner.supports_protocol() is supported, (module, protocol)


def test_protocol_check_reads_ref_not_worktree(tmp_path):
    ref = _driver_repo(tmp_path, "github.com/scylladb/gocql/v2")
    (tmp_path / "go.mod").write_text("module github.com/scylladb/gocql\n")
    runner = Run(gocql_driver_git=tmp_path, driver_type="scylla", tag="2.0.0-rc.1", checkout_ref=ref,
                 tests=["integration"], scylla_version="release:2026.1.0", protocol="3")

    assert runner.is_scylla_v2
    assert not runner.supports_protocol()


@pytest.mark.parametrize("version, folder", [
    ("2.0.0-rc.1", "2.0.0-rc.1"),
    ("v2.0.0-rc.1", "2.0.0-rc.1"),
    ("2.0.0", "2.0.0-rc.1"),
    ("1.19.0", "1.19.0"),
    ("1.20.1", "1.19.0"),
])
def test_version_folder_stays_within_major_version(version, folder):
    runner = Run(gocql_driver_git=".", driver_type="scylla", tag=version, tests=["integration"],
                 scylla_version="release:2026.1.0", protocol="4")

    assert runner.version_folder.name == folder


def test_version_folder_does_not_fall_back_to_older_major_version():
    runner = Run(gocql_driver_git=".", driver_type="scylla", tag="3.0.0", tests=["integration"],
                 scylla_version="release:2026.1.0", protocol="4")

    with pytest.raises(ValueError):
        _ = runner.version_folder


def test_v2_auth_configuration_selects_session_authentication_test():
    auth_config = test_config_map["auth"]

    assert "'-run=^TestSession$/^Connect$/^Authentication$'" in auth_config.v2_test_command_args
    assert "-runauth" in auth_config.v2_test_command_args
