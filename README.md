# USDT/RUB Web App

FastAPI-приложение для расчёта по сырому тексту через функцию `format_transaction(text: str) -> str`.

## Локальный запуск

1. Установите зависимости:

```powershell
pip install -r requirements.txt
```

2. Запустите сервер:

```powershell
python start.py
```

3. Откройте в браузере:

```text
http://127.0.0.1:8000
```

## Деплой на Render

1. Загрузите проект в GitHub.
2. Зайдите в Render и создайте `New +` -> `Web Service`.
3. Подключите репозиторий.
4. Выберите Python environment.
5. Укажите настройки:

- Build Command:

```text
pip install -r requirements.txt
```

- Start Command:

```text
python start.py
```

6. Render сам прочитает `runtime.txt` и будет использовать Python 3.12.
7. Нажмите `Create Web Service`.

## Структура

```text
project/
  .python-version
  usdt_rub_algorithm.py
  start.py
  web_app.py
  requirements.txt
  runtime.txt
  README.md
  templates/
    index.html
    history.html
  static/
    style.css
```

## Важно

- Расчётная логика находится в `usdt_rub_algorithm.py`.
- Веб-приложение использует только `format_transaction(text: str) -> str`.
- История в вебе хранится только в памяти процесса и очищается после перезапуска сервиса.
- Для Render стартовая команда: `python start.py`.
