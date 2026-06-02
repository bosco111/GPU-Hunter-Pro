# GPU-Hunter-Pro v1.2.0

Multi-platform GPU auto-scanner and rental script.

## Supported Platforms
- RunPod (https://console.runpod.io)
- PrimeIntellect (https://app.primeintellect.ai)
- Vast (https://console.vast.ai)
- Clore (https://clore.ai)

## Features
- Auto-scan all 4 platforms simultaneously
- Price range filtering (min/max per GPU type)
- Auto-rental when price matches
- Telegram notifications
- Colored terminal UI with box-drawing
- No external dependencies (Python stdlib only)

## Quick Start
```bash
python3 gpu_hunter_pro.py
```

## Non-interactive Mode
```bash
python3 gpu_hunter_pro.py --no-prompt   --runpod-key "KEY" --vast-key "KEY"   --price-4090 0.50 --price-4090-min 0.15   --price-5090 0.80
```

## Dry-Run (test without ordering)
```bash
python3 gpu_hunter_pro.py --dry-run --once   --runpod-key "KEY" --price-4090 0.50
```

## Environment Variables
- `RUNPOD_API_KEY` - RunPod API Key
- `PRIME_API_KEY` - PrimeIntellect API Key
- `VAST_API_KEY` - Vast API Key
- `CLORE_API_KEY` - Clore API Key
- `TELEGRAM_BOT_TOKEN` - Telegram Bot Token
- `TELEGRAM_CHAT_ID` - Telegram Chat ID
