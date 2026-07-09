from run import Run


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
