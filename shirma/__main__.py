import argparse
import logging

import uvicorn

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="shirma", description="Шлюз к LLM без персональных данных"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
