"""python -m happy --host 0.0.0.0 --port 8000"""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="Happy · local-first personal workspace"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Use 0.0.0.0 for containers or remote previews.",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("happy.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
