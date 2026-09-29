"""数据库表结构：只存原始采样与事件记录，不存任何被平滑/插值篡改的温度。"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 阶段锚点事件：同一批次同一时刻仅保留一条 current（人工修正会让旧记录失效）
ANCHOR_EVENT_TYPES = {"charge", "turn", "first_crack", "drop"}
# 过程事件：允许多条并存（风门调整序列、人工观察标记）
POINT_EVENT_TYPES = {"damper", "marker"}
EVENT_TYPES = ANCHOR_EVENT_TYPES | POINT_EVENT_TYPES
EVENT_SOURCES = {"auto", "manual"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    profile_name: Mapped[str] = mapped_column(String(128))
    bean_origin: Mapped[str] = mapped_column(String(128), default="")
    charge_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_drop_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    roast_date: Mapped[str] = mapped_column(String(32), default="")
    description: Mapped[str] = mapped_column(String(512), default="")
    # 合成数据参数（仅用于复现实验，真实机台连接不在本系统范围内）
    synth_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    samples: Mapped[list["Sample"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class Sample(Base):
    """原始采样：一行 = 探针在 t_s 时刻的一次实测读数，永不就地改写。"""

    __tablename__ = "samples"
    __table_args__ = (UniqueConstraint("batch_id", "t_s", name="uq_sample_t"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), index=True
    )
    # 相对下豆时刻的秒数（下豆 = 0）
    t_s: Mapped[float] = mapped_column(Float)
    bean_temp_c: Mapped[float] = mapped_column(Float)
    env_temp_c: Mapped[float] = mapped_column(Float)
    # ok = 正常实测；spike = 探针跳变但仍如实保留，不静默清洗
    quality: Mapped[str] = mapped_column(String(16), default="ok")

    batch: Mapped[Batch] = relationship(back_populates="samples")


class Event(Base):
    """下豆点/回温点/一爆/出锅/风门/人工标记。

    人工修正不删除旧记录：旧行 is_current=False，新行 supersedes_id 指向旧行，
    source/method/operator/note 全部保留作为来源审计。
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    event_time: Mapped[float] = mapped_column(Float)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    operator: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(String(512), default="")
    # 检测器/合成设计的算法说明，例如 {"detector":"windowed_ls","window_s":30}
    method: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id"), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    batch: Mapped[Batch] = relationship(back_populates="events")
