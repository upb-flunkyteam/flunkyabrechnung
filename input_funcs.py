import re
from logging import *
from functools import partial
import dateutil.parser
from datetime import date


def try_get_input(prompt: str, cond, error: str):
    while True:
        try:
            tmp = input(prompt)
            tmp = tmp.strip()
            if callable(cond) and cond(tmp):
                raise ValueError(error)
            if isinstance(cond, str) and re.fullmatch(cond, tmp) is None:
                raise ValueError(error)
            break
        except ValueError as e:
            warning(e)
    return tmp


def get_email(prompt="Email: "):
    email = try_get_input(prompt, "[a-zA-Z0-9._%+-]+|[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}",
                          "Provide your imt-login or a proper email adress").lower()
    if "@" not in email:
        # its a imt login
        email += "@mail.upb.de"
    print("\033[F{}{}       ".format(prompt, email))


def get_date(prompt="When: ", default=date.today()):
    parse_date = partial(dateutil.parser.parse, dayfirst=True, yearfirst=False)
    date = parse_date(
        try_get_input(prompt, lambda d: d and parse_date(d) is None,
                      "Can't interpret date") or default.strftime("%d-%m-%Y"))
    print("\033[F{}{}      ".format(prompt, date.strftime("%a, %d %b %Y")))
    return date


def get_payment(prompt="Payment in €: "):
    pay = try_get_input(prompt, "|(?:-|\+|)\s?\d+(|[,.]\d{0:2})\s?(?:€|)",
                        "Your Provided payment can not be interpret") or "0"
    payment = float((re.match("(?:-|\+|)\s?\d+(|[,.]\d{0:2})", pay)[0]).replace(",", "."))
    print("\033[F{}{:.2f} €     ".format(prompt, payment))
    return payment


def get_bool(prompt="[Y/n]: "):
    return not try_get_input(prompt,
                             "[yY]es|[yY]|[nN]o|[nN]|",
                             "Couldn't interpret answer").lower().startswith("n")
