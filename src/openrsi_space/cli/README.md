# CLI

`parser.py` defines command arguments. `commands.py` dispatches to the client,
harness tools and integrations. `openrsi_space.cli:main` remains the installed entrypoint;
keep protocol and execution logic in their owning modules.
