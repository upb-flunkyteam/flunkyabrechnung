from db import *
from logging import *
import re
from datetime import datetime, date
from itertools import chain
from input_funcs import *


def addplayers(session: Session):
    name_regex = "(?P<first>(?:\w|-)+)(?:\s+(?P<middle>(?:\w|-)+)|)\s+(?P<last>(?:\w|-)+)"

    print("\nAdding new Players now:\n\tPress ctrl + d to finish input\n")
    try:
        while True:
            # request all the information from the user
            player_id = try_get_input("ID of the new player:\t\t\t ",
                                      lambda x: x.lower() in chain.from_iterable(
                                          session.query(Player.pid).all() or re.fullmatch("\w+", x)),
                                      "id is not unique").lower()
            readline.replace_history_item(0,player_id.capitalize())
            name = try_get_input("Firstname [Middlename] Lastname: ",
                                 lambda x: re.fullmatch(name_regex, x) is None,
                                 "Please provide First and Last name. Names must consist of Letters")
            match = re.fullmatch(name_regex, name)

            nick = input("[Nickname]:\t\t\t\t\t ").strip() or None
            address = try_get_input("Address:\t\t\t\t\t ", lambda x: len(x) < 5,
                                    "The address can't have less than 5 characters")
            phone = try_get_input("[Phone]:\t\t\t\t\t\t ", lambda x: re.fullmatch("|\+?[0-9 ]+/?[0-9 -]+\d", x) is None,
                                  "thats not a proper phone number") or None
            comm = input("[Comment]:\t\t\t\t\t\t ") or None

            init_pay = get_payment("Initial Payment in €:\t\t\t ")
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
    print("\nApportion cost from a player among a set of players:\n\tPress ctrl + d to finish input\n")

    event = input("For what occasion: ")
    date = get_date("When was it: ")
    from_player = get_user(session, "Player that payed: ")
    to_players = set()
    while True:
        try:
            to_players.add(get_user(session, "Other players:   "))
        except (KeyboardInterrupt, EOFError):
            break
    transfer = get_payment("Amount of money to transfer from {} to {}: ".format(to_players, from_player))
    # the transfer is split as evenly as possible. it must properly sum up, but we can only use 2 decimal places
    # to achieve that we will calculate the correct fraction and than cut rounded parts from the sum,
    # in order to get junks as similar as possible. the amounts will not differ by more than 1 cent
    fraction = transfer / len(to_players)

    for i, player in enumerate(to_players):
        fair_amount = round(round(fraction * (i + 1), 2) - round(fraction * i, 2), 2)
        session.add(Account(pid=player.pid, comment=event, deposit=-fair_amount,
                            date=date,
                            last_modified=datetime.now()))
    session.add(Account(pid=from_player.pid, comment=event, deposit=transfer,
                        date=date,
                        last_modified=datetime.now()))
    session.commit()
    print()


def tally(session):
    pass


def deposit(session):
    pass


def billing(session, filename=None):
    pass
