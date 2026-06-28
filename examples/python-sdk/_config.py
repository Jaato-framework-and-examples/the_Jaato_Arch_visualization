"""Harness wiring for the python-sdk examples — NOT part of the SDK surface.

The comparison docs (sdk-comparisons/*.md) show each example connecting to the
*default* daemon with `IPCClient.session(profile={"model": "gpt-4o",
"provider": "openai"})`. To run these end-to-end against a real model on this
host, every example connects instead to a **dedicated** daemon (its own socket,
pid, log, WS port — so it won't collide with any other jaato daemon on the host)
running an OpenRouter model. Two
things are centralised here — the connection target (`CONN`) and the provider
auth knob (`AUTH`) — because both are pure harness, not SDK shape; the SDK call
shape inside each example file (`IPCClient.session(...)`, `s.ask/complete/stream`,
`client_tools=`, `on_permission=`, `cascade_driver_id=`) is reproduced verbatim.

Usage in an example::

    from _config import CONN, AUTH
    async with IPCClient.session(**CONN, profile={
            "model": MODEL, "provider": PROVIDER, "plugins": [], **AUTH}) as s:
        ...

`**CONN` supplies `socket_path` / `env_file`; `**AUTH` supplies the provider's
`pass:` credential knob. Spin the daemon up with `./daemon.sh start`.
"""

import os

# Absolute path to this project dir, so examples run from anywhere.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# The dedicated test daemon (see daemon.sh). A dedicated socket so it won't
# collide with any other jaato daemon on the host.
SOCKET = "/tmp/jaato-examples.sock"

# Provider credential, supplied as a `pass:` resolver knob of the provider
# plugin (NOT an env var, NOT a tracked secret) — the daemon's credential
# resolver reads plugin_configs.<provider>.api_key and resolves the pass:// URI
# from the password store at session creation. `explain provider openrouter`
# shows the resolution order (api_key_param:api_key → env → stored); `explain
# profile` documents secret URIs on the value resolver. Inline-spec examples
# spread `**AUTH` into the profile dict; declarative profiles carry the same
# knob in their JSON.
AUTH = {"plugin_configs": {"openrouter": {"api_key": "pass://jaato/openrouter/api-key"}}}

# Connection kwargs forwarded to {IPCClient,IPCRecoveryClient}.session(...) by
# EVERY example. Just the daemon coordinates — `env_file` (absolute, so
# `python exNN_*.py` works from any cwd) names the provider+model; the socket
# is the dedicated daemon. The docs pass neither, but they also assume the
# default daemon + openai creds; these are the minimal additions to retarget.
#
# NB workspace_path is deliberately NOT here. The docs never pass it, and only
# the *declarative* examples (ex03/04/08/09) need it — to make the daemon
# resolve ./.jaato/ assets — so they pass `workspace_path=WORKSPACE` explicitly.
# Keeping it out of CONN also avoids a real SDK type-inconsistency: IPCClient
# treats workspace_path as a str (cwd), but IPCRecoveryClient feeds it to
# _find_config_files which does `workspace_path / ".jaato"` (config.py:166) and
# crashes on a str. (Flagged to the SDK owners; the programmatic recovery
# example ex10 simply doesn't pass it.)
CONN = dict(
    socket_path=SOCKET,
    env_file=os.path.join(PROJECT_DIR, ".env"),
)

# Declarative examples pass this so the daemon reads personas / profiles /
# completion schemas / reactors from <PROJECT_DIR>/.jaato/.
WORKSPACE = PROJECT_DIR

# The docs write the inline profile as {"model": "gpt-4o", "provider": "openai"}.
# The examples keep that dict inline and visible (faithful shape) but substitute
# the locally-reachable OpenRouter model. `google/gemini-2.5-flash` is cheap and
# reliable for tool-calling + completion gates (what ex04/05/07/08/09 lean on),
# These constants exist for the README to
# point at when explaining the substitution.
MODEL = "google/gemini-2.5-flash"
PROVIDER = "openrouter"
