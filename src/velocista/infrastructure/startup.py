"""Arranque de contenedor: migra antes de aceptar tráfico, un proceso para el hub WS."""

import os

import uvicorn
from alembic import command
from alembic.config import Config


def main():
    command.upgrade(Config("alembic.ini"), "head")
    uvicorn.run(
        "velocista.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        workers=1,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
