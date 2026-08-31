#!/usr/bin/env python3
"""Tiny installed-command dispatcher; importing enables Python bytecode caching."""

import sys


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "menu"
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    if target == "agent":
        import agent
        agent.main()
    elif target == "menu":
        import menu
        menu.main()
    else:
        raise SystemExit("unknown AgentBoot launcher target: %s" % target)


if __name__ == "__main__":
    main()
