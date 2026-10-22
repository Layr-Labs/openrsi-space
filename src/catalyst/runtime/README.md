# Container entrypoints

These files are copied into prepared Docker runs. `launch.py` starts an executable
harness; `problem_server.py` serves the assigned read-only task and resources.
Keep their filesystem and HTTP contracts stable when reorganizing Python modules.
