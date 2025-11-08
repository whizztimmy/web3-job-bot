import requests
from bs4 import BeautifulSoup
import dateparser
from datetime import datetime, timedelta
import schedule
import time
import threading
import os
import pytz
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# -------------------------------------------------
# 1. TIMEZONE (UTC+1) – 12 PM & 6 PM daily
# -------------------------------------------------
os.environ['TZ'] = 'Europe/Berlin'      # CET/CEST = UTC+1
time.tzset()

# -------------------------------------------------
# 2. API KEYS (YOUR KEYS ARE ALREADY HERE)
# -------------------------------------------------
GROK_API_KEY = 'xai-pr4BkVWfZ5c5dgb9fkiNXVYmpKNoVrxvL4h41Y4Y2pUY4Lalr5p89J8YcctdY7cPHtrl8FQkghSPTnRZ'
GROK_API_URL = 'https://api.x.ai/v1/chat/completions'

# YOUR TELEGRAM BOT TOKEN (already inserted)
TELEGRAM_TOKEN = '8355059848:AAF60ExRBClP3NQqHjEMzYvC0XPduZJu_pA'

# -------------------------------------------------
# 3. GLOBAL VARIABLES
# -------------------------------------------------
bot = Bot(token=TELEGRAM_TOKEN)
GROUP_CHAT_ID = None          # will be set when you /start the bot in the group

# -------------------------------------------------
# 4. JOB SITES TO SCRAPE
# -------------------------------------------------
SITES = [
    'https://web3.career/',
    'https://cryptojobslist.com/web3',
    'https://myweb3jobs.com/',
    'https://jobs.ton.org/jobs',
    'https://jobs.solana.com/jobs',
    'https://www.ethereumjobboard.com/'
]

