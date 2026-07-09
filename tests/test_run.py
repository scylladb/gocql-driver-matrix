import sys

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
