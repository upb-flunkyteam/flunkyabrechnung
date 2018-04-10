from db import *
from logging import *
import re
from datetime import datetime, date
from itertools import chain
from complete import Completer
import readline


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


def addplayers(session: Session):
    name_regex = "(?P<first>(?:\w|-)+)(?:\s+(?P<middle>(?:\w|-)+)|)\s+(?P<last>(?:\w|-)+)"

    print("\nAdding new Players now:\n\tPress ctrl + d to finish input\n")
    try:
        while True:
            # request all the information from the user
            player_id = try_get_input("ID of the new player:\t\t\t ",
                                      lambda x: x.lower() in chain.from_iterable(session.query(Player.pid).all()),
                                      "id is not unique").lower()

            name = try_get_input("Firstname [Middlename] Lastname: ",
                                 lambda x: re.fullmatch(name_regex, x) is None,
                                 "Please provide First and Last name. Names must consist of Letters")
            match = re.fullmatch(name_regex, name)

            nick = input("[Nickname]:\t\t\t\t\t\t ").strip() or None  # TODO autocomplete adds id
            address = try_get_input("Address:\t\t\t\t\t\t ", lambda x: len(x) < 5,
                                    "The address can't have less than 5 characters")
            phone = try_get_input("[Phone]:\t\t\t\t\t\t ", lambda x: re.fullmatch("|\+?[0-9 ]+/?[0-9 -]+\d", x) is None,
                                  "thats not a proper phone number") or None
            comm = input("[Comment]:\t\t\t\t\t\t ") or None

            init_pay = try_get_input("Initial Payment in €:\t\t\t ",
                                     lambda x: re.fullmatch("(?:-|\+|)\s*\d+(|[,.]\d{0:2})\s+(?:€|)", x) is None,
                                     "Your Provided payment can not be interpret")
            init_pay = float(re.match("(?:-|\+|)\s*\d+(|[,.]\d{0:2})", init_pay)[0].replace(",", "."))
            print()

            # write the stuff into the db
            session.add(
                Player(pid=player_id, firstname=match["first"], middlename=match["middle"], lastname=match["last"],
                       nickname=nick, address=address, phone=phone, comment=comm))
            session.add(Account(pid=player_id, comment="initial", deposit=init_pay, date=date.today(),
                                last_modified=datetime.now()))
            session.commit()
            info("Added Player \"%s\"" % player_id)
    except (EOFError, KeyboardInterrupt):
        pass


def createtally(session, turnierseq=None, printer=None):
    pass


def transfer(session):
    print("\nTransfering Money from a player to a set of players:\n\tPress ctrl + d to finish input\n")

    from_user = get_user(session, "From: ")
    to_users= set()
    while True:
        try:
            to_users.add(get_user(session, "To:   "))
        except (KeyboardInterrupt,EOFError):
            break
    print(from_user, "->", to_users)


def tally(session):
    pass


def deposit(session):
    pass


def billing(session, filename=None):
    pass


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
            print("    ".join(filter(None, [completer.complete_str(prefix, i) for i in range(20)])))
    readline.set_completer(old_completer)
    return result.player
