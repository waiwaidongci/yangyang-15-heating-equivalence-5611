from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.constants.enums import Decision


class Credentials(BaseModel):
    email: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=128)


class CreateBatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    note: str = Field(default='', max_length=300)

    @field_validator('name')
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip():
            raise ValueError('请填写批次名称')
        return value.strip()


class TicketInput(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    segment: str = Field(min_length=1, max_length=60)
    kind: str = Field(default='initial', max_length=20)
    minutes: float | None = None
    inspected_on: str = Field(min_length=10, max_length=10)
    target_code: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=300)
    procedure: str | None = Field(default=None, max_length=8)


class TicketBatchInput(BaseModel):
    tickets: list[TicketInput] = Field(min_length=1, max_length=500)


class CreateRun(BaseModel):
    title: str = Field(max_length=120)
    parameters: dict = Field(default_factory=dict)

    @field_validator('title')
    @classmethod
    def meaningful_title(cls, value):
        if not value.strip():
            raise ValueError('请填写分析名称')
        return value.strip()


class ReviewInput(BaseModel):
    decision: Decision
    note: str = Field(min_length=2, max_length=1000)

    @field_validator('note')
    @classmethod
    def meaningful_note(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('请填写复核依据')
        return value.strip()


class ScheduleInput(BaseModel):
    run_id: int = Field(gt=0)
    recipient: str = Field(min_length=2, max_length=100)
    interval_minutes: int = Field(ge=1, le=10080)
    start_at: datetime | None = None

    @field_validator('recipient')
    @classmethod
    def meaningful_recipient(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('请填写收件组')
        return value.strip()

    @field_validator('start_at')
    @classmethod
    def absolute_time(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError('首次分发时间必须包含时区')
        return value