# -------------------------------------------------
# 5. SCRAPING FUNCTION
# -------------------------------------------------
def fetch_recent_jobs(site):
    """Return list of job dicts posted in the last 24h (UTC+1)."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; Web3JobBot/1.0)'}
        r = requests.get(site, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        jobs = []
        now = datetime.now(pytz.timezone('Europe/Berlin'))
        cutoff = now - timedelta(hours=24)

        # === cryptojobslist.com ===
        if 'cryptojobslist.com' in site:
            for row in soup.select('tr'):
                time_el = row.select_one('td time')
                if not time_el or not time_el.get('datetime'):
                    continue
                posted_iso = time_el['datetime'].replace('Z', '+00:00')
                posted_dt = datetime.fromisoformat(posted_iso).astimezone(pytz.timezone('Europe/Berlin'))
                if posted_dt < cutoff:
                    continue

                title_a = row.select_one('a[href*="/jobs/"]')
                title = title_a.get_text(strip=True) if title_a else 'Untitled'
                link = 'https://cryptojobslist.com' + title_a['href'] if title_a else ''

                company_a = row.select_one('a[href*="/companies/"]')
                company = company_a.get_text(strip=True) if company_a else 'Unknown'

                loc_td = row.select_one('td:nth-of-type(3)') or row.select_one('td:nth-of-type(4)')
                location = loc_td.get_text(strip=True) if loc_td else 'Remote'

                jobs.append({
                    'title': title,
                    'company': company,
                    'location': location,
                    'posted': posted_dt.strftime('%Y-%m-%d %H:%M'),
                    'link': link
                })

        # === jobs.solana.com ===
        elif 'jobs.solana.com' in site:
            for card in soup.select('a[href*="/jobs/"]'):
                parent = card.find_parent(['div', 'li'])
                if not parent:
                    continue
                time_span = parent.select_one('span')
                if not time_span:
                    continue
                time_text = time_span.get_text(strip=True).lower()

                if 'today' in time_text:
                    posted_dt = now
                elif 'day' in time_text:
                    days = int(''.join(filter(str.isdigit, time_text)) or 1)
                    posted_dt = now - timedelta(days=days)
                else:
                    continue
                if posted_dt < cutoff:
                    continue

                title = card.get_text(strip=True)
                link = 'https://jobs.solana.com' + card['href']

                company_a = parent.select_one('a[href*="/companies/"]')
                company = company_a.get_text(strip=True) if company_a else 'Unknown'

                loc_span = parent.select_one('span')
                location = loc_span.get_text(strip=True) if loc_span else 'Remote'

                jobs.append({
                    'title': title,
                    'company': company,
                    'location': location,
                    'posted': posted_dt.strftime('%Y-%m-%d %H:%M'),
                    'link': link
                })

        # === Generic fallback (for other sites) ===
        else:
            for elem in soup.find_all(string=lambda t: t and ('ago' in t.lower() or 'today' in t.lower() or 'hour' in t.lower())):
                txt = elem.strip()
                parsed = dateparser.parse(txt, settings={'TIMEZONE': 'Europe/Berlin', 'RETURN_AS_TIMEZONE_AWARE': True})
                if parsed and parsed >= cutoff:
                    card = elem.find_parent(['div', 'li', 'tr'])
                    if not card:
                        continue
                    a = card.find('a', href=True)
                    title = a.get_text(strip=True) if a else txt
                    link = a['href'] if a and a['href'].startswith('http') else site.rstrip('/') + (a['href'] if a else '')
                    jobs.append({
                        'title': title,
                        'company': 'Unknown',
                        'location': 'Remote',
                        'posted': parsed.strftime('%Y-%m-%d %H:%M'),
                        'link': link
                    })

        return jobs

    except Exception as e:
        return [{'error': f'{site} → {str(e)}'}]


def get_all_recent_jobs():
    return {site: fetch_recent_jobs(site) for site in SITES}


def format_message(data):
    lines = ["*Daily Web3 Jobs (last 24h – UTC+1)*\n"]
    for site, jobs in data.items():
        lines.append(f"**{site.split('//')[-1].split('/')[0]}**")
        if not jobs or 'error' in jobs[0]:
            lines.append("  _No new jobs / error_")
        else:
            for j in jobs:
                lines.append(
                    f"• *{j['title']}*\n"
                    f"  _{j['company']}_ – {j['location']}\n"
                    f"  Posted: {j['posted']}\n"
                    f"  [Apply]({j['link']})\n"
                )
        lines.append("─" * 30)
    return "\n".join(lines)


# -------------------------------------------------
# 6. SEND FUNCTION
# -------------------------------------------------
def send_update():
    if not GROUP_CHAT_ID:
        print(f"{datetime.now(pytz.timezone('Europe/Berlin'))} – GROUP_CHAT_ID not set. Skipping.")
        return

    jobs = get_all_recent_jobs()
    msg = format_message(jobs)
    bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=msg,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    print(f"{datetime.now(pytz.timezone('Europe/Berlin'))} – Update sent to group {GROUP_CHAT_ID}")


# Schedule at 12:00 and 18:00 (UTC+1)
schedule.every().day.at("12:00").do(send_update)
schedule.every().day.at("18:00").do(send_update)


# -------------------------------------------------
# 7. BOT HANDLERS
# -------------------------------------------------
def start(update: Update, context: CallbackContext):
    global GROUP_CHAT_ID
    GROUP_CHAT_ID = update.message.chat_id
    update.message.reply_text(
        "Bot activated!\n"
        "I will post fresh Web3 jobs **twice daily** at **12:00 PM** and **6:00 PM** (UTC+1).\n"
        "No further commands needed."
    )
    print(f"Chat ID set: {GROUP_CHAT_ID}")


updater = Updater(TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, lambda u, c: None))


# -------------------------------------------------
# 8. SCHEDULER THREAD
# -------------------------------------------------
def scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    threading.Thread(target=scheduler_loop, daemon=True).start()
    print("Web3 Job Bot is running…\nAdd me to your group and type /start")
    updater.start_polling()
    updater.idle()
