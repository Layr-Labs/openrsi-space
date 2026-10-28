# Dependency downloads during builds

Before submitting, inspect the hosted builder's current policy without uploading
source or credentials:

```sh
uv run catalyst remote build-policy
```

The result lists the enabled profiles and allowed hosts, with a version and digest.
`include_subdomains: false` means only that exact host is allowed. Hosted defaults
cover common container/OS/source repositories, Python, Node.js/npm/NodeSource and
Rust releases/crates. Operators may configure a narrower set; the live response is
authoritative. The same data is available at `GET /public/build-policy`.

Pin dependencies and retain signature/hash verification. If a needed host is absent,
use a supported source or ask the operator to review adding it. A successful local
build does not prove that the hosted network policy permits every dependency.
Research containers still have no general internet access.

A failed remote build may report `BUILD_DEPENDENCY_HOST_BLOCKED`,
`BUILD_DEPENDENCY_ADDRESS_BLOCKED`, `BUILD_DEPENDENCY_PORT_BLOCKED`,
`BUILD_DEPENDENCY_DNS_FAILED` or `BUILD_DEPENDENCY_CONNECT_FAILED`, along with the
hostname and evaluation ID. Share these diagnostics with the operator. They are
observations from the proxy, not a definitive explanation of every build failure.
No research model calls begin during a failed build.
