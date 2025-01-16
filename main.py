import sys
import argparse
import logging
import os
import subprocess
from typing import List
import traceback

from run import Run
from email_sender import create_report, get_driver_origin_remote, send_mail

logging.basicConfig(level=logging.INFO)


def main(arguments: argparse.Namespace):
    status = 0
    results = dict()
    driver_type = get_driver_type(arguments.gocql_driver_git)
    for driver_version in arguments.versions:
        for protocol in arguments.protocols:
            logging.info('=== GOCQL DRIVER VERSION %s, PROTOCOL v%s ===', driver_version, protocol)
            runner = Run(gocql_driver_git=arguments.gocql_driver_git,
                             driver_type=driver_type,
                             tag=driver_version,
                             protocol=protocol,
                             tests=arguments.tests,
                             scylla_version=arguments.scylla_version
                             )
            try:
                result = runner.run()

                logging.info("=== (%s:%s) GOCQL DRIVER MATRIX RESULTS FOR PROTOCOL v%s ===",
                             driver_type, driver_version, protocol)
                logging.info(", ".join(f"{key}: {value}" for key, value in result.summary.items()))
                if result.is_failed:
                    if not result.summary["tests"]:
                        logging.error("The run is failed because of one or more steps in the setup are failed")
                    else:
                        logging.error("Please check the report because there were failed tests")
                    status = 1
                results[(driver_version, protocol)] = result.summary
            except Exception:
                logging.exception(f"{driver_version} failed")
                status = 1
                exc_type, exc_value, exc_traceback = sys.exc_info()
                failure_reason = traceback.format_exception(exc_type, exc_value, exc_traceback)
                results[(driver_version, protocol)] = dict(exception=failure_reason)
                runner.create_metadata_for_failure(reason="\n".join(failure_reason))

    if arguments.recipients:
        email_report = create_report(results=results, scylla_version=arguments.scylla_version)
        email_report['driver_remote'] = get_driver_origin_remote(arguments.gocql_driver_git)
        email_report['status'] = "SUCCESS" if status == 0 else "FAILED"
        send_mail(arguments.recipients, email_report)

    quit(status)


def extract_n_latest_repo_tags(repo_directory: str, latest_tags_size: int = 2) -> List[str]:
    commands = [
        f"cd {repo_directory}",
        "git checkout .",
        "git fetch -p --all",
        f"git tag --sort=-creatordate | grep '^v[0-9]*\.[0-9]*\.[0-9]*$'"
    ]
    major_tags = set()
    tags = []
    for repo_tag in subprocess.check_output(" && ".join(commands), shell=True).decode().splitlines():
        if "." in repo_tag and not ("-" in repo_tag and not repo_tag.endswith("-scylla")):
            major_tag = tuple(repo_tag.split(".", maxsplit=2)[:2])
            if major_tag not in major_tags:
                major_tags.add(major_tag)
                tags.append(repo_tag)
            if len(tags) == latest_tags_size:
                break
    else:
        raise ValueError(f"The last {latest_tags_size} tags in {repo_directory} couldn't be extracted")
    return tags


def get_driver_type(gocql_driver_git):
    return "scylla" if "scylladb" in get_driver_origin_remote(gocql_driver_git) else "upstream"

def get_arguments() -> argparse.Namespace:
    default_protocols = ['3', '4']
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('gocql_driver_git', help='folder with git repository of gocql-driver', default="/gocql")
    parser.add_argument('--versions', default="2", type=str,
                        help="gocql-driver versions to test\n"
                             "The value can be number or str with comma (example: 'v1.8.0,v1.7.3').\n"
                             "default=2 - take the two latest driver's tags.")
    parser.add_argument('--tests', default='integration',
                        help='"tags" to pass to go test command, default=integration', nargs='+', choices=['integration', 'database', 'ccm'])
    parser.add_argument('--protocols', default=default_protocols,
                        help='cqlsh native protocol, default={}'.format(','.join(default_protocols)))
    parser.add_argument('--scylla-version', help="relocatable scylla version to use",
                        default=os.environ.get('SCYLLA_VERSION', None)),
    parser.add_argument('--recipients', help="whom to send mail at the end of the run",  nargs='+', default=None)
    arguments = parser.parse_args()
    if not arguments.scylla_version:
        logging.error("Error: --scylla-version is required if SCYLLA_VERSION is not set in the environment.")
        sys.exit(1)
    driver_versions = str(arguments.versions).replace(" ", "")
    if driver_versions.isdigit():
        arguments.versions = extract_n_latest_repo_tags(
            repo_directory=arguments.gocql_driver_git,
            latest_tags_size=int(driver_versions)
        )
    else:
        arguments.versions = driver_versions.split(",")
    if not isinstance(arguments.protocols, list):
        arguments.protocols = arguments.protocols.split(",")
    return arguments


if __name__ == '__main__':
    main(get_arguments())
