import sys
import db
from orchestrator import Orchestrator

def main():
    db.init()
    orch = Orchestrator()

    if len(sys.argv) < 2:
        print("Usage: python main.py [preflight|start|stop|status]")
        return

    cmd = sys.argv[1]

    if cmd == "preflight":
        ok = orch.preflight()
        sys.exit(0 if ok else 1)

    elif cmd == "start":
        if not orch.preflight():
            sys.exit(1)
        ok = orch.start()
        sys.exit(0 if ok else 1)

    elif cmd == "stop":
        ok = orch.stop()
        sys.exit(0 if ok else 1)

    elif cmd == "status":
        orch.status()

    else:
        print(f"Unknown: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
