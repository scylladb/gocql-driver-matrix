# Use multi-stage builds for Python and Go
# Python build
FROM python:3.10.12-bullseye AS python-build

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

FROM golang:1.25.5 AS go-build

FROM bitnami/minideb:bullseye

COPY --from=python-build /usr/local /usr/local
COPY --from=go-build /usr/local/go/ /usr/local/go/

RUN install_packages libssl-dev git openjdk-11-jdk-headless gcc build-essential
RUN git config --global --add safe.directory /gocql

ENV PATH="/usr/local/go/bin:/usr/local/go-packages/bin:${PATH}"
RUN GOPATH=/usr/local/go-packages go install github.com/jstemmer/go-junit-report/v2@v2.0.0

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV CGO_ENABLED=1

ENTRYPOINT ["/entrypoint.sh"]
