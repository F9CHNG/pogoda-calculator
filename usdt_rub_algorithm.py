from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

getcontext().prec = 28

NUMBER = r"\d+(?:\.\d+)?"
WORD_BOUNDARY = r"(?<!\w){tag}(?!\w)"

RATE_RE = re.compile(
    rf"(?P<a>{NUMBER})\s*(?P<op>[+\-*/])\s*(?P<b>{NUMBER})(?P<pct>%?)\s*=\s*(?P<v>{NUMBER})"
)
MULTIPLY_RE = re.compile(
    rf"(?P<x>{NUMBER})\s*\*\s*(?P<v>{NUMBER})(?:\s*=\s*(?P<s>{NUMBER}))?"
)
DIVIDE_RE = re.compile(
    rf"(?P<r>{NUMBER})\s*/\s*(?P<v>{NUMBER})(?:\s*=\s*(?P<x>{NUMBER}))?"
)
HEADER_RE = re.compile(rf"(?i)/\s*юсдт\s*(?P<x>[+\-]?\d+(?:\.\d+)?)")
ADJUSTMENT_RE = re.compile(
    rf"(?i)в\s*руб\s*:\s*(?P<raw>(?P<op>[+\-*/])?\s*(?P<value>{NUMBER})(?P<pct>%?))"
)

CITY_TAGS = {
    "Барнаул": ["Барнаул", "Барнео", "барнэо", "барн"],
    "Благовещинск": ["Блага", "Благовещинск"],
    "Владивосток": ["владик", "Владивосток"],
    "Волгоград": ["Волгоград", "волга"],
    "Воронеж": ["Воронеж"],
    "Донецк": ["Донецк"],
    "Екатеринбург": ["Екатеринбург", "Екб", "екат"],
    "Иркутск": ["Иркутск"],
    "Казань": ["Казань"],
    "Калининград": ["Калининград", "калин"],
    "Красноярск": ["Красноярск", "крас"],
    "Краснодар": ["Краснодар"],
    "Кемерово": ["Кемерово"],
    "Липецк": ["Липецк"],
    "Мариуполь": ["мариуп", "Мариуполь"],
    "МОСКВА": ["МОСКВА", "мск"],
    "Новосибирск": ["Новосибирск", "нск", "сиб", "новосиб"],
    "Новокузнецк": ["Новокузнецк"],
    "Новороссийск": ["Новороссийск", "Новорос"],
    "Нижний-Новгород": ["Нижний-Новгород", "Новгород", "Нижний", "Нижний Новгород"],
    "Омск": ["Омск"],
    "Пермь": ["Пермь", "Перм"],
    "Ростов-на-Дону": ["Ростов-на-Дону", "Ростов", "Рост"],
    "Республика Саха ЯКУТИЯ": ["ЯКУТИЯ", "якутск"],
    "Санкт-Петербург": ["спб", "Питер", "Санкт-Петербург", "Санкт Петербург", "Питербург"],
    "Самара": ["Самара"],
    "Саратов": ["Саратов"],
    "Сочи": ["Сочи"],
    "Томск": ["Томск"],
    "Тюмень": ["Тюмень", "Тюмен"],
    "Уфа": ["Уфа"],
    "Хабаровск": ["Хабаровск", "хабара"],
    "Челябинск": ["Челябинск", "челяб", "челяба"],
    "Южно-Сахалинск": ["сахалин", "Южно Сахалинск", "Южно-Сахалинск", "Сахалинск"],
}

CITY_PAIRS = sorted(
    ((official, tag) for official, tags in CITY_TAGS.items() for tag in tags),
    key=lambda item: len(item[1]),
    reverse=True,
)

RESERVED_WORDS = {
    "нам",
    "мы",
    "в",
    "руб",
    "прием",
    "юсдт",
    "проверка",
    "нет",
    "данных",
}
for official, tag in CITY_PAIRS:
    RESERVED_WORDS.update(re.findall(r"[A-Za-zА-Яа-яЁё-]+", official.lower()))
    RESERVED_WORDS.update(re.findall(r"[A-Za-zА-Яа-яЁё-]+", tag.lower()))


