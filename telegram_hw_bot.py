import os
import logging
import asyncio
import csv

from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters


import openai

print("=== ENV DEBUG ===")
for k in ("BOT_TOKEN", "OPENAI_API_KEY"):
    print(k, repr(os.environ.get(k)))
print("=================")

# ------------------------------------------------------------
# 🗂️  Конфигурация
# ------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "ir_homework_log.csv")

openai.api_key = OPENAI_API_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

assert BOT_TOKEN, "BOT_TOKEN пустой"
assert OPENAI_API_KEY, "OPENAI_API_KEY пустой"
logger.info("Токены загружены, длины: %d / %d", len(BOT_TOKEN), len(OPENAI_API_KEY))

# ------------------------------------------------------------
# 💾  Работа с CSV‑файлом
# ------------------------------------------------------------

def ensure_log_file(path: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "timestamp_utc",
                    "telegram_id",
                    "username",
                    "fio",
                    "group",
                    "task_type",
                    "seminar_no",
                    "task_text",
                    "feedback",
                ]
            )
        logger.info("Создан новый лог‑файл %s", path)


def append_row_to_file(path: str, row: list[str]) -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

# ------------------------------------------------------------
# 🤖  Хэндлеры Telegram
# ------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Пришлите домашнее задание в формате:\n"
        "ФИО; группа (РГ1/РГ21/РГ22); тип (отработка/доп); № семинара; текст задания"
    )




async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    raw_text = update.message.text.strip()

    parts = [p.strip() for p in raw_text.split(";", maxsplit=4)]
    if len(parts) < 5:
        await update.message.reply_text(
            "⚠️ Неверный формат. Должно быть 5 полей, разделённых ‘;’."
        )
        return

    fio, group, task_type, seminar_no, task_text = parts

    feedback = await get_feedback(task_text)
    await update.message.reply_text(feedback)

    ensure_log_file(LOG_FILE_PATH)
    append_row_to_file(
        LOG_FILE_PATH,
        [
            datetime.now(timezone.utc).isoformat(),
            user.id,
            user.username or "—",
            fio,
            group,
            task_type,
            seminar_no,
            task_text,
            feedback,
        ],
    )

# ------------------------------------------------------------
# 🔮  Генерация фидбэка
# ------------------------------------------------------------

import functools

async def get_feedback(task: str) -> str:
    # оборачиваем sync‑метод в поток, чтобы не блокировать event‑loop
    response = await asyncio.to_thread(
        openai.ChatCompletion.create,
        model="gpt-4o",         
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ],
        max_tokens=300,
        temperature=0.4,
    )
    return response["choices"][0]["message"]["content"].strip()


# ------------------------------------------------------------
# 🏃‍♂️  Запуск приложения
# ------------------------------------------------------------

def main() -> None:
    if not (BOT_TOKEN and OPENAI_API_KEY):
        raise RuntimeError("BOT_TOKEN и OPENAI_API_KEY должны быть заданы!")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен. Ожидаю сообщения…")
    application.run_polling()          # ← синхронный, блокирующий вызов

if __name__ == "__main__":
    try:
        main()                         # без asyncio.run
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
