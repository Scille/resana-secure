# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

import pytest
import trio
from pendulum import datetime

from parsec.crypto import PrivateKey, HashDigest

from tests.backend.common import (
    invite_info,
    invite_1_claimer_wait_peer,
    invite_1_greeter_wait_peer,
    invite_2a_claimer_send_hashed_nonce,
    invite_2a_greeter_get_hashed_nonce,
    invite_2b_greeter_send_nonce,
    invite_2b_claimer_send_nonce,
    invite_3a_greeter_wait_peer_trust,
    invite_3a_claimer_signify_trust,
    invite_3b_claimer_wait_peer_trust,
    invite_3b_greeter_signify_trust,
    invite_4_greeter_communicate,
    invite_4_claimer_communicate,
)


class PeerControler:
    def __init__(self):
        self._orders_sender, self._orders_receiver = trio.open_memory_channel(0)
        self._orders_ack_sender, self._orders_ack_receiver = trio.open_memory_channel(0)
        self._results_sender, self._results_receiver = trio.open_memory_channel(1)

    # Methods used to control the peer

    async def send_order(self, order, step_4_payload=None):
        assert self._results_receiver.statistics().current_buffer_used == 0
        await self._orders_sender.send((order, step_4_payload))
        await self._orders_ack_receiver.receive()

    async def get_result(self):
        is_exc, ret = await self._results_receiver.receive()
        if is_exc:
            raise ret
        else:
            return ret

    async def assert_ok_rep(self):
        rep = await self.get_result()
        assert rep["status"] == "ok"

    # Methods used by the peer

    async def peer_do(self, action, *args, **kwargs):
        print("REQ START", action.cmd)
        req_done = False
        try:
            async with action.async_call(*args, **kwargs) as async_rep:
                print("REQ DONE", action.cmd)
                req_done = True
                await self._orders_ack_sender.send(None)

                # Explicit use of `do_recv` instead of relying on the __aexit__
                # which containts a `fail_after` timeout (some commands such
                # as `1_wait_peer` wait for a peer to finish, on which we
                # have here no control on)
                await async_rep.do_recv()
                print("REP", action.cmd, async_rep.rep)
                await self._results_sender.send((False, async_rep.rep))

        except Exception as exc:
            print("EXCEPTION RAISED", action.cmd, repr(exc))
            if not req_done:
                await self._orders_ack_sender.send(None)
            await self._results_sender.send((True, exc))

    async def peer_next_order(self):
        return await self._orders_receiver.receive()


class ExchangeTestBed:
    def __init__(
        self,
        organization_id,
        greeter,
        invitation,
        greeter_privkey,
        claimer_privkey,
        greeter_ctlr,
        claimer_ctlr,
        greeter_sock,
        claimer_sock,
    ):
        self.organization_id = organization_id
        self.greeter = greeter
        self.invitation = invitation
        self.greeter_privkey = greeter_privkey
        self.claimer_privkey = claimer_privkey
        self.greeter_ctlr = greeter_ctlr
        self.claimer_ctlr = claimer_ctlr
        self.greeter_sock = greeter_sock
        self.claimer_sock = claimer_sock

    async def send_order(self, who, order, step_4_payload=b""):
        assert who in ("greeter", "claimer")
        ctlr = getattr(self, f"{who}_ctlr")
        await ctlr.send_order(order, step_4_payload=step_4_payload)

    async def get_result(self, who):
        assert who in ("greeter", "claimer")
        ctlr = getattr(self, f"{who}_ctlr")
        return await ctlr.get_result()

    async def assert_ok_rep(self, who):
        assert who in ("greeter", "claimer")
        ctlr = getattr(self, f"{who}_ctlr")
        return await ctlr.assert_ok_rep()


