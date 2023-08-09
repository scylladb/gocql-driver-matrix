# Gocql Driver Matrix

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
      python3 main.py ../gocql-upstream --tests integration --versions 1 --protocols 3,4 --scylla-version release:5.2.4

      # Run all standard tests with specific gocql tag (--versions 1.8.0)
      python3 main.py ../gocql-scylla --tests integration --versions v1.8.0 --protocols 3,4 --scylla-version release:5.2.4
      ```

## Running locally with docker
```bash
export GOCQL_DRIVER_DIR=`pwd`/../gocql-scylla
scripts/run_test.sh --tests integration --versions 1 --protocols 3 --scylla-version release:5.2.4

```