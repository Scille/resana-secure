#! /bin/bash
set -e

CONFIG_DIR=$HOME/resana_secure_config
CLIENT_ORIGIN="http://127.0.0.1:9000;https://test-resana.interstis.fr"
BACKEND_DOMAIN="127.0.0.1:6777"
BACKEND_ADDR="parsec://$BACKEND_DOMAIN?no_ssl=true"
BOOTSTRAP_ORG_ADDR="parsec://$BACKEND_DOMAIN/ResanaSecureOrg?no_ssl=true&action=bootstrap_organization"

mkdir -p $CONFIG_DIR/devices

# Start parsec Server
parsec backend run --dev --spontaneous-organization-bootstrap &

# Wait for the server to be online
python -c "
from time import sleep
from urllib.request import urlopen, URLError
for i in range(10):
    try:
        urlopen('http://$BACKEND_DOMAIN')
        break
    except URLError:
        print('Retrying...')
        sleep(1)
else:
    raise SystemExit(1)
"

# Now bootstrap organization
parsec core bootstrap_organization $BOOTSTRAP_ORG_ADDR \
    --config-dir=$CONFIG_DIR \
    --password='UEBzc3cwcmQu' \
    --human-label='-unknown-' \
    --human-email='j@doe.com' \
    --device-label='pc42'

# Finally start the resana app
python -m resana_secure \
    --host=0.0.0.0 \
    --port=$PORT \
    --config-dir=$CONFIG_DIR \
    --backend-addr=$BACKEND_ADDR \
    --client-origin=$CLIENT_ORIGIN \
    --disable-mountpoint \
    --disable-gui
