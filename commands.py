from db import *
from logging import *
import re
from complete import Completer
import readline
from datetime import datetime, date
from itertools import chain
from input_funcs import *
from multiprocessing import Pool
from functools import partial
from uploader import asta_upload


class CommandProvider:
    def __init__(self, session: Session, config):
        self.session = session
        self.config = config

    def addplayers(self):
        name_regex = "(?P<first>(?:\w|-)+)(?:\s+(?P<middle>(?:\w|-)+)|)\s+(?P<last>(?:\w|-)+)"

        print("\nAdding new Players now:\n\tPress ctrl + d to finish input\n")
        try:
            while True:
                # request all the information from the user
                player_id = try_get_input("ID of the new player:\t\t\t ",
                                          lambda x: x.lower() in chain.from_iterable(
                                              self.session.query(Player.pid).all() or re.fullmatch("\w+", x)),
                                          "id is not unique").lower()
                readline.replace_history_item(0, player_id.capitalize())
                name = try_get_input("Firstname [Middlename] Lastname: ",
                                     lambda x: re.fullmatch(name_regex, x) is None,
                                     "Please provide First and Last name. Names must consist of Letters")
                match = re.fullmatch(name_regex, name)

                nick = input("[Nickname]:\t\t\t\t\t ").strip() or None
                address = try_get_input("Address:\t\t\t\t\t ", lambda x: len(x) < 5,
                                        "The address can't have less than 5 characters")
                phone = try_get_input("[Phone]:\t\t\t\t\t\t ",
                                      lambda x: re.fullmatch("|\+?[0-9 ]+/?[0-9 -]+\d", x) is None,
                                      "thats not a proper phone number") or None
                comm = input("[Comment]:\t\t\t\t\t\t ") or None

                init_pay = get_payment("Initial Payment in €:\t\t\t ")
                print()

                # write the stuff into the db
                self.session.add(
                    Player(pid=player_id, firstname=match["first"], middlename=match["middle"], lastname=match["last"],
                           nickname=nick, address=address, phone=phone, comment=comm))
                self.session.add(Account(pid=player_id, comment="initial", deposit=init_pay, date=date.today(),
                                         last_modified=datetime.now()))
                self.session.commit()
                info("Added Player \"%s\"" % player_id)
        except (EOFError, KeyboardInterrupt):
            pass

    def createtally(self, turnierseq=None):
        # turnierseq = turnierseq or
        print("createtally")
        pass

    def transfer(self):
        print("\nApportion cost from a player among a set of players:\n\tPress ctrl + d to finish input\n")

        event = input("For what occasion: ")
        date = get_date("When was it: ")
        from_player = self.get_user("Player that payed: ")
        to_players = set()
        while True:
            try:
                to_players.add(self.get_user("Other players:   "))
            except (KeyboardInterrupt, EOFError):
                break
        transfer = get_payment("Amount of money to transfer from {} to {}: ".format(to_players, from_player))
        # the transfer is split as evenly as possible. it must properly sum up, but we can only use 2 decimal places
        # to achieve that we will calculate the correct fraction and than cut rounded parts from the sum,
        # in order to get junks as similar as possible. the amounts will not differ by more than 1 cent
        fraction = transfer / len(to_players)

        for i, player in enumerate(to_players):
            fair_amount = round(round(fraction * (i + 1), 2) - round(fraction * i, 2), 2)
            self.session.add(Account(pid=player.pid, comment=event, deposit=-fair_amount,
                                     date=date,
                                     last_modified=datetime.now()))
        self.session.add(Account(pid=from_player.pid, comment=event, deposit=transfer,
                                 date=date,
                                 last_modified=datetime.now()))
        self.session.commit()
        print()

    def tally(self):
        pass

    def deposit(self):
        print("\nAdding deposit for players:\n\tPress ctrl + d to finish input\n")
        try:
            while True:
                player = self.get_user()
                depo = get_payment("Deposit in €: ")
                date = get_date("When did he pay: ")
                comm = input("[Comment]: ") or None
                self.session.add(Account(pid=player.pid, comment=comm, deposit=depo,
                                         date=date,
                                         last_modified=datetime.now()))
                print()
        except (EOFError, KeyboardInterrupt):
            pass

    def billing(self, filename=None):
        pass

    def printtally(self):
        def printall(logins: dict, display_filename="Flunkyliste.pdf"):
            upload = partial(asta_upload, display_filename=display_filename)

            with Pool() as p:
                results = p.map(upload, logins.items())

    def tallynumbers(self):
        # retrieve tallynumbers by looking at the
        last_number = self.session.query(Tournament).orderby(Tournament.date).last()
        try:
            start = int(last_number) + 1
        except ValueError:
            start = try_get_input("what is the new number?")
        # TODO errorhandling of config
        return list(range(start, start + self.config.get("createtally", "n")))

    def retrieve_most_active_players(self, n=20):
        # retrieve at most the n most active players. (if the tally table is to emtpy less player will be returned)
        # This will calculate an exponentially decaying average over all matches per player
        # and sort players per score
        pass

    def get_user(self, prompt="Input User: ") -> Player:
        players = self.session.query(Player).all()
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


def sanitize_turnierseq():
    # TODO this takes the inputs from the arguments,
    # this will be converted in a list tuples of turnier ids and ordercodes
    # TODO if the turnier ids dont exist, they will be created in Tournament
    pass
