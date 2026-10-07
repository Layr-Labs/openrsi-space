# Circuit smoke-test method

Read the provided task and ask the supplied model endpoint for a JSON circuit.
Use only the three-bit local circuit problem. Each gate is
`[control_a, control_b, target]` and performs a Toffoli operation.

Check the model's proposal on all eight inputs before writing `candidate.json`.
Write the candidate atomically and exit. The service independently verifies the
captured candidate; stdout does not establish its score.
