"""Public CLI entrypoint; implementation lives in parser and commands."""
from catalyst._compat import forward_module as _forward
from . import commands as _commands, parser as _parser

_forward(__name__, {
    "create_harness": _commands,
    "model_access_input": _commands,
    "model_access_notice": _commands,
    "remote_command": _commands,
    "build_parser": _parser,
    "dispatch": _commands,
    "main": _commands,
    "sys": _commands,
})
