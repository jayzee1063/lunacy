# Lunacy Tickets Bot

Discord-бот для тикетов Lunacy:

- заявки на проходку;
- жалобы;
- предложения;
- заявки на вознаграждения;
- одобрение проходки с добавлением ника в whitelist через RCON;
- выдача Discord-роли после одобрения.

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

## Важно

Файл `.env` содержит токен Discord и RCON-пароль. Его нельзя загружать в GitHub.
