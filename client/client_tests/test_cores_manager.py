from parsec.core.types import BackendAddr

from resana_secure.cores_manager import is_org_hosted_on_rie


def test_is_org_hosted_on_rie():
    without_port_addr = BackendAddr("domain.com", None, False)
    with_port_addr = BackendAddr("domain.com", 1337, False)

    assert is_org_hosted_on_rie(without_port_addr, [("otherdomain.com", None)]) is False
    assert is_org_hosted_on_rie(without_port_addr, [("otherdomain.com", 1337)]) is False
    assert is_org_hosted_on_rie(without_port_addr, [("domain.com", 4242)]) is False
    assert is_org_hosted_on_rie(without_port_addr, [("domain.com", None)]) is True
    assert is_org_hosted_on_rie(without_port_addr, [("domain.com", 1337)]) is False

    assert is_org_hosted_on_rie(with_port_addr, [("otherdomain.com", None)]) is False
    assert is_org_hosted_on_rie(with_port_addr, [("otherdomain.com", 1337)]) is False
    assert is_org_hosted_on_rie(with_port_addr, [("domain.com", 4242)]) is False
    assert is_org_hosted_on_rie(with_port_addr, [("domain.com", None)]) is True
    assert is_org_hosted_on_rie(with_port_addr, [("domain.com", 1337)]) is True
