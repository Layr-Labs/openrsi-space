# Dungeness integration

`local.py` coordinates local runs; `agent.py` installs the executable harness;
`managed_runtime.py` owns the tested default revision and atomic download cache;
explicit `--dungeness` checkouts remain user-managed. `runtime_contract.py` checks
required capabilities. `legacy.py` recognizes older
runtime capabilities. Assigned challenge resources are assembled in `challenge/`.
