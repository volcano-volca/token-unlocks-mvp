# Unlock Radar · 代币解锁看板（MVP）

一个最小可用的代币解锁数据看板：每天自动抓取公开解锁日历，展示临近解锁事件。

## 在线看

直接用浏览器打开 `index.html` 即可（数据文件 `data/unlocks.json` 需同目录）。

## 项目结构

```
token-unlocks-mvp/
├── index.html          # 看板页面（纯静态，无构建步骤）
├── data/
│   └── unlocks.json    # 解锁数据（每日更新生成）
├── scripts/
│   └── update.py       # 每日更新脚本：抓取 Dropstab 公开页 → 生成 unlocks.json
└── README.md
```

## 每日更新

```bash
python3 scripts/update.py --top 30
```

建议用 cron 每天跑一次。脚本逻辑：
1. 抓 `dropstab.com/vesting` 列表页（50 个有临近解锁的币种）
2. 按市值取前 N 个，逐个抓详情页内嵌 JSON，提取带日期的解锁事件
3. 生成 `data/unlocks.json`

## 数据说明

- **来源**：Dropstab 公开页面整理，仅供参考，不构成投资建议；关键事件以项目官方披露为准。
- **覆盖边界（重要）**：免费数据源只覆盖"有临近解锁"的币种（约 50 个，多为中小市值）；主流大币种若无临近解锁不会出现在列表中。全覆盖需要付费 API（Tokenomist Pro $69/月起 / CryptoRank Pro）。
- **解锁≠卖出**：解锁只是"可以卖"，实际抛压取决于解锁后资金流向（是否转入交易所）。

## MVP 验证目标（3 个月）

1. 有没有人持续看（访问量）
2. 数据准不准（抽查解锁事件 vs 官方公告）
3. 用户愿不愿意为"更全/更准"付费（决定是否升级付费数据源）

## 下一步（如果验证通过）

- 接入付费 API（Tokenomist/CryptoRank），覆盖全币种
- 加"解锁后抛售追踪"（地址追踪，解锁≠卖出的闭环）
- 回购/销毁数据（Tokenomist 正在做的方向）
- 邮件/Telegram 预警推送
