#!/usr/bin/env python3
"""Redeploy a Portainer stack while preserving its stored configuration."""

import json
import os
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


portainer_url = os.environ["PORTAINER_URL"].rstrip("/")
api_token = os.environ["PORTAINER_API_TOKEN"]
stack_name = os.environ["PORTAINER_STACK_NAME"]


def request_json(path: str, *, method: str = "GET", payload: dict | None = None) -> dict | list:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{portainer_url}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_token,
        },
    )
    context = ssl._create_unverified_context() if os.environ.get("PORTAINER_INSECURE_TLS") == "1" else None

    try:
        with urlopen(request, context=context) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"Portainer returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not connect to Portainer: {error.reason}") from error


try:
    stacks = request_json("/api/stacks")
    stack = next((item for item in stacks if item["Name"] == stack_name), None)
    if stack is None:
        raise RuntimeError(f"Portainer stack '{stack_name}' was not found.")

    stack_id = stack["Id"]
    endpoint_id = stack["EndpointId"]
    stack_file = request_json(f"/api/stacks/{stack_id}/file")
    stack_detail = request_json(f"/api/stacks/{stack_id}")

    request_json(
        f"/api/stacks/{stack_id}?endpointId={endpoint_id}",
        method="PUT",
        payload={
            "StackFileContent": stack_file["StackFileContent"],
            "Env": stack_detail.get("Env", []),
            "Prune": stack_detail.get("Option", {}).get("Prune", False),
            "RepullImageAndRedeploy": True,
        },
    )
except (KeyError, RuntimeError) as error:
    print(f"Portainer redeploy failed: {error}", file=sys.stderr)
    sys.exit(1)

print(f"Portainer stack '{stack_name}' redeploy requested.")
