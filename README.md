# GPU-Hunter-Pro v1.2.0

> 多平台 GPU 自动扫描与租用脚本 | 纯 Python 标准库, 零依赖

## 支持平台

| 平台 | 官网 | 特点 |
|------|------|------|
| **RunPod** | console.runpod.io | 主流 GPU 云, 型号齐全 |
| **PrimeIntellect** | app.primeintellect.ai | 分布式训练, 按需实例 |
| **Vast** | console.vast.ai | 社区 GPU, 价格灵活 |
| **Clore** | clore.ai | 新兴市场, 支持多卡 |

## 功能特性

- 四平台并行扫描, 自动比价
- 价格区间过滤 (最低价 ~ 最高价/卡)
- 价格匹配自动下单
- Telegram 通知推送
- 彩色终端 UI (Tokyo Night 配色)
- 全 GPU 型号支持 (RTX 3090/4090/5090, A100, H100, L40S...)
- Dry-Run 测试模式
- 纯 Python 标准库, 无需安装依赖

## 快速开始

### 1. 克隆 & 运行

```bash
git clone https://github.com/bosco111/GPU-Hunter-Pro.git
cd GPU-Hunter-Pro
python3 gpu_hunter_pro.py
```

### 2. 交互模式 (推荐)

直接运行, 按提示配置:

```bash
python3 gpu_hunter_pro.py
```

交互向导会引导你完成:
1. 选择平台并输入 API Key
2. 设置价格区间 (最低 ~ 最高)
3. 配置容器 / Telegram / 扫描参数
4. 确认启动

### 3. 非交互模式

```bash
python3 gpu_hunter_pro.py --no-prompt   --runpod-key "YOUR_KEY"   --vast-key "YOUR_KEY"   --price-4090 0.50 --price-4090-min 0.15   --price-5090 0.80 --price-5090-min 0.25   --price-default 1.00   --telegram-bot-token "BOT_TOKEN"   --telegram-chat-id "CHAT_ID"
```

### 4. Dry-Run 测试

```bash
python3 gpu_hunter_pro.py --dry-run --once   --runpod-key "KEY" --price-4090 0.50
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
|  | 非交互模式 | - |
|  | 只查询不下单 | - |
|  | 只扫描一轮 | - |
|  | RunPod API Key | - |
|  | PrimeIntellect API Key | - |
|  | Vast API Key | - |
|  | Clore API Key | - |
|  | RTX 4090 最高价 | - |
|  | RTX 4090 最低价 | 0 |
|  | RTX 5090 最高价 | - |
|  | RTX 5090 最低价 | 0 |
|  | RTX 3090 最高价 | - |
|  | A100 最高价 | - |
|  | H100 最高价 | - |
|  | L40S 最高价 | - |
|  | 通用最高价 | - |
|  | 通用最低价 | 0 |
|  | 扫描间隔 (秒) | 30 |
|  | 最少 GPU 数量 | 1 |
|  | 最多 GPU 数量 | 8 |
|  | Docker 镜像 | pytorch:2.1.0-cuda12 |
|  | 磁盘大小 (GB) | 50 |
|  | SSH 密码 | 自动生成 |
|  | Telegram Bot Token | - |
|  | Telegram Chat ID | - |
|  | 只扫描指定平台 | 全部 |

## 环境变量

```bash
export RUNPOD_API_KEY="your_key"
export PRIME_API_KEY="your_key"
export VAST_API_KEY="your_key"
export CLORE_API_KEY="your_key"
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

## 价格区间示例

```bash
# RTX 4090: 只看 /usr/bin/bash.15 ~ /usr/bin/bash.50/hr/卡
--price-4090 0.50 --price-4090-min 0.15

# H100: 只看 .00 ~ .50/hr/卡
--price-h100 2.50 --price-h100-min 1.00

# 通用: 所有未单独设置的 GPU, 最高 .00
--price-default 1.00
```

## 安全提醒

- API Key 不要提交到 GitHub
- 使用环境变量或 .env 文件管理密钥
- 命令行传参可能留在 shell history, 建议用环境变量

## License

MIT
