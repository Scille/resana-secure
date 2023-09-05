#!bash

set -e -o pipefail

# Allow the user to overwrite `SCRIPT_DIR` by exporting it beforehand.
SCRIPT_DIR=${SCRIPT_DIR:=$(dirname $(realpath -s "$0"))}
# Allow the user to overwrite `ROOT_DIR` by exporting it beforehand.
ROOT_DIR=${ROOT_DIR:=$(realpath -s "$SCRIPT_DIR/../..")}

SNAPCRAFT_ARGS=${SNAPCRAFT_ARGS:=--use-lxd}

export SNAPCRAFT_BUILD_ENVIRONMENT_CPU=${SNAPCRAFT_BUILD_ENVIRONMENT_CPU:=4}
export SNAPCRAFT_BUILD_ENVIRONMENT_MEMORY=${SNAPCRAFT_BUILD_ENVIRONMENT_MEMORY:=4G}

echo "SCRIPT_DIR=$SCRIPT_DIR"
echo "ROOT_DIR=$ROOT_DIR"

if [ "$NO_CLEANUP" != "1" ]; then
    function cleanup {
        echo 'Deleting snap & bin dir'
        set -x
        (
            cd $ROOT_DIR;
            snapcraft clean $SNAPCRAFT_ARGS;
            rm -rf snap bin;
        )
    }

    trap cleanup EXIT INT
fi

cp -R $ROOT_DIR/packaging/snap/{bin,snap} $ROOT_DIR

(
    cd $ROOT_DIR;
    TERM=xterm-256color snapcraft snap $SNAPCRAFT_ARGS
)
