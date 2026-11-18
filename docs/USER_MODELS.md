# User-supplied models

MSH includes no weights and never downloads a fallback. Select an existing local
detection model in the GUI. Without a model MSH can start, but AI recognition
is unavailable. CLI and training commands require local model files.

Local training remains supported; data, labels, weights and outputs stay outside
Git. Research presets describe paths, not included models. Supply your own label
lists if required. No particular model name or hash is required to build MSH.

See [the application-only policy](APPLICATION_ONLY_POLICY.md).
Historical v0.1.1 identity metadata is archived under `docs/legacy/model-release-v0.1.1/`;
it is not imported by the application and is not permission to bundle a model.