@pytest.fixture
async def exchange_testbed(backend, alice, alice_backend_sock, backend_invited_sock_factory):
    async def _run_greeter(tb):
        peer_controller = tb.greeter_ctlr
        while True:
            order, step_4_payload = await peer_controller.peer_next_order()

            if order == "1_wait_peer":
                await peer_controller.peer_do(
                    invite_1_greeter_wait_peer,
                    tb.greeter_sock,
                    token=tb.invitation.token,
                    greeter_public_key=tb.greeter_privkey.public_key,
                )

            elif order == "2a_get_hashed_nonce":
                await peer_controller.peer_do(
                    invite_2a_greeter_get_hashed_nonce, tb.greeter_sock, token=tb.invitation.token
                )

            elif order == "2b_send_nonce":
                await peer_controller.peer_do(
                    invite_2b_greeter_send_nonce,
                    tb.greeter_sock,
                    token=tb.invitation.token,
                    greeter_nonce=b"<greeter_nonce>",
                )

            elif order == "3a_wait_peer_trust":
                await peer_controller.peer_do(
                    invite_3a_greeter_wait_peer_trust, tb.greeter_sock, token=tb.invitation.token
                )

            elif order == "3b_signify_trust":
                await peer_controller.peer_do(
                    invite_3b_greeter_signify_trust, tb.greeter_sock, token=tb.invitation.token
                )

            elif order == "4_communicate":
                assert step_4_payload is not None
                await peer_controller.peer_do(
                    invite_4_greeter_communicate,
                    tb.greeter_sock,
                    token=tb.invitation.token,
                    payload=step_4_payload,
                )

            else:
                assert False

    async def _run_claimer(tb):
        peer_controller = tb.claimer_ctlr
        while True:
            order, step_4_payload = await peer_controller.peer_next_order()

            if order == "invite_info":
                await peer_controller.peer_do(invite_info, tb.claimer_sock)

            elif order == "1_wait_peer":
                await peer_controller.peer_do(
                    invite_1_claimer_wait_peer,
                    tb.claimer_sock,
                    claimer_public_key=tb.claimer_privkey.public_key,
                )

            elif order == "2a_send_hashed_nonce":
                await peer_controller.peer_do(
                    invite_2a_claimer_send_hashed_nonce,
                    tb.claimer_sock,
                    claimer_hashed_nonce=HashDigest.from_data(b"<claimer_nonce>"),
                )

            elif order == "2b_send_nonce":
                await peer_controller.peer_do(
                    invite_2b_claimer_send_nonce, tb.claimer_sock, claimer_nonce=b"<claimer_nonce>"
                )

            elif order == "3a_signify_trust":
                await peer_controller.peer_do(invite_3a_claimer_signify_trust, tb.claimer_sock)

            elif order == "3b_wait_peer_trust":
                await peer_controller.peer_do(invite_3b_claimer_wait_peer_trust, tb.claimer_sock)

            elif order == "4_communicate":
                assert step_4_payload is not None
                await peer_controller.peer_do(
                    invite_4_claimer_communicate, tb.claimer_sock, payload=step_4_payload
                )

            else:
                assert False

    greeter_ctlr = PeerControler()
    claimer_ctlr = PeerControler()
    greeter_privkey = PrivateKey.generate()
    claimer_privkey = PrivateKey.generate()

    invitation = await backend.invite.new_for_device(
        organization_id=alice.organization_id,
        greeter_user_id=alice.user_id,
        created_on=datetime(2000, 1, 2),
    )
    async with backend_invited_sock_factory(
        backend,
        organization_id=alice.organization_id,
        invitation_type=invitation.TYPE,
        token=invitation.token,
        # claimer gets it connection closed if invitation is deleted
        freeze_on_transport_error=False,
    ) as claimer_sock:

        async with trio.open_nursery() as nursery:
            tb = ExchangeTestBed(
                organization_id=alice.organization_id,
                greeter=alice,
                invitation=invitation,
                greeter_privkey=greeter_privkey,
                claimer_privkey=claimer_privkey,
                greeter_ctlr=greeter_ctlr,
                claimer_ctlr=claimer_ctlr,
                greeter_sock=alice_backend_sock,
                claimer_sock=claimer_sock,
            )
            nursery.start_soon(_run_greeter, tb)
            nursery.start_soon(_run_claimer, tb)
            yield tb

            nursery.cancel_scope.cancel()