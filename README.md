# Python Driver Matrix

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
  ```

##### Repositories dependencies
All repositories should be under the **same base folder**
```bash
  git clone git@github.com:scylladb/gocql.git scylla-gocql &
  git clone git@github.com:gocql/gocql.git upstream-gocql &
  wait
```

## Running locally

* Execute the main.py wrapper like:
  * Running with relocatable packages: 
    * Scylla driver:
      ```bash
      # Run all standard tests on latest scylla-gocql tag (--versions 1)
      python3 main.py ../scylla-gocql --tests integration --driver-type scylla --versions 1 --protocols 3,4 --scylla-version 5.2.4

      # Run all standard tests with specific python-driver tag (--versions 3.25.0-scylla)
      python3 main.py ../scylla-gocql --tests integration --driver-type scylla --versions v1.8.0 --protocols 3,4 --scylla-version 5.2.4
      ```
    * upstream driver:
      ```bash
      # Run all standard tests on latest scylla-gocql tag (--versions 1)
      python3 main.py ../upstream-gocql --tests integration --driver-type scylla --versions 1 --protocols 3,4 --scylla-version 5.2.4

      # Run all standard tests with specific python-driver tag (--versions 3.25.0-scylla)
      python3 main.py ../upstream-gocql --tests integration --driver-type scylla --versions v1.5.2 --protocols 3,4 --scylla-version 5.2.4
      ```

