# Problem set

Each challenge owns one directory containing its description, release manifests,
knowledge-base catalogs, scaffolds, verifiers and runtime asset mapping.
Shared loading and preparation code lives in [`../challenge/`](../challenge/).

[`ecdsa-fail/`](ecdsa-fail/) contains the ECDSA challenge. This compatibility branch
retains the hosted evaluator's unversioned problem identity and 50-paper library.
It does not include the retired v0 release. File moves preserve manifest contents
and the runtime paths assigned by the asset mapping.
