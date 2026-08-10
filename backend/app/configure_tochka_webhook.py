import asyncio

from app.core.config import get_settings
from app.payments.tochka import TochkaPaymentService


async def configure() -> None:
    settings = get_settings()
    callback_url = f"{settings.web_frontend_url.rstrip('/')}/api/v1/payments/tochka/webhook"
    await TochkaPaymentService(settings).configure_webhook(callback_url)
    print(f"Tochka webhook configured: {callback_url}")


if __name__ == "__main__":
    asyncio.run(configure())
