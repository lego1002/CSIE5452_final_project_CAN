# 協作規則

## 基本原則

- **`uv.lock` 一定要 commit**：這是確保所有人套件版本相同的唯一方式
- **`.venv/` 絕對不 commit**：每個人自己 `uv sync` 產生
- **`.png` 圖片不 commit**：執行程式後本地自動產生

---

## 每次開始工作前

```bash
git pull
uv sync        # 如果隊友有新增套件，這步會自動裝好
```

---

## Commit 規範

格式：`<類型>: <簡短說明>`

| 類型 | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `docs` | 只改文件 |
| `refactor` | 重構，不影響功能 |
| `chore` | 雜項（更新依賴、改設定） |

範例：
```
feat: 加入 Davis 修正公式
fix: 修正 WCRT 迭代收斂條件
docs: 更新 README 安裝步驟
chore: uv add numpy
```

---

## 新增套件的正確流程

```bash
uv add <套件名稱>
git add pyproject.toml uv.lock
git commit -m "chore: uv add <套件名稱>"
git push
```

**不要** 用 `pip install`，這樣隊友不會知道你裝了什麼。

---

## 推送流程

```bash
git add <你修改的檔案>
git commit -m "feat: 說明你做了什麼"
git pull --rebase   # 先拉，避免衝突
git push
```

---

## 分支策略（簡單版）

- `main`：隨時保持可執行狀態
- 做大改動時，開新分支：`git checkout -b feat/你的功能名稱`
- 完成後發 Pull Request，讓另一人 review 再 merge
