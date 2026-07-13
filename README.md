# Lunacy Tickets Bot

Discord-бот для тикетов Lunacy:

- заявки на проходку;
- жалобы;
- предложения;
- заявки на вознаграждения;
- одобрение проходки с добавлением ника в whitelist через RCON;
- выдача Discord-роли после одобрения;
- постоянная связь Discord ID с Minecraft-ником;
- автоматическое удаление ника из whitelist при выходе, кике или бане участника на Discord-сервере.

## Запуск

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Заполните `.env`, затем запустите:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Команды создания панелей

```text
/setup_pass_tickets
/setup_complaint_tickets
/setup_suggestion_tickets
/setup_reward_tickets
```

Запасные prefix-команды:

```text
!setup_pass_tickets
!setup_complaint_tickets
!setup_suggestion_tickets
!setup_reward_tickets
```

## Архив тикетов

Закрытые тикеты не удаляются: бот переносит их в категорию `CLOSED_TICKET_CATEGORY_ID` и забирает у автора доступ к просмотру канала.

## Синхронизация whitelist с Discord

После одобрения проходки бот сохраняет Discord ID и Minecraft-ник в локальной SQLite-базе `data/whitelist_links.sqlite3`. Если участник выходит, его кикают или банят на Discord-сервере, бот выполняет `UNWHITELIST_COMMAND_TEMPLATE` через RCON. По умолчанию используется команда `swl remove {nickname}`.

При запуске бот сверяет сохранённые связи с участниками Discord. Поэтому выход, произошедший во время отключения бота, будет обработан после запуска. Если RCON временно недоступен, связь не удаляется из базы и операция будет повторена при следующей сверке.

Для переноса уже одобренных участников в базу включён параметр `WHITELIST_BACKFILL_FROM_ACCEPTED_ROLE=true`: участники с ролью `ACCEPTED_ROLE_ID`, Discord-ник которых соответствует формату Minecraft-ника, автоматически запоминаются.

```env
UNWHITELIST_COMMAND_TEMPLATE=swl remove {nickname}
WHITELIST_LINKS_DB=data/whitelist_links.sqlite3
WHITELIST_BACKFILL_FROM_ACCEPTED_ROLE=true
WHITELIST_RECONCILE_INTERVAL_SECONDS=600
```

В Discord Developer Portal у бота должен быть включён privileged intent **Server Members Intent**. Без него Discord не отправляет надёжные события выхода участников и не позволяет выполнить полную сверку списка.

## Важно

Файл `.env` содержит токен Discord и RCON-пароль. Его нельзя загружать в GitHub.
