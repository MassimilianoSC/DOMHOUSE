# The bench of tests/broker_container_test.py: a Linux with bash, python3, openssl and the docker client, that drives
# the machine's Docker through its socket and runs the real scripts/broker-vm.sh as root, like on the VM.
FROM docker:27-cli
RUN apk add --no-cache bash python3 openssl coreutils
