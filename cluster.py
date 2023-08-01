from pathlib import Path

from ccmlib import scylla_cluster as ccm


class TestCluster:

    def __init__(self, driver_directory: Path, version: str) -> None:
        self.cluster_directory = driver_directory / "ccm"
        self.cluster_directory.mkdir(parents=True, exist_ok=True)
        self._cluster: ccm.ScyllaCluster = ccm.ScyllaCluster(self.cluster_directory, 'test', version=f"release:{version}")
        self._cluster.populate(1)

    @property
    def ip_addresses(self):
        storage_interfaces = [node.network_interfaces['storage'][0] for node in list(self._cluster.nodes.values()) if node.is_live()]
        return ",".join(storage_interfaces)

    def start(self):
        self._cluster.start(wait_for_binary_proto=True)

    def stop(self):
        self._cluster.stop(wait=True)

    def remove(self):
        self._cluster.remove()
