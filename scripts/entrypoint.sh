#!/bin/bash
if [ ! -d "/scylla-ccm" ]
  then echo "Error. /scylla-ccm is not mounted. Mount scylla-ccm repo to /scylla-ccm in docker run command."
  exit 1
fi
if [ ! -d "/gocql" ]
  then echo "Error. /gocql is not mounted. Mount gocql repo to /gocql in docker run command."
  exit 1
fi
if [ ! -d "/gocql-driver-matrix" ]
  then echo "Error. /gocql-driver-matrix is not mounted. Mount gocql-driver-matrix repo to /gocql-driver-matrix in docker run command."
  exit 1
fi
pip install /scylla-ccm
cd /gocql-driver-matrix && python3 main.py /gocql "$@"
