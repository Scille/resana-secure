from parsec.utils import from_jsonb64, to_jsonb64


class BackendError(Exception):
    pass


class BackendConcurrencyError(BackendError):
    pass


class BackendAccessError(BackendError):
    pass


class BackendStorage:

    def __init__(self, backend_connection):
        self.backend_conn = backend_connection

    async def fetch_user_manifest(self, version=None):
        payload = {
            'cmd': 'user_vlob_read',
        }
        if version is not None:
            payload['version'] = version
        rep = await self.backend_conn.send(payload)
        if rep['status'] == 'ok':
            return from_jsonb64(rep['blob'])
        else:
            raise BackendAccessError(
                'Error %s: %s' % (rep['status'], rep['reason']))

    async def sync_user_manifest(self, version, blob):
        rep = await self.backend_conn.send({
            'cmd': 'user_vlob_update',
            'version': version,
            'blob': to_jsonb64(blob)
        })
        if rep['status'] != 'ok':
            raise BackendConcurrencyError(
                'Error %s: %s' % (rep['status'], rep['reason']))

    async def fetch_manifest(self, id, rts, version=None):
        payload = {
            'cmd': 'vlob_read',
            'id': id,
            'trust_seed': rts,
        }
        if version is not None:
            payload['version'] = version
        rep = await self.backend_conn.send(payload)
        if rep['status'] == 'ok':
            return from_jsonb64(rep['blob'])
        else:
            raise BackendAccessError(
                'Error %s: %s' % (rep['status'], rep['reason']))

    async def sync_manifest(self, id, wts, version, blob):
        rep = await self.backend_conn.send({
            'cmd': 'vlob_update',
            'id': id,
            'trust_seed': wts,
            'version': version,
            'blob': to_jsonb64(blob)
        })
        if rep['status'] != 'ok':
            raise BackendConcurrencyError(
                'Error %s: %s' % (rep['status'], rep['reason']))

    async def sync_new_manifest(self, blob):
        rep = await self.backend_conn.send({
            'cmd': 'vlob_create',
            'blob': to_jsonb64(blob)
        })
        if rep['status'] != 'ok':
            raise BackendAccessError(
                'Error %s: %s' % (rep['status'], rep['reason']))
        return rep['id'], rep['read_trust_seed'], rep['write_trust_seed']

    async def sync_new_block(self, block):
        rep = await self.backend_conn.send({
            'cmd': 'blockstore_post',
            'block': to_jsonb64(block)
        })
        if rep['status'] != 'ok':
            raise BackendAccessError(
                'Error %s: %s' % (rep['status'], rep['reason']))
        return rep['id']

    async def fetch_block(self, id):
        rep = await self.backend_conn.send({
            'cmd': 'blockstore_get',
            'id': id
        })
        if rep['status'] == 'ok':
            return from_jsonb64(rep['block'])
        else:
            raise BackendAccessError(
                'Error %s: %s' % (rep['status'], rep['reason']))
