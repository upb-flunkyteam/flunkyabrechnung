import re
from datetime import date
from functools import partial
from itertools import chain
from logging import *

import dateutil.parser


def try_get_input(prompt: str, cond, error: str, strip=True):
    while True:
        try:
            tmp = input("\r" + prompt)
            if strip:
                tmp = tmp.strip()
            if callable(cond) and cond(tmp):
                raise ValueError(error)
            if isinstance(cond, str) and re.fullmatch(cond, tmp) is None:
                raise ValueError(error)
            break
        except ValueError as e:
            warning(e)
    return tmp


def get_name(prompt="Firstname [Middlename] Lastname: "):
    name_regex = "(?P<first>(?:\w|-)+)(?:\s+(?P<middle>(?:\w|-)+)|)\s+(?P<last>(?:\w|-)+)"
    name = try_get_input(prompt, name_regex,
                         "Please provide First and Last name. Names must consist of Letters")
    match = re.fullmatch(name_regex, name)
    return match["first"], match["middle"], match["last"]


def get_email(prompt="Email: "):
    email = try_get_input(prompt, "|[a-zA-Z0-9._%+-]+|[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}",
                          "Provide your imt-login or a proper email adress").lower()
    if email and "@" not in email:
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


def setdefault(dictionary, key, callable):
    dictionary["player_id"] = dictionary.get("player_id", None) or dictionary.setdefault(
        callable())


def get_tallymarks(n, prompt=""):
    marks = try_get_input(prompt, "|\d*(?:\s\d*){0," + str(n - 1) + "}", "tab separated integers", strip=False)
    # fill up with zeros
    marks = list(map(lambda s: int(s) if s else 0, re.split("\s", marks))) + [0 for _ in range(n)]
    marks = marks[:n]
    print("\033[F{}{}       ".format(prompt, " ".join(map(str, marks))))
    return marks


def get_tournaments(prompt="Provide Tournament numbers: ", maximum=None):
    intervall = r"(?:\d+|\d+-\d+|\d+-)" if maximum else r"(?:\d+|\d+-\d+)"
    pattern = intervall + "(?:,\s*" + intervall + ")*|"
    tids = try_get_input(prompt, pattern,
                         "Provided turnier sequence has wrong syntax (pattern: " + pattern + ")")
    if not tids:
        return set()
    tids = re.split(",\s*", tids)
    # duplicate if single number
    tids = [(tidrange.split("-") + tidrange.split("-"))[:2] for tidrange in tids]
    # increment second number
    # if interval was "\d+-" we have to substitute the empty string with the maximum
    tids = [[int(start), int(end or maximum) + 1] for start, end in tids]
    # inflate ranges
    return set(chain.from_iterable((range(*tidrange) for tidrange in tids)))
