# The bench of tests/broker_container_test.py: a Linux with bash, python3, openssl and the docker client, that drives
# the machine's Docker through its socket and runs the real scripts/broker-vm.sh as root, like on the VM.
# util-linux and e2fsprogs: the keys' disk is prepared with the same tools as on the VM (blkid, mkfs.ext4, chattr, mount);
# nftables and iproute2: the limit on new connections, behind a DNAT like docker's.
FROM docker:27-cli
RUN apk add --no-cache bash python3 openssl coreutils util-linux util-linux-misc e2fsprogs e2fsprogs-extra findutils nftables iproute2
