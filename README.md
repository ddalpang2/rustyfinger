# rustyfinger

### Rust! So excited!

## Telegram Booli bot (trigger: "집")

This repo now includes a minimal Telegram bot script:

- File: `booli_telegram_bot.py`
- Trigger text: `집`
- Behavior: replies in the same chat with filtered Booli listings

### Conditions used

- Apartment (`Lägenhet`)
- Rooms: `3+`
- List price: `6,000,000 - 8,000,000 SEK`
- Areas:
  - Kungsholmen (with extra west/north and area exclusions)
  - Sofia (Sodermalm)
- Removes long-listed objects older than `90` days (configurable)
- Result buckets:
  - `<= 7.0M`
  - `7.0M-7.5M`
  - `7.5M-8.0M`
  - `기타`

### Setup

1. Export bot token:

```bash
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
```

2. Optional config:

```bash
export BOOLI_MAX_DAYS_ACTIVE=90
export BOOLI_KUNG_LON_MIN=18.017
export BOOLI_KUNG_LAT_MAX=59.3365
```

### Run

Process updates once and exit:

```bash
python3 booli_telegram_bot.py --once
```

Continuous polling:

```bash
python3 booli_telegram_bot.py
```

Dry-run (prints outgoing messages, no Telegram send):

```bash
python3 booli_telegram_bot.py --once --dry-run
```
