# Early monkey patches


def _monkeypatch_parsec_version() -> None:
    # Globally patch parsec version to add `+resana`
    import parsec._version

    version = parsec._version.__version__
    parsec._version.__version__ = f"{version}+resana"


def _monkeypatch_user_agent() -> None:
    from ._version import __version__
    import parsec.api.transport
    import parsec.core.backend_connection.proxy

    USER_AGENT = f"resana-secure/{__version__}"
    parsec.api.transport.USER_AGENT = USER_AGENT
    parsec.core.backend_connection.proxy.USER_AGENT = USER_AGENT


_monkeypatch_user_agent()
_monkeypatch_parsec_version()
