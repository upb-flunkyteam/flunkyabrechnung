from dbo import *
from complete import Completer
import readline
from datetime import datetime
from itertools import chain, groupby
from input_funcs import *
from multiprocessing import Pool
from functools import partial
from collections import defaultdict
from uploader import asta_upload
from random import sample


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

    def createtally(self, turnierseq: str):
        if not turnierseq:
            # strip of tourniercodes
            turnierseq = self.infer_turniernumbers()

        players = self.retrieve_most_active_players()
        ordercode = self.create_or_retrieve_ordercode(players)
        for turnier in turnierseq:
            if isinstance(turnier, tuple):
                n, code = turnier
                if code:
                    print("Turnier {} uses ordercode {}".format(n, code))
                else:
                    code = ordercode
            else:
                n, code = turnier, ordercode
            self.session.add(Tournament(tid=n, ordercode=code))
        self.session.commit()
        print('Created tallies with the numbers {} and ordercode "{}"'.format(str(turnierseq), ordercode))

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

    def printtally(self,print_target:str):
        # prints all unprinted tallys. if there are none, it will ask, which tallys to print
        # TODO it will check if the unprinted tallies make sense:
        #    - ask for validation if printing more than twice as many tallies as in config.createtally.n
        #    - ask for validation if printing older unprinted lists, with at least half of config.createtally.n printed lists in between
        #    - ask the user if the rejected lists should be marked as printed.
        # TODO
        def printall(logins: dict, display_filename="Flunkyliste.pdf"):
            upload = partial(asta_upload, display_filename=display_filename)

            with Pool() as p:
                results = p.map(upload, logins.items())

    def infer_turniernumbers(self):
        # retrieve tallynumbers by looking at the
        last_number = self.session.query(Tournament.tid).order_by(Tournament.tid.desc()).first()[0]
        try:
            start = int(last_number) + 1
        except (ValueError, AttributeError):
            # there are no tournaments in the database
            start = int(
                try_get_input("What is the number of the next tournament? ", lambda i: not isinstance(int(i), int),
                              "You did not provide a number!"))
        return list(range(start, start + self.config.getint("createtally", "n")))

    def retrieve_most_active_players(self):
        # retrieve at most the n most active players using an exponentialy weighted average

        limit, alpha, n = self.config.getint("createtally", "cutoff"), \
                          self.config.getfloat("createtally", "alpha"), \
                          self.config.getint("createtally", "n_active_players")

        player_activity = defaultdict(int)

        for tournament in self.session.query(Tournament).order_by(Tournament.date.desc()).limit(limit).all():
            # starting with the latest date
            players_at_tournament = self.session.query(Tallymarks.pid).filter(Tallymarks.tid == tournament.tid).all()
            for player in players_at_tournament:
                # actually "alpha * 1" for the current + the history
                player_activity[player.pid] = alpha + (1 - alpha) * player_activity[player.pid]

        # get the "n" most active players
        n_most_active = list(sorted(player_activity.items(), key=lambda x: x[1]))[:n]
        if len(n_most_active) < n:
            info("There where not enough active players to fill the list")
        # return the players in alphabetical order
        return list(sorted(map(lambda x: x[0], n_most_active)))

    def create_or_retrieve_ordercode(self, players: set()) -> str:
        if not players:
            return ""
        groups = groupby(self.session.query(TournamentPlayerLists).all(), key=lambda x: x[0])
        groups = dict(map(lambda k, g: (frozenset([v for k, v in g]), k), groups))
        ordercode = groups.get(frozenset(players), None)
        if ordercode is None:
            # create new ordercode
            while True:
                ordercode = self.gen_ordercode()
                if ordercode not in chain.from_iterable(self.session.query(TournamentPlayerLists.id).all()):
                    break
            self.session.add_all(*(TournamentPlayerLists(id=ordercode, pid=player.pid) for player in players))
            self.session.commit()

        return ordercode

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

    @staticmethod
    def gen_ordercode():
        vovel = set("a e i o u".split())
        consonant = set(map(chr, range(97, 123))) - vovel

        code = ""
        for i in range(6):
            code += sample(vovel) if i % 2 == 0 else sample(consonant)

        return code.capitalize()
