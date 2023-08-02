import logging
from pathlib import Path

from ccmlib import scylla_cluster as ccm
from ccmlib.common import get_version_from_build

logger = logging.getLogger(__name__)


class TestCluster:
    """Responsible for configuring, starting and stopping cluster for tests"""

    def __init__(self, driver_directory: Path, version: str) -> None:
        self.cluster_directory = driver_directory / "ccm"
        self.cluster_directory.mkdir(parents=True, exist_ok=True)
        self._cluster: ccm.ScyllaCluster = ccm.ScyllaCluster(self.cluster_directory, 'test', version=f"release:{version}")
        self._cluster.populate(1)
        logger.info(self._cluster.version())

    @property
    def ip_addresses(self):
        storage_interfaces = [node.network_interfaces['storage'][0] for node in list(self._cluster.nodes.values()) if node.is_live()]
        return ",".join(storage_interfaces)

    def start(self):
        logger.info("Starting test cluster...")
        self._cluster.start(wait_for_binary_proto=True)
        logger.info("test cluster started")

    def remove(self):
        logger.info("Removing test cluster...")
        self._cluster.remove()
        logger.info("test cluster removed")
