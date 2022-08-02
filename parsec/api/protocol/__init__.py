# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

from typing import TYPE_CHECKING
from parsec.api.protocol.base import (
    ProtocolError,
    MessageSerializationError,
    InvalidMessageError,
    packb,
    unpackb,
    api_typed_msg_adapter,
    any_cmd_req_factory,
)
from parsec.api.protocol.types import (
    UserID,
    DeviceID,
    DeviceName,
    OrganizationID,
    HumanHandle,
    UserIDField,
    DeviceIDField,
    DeviceNameField,
    OrganizationIDField,
    HumanHandleField,
    UserProfileField,
    UserProfile,
    DeviceLabelField,
    DeviceLabel,
    StrBased,
)
from parsec.api.protocol.handshake import (
    HandshakeError,
    HandshakeFailedChallenge,
    HandshakeBadAdministrationToken,
    HandshakeBadIdentity,
    HandshakeOrganizationExpired,
    HandshakeRVKMismatch,
    HandshakeRevokedDevice,
    HandshakeOutOfBallparkError,
    HandshakeAPIVersionError,
    ServerHandshake,
    HandshakeType,
    BaseClientHandshake,
    AuthenticatedClientHandshake,
    InvitedClientHandshake,
    APIV1_HandshakeType,
    APIV1_AnonymousClientHandshake,
)
from parsec.api.protocol.organization import (
    organization_bootstrap_serializer,
    apiv1_organization_bootstrap_serializer,
    organization_bootstrap_webhook_serializer,
    organization_stats_serializer,
    organization_config_serializer,
    UsersPerProfileDetailItemSchema,
)
from parsec.api.protocol.events import (
    events_subscribe_serializer,
    events_listen_serializer,
    APIEvent,
)
from parsec.api.protocol.ping import ping_serializer
from parsec.api.protocol.user import (
    user_get_serializer,
    user_create_serializer,
    user_revoke_serializer,
    device_create_serializer,
    human_find_serializer,
)
from parsec.api.protocol.invite import (
    InvitationToken,
    InvitationTokenField,
    InvitationType,
    InvitationTypeField,
    InvitationDeletedReason,
    InvitationStatus,
    InvitationStatusField,
    invite_new_serializer,
    invite_delete_serializer,
    invite_list_serializer,
    invite_info_serializer,
    invite_1_claimer_wait_peer_serializer,
    invite_1_greeter_wait_peer_serializer,
    invite_2a_claimer_send_hashed_nonce_serializer,
    invite_2a_greeter_get_hashed_nonce_serializer,
    invite_2b_greeter_send_nonce_serializer,
    invite_2b_claimer_send_nonce_serializer,
    invite_3a_greeter_wait_peer_trust_serializer,
    invite_3a_claimer_signify_trust_serializer,
    invite_3b_claimer_wait_peer_trust_serializer,
    invite_3b_greeter_signify_trust_serializer,
    invite_4_greeter_communicate_serializer,
    invite_4_claimer_communicate_serializer,
    InvitationEmailSentStatus,
)
from parsec.api.protocol.message import message_get_serializer
from parsec.api.protocol.realm import (
    RealmID,
    RealmIDField,
    RealmRole,
    RealmRoleField,
    MaintenanceType,
    MaintenanceTypeField,
    realm_create_serializer,
    realm_status_serializer,
    realm_stats_serializer,
    realm_get_role_certificates_serializer,
    realm_update_roles_serializer,
    realm_start_reencryption_maintenance_serializer,
    realm_finish_reencryption_maintenance_serializer,
)
from parsec.api.protocol.block import (
    BlockID,
    BlockIDField,
    block_create_serializer,
    block_read_serializer,
    BlockReadReq,
    BlockReadRep,
    BlockReadRepType,
    _PyBlockReadReq,
)
from parsec.api.protocol.vlob import (
    VlobID,
    VlobIDField,
    vlob_create_serializer,
    vlob_read_serializer,
    vlob_update_serializer,
    vlob_poll_changes_serializer,
    vlob_list_versions_serializer,
    vlob_maintenance_get_reencryption_batch_serializer,
    vlob_maintenance_save_reencryption_batch_serializer,
)
from parsec.api.protocol.pki import (
    PkiEnrollmentStatus,
    PkiEnrollmentStatusField,
    pki_enrollment_submit_serializer,
    pki_enrollment_info_serializer,
    pki_enrollment_list_serializer,
    pki_enrollment_reject_serializer,
    pki_enrollment_accept_serializer,
)
from parsec.api.protocol.sequester import SequesterServiceID, SequesterServiceIDField
from parsec.api.protocol.cmds import AUTHENTICATED_CMDS, INVITED_CMDS, APIV1_ANONYMOUS_CMDS


AuthenticatedAnyCmdReq = any_cmd_req_factory("AuthenticatedAnyCmdReq", _PyBlockReadReq)

