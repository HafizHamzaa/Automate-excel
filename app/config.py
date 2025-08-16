from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    phone_number_id: str = Field("", alias="WABA_PHONE_NUMBER_ID")
    verify_token: str = Field("", alias="WABA_VERIFY_TOKEN")
    permanent_token: str = Field("", alias="WABA_PERMANENT_TOKEN")
    template_ns: str = Field("", alias="WABA_TEMPLATE_NAMESPACE")

    owner_phone: str = Field("", alias="OWNER_PHONE_E164")
    timezone: str = Field("Asia/Riyadh", alias="TIMEZONE")

    excel_file: str = Field("./data/attendance_template.xlsx", alias="EXCEL_FILE")
    db_url: str = Field("sqlite:///./data/attendance.db", alias="DB_URL")


settings = Settings()