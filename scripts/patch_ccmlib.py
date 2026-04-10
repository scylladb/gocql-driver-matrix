#!/usr/bin/env python3
"""
Patch ccmlib's ClusterAddCmd.run() to auto-detect Scylla cluster type.

When 'ccm add' is invoked without --scylla (as done by the gocql driver's
internal/ccm/ccm.go helper), the upstream code creates a plain Node() instead
of a ScyllaNode(), which causes a FileNotFoundError when it tries to open
cassandra.yaml (which does not exist in a Scylla installation).

This patch adds an isinstance() check for ScyllaCluster/ScyllaDockerCluster
and delegates to cluster.create_node(), which always returns the correct type.

NOTE: The patch uses exact string matching against a specific code block in
ccmlib's cluster_cmds.py.  If ccmlib changes that block, this script will
exit with an error and must be updated.  This is intentional -- a silent
mis-patch would be worse than a loud failure.
"""
import pathlib
import sys

OLD = (
    "            else:\n"
    "                node = Node(self.name, self.cluster, self.options.bootstrap, self.storage,"
    " self.jmx_port, self.remote_debug_port, self.initial_token, binary_interface=self.binary)\n"
    "            self.cluster.add(node, self.options.is_seed,"
    " data_center=self.options.data_center, rack=self.options.rack)"
)

NEW = (
    "            elif isinstance(self.cluster, (ScyllaCluster, ScyllaDockerCluster)):\n"
    "                # Auto-detect Scylla cluster: delegate to cluster.create_node() so the\n"
    "                # correct node type (ScyllaNode / ScyllaDockerNode) is used even when\n"
    "                # the caller did not pass --scylla (e.g. the gocql ccm helper).\n"
    "                node = self.cluster.create_node(self.name, self.options.bootstrap,"
    " self.storage, self.jmx_port, self.remote_debug_port, self.initial_token,"
    " binary_interface=self.binary)\n"
    "            else:\n"
    "                node = Node(self.name, self.cluster, self.options.bootstrap, self.storage,"
    " self.jmx_port, self.remote_debug_port, self.initial_token, binary_interface=self.binary)\n"
    "            self.cluster.add(node, self.options.is_seed,"
    " data_center=self.options.data_center, rack=self.options.rack)"
)

# Symbols that must be importable in cluster_cmds.py for the patch to work.
REQUIRED_SYMBOLS = ("ScyllaCluster", "ScyllaDockerCluster")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <ccm-dir>", file=sys.stderr)
        sys.exit(1)

    ccm_dir = pathlib.Path(sys.argv[1])
    target = ccm_dir / "ccmlib" / "cmds" / "cluster_cmds.py"

    if not target.exists():
        print(f"ERROR: {target} not found", file=sys.stderr)
        sys.exit(1)

    content = target.read_text()

    if NEW in content:
        print(f"[patch_ccmlib] Already patched: {target}")
        return

    # Validate that the symbols we reference in the patch are importable
    # from somewhere in the file (directly or via star-import).
    for sym in REQUIRED_SYMBOLS:
        if sym not in content:
            print(
                f"ERROR: required symbol '{sym}' not found in {target} "
                f"-- ccmlib version may be incompatible with the patch",
                file=sys.stderr,
            )
            sys.exit(1)

    if OLD not in content:
        print(f"ERROR: patch target not found in {target} -- ccmlib version may have changed",
              file=sys.stderr)
        sys.exit(1)

    target.write_text(content.replace(OLD, NEW, 1))
    print(f"[patch_ccmlib] Patched: {target}")


if __name__ == "__main__":
    main()
