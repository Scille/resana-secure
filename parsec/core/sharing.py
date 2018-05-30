import trio
import logbook
import traceback
from nacl.public import SealedBox
from nacl.signing import VerifyKey

from parsec.schema import UnknownCheckedSchema, fields
from parsec.core.base import BaseAsyncComponent
from parsec.utils import from_jsonb64, ejson_loads, ParsecError
from parsec.core.fs import FSInvalidPath
from parsec.core.backend_connection import BackendNotAvailable, BackendError


logger = logbook.Logger("parsec.core.sharing")


class SharingError(ParsecError):
    status = "sharing_error"


class BackendMessageGetRepMessagesSchema(UnknownCheckedSchema):
    count = fields.Int(required=True)
    body = fields.Base64Bytes(required=True)
    sender_id = fields.String(required=True)


class BackendMessageGetRepSchema(UnknownCheckedSchema):
    status = fields.CheckedConstant("ok", required=True)
    messages = fields.List(fields.Nested(BackendMessageGetRepMessagesSchema), required=True)


backend_message_get_rep_schema = BackendMessageGetRepSchema()


class BackendUserGetRepDeviceSchema(UnknownCheckedSchema):
    created_on = fields.DateTime(required=True)
    revocated_on = fields.DateTime(missing=None)
    verify_key = fields.Base64Bytes(required=True)


class BackendUserGetRepSchema(UnknownCheckedSchema):
    status = fields.CheckedConstant("ok", required=True)
    user_id = fields.String(required=True)
    created_on = fields.DateTime(required=True)
    created_by = fields.String(required=True)
    broadcast_key = fields.Base64Bytes(required=True)
    devices = fields.Map(fields.String(), fields.Nested(BackendUserGetRepDeviceSchema), missing={})


backend_user_get_rep_schema = BackendUserGetRepSchema()


class BackendMessageError(Exception):
    pass


class Sharing(BaseAsyncComponent):
    def __init__(self, device, fs, backend_connection, backend_event_manager, signal_ns):
        super().__init__()
        self._signal_ns = signal_ns
        self.fs = fs
        self._backend_connection = backend_connection
        self._backend_event_manager = backend_event_manager
        self.device = device
        self.msg_arrived = trio.Event()
        self._message_listener_task_cancel_scope = None

    async def _init(self, nursery):
        self._message_listener_task_cancel_scope = await nursery.start(self._message_listener_task)
        await self._backend_event_manager.subscribe_backend_event(
            "message_arrived", self.device.user_id
        )
        self._signal_ns.signal("message_arrived").connect(self._msg_arrived_cb, weak=True)

    async def _teardown(self):
        if self._message_listener_task_cancel_scope:
            self._message_listener_task_cancel_scope.cancel()

    async def _process_message(self, msg):
        sender_user_id, sender_device_name = msg["sender_id"].split("@")
        rep = await self._backend_connection.send({"cmd": "user_get", "user_id": sender_user_id})
        rep, errors = backend_user_get_rep_schema.load(rep)
        if errors:
            raise BackendMessageError(
                "Cannot retreive message %r sender's device informations: %r" % (msg, rep)
            )

        try:
            device = rep["devices"][sender_device_name]
        except KeyError:
            raise BackendMessageError("Message %r sender device doesn't exists" % msg)

        # TODO: handle key validity expiration
        sender_verifykey = VerifyKey(device["verify_key"])
        box = SealedBox(self.device.user_privkey)

        # TODO: handle bad signature, bad encryption, bad json, bad payload...
        sharing_msg_encrypted = msg["body"]
        sharing_msg_signed = box.decrypt(sharing_msg_encrypted)
        sharing_msg_clear = sender_verifykey.verify(sharing_msg_signed)
        sharing_msg = ejson_loads(sharing_msg_clear.decode("utf8"))

        # TODO: handle other type of message
        # assert sharing_msg["type"] == "share"
        if sharing_msg["type"] == "share":
            sharing_access = sharing_msg['content']
            sharing_access['key'] = from_jsonb64(sharing_access['key'])

            shared_with_folder_name = "shared-with-%s" % sender_user_id
            # TODO: leaky abstraction...
            parent_manifest = None
            parent_path = '/%s' % shared_with_folder_name
            while not parent_manifest:
                try:
                    parent_access, parent_manifest = await self.fs._local_tree.retrieve_entry(parent_path)
                except FSInvalidPath:
                    await self.fs.folder_create(parent_path)

            # TODO: if parent is a file, this is going to fail...
            sharing_name = sharing_msg['name']
            while sharing_name in parent_manifest['children']:
                sharing_name += '-dup'
            parent_manifest['children'][sharing_msg['name']] = sharing_access
            self.fs._local_tree.update_entry(parent_access, parent_manifest)
            self._signal_ns.signal("new_sharing").send('%s/%s' % (parent_path, sharing_name))
        elif sharing_msg["type"] == "ping":
            self._signal_ns.signal("ping").send(sharing_msg["ping"])

        self.fs.update_last_processed_message(msg["count"])

    async def _process_all_last_messages(self):
        rep = await self._backend_connection.send(
            {"cmd": "message_get", "offset": self.fs.get_last_processed_message()}
        )

        rep, errors = backend_message_get_rep_schema.load(rep)
        if errors:
            raise BackendMessageError(
                "Cannot retreive user messages: %r (errors: %r)" % (rep, errors)
            )

        for msg in rep["messages"]:
            try:
                await self._process_message(msg)
            except SharingError as exc:
                logger.warning(exc.args[0])

    async def _message_listener_task(self, *, task_status=trio.TASK_STATUS_IGNORED):
        with trio.open_cancel_scope() as cancel_scope:
            task_status.started(cancel_scope)
            while True:
                try:
                    await self.msg_arrived.wait()
                    self.msg_arrived.clear()
                    await self._process_all_last_messages()
                except BackendNotAvailable:
                    pass
                except BackendError:
                    logger.exception("Error with backend: " % traceback.format_exc())

    def _msg_arrived_cb(self, sender):
        self.msg_arrived.set()
