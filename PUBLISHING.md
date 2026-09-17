# Publishing to the Comfy Registry

This pack is published from its own repository
(https://github.com/mccaffrey-jonathan/ComfyUI-DurableWatermark) to https://registry.comfy.org,
which ComfyUI-Manager and the ComfyUI desktop app install from.

## One-time setup

1. Sign in at https://registry.comfy.org and create a **publisher**. Note its id
   (for example `mccaffrey-jonathan`).
2. Put that id in `pyproject.toml` under `[tool.comfy].PublisherId`.
3. In the registry, create an **API key** for the publisher.
4. In this GitHub repository: *Settings → Secrets and variables → Actions* and add
   a secret named `REGISTRY_ACCESS_TOKEN` with the API key.

## Releasing a version

1. Bump `[project].version` in `pyproject.toml` (semantic versioning).
2. Commit and push to `main`. The workflow in `.github/workflows/publish.yml`
   (Comfy-Org/publish-node-action) runs whenever `pyproject.toml` changes on `main`
   and uploads the new version. It can also be started by hand from the Actions tab.
3. Watch the run; the registry rejects duplicate versions and packs that fail its
   security scan (no `eval`, no downloads at import time, no subprocesses).

To publish manually instead: `pip install comfy-cli`, then in the pack directory
`comfy node publish` (it prompts for the API key).

## Also listing in ComfyUI-Manager's legacy catalogue

Open a pull request against https://github.com/ltdrdata/ComfyUI-Manager adding this
repository URL to `custom-node-list.json`. The registry listing is picked up
automatically by current Manager versions, so this is optional.

## Checks before a release

- `python -m pytest -q` passes (the Tests workflow runs it on Python 3.10 and 3.12).
- `requirements.txt` matches `[project].dependencies`.
- No secrets, certificates or generated files are tracked (`config/` is git-ignored).
- `README.md` links point at the standalone repositories, not at paths inside a ComfyUI checkout.
