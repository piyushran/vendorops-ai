import asyncio

from app.config.settings import get_settings
from app.workers.document_jobs import DocumentWorker, install_signal_handlers


async def main() -> None:
    worker = DocumentWorker(get_settings())
    install_signal_handlers(worker)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
