#! /bin/sh

CONFIG_DIR=$HOME/resana_secure_config
CLIENT_ORIGIN=http://127.0.0.1:9000
BACKEND_ADDR=parsec://102.0.0.1:6777

mkdir -p $CONFIG_DIR/devices

echo 'iKpjaXBoZXJ0ZXh0xQIsEizKLW/y0EhNMqQ1Xr631C3GgNVjUjljWF2SX74VPBcfoC7q83MUYfEl
YnfpwrSOkLI4mmMiSZStKxr+33R2YNMU0mI9AoVS3wn3cus8R+56HDy8lGqcB3IAAfvOg38j0mGb
g4k13MKP8GTccaOfxW9tPGLxwUX1BC0H1DELR8sZ2XfZ/PoKQG0BEXkh9CpySd2OwygzOEvWHmsS
BFgfoeEupPn9fQrV4Heu3eHNTx3Jknz87+ab9QYFlJEHxdyfaBh/Zs19fsUwOc891TmP8P0FQEYE
S1Nuwoxfr7g98HJ1AmBeVgy/ViCgkBv7htTHJogTr//GAP8PhCmuY3tozdnCZWPzVCkf8AjIysjU
cXTmrzXtydKGPhblHAA+Bfne1ozcFJsntfrcPVTbVA6HUsRr0w3PMnvAPZiym0o8vLwPq5AIFtHJ
Ylw+QDM9zfuAJBbDz1gFJZdyOnBvgMdre1aBXdaC930aQelrYAg+NTYMf90mJhNCx6+wy14PwlLy
Z3hRY/YlPal2UT6bZbuCESG60eiO0CI/u0vwGfbzY6k+9zKe3vrJ7w1k/pP7zzZvYnp0Cmgag/zq
jQ4lBEv2UbcLgiiBOmIR4rR/b054m0psjzXldwp0VLX8yRNDzhYahek6/h1Z/b7mStj7YSpCOFVE
yEWC1iwJq5g/DZGCU4Xi/pyXKrKzML148qZtYrlKsvn6gPVJu5hb57kqZmCH6PIv6Idp+Wyt64PX
talkZXZpY2VfaWTZQWNiMDE0MDE2ZjEwMTRjZmQ5Mjg5NTljNjM2ZmNkZGM5QDI5ODkxODMyY2Uy
OTRhZjhhNWQ4ZGYyYmU1MjZiMGQyrGRldmljZV9sYWJlbLBpcC0xNzItMzEtMTgtMjM4rGh1bWFu
X2hhbmRsZZKpakBkb2UuY29tqEpvaG4gRG9lr29yZ2FuaXphdGlvbl9pZKhDb29sT3JnMqRzYWx0
xBCCBhYYIUkJBgFMbH3DFhYqpHNsdWfZVTEyMzM3ODg5MmIjQ29vbE9yZzIjY2IwMTQwMTZmMTAx
NGNmZDkyODk1OWM2MzZmY2RkYzlAMjk4OTE4MzJjZTI5NGFmOGE1ZDhkZjJiZTUyNmIwZDKkdHlw
ZahwYXNzd29yZA==' | base64 -d > $CONFIG_DIR/devices/901fc5f481f571af2bfcfc6e5362836dc3088e68c0eaca909c28c5da6a1a56d3.keys

# scalingo doesn't support libfuse, so mock around to disable fuse mountpoint
sed -is 's/runner = get_mountpoint_runner()/async def runner(*args, **kwargs): None/' subtree/parsec-cloud/parsec/core/mountpoint/manager.py

python -m resana_secure.app \
    --host=0.0.0.0 \
    --port=$PORT \
    --config-dir=$CONFIG_DIR \
    --client-origin=$CLIENT_ORIGIN \
    --backend-addr=$BACKEND_ADDR
