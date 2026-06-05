# CSIE5452 Final Project — CAN Bus Scheduling Analysis

CAN 匯流排排程分析工具，實作 Tindell WCRT 理論公式與離散事件模擬，並輸出反應時間對照圖與匯流排甘特圖。

---

## 專案結構

```
can-project/
├── can_scheduling.py   # 核心分析：WCRT 公式 + 模擬 + 繪圖
├── main.py             # 程式進入點
├── pyproject.toml      # 專案依賴定義
├── uv.lock             # 鎖定版本（確保所有人環境相同，必須 commit）
├── .python-version     # 指定 Python 3.12
└── .gitignore
```

> `.venv/` 虛擬環境**不進版控**。每個人在自己電腦上用 `uv sync` 產生即可。

---

## 環境需求

| 工具 | 版本 | 說明 |
|------|------|------|
| Python | 3.12+ | |
| uv | 最新版 | 套件與虛擬環境管理器 |

---

## 安裝 uv

### macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安裝完後重開終端機，確認：

```bash
uv --version
```

### Windows（PowerShell）

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安裝完後重開 PowerShell，確認：

```powershell
uv --version
```

---

## 第一次設定（Clone 後）

```bash
# 1. clone 專案
git clone git@github.com:lego1002/CSIE5452_final_project_CAN.git
cd CSIE5452_final_project_CAN/can-project

# 2. 建立虛擬環境並安裝依賴（uv.lock 保證版本一致）
uv sync
```

完成，虛擬環境自動建在 `.venv/`，不需要手動 activate。

---

## 執行程式

### macOS / Linux

```bash
uv run python can_scheduling.py
```

### Windows（PowerShell）

```powershell
uv run python can_scheduling.py
```

執行後會在同一資料夾產生：

| 檔案 | 內容 |
|------|------|
| `response_time_comparison.png` | 理論 WCRT 上界 vs 情境 A vs 情境 B 長條圖 |
| `bus_gantt.png` | 前 30 ms 匯流排甘特圖 |

---

## 新增套件

```bash
uv add <套件名稱>
```

加完後 `pyproject.toml` 與 `uv.lock` 都會自動更新，**請一起 commit**。

---

## 常見問題

**Q: `uv: command not found`**
重開終端機，或手動執行安裝腳本後再試。

**Q: Python 版本不對**
uv 會自動抓 `.python-version` 裡指定的 3.12，不需要手動切換。

**Q: 圖片沒跳出來**
圖片會存在資料夾裡，直接打開 `.png` 檔即可。macOS 上 `plt.show()` 需要有視窗環境（SSH 遠端連線下不會跳出）。
