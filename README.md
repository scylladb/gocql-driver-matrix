# GoCQL Driver Matrix

## Pre-release integration gate

The reusable `.github/workflows/driver-integration-matrix.yml` runs the same five
lanes as PR CI: upstream gocql against Scylla `LATEST`, and Scylla gocql against
`LATEST`, `PRIOR`, `LTS-LATEST`, and `LTS-PRIOR`. Set `run_upstream` or
`run_scylla` to `false` to select one driver group.

The [Scylla GoCQL driver's release workflow](https://github.com/scylladb/gocql/blob/master/.github/workflows/release.yml)
already resolves the release target in `preflight`. Add this job and include it in
the `publication-gate` dependency list:

```yaml
  pre-release-integration:
    name: Driver compatibility matrix
    needs: preflight
    uses: scylladb/gocql-driver-matrix/.github/workflows/driver-integration-matrix.yml@master
    with:
      driver_ref: ${{ needs.preflight.outputs.resolved_sha }}
      driver_version: ${{ inputs.version }}

  publication-gate:
    needs: [preflight, build, integration, pre-release-integration]
    # Existing publication-gate configuration follows.
```

This blocks publication when a matrix lane fails. The release caller uses matrix
`master` for its runner and patches. For an untagged candidate, add a
`versions/scylla/<version>/` directory with its patch and ignore list when the
previous version's files do not apply. A `checkout-ref` file in that directory
can point PR validation at the candidate commit or branch; PR CI then runs all
four Scylla lanes. Remove `checkout-ref` after the release tag exists.

### GoCQL v2

The runner recognizes the Scylla driver's v2 module (`github.com/scylladb/gocql/v2`
in the tested ref's `go.mod`) and then:

* runs the integration suite in `./tests/integration` instead of `./...`;
* runs protocol 4 only and skips the other requested protocols, since the suite
  is built for ScyllaDB on protocol 4; a run that requests no protocol 4 fails;
* runs `TestSession/Connect/Authentication` in the `auth` lane, v2's counterpart
  of `TestAuthentication`.

Version folders never apply across major versions, so a v2 candidate uses the
newest `versions/scylla/2.*` folder at or below its version, never a 1.x patch.

## Prerequisites
* Python3.10
* pip
* docker
* git

#### Installing dependencies
Following commands will install all project dependencies using [Pipenv](https:/e/pipenv.readthedocs.io/en/latest/)

Have python 3.10, pip and virtualenv installed
* Updates the package sources list
  ```bash
  virtualenv -p python3.10 venv
  source venv/bin/activate
  pip install -r scripts/requirements.txt
  pip install ../scylla-ccm  # path to scylla-ccm repo
  ```

##### Repositories dependencies
All repositories should be under the **same base folder**
```bash
  git clone git@github.com:scylladb/gocql.git gocql-scylla &
  git clone git@github.com:gocql/gocql.git gocql-upstream &
  wait
```

## Running locally

* Execute the main.py wrapper like:
  * Running with relocatable packages: 
    * Regardless if this is Scylla or Upstream driver (script automatically discovers based on git origin source):
      ```bash
      # Run all standard tests on latest gocql tag (--versions 1)
      python3 main.py ../gocql-upstream --tests integration auth --versions 1 --protocols 3,4 --scylla-version release:5.2.4

      # Run all standard tests with specific gocql tag (--versions 1.8.0)
      python3 main.py ../gocql-scylla --tests integration auth --versions v1.8.0 --protocols 3,4 --scylla-version release:5.2.4
      ```

## Running locally with docker
```bash
export GOCQL_DRIVER_DIR=`pwd`/../gocql-scylla
scripts/run_test.sh --tests integration auth --versions 1 --protocols 3 --scylla-version release:5.2.4

```

## Available tests:
* integration
* auth
* ccm
