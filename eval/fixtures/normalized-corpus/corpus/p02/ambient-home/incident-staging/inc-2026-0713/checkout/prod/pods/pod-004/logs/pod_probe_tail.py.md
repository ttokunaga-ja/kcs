```py
#!/usr/bin/env python3
"""Print the latest Kubernetes probe events for a single gateway pod."""

from __future__ import annotations

import argparse
import subprocess


def kubectl_events(namespace: str, pod: str) -> str:
    command = [
        "kubectl",
        "--namespace",
        namespace,
        "get",
        "events",
        "--field-selector",
        f"involvedObject.name={pod}",
        "--sort-by=.lastTimestamp",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="checkout-prod")
    parser.add_argument("--pod", default="checkout-gateway-pod-004")
    parser.add_argument("--lines", type=int, default=12)
    args = parser.parse_args()

    tail = kubectl_events(args.namespace, args.pod).splitlines()[-args.lines :]
    print("\n".join(tail))


if __name__ == "__main__":
    main()
```
