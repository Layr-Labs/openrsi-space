# Problem set

Versioned challenge content consumed by [`../challenge/`](../challenge/): problem
manifests, descriptions, paper catalogs, scaffolds and verifier bundles.

`initial.json` and `initial-v0.json` select the published releases.
`runtime-assets.json` maps trusted runtime paths to the packaged assets under
`ecdsa-fail/`. Only assets selected by the assigned problem are installed.

These files define challenge content and execution behavior. Changes to pinned
content require the corresponding version and compatibility review. Shared
loading, validation and preparation logic belongs in `challenge/`.
