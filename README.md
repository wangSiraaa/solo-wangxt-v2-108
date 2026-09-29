# RoastLog · 咖啡烘焙批次过程记录与对比

面向烘焙负责人的**过程记录**工具：记录与比较豆温（BT）、环境温度（ET）和操作事件，
**不**用成品评分替代过程数据。系统使用合成数据，**不连接真实烘焙机**。

- 后端：FastAPI + NumPy + SQLAlchemy（PostgreSQL 驱动 `psycopg`，本地默认 SQLite）
- 前端：Svelte 4 + ECharts 5 + Vite
- 存储内容：原始采样、下豆点/回温点/一爆/出锅等锚点、风门变化与人工标记（含修正历史）

## 核心数据原则

1. **原始采样不可变**：`samples` 表只存探针实测读数（含跳变点，标记 `quality=spike`
   但绝不静默清洗）。任何平滑、窗口、插值参数的改变都只产生新的派生数组，
   测试 `test_raw_samples_identical_regardless_of_window` 与 HTTP 行为均验证这一点。
2. **温升率（RoR）窗口是显式声明的**：采用 **末端（trailing）线性回归窗口**
   `[t−W, t]` 对**实测点**最小二乘拟合，斜率 ×60 得 °C/min。要求窗口内实测锚点
   ≥4 个且覆盖 ≥50% 窗口长度，否则该点 RoR 为空——探针失联后复出的首个点因此天然为空。
   每次响应都带回 `ror_method`（窗口秒数、锚点数、覆盖率），图表标题也标注窗口。
3. **插值段不冒充实测**：短失联（默认严格小于 12s）在显示序列中做线性插值并逐点标记
   `origin=interpolated`（虚线）；达到/超过阈值的失联标记 `origin=missing` 并以 NaN
   断线（灰带）。插值点**不参与** RoR 拟合，也不参与指标计算。阈值设为 0 表示一律不插值。
4. **事件人工修正保留来源**：锚点（下豆/回温点/一爆/出锅）修正时旧行置
   `is_current=false` 但保留，新行以 `supersedes_id` 指向旧行，记录
   `source(auto/manual)`、`operator`、`note`、`method`；可恢复历史版本。
   回温点检测器只产出**算法建议**，须操作员确认才成为记录。
5. **发展时间比按明确区间计算**，时间零点 = 下豆：
   - 干燥区间 = 回温点 − 下豆
   - 梅纳区间 = 一爆 − 回温点
   - 发展区间 = 出锅 − 一爆
   - **DTR = (出锅 − 一爆) / (出锅 − 下豆)**
   锚点缺失或顺序非法时指标返回空并给出错误，绝不猜测。
6. **双批次对比不宣称因果**：两批次按各自下豆后的秒数对齐并置，风门区间以色块标注，
   页面与接口均带观察性免责声明。

## 目录

```
backend/
  app/            FastAPI 应用
    signals.py    NumPy：缺测识别/插值标记/窗口 RoR/回温点检测
    metrics.py    阶段区间与 DTR
    synthetic.py  含噪声、非均匀采样、失联、跳变的合成批次
    services.py   序列装配、人工修正（supersedes 链）
    exporters.py  JSON 复现包 / CSV
  tests/          21 项 pytest
  scripts/reproduce.py  仅凭导出包 + NumPy 独立复现全部指标
frontend/
  src/
    lib/charts.js ECharts 配置（实测实线/插值虚线/失联灰带/事件线/风门色块）
    views/        BatchView（单批次）、CompareView（双批次）
docker-compose.yml  PostgreSQL + API
```

## 本地运行（SQLite，零外部依赖）

```bash
# 后端
pip install -r backend/requirements.txt
cd backend && python3 -m uvicorn app.main:app --reload --port 8000
# 首次启动自动建表并播种 2 个合成批次

# 前端（开发热更新，自动代理 /api）
cd frontend && npm install && npm run dev
```

或直接使用已构建的前端（FastAPI 托管 `frontend/dist`）：

```bash
cd frontend && npm install && npm run build
# 重启后端后访问 http://localhost:8000
```

## 使用 PostgreSQL

```bash
cp backend/.env.example backend/.env       # 按需修改
export DATABASE_URL=postgresql+psycopg://roast:roast@localhost:5432/roastlog
# 或一键：
docker compose up --build
```

## API 摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/batches` | 批次列表 |
| GET | `/api/batches/{id}?ror_window_s=&max_interp_gap_s=` | 原始采样、显示序列、RoR、事件、指标 |
| POST | `/api/batches/{id}/events` | 新增/修正事件（`operator` 必填） |
| POST | `/api/events/{id}/revert?operator=` | 恢复历史锚点版本（留痕） |
| GET | `/api/compare?a=&b=` | 双批次并置（含观察性免责声明） |
| GET | `/api/batches/{id}/export.json` | **复现包**：原始采样+事件历史+窗口参数+指标 |
| GET | `/api/batches/{id}/export/{samples\|events}.csv` | CSV 导出 |

## 复现所有阶段指标

```bash
curl -s http://localhost:8000/api/batches/1/export.json -o bundle.json
python3 backend/scripts/reproduce.py bundle.json
```

脚本只读导出包和 NumPy：用当前生效锚点重算四个区间与 DTR，用 `raw_samples`
与声明的窗口参数重算全部 RoR 点并逐点比对。

## 测试

```bash
cd backend && python3 -m pytest
```

覆盖：已知斜率的 RoR 恢复、缺口复出 RoR 为空、插值/留空标记、
**改窗口参数原始温度逐位不变**、跳变点保留、事件修正来源链、
非法/缺失锚点报错、API 全流程、导出包独立复现。

## 合成数据设计

- 采样基线 2s ± 0.45s 抖动（**非均匀**）
- 白噪声（BT σ≈0.55°C，ET σ≈0.85°C）+ 慢漂移
- 批次 A：1 段短失联（插值）+ 1 段较长失联（留空）；批次 B：2 短 + 1 段约 30s 长失联
- 个别跳变读数保留并标 `spike`
- 两批次风门调整时刻不同（A 在回温后 120s，B 在回温前 45s），供并置观察
