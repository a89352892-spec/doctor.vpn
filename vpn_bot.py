import os
import re
import socket
import time
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ КОНФИГУРАЦИЯ ============
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_IDS = [7891125109]

# ============ ПАРСИНГ КОНФИГОВ ============

def parse_config(link):
    link = link.strip()
    
    if link.startswith('vless://'):
        try:
            parts = link.split('@')
            uuid = parts[0].replace('vless://', '')
            host_part = parts[1].split('?')[0]
            if ':' in host_part:
                host, port = host_part.split(':')
                port = int(port)
            else:
                host = host_part
                port = 443
            return {'type': 'VLESS', 'host': host, 'port': port, 'uuid': uuid[:8] + '...', 'full': link}
        except:
            return None
    
    if link.startswith('vmess://'):
        try:
            import base64
            encoded = link.replace('vmess://', '')
            encoded += '=' * (4 - len(encoded) % 4)
            decoded = base64.b64decode(encoded).decode('utf-8')
            data = json.loads(decoded)
            host = data.get('add', '')
            port = int(data.get('port', 443))
            return {'type': 'VMess', 'host': host, 'port': port, 'uuid': data.get('id', '')[:8] + '...', 'full': link}
        except:
            return None
    
    if link.startswith('ss://'):
        try:
            import base64
            content = link.replace('ss://', '')
            if '@' in content:
                parts = content.split('@')
                host_part = parts[1]
                if ':' in host_part:
                    host, port = host_part.split(':')
                    port = int(port)
                else:
                    host = host_part
                    port = 443
                return {'type': 'Shadowsocks', 'host': host, 'port': port, 'uuid': 'SS', 'full': link}
        except:
            return None
    
    if link.startswith('trojan://'):
        try:
            content = link.replace('trojan://', '')
            if '@' in content:
                parts = content.split('@')
                host_part = parts[1]
                if ':' in host_part:
                    host, port = host_part.split(':')
                    port = int(port)
                else:
                    host = host_part
                    port = 443
                return {'type': 'Trojan', 'host': host, 'port': port, 'uuid': 'Trojan', 'full': link}
        except:
            return None
    
    if link.startswith('hysteria2://'):
        try:
            content = link.replace('hysteria2://', '')
            if '@' in content:
                parts = content.split('@')
                host_part = parts[1].split('?')[0]
                if ':' in host_part:
                    host, port = host_part.split(':')
                    port = int(port)
                else:
                    host = host_part
                    port = 443
                return {'type': 'Hysteria2', 'host': host, 'port': port, 'uuid': 'H2', 'full': link}
        except:
            return None
    
    return None

def check_port(host, port, timeout=3):
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        end = time.time()
        sock.close()
        
        if result == 0:
            ping = int((end - start) * 1000)
            return True, ping
        return False, None
    except:
        return False, None

def check_multiple(links, max_workers=10):
    results = []
    parsed_links = []
    
    for link in links:
        parsed = parse_config(link)
        if parsed:
            parsed_links.append(parsed)
        else:
            results.append({
                'type': 'Неизвестный',
                'host': 'Ошибка парсинга',
                'port': '?',
                'alive': False,
                'ping': None,
                'error': True,
                'full': link[:50] + '...'
            })
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_parsed = {
            executor.submit(check_port, p['host'], p['port']): p 
            for p in parsed_links
        }
        
        for future in as_completed(future_to_parsed):
            parsed = future_to_parsed[future]
            alive, ping = future.result()
            results.append({
                'type': parsed['type'],
                'host': parsed['host'],
                'port': parsed['port'],
                'alive': alive,
                'ping': ping if alive else None,
                'uuid': parsed.get('uuid', ''),
                'error': False,
                'full': parsed['full']
            })
    
    return results

