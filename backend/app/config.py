"""运行配置。

DATABASE_URL 未设置时默认使用本地 SQLite，便于离线测试；
生产/容器环境通过环境变量指向 PostgreSQL，例如：
    postgresql+psycopg://roast:roast@db:5432/roastlog
"""
import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE = f"sqlite+pysqlite:///{_BACKEND_ROOT / 'data' / 'roast.db'}"


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = _env("DATABASE_URL", _DEFAULT_SQLITE)
    # 温升率（RoR）默认采用的末端线性回归窗口（秒）
    default_ror_window_s: float = float(_env("ROR_WINDOW_S", "30"))
    # 允许线性插值补绘的最大探针失联时长（秒）；严格小于该值才插值，达到或超过则留空断线
    default_max_interp_gap_s: float = float(_env("MAX_INTERP_GAP_S", "12"))
    ror_min_anchors: int = int(_env("ROR_MIN_ANCHORS", "4"))
    ror_min_coverage: float = float(_env("ROR_MIN_COVERAGE", "0.5"))
    seed_on_startup: bool = _env("SEED_ON_STARTUP", "true").lower() == "true"


settings = Settings()
