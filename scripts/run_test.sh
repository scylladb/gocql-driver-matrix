#!/usr/bin/env bash
set -e

help_text="
Script to run gocql driver matrix from within docker

    Optional values can be set via environment variables
    GOCQL_MATRIX_DIR, GOCQL_DRIVER_DIR, CCM_DIR

    export GOCQL_DRIVER_DIR=`pwd`/../gocql-scylla
    scripts/run_test.sh python3 main.py --tests integration --versions 1 --protocols 3 --scylla-version 5.2.4
"

here="$(realpath $(dirname "$0"))"
DOCKER_IMAGE="$(<"$here/image")"

export GOCQL_MATRIX_DIR=${GOCQL_MATRIX_DIR:-`pwd`}
export GOCQL_DRIVER_DIR=${GOCQL_DRIVER_DIR:-`pwd`/../gocql-scylla}
export CCM_DIR=${CCM_DIR:-`pwd`/../scylla-ccm}

if [[ ! -d ${GOCQL_MATRIX_DIR} ]]; then
    echo -e "\e[31m\$GOCQL_MATRIX_DIR = $GOCQL_MATRIX_DIR doesn't exist\e[0m"
    echo "${help_text}"
    exit 1
fi
if [[ ! -d ${CCM_DIR} ]]; then
    echo -e "\e[31m\$CCM_DIR = $CCM_DIR doesn't exist\e[0m"
    echo "${help_text}"
    exit 1
fi

mkdir -p ${HOME}/.ccm
mkdir -p ${HOME}/.local/lib
mkdir -p ${HOME}/.docker

# export all BUILD_* env vars into the docker run
BUILD_OPTIONS=$(env | sed -n 's/^\(BUILD_[^=]\+\)=.*/--env \1/p')
# export all JOB_* env vars into the docker run
JOB_OPTIONS=$(env | sed -n 's/^\(JOB_[^=]\+\)=.*/--env \1/p')
# export all AWS_* env vars into the docker run
AWS_OPTIONS=$(env | sed -n 's/^\(AWS_[^=]\+\)=.*/--env \1/p')

# if in jenkins also mount the workspace into docker
if [[ -d ${WORKSPACE} ]]; then
WORKSPACE_MNT="-v ${WORKSPACE}:${WORKSPACE}"
else
WORKSPACE_MNT=""
fi

DOCKER_CONFIG_MNT="-v $(eval echo ~${USER})/.docker:${HOME}/.docker"

if [[ -z ${SCYLLA_VERSION} ]]; then
      echo -e "\e[31m\$SCYLLA_VERSION is not set\e[0m"
      echo "${help_text}"
      exit 1
fi

# export all SCYLLA_* env vars into the docker run
SCYLLA_OPTIONS=$(env | sed -n 's/^\(SCYLLA_[^=]\+\)=.*/--env \1/p')

group_args=()
for gid in $(id -G); do
    group_args+=(--group-add "$gid")
done

docker_cmd="docker run --detach=true \
    ${WORKSPACE_MNT} \
    ${SCYLLA_OPTIONS} \
    ${DOCKER_CONFIG_MNT} \
    -v ${GOCQL_MATRIX_DIR}:/gocql-driver-matrix \
    -v ${GOCQL_DRIVER_DIR}:/gocql \
    -v ${CCM_DIR}:/scylla-ccm \
    -e HOME \
    -e SCYLLA_EXT_OPTS \
    -e DEV_MODE \
    -e WORKSPACE \
    ${BUILD_OPTIONS} \
    ${JOB_OPTIONS} \
    ${AWS_OPTIONS} \
    -w /gocql-driver-matrix \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    -v /etc/passwd:/etc/passwd:ro \
    -v /etc/group:/etc/group:ro \
    -u $(id -u ${USER}):$(id -g ${USER}) \
    ${group_args[@]} \
    --tmpfs ${HOME}/.cache \
    --tmpfs ${HOME}/.config \
    --tmpfs ${HOME}/.cassandra \
    --tmpfs ${HOME}/go \
    -v ${HOME}/.local:${HOME}/.local \
    -v ${HOME}/.ccm:${HOME}/.ccm \
    --network=host --privileged \
    ${DOCKER_IMAGE} bash -c '$* /gocql'"

echo "Running Docker: $docker_cmd"
container=$(eval $docker_cmd)


kill_it() {
    if [[ -n "$container" ]]; then
        docker rm -f "$container" > /dev/null
        container=
    fi
}

trap kill_it SIGTERM SIGINT SIGHUP EXIT

docker logs "$container" -f

if [[ -n "$container" ]]; then
    exitcode="$(docker wait "$container")"
else
    exitcode=99
fi

echo "Docker exitcode: $exitcode"

kill_it

trap - SIGTERM SIGINT SIGHUP EXIT

# after "docker kill", docker wait will not print anything
[[ -z "$exitcode" ]] && exitcode=1

exit "$exitcode"

