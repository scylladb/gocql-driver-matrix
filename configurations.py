from dataclasses import dataclass
from typing import Any, List, Dict


@dataclass
class TestConfiguration:
    tags: List[str]
    test_command_args: str
    cluster_configuration: Dict[str, Any]
    startup_delay_seconds: int = 0


integration_tests = TestConfiguration(tags=["integration"], test_command_args='-timeout=10m -race -tags="integration"', cluster_configuration={})
auth_tests = TestConfiguration(
    tags=["integration"],
    test_command_args='-timeout=5m -tags="integration" -run=TestAuthentication -runauth',
    cluster_configuration={
        "authenticator": "PasswordAuthenticator",
        "authorizer": "CassandraAuthorizer",
        "auth_superuser_name": "cassandra",
        "auth_superuser_salted_password": "$6$x7IFjiX5VCpvNiFk$2IfjTvSyGL7zerpV.wbY7mJjaRCrJ/68dtT3UpT.sSmNYz1bPjtn3mH.kJKFvaZ2T4SbVeBijjmwGjcb83LlV/",
    },
    startup_delay_seconds=30,
)
ccm_tests = TestConfiguration(tags=["ccm"], test_command_args='-timeout=10m -race -tags="ccm"', cluster_configuration={})

test_config_map = {
    "integration": integration_tests,
    "auth": auth_tests,
    "ccm": ccm_tests,
}
