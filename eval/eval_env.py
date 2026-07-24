"""Hermetic device environment shared by synthetic replay and evaluation."""

import os


_AMBIENT_CREDENTIAL_VARS_TO_REMOVE = (
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
)


def subprocess_env(corpus_dir, home_dir=None):
    """Return an isolated KIO device environment rooted in the corpus.

    The synthetic `--all-scopes` registry must never discover a developer's real
    scopes, and the replay must never use ambient API credentials.
    """
    root = os.path.join(os.path.abspath(corpus_dir), ".kio-eval-device")
    home = (
        os.path.abspath(home_dir)
        if home_dir is not None
        else os.path.join(root, "home")
    )
    config = os.path.join(root, "config")
    data = os.path.join(root, "data")
    cache = os.path.join(root, "cache")
    for path in (home, config, data, cache):
        os.makedirs(path, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "HOME": home,
        "XDG_CONFIG_HOME": config,
        "XDG_DATA_HOME": data,
        "XDG_CACHE_HOME": cache,
    })
    for name in tuple(env):
        # Every KIO override/test seam is opt-in at the individual call site.
        # Inheriting even an unknown future KIO_* value would make a synthetic
        # device depend on the developer shell (clock, delays, faults, limits,
        # adapter mocks, registry behavior, and metrics paths have all used
        # this namespace).
        if name.startswith("KIO_"):
            env.pop(name, None)
    for name in _AMBIENT_CREDENTIAL_VARS_TO_REMOVE:
        env.pop(name, None)
    return env