@dataclass
class RateFormula:
    a: Decimal
    a_raw: str
    op: str
    b: Decimal
    b_raw: str
    is_percent: bool
    result_raw: str


@dataclass
class MultiplyFormula:
    x: Decimal
    x_raw: str
    v: Decimal
    v_raw: str
    s_raw: str | None


@dataclass
class DivideFormula:
    r: Decimal
    r_raw: str
    v: Decimal
    v_raw: str
    x_raw: str | None


@dataclass
class Adjustment:
    op: str
    amount: Decimal
    amount_raw: str
    is_percent: bool


@dataclass
class ResaleBranch:
    label: str
    r: Decimal
    r_raw: str
    v: Decimal
    v_raw: str
    x_value: Decimal
    x_raw: str
    rate_line: str | None = None


def d(raw: str) -> Decimal:
    return Decimal(raw)


def decimal_places(raw: str) -> int:
    return len(raw.split(".", 1)[1]) if "." in raw else 0


def quantize_to_places(value: Decimal, places: int) -> Decimal:
    quantum = Decimal("1").scaleb(-places)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def fmt(value: Decimal, places: int | None = None, *, fixed: bool = False) -> str:
    if places is not None:
        quantized = quantize_to_places(value, places)
        rendered = format(quantized, f".{places}f")
        if fixed or places == 0:
            return rendered
        return rendered.rstrip("0").rstrip(".")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def round_int(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def normalize_text(text: str) -> str:
    text = text.replace("\u00A0", " ")
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"(?<=\d)[ '\u00A0](?=\d)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    return text.strip()


def cleaned_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def calculate_rate(formula: RateFormula) -> Decimal:
    if formula.op == "+" and formula.is_percent:
        return formula.a * (Decimal("1") + formula.b / Decimal("100"))
    if formula.op == "-" and formula.is_percent:
        return formula.a * (Decimal("1") - formula.b / Decimal("100"))
    if formula.op == "+":
        return formula.a + formula.b
    if formula.op == "-":
        return formula.a - formula.b
    if formula.op == "*":
        return formula.a * formula.b
    if formula.op == "/":
        return formula.a / formula.b
    raise ValueError(f"Unsupported rate operation: {formula.op}")


def apply_adjustment(value: Decimal, adjustment: Adjustment) -> Decimal:
    if adjustment.is_percent and adjustment.op == "+":
        result = value * (Decimal("1") + adjustment.amount / Decimal("100"))
    elif adjustment.is_percent and adjustment.op == "-":
        result = value * (Decimal("1") - adjustment.amount / Decimal("100"))
    elif adjustment.op == "+":
        result = value + adjustment.amount
    elif adjustment.op == "-":
        result = value - adjustment.amount
    elif adjustment.op == "*":
        result = value * adjustment.amount
    elif adjustment.op == "/":
        result = value / adjustment.amount
    else:
        raise ValueError(f"Unsupported adjustment operation: {adjustment.op}")
    return quantize_to_places(result, 2)


def build_tag_regex(tag: str) -> re.Pattern[str]:
    return re.compile(WORD_BOUNDARY.format(tag=re.escape(tag)), re.IGNORECASE)


def find_city(text: str) -> str | None:
    best: tuple[int, str] | None = None
    for official, tag in CITY_PAIRS:
        match = build_tag_regex(tag).search(text)
        if not match:
            continue
        candidate = (match.start(), official)
        if best is None or candidate < best:
            best = candidate
    return None if best is None else best[1]


def strip_formula_chunks(text: str) -> str:
    cleaned = HEADER_RE.sub(" ", text)
    cleaned = ADJUSTMENT_RE.sub(" ", cleaned)
    cleaned = RATE_RE.sub(" ", cleaned)
    cleaned = MULTIPLY_RE.sub(" ", cleaned)
    cleaned = DIVIDE_RE.sub(" ", cleaned)
    for _, tag in CITY_PAIRS:
        cleaned = build_tag_regex(tag).sub(" ", cleaned)
    cleaned = re.sub(r"(?i)\b(нам|мы|прием|руб|в|юсдт|проверка)\b", " ", cleaned)
    return cleaned


def find_group(text: str, city: str | None) -> str:
    cleaned = strip_formula_chunks(text)
    words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", cleaned)
    for word in words:
        if word.lower() not in RESERVED_WORDS:
            return word
    return city or "нет данных"


def parse_header_x(text: str) -> tuple[Decimal | None, bool]:
    match = HEADER_RE.search(text)
    if not match:
        return None, False
    raw = match.group("x")
    return abs(d(raw)), raw.strip().startswith("-")


def parse_adjustment(lines: list[str]) -> Adjustment | None:
    for line in lines:
        match = ADJUSTMENT_RE.search(line)
        if not match:
            continue
        raw = match.group("raw").replace(" ", "")
        op = match.group("op") or "+"
        if raw.startswith("-"):
            op = "-"
        elif raw.startswith("+"):
            op = "+"
        value = match.group("value")
        return Adjustment(op=op, amount=abs(d(value)), amount_raw=value, is_percent=match.group("pct") == "%")
    return None


def classify_rate(line: str) -> RateFormula | None:
    match = RATE_RE.search(line)
    if not match:
        return None
    op = match.group("op")
    a_raw = match.group("a")
    b_raw = match.group("b")
    v_raw = match.group("v")
    if op in "+-":
        return RateFormula(d(a_raw), a_raw, op, d(b_raw), b_raw, match.group("pct") == "%", v_raw)
    result_value = d(v_raw)
    first_value = d(a_raw)
    if first_value <= Decimal("1000") and result_value <= Decimal("1000"):
        return RateFormula(d(a_raw), a_raw, op, d(b_raw), b_raw, match.group("pct") == "%", v_raw)
    return None


def extract_standalone_rate(line: str) -> tuple[Decimal, str] | None:
    cleaned = line
    for _, tag in CITY_PAIRS:
        cleaned = build_tag_regex(tag).sub(" ", cleaned)
    cleaned = re.sub(r"(?i)\b(нам|мы|прием|руб|в|юсдт|проверка)\b", " ", cleaned)
    numbers = re.findall(NUMBER, cleaned)
    if len(numbers) != 1:
        return None
    raw = numbers[0]
    value = d(raw)
    if Decimal("0") < value < Decimal("1000"):
        return value, raw
    return None


def parse_ordinary_blocks(lines: list[str]) -> tuple[RateFormula | None, MultiplyFormula | None, DivideFormula | None, tuple[Decimal, str] | None]:
    rate_formula = None
    multiply_formula = None
    divide_formula = None
    standalone_rate = None

    for line in lines:
        if HEADER_RE.search(line) or ADJUSTMENT_RE.search(line):
            continue

        candidate_rate = classify_rate(line)
        if candidate_rate and rate_formula is None:
            rate_formula = candidate_rate
            continue

        mult_match = MULTIPLY_RE.search(line)
        if mult_match and multiply_formula is None:
            x_raw = mult_match.group("x")
            v_raw = mult_match.group("v")
            s_raw = mult_match.group("s")
            multiply_formula = MultiplyFormula(d(x_raw), x_raw, d(v_raw), v_raw, s_raw)
            continue

        div_match = DIVIDE_RE.search(line)
        if div_match and divide_formula is None:
            r_raw = div_match.group("r")
            v_raw = div_match.group("v")
            x_raw = div_match.group("x")
            divide_formula = DivideFormula(d(r_raw), r_raw, d(v_raw), v_raw, x_raw)
            continue

        if standalone_rate is None:
            standalone_rate = extract_standalone_rate(line)

    return rate_formula, multiply_formula, divide_formula, standalone_rate


def determine_effective_v(
    rate_formula: RateFormula | None,
    multiply_formula: MultiplyFormula | None,
    divide_formula: DivideFormula | None,
    standalone_rate: tuple[Decimal, str] | None,
) -> tuple[Decimal | None, str | None, int]:
    if divide_formula is not None:
        return divide_formula.v, divide_formula.v_raw, decimal_places(divide_formula.v_raw)
    if multiply_formula is not None:
        return multiply_formula.v, multiply_formula.v_raw, decimal_places(multiply_formula.v_raw)
    if rate_formula is not None:
        places = decimal_places(rate_formula.result_raw)
        return d(rate_formula.result_raw), rate_formula.result_raw, places
    if standalone_rate is not None:
        value, raw = standalone_rate
        return value, raw, decimal_places(raw)
    return None, None, 0


def render_rate_line(
    rate_formula: RateFormula | None,
    standalone_rate: tuple[Decimal, str] | None,
    effective_v: Decimal | None,
    effective_v_raw: str | None,
    effective_v_places: int,
) -> str | None:
    if rate_formula is not None:
        percent = "%" if rate_formula.is_percent else ""
        return f"{rate_formula.a_raw}{rate_formula.op}{rate_formula.b_raw}{percent}={rate_formula.result_raw}"

    if standalone_rate is not None and effective_v is not None:
        a_value, a_raw = standalone_rate
        if a_value == effective_v:
            return a_raw
        op = "+" if effective_v > a_value else "-"
        diff = abs(effective_v - a_value)
        diff_places = max(decimal_places(a_raw), effective_v_places)
        v_text = effective_v_raw if effective_v_raw is not None else fmt(effective_v, effective_v_places, fixed=effective_v_places > 0)
        return f"{a_raw}{op}{fmt(diff, diff_places, fixed=diff_places > 0)}={v_text}"

    if effective_v_raw is not None:
        return effective_v_raw
    if effective_v is not None:
        return fmt(effective_v, effective_v_places, fixed=effective_v_places > 0)
    return None


def determine_header_sign(
    text: str,
    manual_negative: bool,
    rate_formula: RateFormula | None,
    rate_line: str | None,
    standalone_rate: tuple[Decimal, str] | None,
    effective_v: Decimal | None,
    adjustment: Adjustment | None,
) -> bool:
    lowered = text.lower()
    if manual_negative:
        return True
    if "прием" in lowered or "руб в тез" in lowered:
        return True

    if rate_formula is not None and rate_formula.b != 0:
        return rate_formula.op in {"+", "*"}

    if standalone_rate is not None and effective_v is not None and standalone_rate[0] != effective_v:
        return effective_v > standalone_rate[0]

    if adjustment is not None and adjustment.amount != 0:
        return adjustment.op in {"-", "/"}

    return False


def render_adjustment_label(adjustment: Adjustment) -> str:
    suffix = "%" if adjustment.is_percent else ""
    return f"{adjustment.op}{adjustment.amount_raw}{suffix}"


def render_resale_x(exact_x: Decimal, v_raw: str, input_x_raw: str | None) -> tuple[Decimal, str]:
    if input_x_raw is not None:
        input_places = decimal_places(input_x_raw)
        rounded_to_input = quantize_to_places(exact_x, input_places)
        if rounded_to_input == d(input_x_raw):
            return rounded_to_input, fmt(rounded_to_input, input_places, fixed=input_places > 0)

    if decimal_places(v_raw) == 0:
        rounded = quantize_to_places(exact_x, 3)
        return rounded, fmt(rounded, 3, fixed=True)

    rounded = round_int(exact_x)
    return rounded, fmt(rounded, 0, fixed=True)


def render_resale_rate_line(a_value: Decimal, a_raw: str, v_raw: str) -> str:
    v_value = d(v_raw)
    op = "+" if v_value >= a_value else "-"
    diff = abs(v_value - a_value)
    diff_places = max(decimal_places(a_raw), decimal_places(v_raw))
    diff_text = fmt(diff, diff_places, fixed=diff_places > 0)
    return f"{a_raw}{op}{diff_text}={v_raw}"


def solve_ordinary(text: str) -> str:
    normalized = normalize_text(text)
    lines = cleaned_lines(normalized)
    header_x, manual_negative = parse_header_x(normalized)
    adjustment = parse_adjustment(lines)
    rate_formula, multiply_formula, divide_formula, standalone_rate = parse_ordinary_blocks(lines)

    city = find_city(normalized) or "нет данных"
    group = find_group(normalized, None if city == "нет данных" else city)
    if group == "нет данных" and city != "нет данных":
        group = city

    effective_v, effective_v_raw, effective_v_places = determine_effective_v(
        rate_formula, multiply_formula, divide_formula, standalone_rate
    )

    x_value: Decimal | None = None
    if multiply_formula is not None:
        x_value = round_int(multiply_formula.x)
    elif header_x is not None:
        x_value = header_x
    elif divide_formula is not None:
        x_value = round_int(divide_formula.r / divide_formula.v)
    elif effective_v is not None and standalone_rate is not None and header_x is not None:
        x_value = round_int(header_x)

    if x_value is None and effective_v is None:
        return "недостаточно данных для расчёта"

    if x_value is None and multiply_formula is None and divide_formula is None:
        return "недостаточно данных для расчёта"

    if effective_v is None and standalone_rate is not None:
        effective_v = standalone_rate[0]
        effective_v_raw = standalone_rate[1]
        effective_v_places = decimal_places(standalone_rate[1])

    if x_value is None or effective_v is None:
        return "недостаточно данных для расчёта"

    s_value: Decimal | None = None
    if multiply_formula is not None:
        s_value = multiply_formula.x * multiply_formula.v
    else:
        s_value = x_value * effective_v

    r_final = s_value
    if adjustment is not None:
        r_final = apply_adjustment(s_value, adjustment)

    z_places = effective_v_places or 2
    z_value = quantize_to_places(r_final / x_value, z_places) if adjustment is not None else effective_v

    rate_line = render_rate_line(rate_formula, standalone_rate, effective_v, effective_v_raw, effective_v_places)
    negative_header = determine_header_sign(
        normalized,
        manual_negative,
        rate_formula,
        rate_line,
        standalone_rate,
        effective_v,
        adjustment,
    )

    output_lines = [
        f"/юсдт {'-' if negative_header else ''}{fmt(x_value, 0, fixed=True)} группа: {group}",
        f"Город: {city}",
        "",
    ]

    if rate_line:
        output_lines.append(rate_line)

    if multiply_formula is not None:
        output_lines.append(
            f"{fmt(x_value, 0, fixed=True)}*{multiply_formula.v_raw}={fmt(s_value)}"
        )
    elif divide_formula is not None:
        output_lines.append(
            f"{divide_formula.r_raw}/{divide_formula.v_raw}={fmt(x_value, 0, fixed=True)}"
        )
    elif effective_v_raw is not None:
        output_lines.append(f"{fmt(x_value, 0, fixed=True)}*{effective_v_raw}={fmt(s_value)}")

    if adjustment is not None:
        output_lines.extend(
            [
                "",
                f"В руб: {render_adjustment_label(adjustment)}",
                f"{fmt(s_value)}{render_adjustment_label(adjustment)}={fmt(r_final, 2, fixed=True)}",
            ]
        )

    output_lines.extend(["", "проверка:"])
    if adjustment is not None:
        output_lines.append(
            f"{fmt(r_final, 2, fixed=True)}/{fmt(x_value, 0, fixed=True)}={fmt(z_value, z_places, fixed=z_places > 0)}"
        )
    else:
        output_lines.append(
            f"{fmt(s_value)}/{fmt(x_value, 0, fixed=True)}={effective_v_raw or fmt(effective_v, effective_v_places, fixed=effective_v_places > 0)}"
        )

    return "\n".join(output_lines)


def extract_resale_payload(lines: list[str], index: int) -> str:
    line = lines[index]
    _, payload = line.split(":", 1)
    payload = payload.strip()
    if payload:
        return payload
    if index + 1 < len(lines):
        return lines[index + 1]
    return ""


def is_resale_label_line(line: str) -> bool:
    return bool(re.match(r"(?i)\s*(нам|мы)\s*:", line))


def iter_resale_candidates(lines: list[str], index: int) -> list[str]:
    line = lines[index]
    _, payload = line.split(":", 1)
    candidates: list[str] = []
    if payload.strip():
        candidates.append(payload.strip())

    for next_index in range(index + 1, len(lines)):
        candidate = lines[next_index].strip()
        if is_resale_label_line(candidate):
            break
        if candidate:
            candidates.append(candidate)

    return candidates


def parse_resale_branch(lines: list[str], label: str) -> ResaleBranch:
    for index, line in enumerate(lines):
        if not re.match(rf"(?i){label}\s*:", line):
            continue
        candidates = iter_resale_candidates(lines, index)
        branch_rate: tuple[Decimal, str] | None = None
        for payload in candidates:
            if branch_rate is None:
                branch_rate = extract_standalone_rate(payload)
            match = DIVIDE_RE.search(payload)
            if not match:
                continue
            r_raw = match.group("r")
            v_raw = match.group("v")
            x_raw = match.group("x")
            exact_x = d(r_raw) / d(v_raw)
            x_value, rendered_x = render_resale_x(exact_x, v_raw, x_raw)
            rate_line = None
            if branch_rate is not None:
                rate_line = render_resale_rate_line(branch_rate[0], branch_rate[1], v_raw)
            return ResaleBranch(
                label=label,
                r=d(r_raw),
                r_raw=r_raw,
                v=d(v_raw),
                v_raw=v_raw,
                x_value=x_value,
                x_raw=rendered_x,
                rate_line=rate_line,
            )

        payload = candidates[0] if candidates else ""
        raise ValueError(f"Не удалось распознать блок {label}: {payload}")
    raise ValueError(f"Во входе нет блока {label}:")


def solve_resale(text: str) -> str:
    normalized = normalize_text(text)
    lines = cleaned_lines(normalized)
    city = find_city(normalized) or "нет данных"
    group = find_group(normalized, None if city == "нет данных" else city)
    if group == "нет данных" and city != "нет данных":
        group = city

    nam = parse_resale_branch(lines, "Нам")
    my = parse_resale_branch(lines, "Мы")

    nam_rounded = round_int(nam.x_value)
    my_rounded = round_int(my.x_value)
    diff = nam.x_value - my.x_value
    diff_places = max(decimal_places(nam.x_raw), decimal_places(my.x_raw))

    return "\n".join(
        [
            f"/юсдт {fmt(nam_rounded, 0, fixed=True)}-{fmt(my_rounded, 0, fixed=True)} группа: {group}",
            f"Город: {city}",
            "",
            "Нам:",
            *([nam.rate_line] if nam.rate_line else []),
            f"{nam.r_raw}/{nam.v_raw}={nam.x_raw}",
            "",
            "Мы:",
            *([my.rate_line] if my.rate_line else []),
            f"{my.r_raw}/{my.v_raw}={my.x_raw}",
            "",
            "Проверка",
            f"{nam.x_raw}-{my.x_raw}={fmt(diff, diff_places, fixed=diff_places > 0)}",
        ]
    )


def format_transaction(text: str) -> str:
    normalized = normalize_text(text)
    if re.search(r"(?i)/\s*руб\b", normalized):
        return "режим /руб пока не поддерживается"
    if re.search(r"(?i)\bнам\s*:", normalized) and re.search(r"(?i)\bмы\s*:", normalized):
        return solve_resale(normalized)
    return solve_ordinary(normalized)


def load_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    if args.file is not None:
        return Path(args.file).read_text(encoding="utf-8")
    stdin_text = sys.stdin.read()
    if stdin_text.strip():
        return stdin_text
    raise SystemExit("Передайте текст через --text, файл или stdin.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Форматирует расчёты USDT/RUB по заданному алгоритму.")
    parser.add_argument("file", nargs="?", help="Путь к текстовому файлу со входными данными.")
    parser.add_argument("--text", help="Входной текст расчёта.")
    args = parser.parse_args()
    text = load_text(args)
    print(format_transaction(text))


if __name__ == "__main__":
    main()