def format_report(results, source):
    alive = [r for r in results if r.get('alive')]
    dead = [r for r in results if not r.get('alive')]
    errors = [r for r in results if r.get('error', False)]
    
    alive_sorted = sorted(alive, key=lambda x: x.get('ping') or 9999)
    
    report = f"📡 *Отчёт по проверке VPN серверов*\n"
    report += f"📂 *Источник:* {source}\n"
    report += f"⏰ *Время:* {time.strftime('%d.%m.%Y %H:%M:%S')}\n"
    report += f"{'─' * 30}\n"
    
    report += f"\n📊 *Статистика:*\n"
    report += f"🟢 ✅ Живых: {len(alive)}\n"
    report += f"🔴 ❌ Мёртвых: {len(dead)}\n"
    report += f"🟡 ⚠️ Ошибок: {len(errors)}\n"
    report += f"📌 Всего: {len(results)}\n"
    
    if alive_sorted:
        report += f"\n🏆 *Лучшие сервера (по пингу):*\n"
        for i, r in enumerate(alive_sorted[:10], 1):
            emoji = '⚡' if r.get('ping', 999) < 50 else '🌐'
            type_emoji = {
                'VLESS': '🔹',
                'VMess': '🔸',
                'Shadowsocks': '🔹',
                'Trojan': '🔹',
                'Hysteria2': '🔹'
            }.get(r['type'], '📦')
            
            report += f"  {i}. {type_emoji} *{r['host']}*:{r['port']} | {emoji} {r['ping']}мс | {r['type']}"
            if r.get('uuid'):
                report += f" | ID: {r['uuid']}"
            report += "\n"
        
        if len(alive_sorted) > 10:
            report += f"\n  ... и ещё {len(alive_sorted) - 10} серверов\n"
    
    if dead:
        report += f"\n🔴💀 *Мёртвые сервера (первые 5):*\n"
        for r in dead[:5]:
            report += f"  • {r['host']}:{r['port']} ({r['type']})\n"
        if len(dead) > 5:
            report += f"  ... и ещё {len(dead) - 5}\n"
    
    if errors:
        report += f"\n🟡⚠️ *Ошибки парсинга:* {len(errors)}\n"
    
    if alive:
        report += f"\n📥 *Живые ссылки (копируй):*"
        for r in alive[:3]:
            if r['full'].startswith('vless://') or r['full'].startswith('vmess://'):
                short = r['full'][:60] + '...' if len(r['full']) > 60 else r['full']
                report += f"\n`{short}`"
        if len(alive) > 3:
            report += f"\n... всего {len(alive)} живых серверов"
    
    return report

