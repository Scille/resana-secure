# Early monkey patches


def _monkeypatch_user_agent():
    from ._version import __version__
    import parsec.api.transport
    import parsec.core.backend_connection.transport

    USER_AGENT = f"antivirus-connector/{__version__}"
    parsec.api.transport.USER_AGENT = USER_AGENT
    parsec.core.backend_connection.transport.USER_AGENT = USER_AGENT


_monkeypatch_user_agent()
