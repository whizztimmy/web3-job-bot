# Web3 Job Bot

Automated Telegram bot that scrapes and posts recent Web3 jobs (last 24 hours) from top sites twice daily (12 PM & 6 PM UTC+1).

## Features
- Scrapes: web3.career, cryptojobslist.com, myweb3jobs.com, jobs.ton.org, jobs.solana.com, ethereumjobboard.com
- Filters for jobs posted in the last 24 hours
- Posts formatted updates to your Telegram group
- Uses Grok AI for potential summaries (optional)

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Update `TELEGRAM_TOKEN` and `GROK_API_KEY` in `web3_job_bot.py` (already pre-filled in this repo)
3. Run: `python web3_job_bot.py`
4. Add bot to Telegram group and type `/start`

## Deployment
- **Local**: Run on your machine
- **24/7**: Deploy to Replit, Render, or Heroku (use as a background worker)

## License
MIT