_PyAuthenticatedAnyCmdReq = AuthenticatedAnyCmdReq
if not TYPE_CHECKING:
    try:
        from libparsec.types import AuthenticatedAnyCmdReq as _RsAuthenticatedAnyCmdReq
    except:
        pass
    else:
        AuthenticatedAnyCmdReq = _RsAuthenticatedAnyCmdReq


__all__ = (
    "ProtocolError",
    "MessageSerializationError",
    "InvalidMessageError",
    "packb",
    "unpackb",
    "api_typed_msg_adapter",
    "HandshakeError",
    "HandshakeFailedChallenge",
    "HandshakeBadAdministrationToken",
    "HandshakeBadIdentity",
    "HandshakeOrganizationExpired",
    "HandshakeRVKMismatch",
    "HandshakeRevokedDevice",
    "HandshakeOutOfBallparkError",
    "HandshakeAPIVersionError",
    "ServerHandshake",
    "HandshakeType",
    "BaseClientHandshake",
    "AuthenticatedClientHandshake",
    "InvitedClientHandshake",
    "APIV1_HandshakeType",
    "APIV1_AnonymousClientHandshake",
    # Types
    "UserID",
    "DeviceID",
    "DeviceName",
    "OrganizationID",
    "HumanHandle",
    "UserIDField",
    "DeviceIDField",
    "DeviceNameField",
    "OrganizationIDField",
    "HumanHandleField",
    "UserProfileField",
    "UserProfile",
    "DeviceLabelField",
    "DeviceLabel",
    "StrBased",
    # Organization
    "organization_bootstrap_serializer",
    "apiv1_organization_bootstrap_serializer",
    "organization_bootstrap_webhook_serializer",
    "organization_stats_serializer",
    "organization_config_serializer",
    "UsersPerProfileDetailItemSchema",
    # Events
    "events_subscribe_serializer",
    "events_listen_serializer",
    "APIEvent",
    # Ping
    "ping_serializer",
    # User
    "user_get_serializer",
    "user_create_serializer",
    "user_revoke_serializer",
    "device_create_serializer",
    "human_find_serializer",
    # Invite
    "InvitationToken",
    "InvitationTokenField",
    "InvitationType",
    "InvitationTypeField",
    "InvitationDeletedReason",
    "InvitationStatus",
    "InvitationStatusField",
    "InvitationEmailSentStatus",
    "invite_new_serializer",
    "invite_delete_serializer",
    "invite_list_serializer",
    "invite_info_serializer",
    "invite_1_claimer_wait_peer_serializer",
    "invite_1_greeter_wait_peer_serializer",
    "invite_2a_claimer_send_hashed_nonce_serializer",
    "invite_2a_greeter_get_hashed_nonce_serializer",
    "invite_2b_greeter_send_nonce_serializer",
    "invite_2b_claimer_send_nonce_serializer",
    "invite_3a_greeter_wait_peer_trust_serializer",
    "invite_3a_claimer_signify_trust_serializer",
    "invite_3b_claimer_wait_peer_trust_serializer",
    "invite_3b_greeter_signify_trust_serializer",
    "invite_4_greeter_communicate_serializer",
    "invite_4_claimer_communicate_serializer",
    # Message
    "message_get_serializer",
    # Realm
    "RealmID",
    "RealmIDField",
    "RealmRole",
    "RealmRoleField",
    "MaintenanceType",
    "MaintenanceTypeField",
    "realm_create_serializer",
    "realm_status_serializer",
    "realm_stats_serializer",
    "realm_get_role_certificates_serializer",
    "realm_update_roles_serializer",
    "realm_start_reencryption_maintenance_serializer",
    "realm_finish_reencryption_maintenance_serializer",
    # Vlob
    "VlobID",
    "VlobIDField",
    "vlob_create_serializer",
    "vlob_read_serializer",
    "vlob_update_serializer",
    "vlob_poll_changes_serializer",
    "vlob_list_versions_serializer",
    "vlob_maintenance_get_reencryption_batch_serializer",
    "vlob_maintenance_save_reencryption_batch_serializer",
    # Block
    "BlockID",
    "BlockIDField",
    "block_create_serializer",
    "block_read_serializer",
    "BlockReadReq",
    "BlockReadRep",
    "BlockReadRepType",
    # PKI enrollment
    "PkiEnrollmentStatus",
    "PkiEnrollmentStatusField",
    "pki_enrollment_submit_serializer",
    "pki_enrollment_info_serializer",
    "pki_enrollment_list_serializer",
    "pki_enrollment_reject_serializer",
    "pki_enrollment_accept_serializer",
    # Sequester
    "SequesterServiceID",
    "SequesterServiceIDField",
    # List of cmds
    "AUTHENTICATED_CMDS",
    "INVITED_CMDS",
    "APIV1_ANONYMOUS_CMDS",
    "AuthenticatedAnyCmdReq",
)
