from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from usdt_rub_algorithm import format_transaction


BASE_DIR = Path(__file__).resolve().parent
MAX_HISTORY_ITEMS = 50
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
INDEX_TEMPLATE_PATH = TEMPLATES_DIR / "index.html"
STYLE_PATH = STATIC_DIR / "style.css"


MINIMAL_INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>USDT/RUB Calculator</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <main class="page">
        <h1>USDT/RUB Calculator</h1>
        <form action="/calculate" method="post">
            <textarea name="text" rows="12" placeholder="Введите текст для расчёта"></textarea>
            <button type="submit">Рассчитать</button>
        </form>
    </main>
</body>
</html>
"""


MINIMAL_STYLE_CSS = """body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 24px;
    background: #f7f7f7;
    color: #111;
}

.page {
    max-width: 720px;
    margin: 0 auto;
}

textarea {
    width: 100%;
    box-sizing: border-box;
    margin: 12px 0;
}

button {
    padding: 12px 16px;
}
"""


@dataclass
class HistoryEntry:
    input_text: str
    result: str
    error: str
    timestamp: str


STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

if not INDEX_TEMPLATE_PATH.exists():
    INDEX_TEMPLATE_PATH.write_text(MINIMAL_INDEX_HTML, encoding="utf-8")

if not STYLE_PATH.exists():
    STYLE_PATH.write_text(MINIMAL_STYLE_CSS, encoding="utf-8")


app = FastAPI(title="USDT/RUB Calculator")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
history_store: deque[HistoryEntry] = deque(maxlen=MAX_HISTORY_ITEMS)


def get_history_context() -> list[dict[str, str]]:
    return [asdict(entry) for entry in history_store]


def add_history_entry(*, input_text: str, result: str = "", error: str = "") -> None:
    history_store.appendleft(
        HistoryEntry(
            input_text=input_text,
            result=result,
            error=error,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    )


def render_page(
    request: Request,
    *,
    input_text: str = "",
    result: str = "",
    error: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "input_text": input_text,
            "result": result,
            "error": error,
            "result_text": result,
            "error_message": error,
        },
        status_code=status_code,
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return render_page(request)


@app.post("/calculate", response_class=HTMLResponse)
async def calculate(request: Request, text: str = Form(...)) -> HTMLResponse:
    try:
        result = format_transaction(text)
        add_history_entry(input_text=text, result=result)
        return render_page(request, input_text=text, result=result)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        add_history_entry(input_text=text, error=error)
        return render_page(
            request,
            input_text=text,
            error=error,
            status_code=400,
        )


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "history_items": get_history_context(),
        },
    )
