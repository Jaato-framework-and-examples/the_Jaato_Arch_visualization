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

# Connection kwargs forwarded to IPCClient.session(...). `workspace_path` points
# the daemon at THIS dir so it resolves declarative assets from ./.jaato/
# (personas, profiles, completion schemas, reactors). `env_file` names the
# provider+model. Both are absolute so `python exNN_*.py` works from any cwd.
CONN = dict(
    socket_path=SOCKET,
    workspace_path=PROJECT_DIR,
    env_file=os.path.join(PROJECT_DIR, ".env"),
)

# The programmatic profile the docs write inline as
# {"model": "gpt-4o", "provider": "openai"}. The examples keep that dict inline
# and visible (faithful shape); this constant exists only for the README to
# point at when explaining the substitution.
MODEL = "glm-5-turbo"
PROVIDER = "zhipuai"
