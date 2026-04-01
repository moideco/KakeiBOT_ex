import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    EXPENSE_CHANNEL_ID: int = int(os.getenv("EXPENSE_CHANNEL_ID", "0"))
    REPORT_CHANNEL_ID: int = int(os.getenv("REPORT_CHANNEL_ID", "0"))

    SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "")
    GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

    # 日次レポートの時刻 (JST, 24h)
    DAILY_REPORT_HOUR: int = int(os.getenv("DAILY_REPORT_HOUR", "21"))
    DAILY_REPORT_MINUTE: int = int(os.getenv("DAILY_REPORT_MINUTE", "0"))

    # 週次レポートの時刻 (JST, 24h, 日曜日に送信)
    WEEKLY_REPORT_HOUR: int = int(os.getenv("WEEKLY_REPORT_HOUR", "20"))
    WEEKLY_REPORT_MINUTE: int = int(os.getenv("WEEKLY_REPORT_MINUTE", "0"))

    # 月次レポートの時刻 (JST, 24h, 毎月1日に送信)
    MONTHLY_REPORT_HOUR: int = int(os.getenv("MONTHLY_REPORT_HOUR", "9"))
    MONTHLY_REPORT_MINUTE: int = int(os.getenv("MONTHLY_REPORT_MINUTE", "0"))

    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))

    TIMEZONE: str = "Asia/Tokyo"

    # サポートする通貨 (JPY / USD)
    SUPPORTED_CURRENCIES: tuple[str, ...] = ("JPY", "USD")
    DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "JPY")
