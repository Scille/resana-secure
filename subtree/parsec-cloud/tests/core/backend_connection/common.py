# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

from parsec.api.protocol import AUTHENTICATED_CMDS, INVITED_CMDS, APIV1_ANONYMOUS_CMDS


ALL_CMDS = AUTHENTICATED_CMDS | INVITED_CMDS | APIV1_ANONYMOUS_CMDS