# ============ КОМАНДЫ БОТА ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🩺 *Doctor VPN Checker*\n\n"
        f"Я проверяю VPN сервера на доступность!\n\n"
        f"📌 *Команды:*\n"
        f"/check - проверить ссылки\n"
        f"/check_file - проверить 30days.txt\n"
        f"/stats - статистика\n"
        f"/help - помощь\n\n"
        f"📎 *Как использовать:*\n"
        f"1. Отправь мне VLESS/VMess ссылки\n"
        f"2. Или используй /check в ответ на сообщение\n"
        f"3. Получи отчёт с результатами",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🩺 *Doctor VPN Checker - помощь*\n\n"
        f"📌 *Команды:*\n"
        f"/start - приветствие\n"
        f"/check <ссылки> - проверить ссылки\n"
        f"/check_file - проверить 30days.txt\n"
        f"/stats - статистика\n"
        f"/help - эта справка\n\n"
        f"📎 *Поддерживаемые форматы:*\n"
        f"• VLESS (vless://...)\n"
        f"• VMess (vmess://...)\n"
        f"• Shadowsocks (ss://...)\n"
        f"• Trojan (trojan://...)\n"
        f"• Hysteria2 (hysteria2://...)\n\n"
        f"💡 *Пример:*\n"
        f"`/check vless://uuid@host:port`",
        parse_mode='Markdown'
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "Пользователь"
    
    text = update.message.text or ''
    args = text.split(maxsplit=1)
    links_text = args[1] if len(args) > 1 else ''
    
    if not links_text and update.message.reply_to_message:
        reply_msg = update.message.reply_to_message
        links_text = reply_msg.text or reply_msg.caption or ''
    
    if not links_text:
        await update.message.reply_text(
            f"📎 *Отправь ссылки для проверки*\n\n"
            f"Используй `/check vless://...`\n"
            f"Или ответь на сообщение со ссылками командой `/check`",
            parse_mode='Markdown'
        )
        return
    
    links = []
    for line in links_text.split('\n'):
        line = line.strip()
        if line and (line.startswith('vless://') or line.startswith('vmess://') or 
                     line.startswith('ss://') or line.startswith('trojan://') or 
                     line.startswith('hysteria2://')):
            links.append(line)
    
    if not links:
        await update.message.reply_text(
            f"🔴 ❌ *Не найдено ни одной ссылки!*",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await update.message.reply_text(
        f"🔍 *Проверяю {len(links)} серверов...*\n⏳ Подождите 5-10 секунд",
        parse_mode='Markdown'
    )
    
    try:
        results = check_multiple(links)
        source = f"Команда /check (от {user_name})"
        report = format_report(results, source)
        
        await status_msg.edit_text(
            report,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        await status_msg.edit_text(
            f"🔴 ❌ *Ошибка:*\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def check_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f"🔴 ❌ *Доступ запрещён*\nЭта команда только для администратора",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await update.message.reply_text(
        f"🔍 *Загружаю и проверяю 30days.txt...*\n⏳ Подождите",
        parse_mode='Markdown'
    )
    
    try:
        url = "https://raw.githubusercontent.com/a89352892-spec/doctor.vpn/main/30days.txt"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            await status_msg.edit_text(
                f"🔴 ❌ *Не удалось загрузить файл*\nКод ошибки: {response.status_code}",
                parse_mode='Markdown'
            )
            return
        
        links = []
        for line in response.text.split('\n'):
            line = line.strip()
            if line.startswith('vless://'):
                links.append(line)
        
        if not links:
            await status_msg.edit_text(
                f"🟡 ⚠️ *В файле не найдено VLESS ссылок*",
                parse_mode='Markdown'
            )
            return
        
        await status_msg.edit_text(
            f"🔍 *Проверяю {len(links)} серверов из 30days.txt...*\n⏳ Подождите 15-30 секунд",
            parse_mode='Markdown'
        )
        
        results = check_multiple(links, max_workers=20)
        alive = [r for r in results if r.get('alive')]
        
        source = f"30days.txt (GitHub)"
        report = format_report(results, source)
        
        await status_msg.edit_text(
            report,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        if alive:
            alive_links = [r['full'] for r in alive]
            alive_text = '# Живые сервера из 30days.txt\n'
            alive_text += f'# Количество: {len(alive_links)}\n'
            alive_text += f'# Дата: {time.strftime("%d.%m.%Y %H:%M:%S")}\n\n'
            alive_text += '\n'.join(alive_links)
            
            with open('alive_temp.txt', 'w', encoding='utf-8') as f:
                f.write(alive_text)
            
            with open('alive_temp.txt', 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f'alive_{int(time.time())}.txt',
                    caption=f"✅ {len(alive)} живых серверов"
                )
            os.remove('alive_temp.txt')
        
    except Exception as e:
        await status_msg.edit_text(
            f"🔴 ❌ *Ошибка:*\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    stats_text = f"""
📊 *Статистика бота*

👤 Ваш ID: `{user_id}`
📅 Активен с: {time.strftime('%d.%m.%Y')}

📌 *Доступные команды:*
/check - проверить ссылки
/check_file - проверить 30days.txt
/stats - эта статистика
/help - помощь
    """
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ''
    
    links = []
    for line in text.split('\n'):
        line = line.strip()
        if line and (line.startswith('vless://') or line.startswith('vmess://') or 
                     line.startswith('ss://') or line.startswith('trojan://') or 
                     line.startswith('hysteria2://')):
            links.append(line)
    
    if not links:
        return
    
    status_msg = await update.message.reply_text(
        f"🔍 *Найдено {len(links)} ссылок, проверяю...*\n⏳ Подождите",
        parse_mode='Markdown'
    )
    
    try:
        results = check_multiple(links)
        source = "Сообщение пользователя"
        report = format_report(results, source)
        
        await status_msg.edit_text(
            report,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        await status_msg.edit_text(
            f"🔴 ❌ *Ошибка:*\n`{str(e)}`",
            parse_mode='Markdown'
        )

# ============ ЗАПУСК ============

def main():
    print("""
╔═══════════════════════════════════════════╗
║     🩺 DOCTOR VPN BOT                    ║
║     Проверка серверов в Telegram         ║
╚═══════════════════════════════════════════╝
    """)
    
    # Токен берётся из секретов GitHub
    if not TOKEN:
        print("❌ ОШИБКА: Токен не найден в секретах GitHub!")
        print("   Добавь секрет TELEGRAM_TOKEN в настройках репозитория")
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("check_file", check_file))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен! Напиши /start в Telegram")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("check_file", check_file))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен! Напиши /start в Telegram")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
