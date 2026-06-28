"""Harness wiring for the python-sdk examples — NOT part of the SDK surface.

The comparison docs (sdk-comparisons/*.md) show each example connecting to the
*default* daemon with `IPCClient.session(profile={"model": "gpt-4o",
"provider": "openai"})`. To run these end-to-end against a real model on this
host, every example connects instead to a **dedicated** GLM daemon (its own
socket, pid, log, WS port — never the live bot's). That connection target is
the only thing centralised here; the SDK call shape inside each example file
(`IPCClient.session(...)`, `s.ask/complete/stream`, `client_tools=`,
`on_permission=`, `cascade_driver_id=`) is reproduced verbatim from the doc.

Usage in an example::

    from _config import CONN
    async with IPCClient.session(**CONN, profile={...}) as s:
        ...

`**CONN` supplies only `socket_path` / `workspace_path` / `env_file` — the
dedicated-daemon coordinates. Spin the daemon up with `./daemon.sh start`.
"""

import os

# Absolute path to this project dir, so examples run from anywhere.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# The dedicated test daemon (see daemon.sh). Isolated from the live telegram
# bot (:8089 / its own socket) and from /tmp/jaato-glm.sock (the kb's).
SOCKET = "/tmp/jaato-examples.sock"

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

# The programmatic profile the docs write inline as
# {"model": "gpt-4o", "provider": "openai"}. The examples keep that dict inline
# and visible (faithful shape); this constant exists only for the README to
# point at when explaining the substitution.
MODEL = "glm-5-turbo"
PROVIDER = "zhipuai"
