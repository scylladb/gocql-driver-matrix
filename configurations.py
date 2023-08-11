from dataclasses import dataclass
from typing import Literal, List, Dict


@dataclass
class TestConfiguration:
    tags: List[str]
    test_command_args: str
    cluster_configuration: Dict[str, str]


integration_tests = TestConfiguration(tags=["integration"], test_command_args='-timeout=1m -race -tags="integration"', cluster_configuration={})
database_tests = TestConfiguration(tags=["scylla", "cassandra"], test_command_args='-timeout=1m -race -tags="scylla cassandra"', cluster_configuration={})
ccm_tests = TestConfiguration(tags=["ccm"], test_command_args='-timeout=1m -race -tags="ccm"', cluster_configuration={})

test_config_map = {
    "integration": integration_tests,
    "database": database_tests,
    "ccm": ccm_tests,
}