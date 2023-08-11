import logging
from pathlib import Path
from typing import Dict

from ccmlib import scylla_cluster as ccm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestCluster:
    """Responsible for configuring, starting and stopping cluster for tests"""

    def __init__(self, driver_directory: Path, version: str, configuration: Dict[str, str]) -> None:
        self.cluster_directory = driver_directory / "ccm"
        self.cluster_directory.mkdir(parents=True, exist_ok=True)
        logger.info("Preparing test cluster binaries and configuration...")
        self._cluster: ccm.ScyllaCluster = ccm.ScyllaCluster(self.cluster_directory, 'test', cassandra_version=version)
        cluster_config = {
                "experimental_features": ["udf"],
                "enable_user_defined_functions": "true",
            }
        cluster_config.update(configuration)
        self._cluster.set_configuration_options(cluster_config)
        self._cluster.populate(1)
        logger.info("Cluster prepared")

    @property
    def ip_addresses(self):
        storage_interfaces = [node.network_interfaces['storage'][0] for node in list(self._cluster.nodes.values()) if node.is_live()]
        return ",".join(storage_interfaces)

    def start(self) -> str:
        logger.info("Starting test cluster...")
        self._cluster.start(wait_for_binary_proto=True)
        nodes_count = len(self._cluster.nodes)
        logger.info("test cluster started")
        return f"-rf={nodes_count} -clusterSize={nodes_count} -cluster={self.ip_addresses}"

    def remove(self):
        logger.info("Removing test cluster...")
        self._cluster.remove()
        logger.info("test cluster removed")
