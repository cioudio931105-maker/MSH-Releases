# User-supplied models

MSH includes no weights and never downloads a fallback. Select an existing local
detection model in the GUI. Without a model MSH can start, but AI recognition
is unavailable. CLI and training commands require local model files.

Local training remains supported; data, labels, weights and outputs stay outside
Git. Research presets describe paths, not included models. Supply your own label
lists if required. No particular model name or hash is required to build MSH.

`msh_release_model.py` and `RELEASE_MODEL_v0.1.1.md` are historical identity records
for earlier review artifacts only; they do not authorize bundling a model today.
See [the application-only policy](../docs/APPLICATION_ONLY_POLICY.md).
