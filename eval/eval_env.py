"""Hermetic device environment shared by synthetic replay and evaluation."""

import os


_CREDENTIAL_AND_TEST_VARS = (
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KCS_TEST_GEMINI_EMBED",
    "KCS_TEST_MISTRAL_OCR",
    "KCS_TEST_MARKDOWNIZE_ADAPTER",
)


def subprocess_env(corpus_dir):
    """Return an isolated KCS device environment rooted in the corpus.

    The synthetic `--all-scopes` registry must never discover a developer's real
    scopes, and the replay must never use ambient API credentials.
    """
    root = os.path.join(os.path.abspath(corpus_dir), ".kcs-eval-device")
    config = os.path.join(root, "config")
    data = os.path.join(root, "data")
    cache = os.path.join(root, "cache")
    for path in (config, data, cache):
        os.makedirs(path, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "XDG_CONFIG_HOME": config,
        "XDG_DATA_HOME": data,
        "XDG_CACHE_HOME": cache,
    })
    for name in _CREDENTIAL_AND_TEST_VARS:
        env.pop(name, None)
    return env
