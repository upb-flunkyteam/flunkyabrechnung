from dbo import *
from complete import Completer
import readline
from datetime import datetime, timedelta
from itertools import chain, groupby
from input_funcs import *
from multiprocessing import Pool
from functools import partial
from collections import defaultdict
from uploader import asta_upload
from random import sample
from tally_gen import *
from subprocess import run, DEVNULL


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
                name = try_get_input("Firstname [Middlename] Lastname: ", name_regex,
                                     "Please provide First and Last name. Names must consist of Letters")
                match = re.fullmatch(name_regex, name)

                nick = input("[Nickname]:\t\t\t\t\t ").strip() or None
                address = try_get_input("Address:\t\t\t\t\t ", lambda x: len(x) < 5,
                                        "The address can't have less than 5 characters")
                phone = try_get_input("[Phone]:\t\t\t\t\t\t ", "|\+?[0-9 ]+/?[0-9 -]+\d",
                                      "thats not a proper phone number") or None

                email = get_email("[Email]: ")
                comm = input("[Comment]:\t\t\t\t\t\t ") or None

                init_pay = get_payment("Initial Payment in €:\t\t\t ")
                print()

                # write the stuff into the db
                self.session.add(
                    Player(pid=player_id, firstname=match["first"], middlename=match["middle"], lastname=match["last"],
                           nickname=nick, address=address, phone=phone, email=email, comment=comm))
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

    def printtally(self, print_target: str):
        # prints all unprinted tallys. if there are none, it will ask, which tallys to print
        #
        # TODO

        filename = self.create_tally_pdf()

        if filename is None:
            print("pdf has been created, all tallys are printed")

        if print_target:
            pass

        def printall(logins: dict, display_filename="Flunkyliste.pdf"):
            upload = partial(asta_upload, display_filename=display_filename)

            with Pool() as p:
                results = p.map(upload, logins.items())

    def infer_turniernumbers(self):
        # retrieve tallynumbers by looking at the
        last_number = self.session.query(Tournament.tid).order_by(Tournament.tid.desc()).first()
        if last_number:
            start = last_number[0] + 1
        else:
            # there are no tournaments in the database
            start = int(try_get_input("What is the number of the next tournament? ",
                                      "\d+",
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
        vowel = set("a e i o u".split())
        consonant = set(map(chr, range(97, 123))) - vowel

        code = ""
        for i in range(6):
            code += sample(vowel) if i % 2 == 0 else sample(consonant)

        return code.capitalize()

    def create_tally_pdf(self):
        # get all non printed tournaments
        unprinted_tallys = self.session.query(Tournament).filter(Tournament.printed == False).order_by(
            Tournament.tid).all()
        latest_printed = self.session.query(Tournament).filter(Tournament.printed == True).order_by(
            Tournament.tid.desc()).first()
        # if not empty we retrieve the value, otherwise we assume zero
        if latest_printed:
            latest_printed = latest_printed.tid
        else:
            latest_printed = 0

        if unprinted_tallys is None:
            return None

        old_tallys = list(filter(lambda tally: tally.tid < latest_printed, unprinted_tallys))
        if old_tallys:
            print("There are old tallies that are not printed:\n ", ", ".join(map(str, old_tallys)))
            docreate = get_bool("Should they be printed? [Y/n]: ")
            if docreate or get_bool("Should they be marked printed? [Y/n]: "):
                for t in old_tallys:
                    t.printed = True

            if not docreate:
                unprinted_tallys = list(sorted(set(unprinted_tallys) - set(old_tallys)))

        # TODO validate that at most thice as many tallies are printed as in config.createtally.n
        if len(unprinted_tallys) > self.config.getint("createtally", "n") * 2:
            print("The you are about to print {:d} pages of tallies. Are the numbers:\n {}".format(
                len(unprinted_tallys), ", ".join(map(lambda x: str(x.tid), unprinted_tallys))))
            printall = get_bool("Do you want to print them? [Y/n]: ")
            if not printall:
                tallys_to_print = set((int(i) for i in try_get_input(
                    "Provide a comma separated list of tallies to print\n (the result will be intersected with the previous list): ",
                    "\d+(?:\s*\,\s*\d+)*", "Could not interpret input").split(",")))
                unprinted_tallys = list(filter(lambda elem: elem.tid in tallys_to_print, unprinted_tallys))

        code = ""
        for tally in unprinted_tallys:
            date = tally.date or self.predict_tournament_date(tally.tid)
            playerlist = self.session.query(Player).join(TournamentPlayerLists).filter(
                TournamentPlayerLists.id == tally.ordercode).all()
            responsible = re.split(",\s*",self.config.get("createtally","responsible"))
            code += create_tally_latex_code(tally.tid, date, tally.ordercode, [repr(p) for p in playerlist],responsible)
            tally.printed = True

            with open("latex/content.tex", "w") as f:
                print(code, file=f)

            # compile document
            run("pdflatex -interaction=nonstopmode Flunkyliste.tex".split(), stdout=DEVNULL, cwd="latex")

        self.session.commit()

    def predict_tournament_date(self, tid) -> date:
        # retrieve last tournament with date
        last_tournament_wdate = self.session.query(Tournament).filter(
            Tournament.date != None).order_by(Tournament.date.desc()).first()
        if last_tournament_wdate:
            delta_tournament_n = tid - last_tournament_wdate.tid
            return last_tournament_wdate.date + timedelta(weeks=delta_tournament_n)
