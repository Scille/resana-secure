#! /bin/bash
set -e

CONFIG_DIR=$HOME/resana_secure_config
CLIENT_ORIGIN=http://127.0.0.1:9000
BACKEND_ADDR=parsec://127.0.0.1:6777?no_ssl=true

# scalingo doesn't support libfuse, so mock around to disable fuse mountpoint
sed -is 's/runner = get_mountpoint_runner()/async def runner(*args, **kwargs): None/' subtree/parsec-cloud/parsec/core/mountpoint/manager.py

mkdir -p $CONFIG_DIR/devices

# Start parsec Server
parsec backend run --dev --spontaneous-organization-bootstrap &

# Wait for the server to be online
python -c "
from time import sleep
from urllib.request import urlopen, URLError
url = '$BACKEND_ADDR'.replace('parsec://', 'http://')
for i in range(10):
    try:
        urlopen(url)
        break
    except URLError:
        print('Retrying...')
        sleep(1)
else:
    raise SystemExit(1)
"

# Now bootstrap organization
parsec core bootstrap_organization \
    'parsec://127.0.0.1:6777/touillette42?no_ssl=true&action=bootstrap_organization' \
    --config-dir=$CONFIG_DIR \
    --password='UEBzc3cwcmQu' \
    --human-label='-unknown-' \
    --human-email='j@doe.com' \
    --device-label='pc42'

# Finally start the resana app
python -m resana_secure.app \
    --host=0.0.0.0 \
    --port=$PORT \
    --config-dir=$CONFIG_DIR \
    --client-origin=$CLIENT_ORIGIN \
    --backend-addr=$BACKEND_ADDR
