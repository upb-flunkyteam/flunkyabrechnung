from complete import Completer
import readline
import re
from db import *
from logging import *
from functools import partial
import dateutil.parser
from datetime import date


def try_get_input(prompt: str, cond: callable, error: str):
    while True:
        try:
            tmp = input(prompt)
            tmp = tmp.strip()
            if cond(tmp):
                raise ValueError(error)
            break
        except ValueError as e:
            warning(e)
    return tmp


def get_date(prompt="When: ", default=date.today()):
    # TODO should also be able to handle: Today, last tuesday, schould infer year if missing
    # TODO date cant be in future and not 5 years older than the first entry
    #  (of course this needs a proper error message)
    parse_date = partial(dateutil.parser.parse, dayfirst=True, yearfirst=False)
    date = parse_date(
        try_get_input(prompt, lambda d: d and parse_date(d) is None,
                      "Can't interpret date") or default.strftime("%d-%m-%Y"))
    print("\033[F{}{}      ".format(prompt, date.strftime("%a, %d %b %Y")))
    return date


def get_payment(prompt="Payment in €: "):
    pay = try_get_input(prompt,
                        lambda x: x and re.fullmatch("(?:-|\+|)\s?\d+(|[,.]\d{0:2})\s?(?:€|)", x) is None,
                        "Your Provided payment can not be interpret") or "0"
    payment = float((re.match("(?:-|\+|)\s?\d+(|[,.]\d{0:2})", pay)[0]).replace(",", "."))
    print("\033[F{}{:.2f} €     ".format(prompt, payment))
    return payment


def get_user(session, prompt="Input User: ") -> Player:
    players = session.query(Player).all()
    completer = Completer(players)
    old_completer = readline.get_completer()
    readline.set_completer(completer.complete_str)
    readline.parse_and_bind('tab: complete')
    while True:
        prefix = input(prompt)
        first, second = completer.complete(prefix, 0), completer.complete(prefix, 1)
        if first is not None and second is None:
            # there is no second element in the completion
            # therefore we take the first
            result = first
            # autocomplete the console output (the trailing whitespaces are needed to clear the previous line)
            print("\033[F{}{} ({})      ".format(prompt, result.player.pid, repr(result.player)))
            break
        else:
            completes = list(filter(None, [completer.complete_str(prefix, i) for i in range(20)]))
            if len(completes) > 0:
                print("    ".join(completes))
            else:
                print("Couldn't interpret input")
    readline.set_completer(old_completer)
    return result.player
