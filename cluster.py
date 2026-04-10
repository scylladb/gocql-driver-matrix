import logging
import socket
import time
from pathlib import Path
from typing import Dict, Tuple

from ccmlib import scylla_cluster as ccm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ports that a running Scylla node binds on its listen address.
_SCYLLA_PORTS = (9042, 9160, 7000, 7001)
# Number of nodes populated by default.
_CLUSTER_NODES = 3


def _is_port_bound(ip: str, port: int) -> bool:
    """Return True if something is actively listening on ip:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((ip, port))
            return True
        except OSError:
            return False


def _wait_for_ports_free(ip_prefix: str, timeout: int = 120) -> bool:
    """Wait until no Scylla ports are bound on any node of the cluster.

    This is necessary because Scylla processes can enter kernel D-state and
    survive SIGKILL.  We wait for them to release their ports before declaring
    the IP prefix available for reuse.

    Returns True if all ports are free within *timeout* seconds, False otherwise.
    """
    node_ips = [f"{ip_prefix}{i + 1}" for i in range(_CLUSTER_NODES)]
    deadline = time.time() + timeout
    while time.time() < deadline:
        still_bound = [
            (ip, port)
            for ip in node_ips
            for port in _SCYLLA_PORTS
            if _is_port_bound(ip, port)
        ]
        if not still_bound:
            return True
        logger.warning("Waiting for Scylla ports to be released: %s", still_bound)
        time.sleep(3)
    return False


def acquire_ip_prefix() -> Tuple[socket.socket, str]:
    """Gets a machine-unique IP prefix to support parallel tests.

    Skips any prefix where a Scylla CQL port (9042) is still bound -- this can
    happen when a previous cluster's processes are stuck in kernel D-state after
    SIGKILL and have not yet released their ports.

    Returns a tuple of (lock socket, ip prefix).  The caller must close the
    socket via release_ip_prefix_lock() when the prefix is no longer needed.
    """
    logger.info("Getting machine-unique ip prefix to support parallel tests...")
    for index in range(1, 126):
        ip_prefix = f'127.0.{index}.'
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((f'{ip_prefix}1', 48783))  # arbitrary lock port
        except OSError:
            sock.close()
            continue
        # Lock port is free, but a zombie Scylla from a previous run might still
        # hold the CQL port.  Skip this prefix if that's the case.
        if any(_is_port_bound(f'{ip_prefix}{i + 1}', 9042) for i in range(_CLUSTER_NODES)):
            logger.warning(
                "IP prefix %s: lock port free but Scylla CQL port 9042 still bound; skipping",
                ip_prefix,
            )
            sock.close()
            continue
        logger.info("Cluster ip prefix acquired: %s", ip_prefix)
        return sock, ip_prefix
    raise ValueError("Couldn't acquire ip prefix - looks clusters are not cleared properly")


def release_ip_prefix_lock(sock: socket.socket) -> None:
    sock.close()


class TestCluster:
    """Responsible for configuring, starting and stopping cluster for tests"""

    def __init__(self, driver_directory: Path, version: str, configuration: Dict[str, str]) -> None:
        self.cluster_directory = driver_directory / "ccm"
        self.cluster_directory.mkdir(parents=True, exist_ok=True)
        logger.info("Preparing test cluster binaries and configuration...")
        self._ip_prefix_lock, self._ip_prefix = acquire_ip_prefix()
        self._cluster: ccm.ScyllaCluster = ccm.ScyllaCluster(self.cluster_directory, 'test', cassandra_version=version)
        # Write CURRENT file so the ccm CLI knows which cluster is active.
        # ccmlib only writes this via switch_cluster() / `ccm switch`, not during cluster creation.
        # Without it, `ccm start --wait-for-binary-proto` (called by Go ccm tests) fails with exit status 1.
        (self.cluster_directory / 'CURRENT').write_text('test\n')
        self._cluster.set_ipprefix(self._ip_prefix)
        cluster_config = {
                "maintenance_socket": "workdir",
                "experimental_features": ["udf"],
                "enable_user_defined_functions": "true",
            }
        cluster_config.update(configuration)
        self._cluster.set_configuration_options(cluster_config)
        self._cluster.populate(3)
        logger.info("Cluster prepared")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.remove()
        release_ip_prefix_lock(self._ip_prefix_lock)

    @property
    def ip_addresses(self):
        storage_interfaces = [node.network_interfaces['storage'][0] for node in list(self._cluster.nodes.values()) if node.is_live()]
        return ",".join(storage_interfaces)

    def start(self) -> str:
        logger.info("Starting test cluster...")
        self._cluster.start(wait_for_binary_proto=True)
        nodes_count = len(self._cluster.nodes)
        logger.info("test cluster started")
        path = "../gocql-scylla/ccm/test/node1/cql.m"
        if not Path(path).exists():
            logger.info("Cluster socket file %s is not found", path)
            return f"-rf={nodes_count} -clusterSize={nodes_count} -cluster={self.ip_addresses}"
        else:
            return f"-rf={nodes_count} -clusterSize={nodes_count} -cluster={self.ip_addresses} -cluster-socket=../gocql-scylla/ccm/test/node1/cql.m"

    def stop(self):
        logger.info("Stopping test cluster...")
        self._cluster.stop()
        logger.info("test cluster stopped")

    def remove(self):
        logger.info("Removing test cluster...")
        self._cluster.remove()
        logger.info("Waiting for Scylla processes to release ports on prefix %s...", self._ip_prefix)
        if not _wait_for_ports_free(self._ip_prefix):
            logger.warning(
                "Scylla processes on prefix %s still holding ports after timeout; "
                "the next cluster will use a different IP prefix.",
                self._ip_prefix,
            )
        else:
            logger.info("All Scylla ports on prefix %s are free.", self._ip_prefix)
