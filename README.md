# Orqella module index

A small, curated index of installable Orqella modules. The daemon reads this
file to offer one-click installation in **Settings → General → Install module**
without asking the user for a repository URL, branch, or release asset.

The index is a single static JSON file:

```text
index.json
```

Only modules whose git repository or release archive is publicly installable
belong here. Private first-party modules stay out of the public index until they
are published.

Published URL (default in Orqella):

```text
https://raw.githubusercontent.com/orqella/orqella-module-index/main/index.json
```

There is no server component. `index.json` is validated in CI and intended to be
served over HTTPS or consumed from a pinned local mirror.

## What the index guarantees

Every distribution pins the exact module contents:

- **Git distributions** pin an immutable `commit` and the deterministic
  `tree_sha256` of the module files. The daemon clones the commit, computes the
  tree digest with the same algorithm used by module signing, and refuses a
  mismatch.
- **Archive distributions** pin the archive `sha256`, and the extracted module
  tree `tree_sha256`. The daemon verifies both before installing.

The index does not replace permission review. Sensitive module permissions
(`backend`, `agent`, `media.record`, `app.open`, and proxy mounts) still require
explicit approval in **Settings → Modules**.

## File format

```json
{
  "schema": 1,
  "updated_at": "2026-11-22T00:00:00Z",
  "modules": [
    {
      "id": "system",
      "name": "System",
      "description": "Live host metrics, the Network Universe, and system services.",
      "category": "System",
      "tags": ["metrics", "network"],
      "publisher": {
        "name": "Orqella",
        "url": "https://orqella.io"
      },
      "official": true,
      "homepage": "https://github.com/orqella/orqella-system",
      "license": "MIT",
      "node_scope": "node",
      "permissions": ["node.metrics", "nodes.read", "backend", "agent"],
      "versions": [
        {
          "version": "0.3.6",
          "api_version": "1",
          "released_at": "2026-11-17",
          "notes_url": "https://github.com/orqella/orqella-system/commit/bcbad2f4387026cb576ed91a8344fe018dc54157",
          "distributions": [
            {
              "platforms": [
                "linux-x86_64",
                "linux-aarch64",
                "macos-x86_64",
                "macos-aarch64",
                "windows-x86_64",
                "windows-aarch64"
              ],
              "source": {
                "type": "git",
                "url": "https://github.com/orqella/orqella-system",
                "ref": "main",
                "commit": "bcbad2f4387026cb576ed91a8344fe018dc54157"
              },
              "tree_sha256": "3e39e506ec729598d08a1dbeca3e03ca29c4ddd8834fd90805c2420975be8d12",
              "backend": {
                "kind": "sidecar",
                "compiled": false,
                "platforms": [
                  "linux-x86_64",
                  "linux-aarch64",
                  "macos-x86_64",
                  "macos-aarch64",
                  "windows-x86_64",
                  "windows-aarch64"
                ]
              }
            }
          ]
        }
      ]
    }
  ]
}
```

The canonical schema is [`index.schema.json`](index.schema.json).

### Sources

`source.type = "git"`:

| Field | Meaning |
| --- | --- |
| `url` | Public HTTPS git URL. |
| `ref` | Human-readable ref such as `main` or `v0.2.3`; informational only. |
| `commit` | Full commit SHA. This is the authoritative pin. |

The daemon clones `url`, checks out `commit`, then verifies `tree_sha256`.

`source.type = "archive"`:

| Field | Meaning |
| --- | --- |
| `url` | Public HTTPS archive URL. GitHub release assets are fine. |
| `format` | `zip` or `tar.gz`. |
| `sha256` | SHA-256 of the downloaded archive bytes. |
| `size` | Optional size in bytes for progress and a fast sanity check. |

The daemon downloads the archive, verifies `sha256`, extracts it, and verifies
`tree_sha256`.

### Platforms

Platform names use `<os>-<arch>` exactly as in a module manifest:

```text
linux-x86_64   linux-aarch64
macos-x86_64   macos-aarch64
windows-x86_64 windows-aarch64
```

`platforms` on a distribution lists where the module can run. Omit it when the
module works on every supported platform. The daemon ignores a version whose
distributions do not match the host.

`backend.platforms` lists where the module's sidecar works. `backend.compiled`
is `true` when the module ships prebuilt sidecar artifacts. A module can still be
installable on a platform where its backend is unavailable, but the daemon and
UI must degrade to the module's non-backend surfaces. Index entries should
usually restrict `platforms` to the platforms where the whole module is useful.

A compiled module can publish one archive per platform instead of a shared git
source:

```json
{
  "platforms": ["linux-x86_64", "macos-aarch64"],
  "source": {
    "type": "archive",
    "url": "https://github.com/acme/orqella-sidecar/releases/download/v1.2.0/orqella-sidecar-linux-x86_64.zip",
    "format": "zip",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "size": 18432000
  },
  "tree_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
  "backend": {
    "kind": "sidecar",
    "compiled": true,
    "platforms": ["linux-x86_64", "macos-aarch64"]
  }
}
```

The daemon selects the first distribution matching the host, verifies the
archive SHA-256, extracts it, and verifies the tree digest. A platform with no
matching distribution is shown as unavailable in Settings.

### Versions

`versions` is ordered newest first. The client selects the highest version whose
`api_version` matches the daemon and which has a distribution for the host
platform. `version` must match the `version` in the module's `module.toml`.

## Updating an entry

1. Tag or commit the module change.
2. Compute the tree digest at the exact ref:

   ```bash
   python3 scripts/tree_digest.py --repo https://github.com/orqella/orqella-system --ref main
   ```

   Or against a local checkout:

   ```bash
   python3 scripts/tree_digest.py --path ../modules/system --ref main
   ```

3. Copy the module's `id`, `name`, `description`, `permissions`, `node_scope`,
   version, and backend platform data from `module.toml`.
4. Add the new version at the top of the module's `versions` array. Keep older
   versions when clients might still be on an older daemon API.
5. Run `python3 scripts/validate.py`.
6. Commit and push `index.json`. Orqella fetches the file directly; no deploy
   step is required.

## Trust

This repository is the curation point. A distribution digest is the daemon's
integrity check, so protect the default branch and review changes to
`index.json` like code. Modules are still installed as ordinary module
repositories and remain subject to permission review.

The Orqella installer runs `orqella setup`, which installs the official
`agent-harness` entry and grants its declared first-party access. That
auto-grant is limited to the exact official index URL, `official = true`, and
the module's known permission set (`backend`, `storage`, `app.open`, `fs.pick`).
A custom `index_url` never auto-grants. All other modules, and any permission
added later, still start with sensitive grants pending.

The daemon can point at another index with `[modules] index_url` in
`config.toml`, for private mirrors or testing.

## License

MIT. See [`LICENSE`](LICENSE).
