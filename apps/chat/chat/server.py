import logging

import uvicorn
from fastapi import FastAPI

from chat.api import create_app


def create_server(app: FastAPI, host: str = "0.0.0.0", port: int = 8000) -> uvicorn.Server:
    return uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            workers=1,
            ws="websockets",
            ws_ping_interval=20.0,
            ws_ping_timeout=20.0,
        )
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    create_server(create_app()).run()


if __name__ == "__main__":
    main()
