import readline
import socket
from collections import defaultdict, OrderedDict
from datetime import timedelta
from email.message import Message
from functools import lru_cache
from getpass import getpass
from itertools import groupby
from math import ceil
from multiprocessing import Pool
from os import path
from random import sample
from smtplib import SMTP, SMTPAuthenticationError
from subprocess import run, DEVNULL, CalledProcessError
from typing import Set, List, Union

from sqlalchemy.orm import Session

from complete import Completer
from dbo import *
from input_funcs import *
from tally_gen import *
from tally_viewmodel import TallyVM
from uploader import asta_upload


class OrderedSet(OrderedDict):
    def __init__(self, items):
        super().__init__(((i, None) for i in items))

    def add(self, key):
        self[key] = None

    def __setitem__(self, key, value, **kwargs):
        if value is not None:
            TypeError("OrderedSet does not support item setting")
        super().__setitem__(key, value, **kwargs)

    def __str__(self):
        return "{%(list)s}" % {"list": ", ".join(map(str, self.keys()))}


class CommandProvider:
    def __init__(self, session: Session, config):
        self.session = session
        self.config = config

    def addplayers(self):
        print("\nAdding new Players now:\n\tPress ctrl + d to finish input\n")

        history = OrderedDict()
        while True:
            try:
                # request all the information from the user
                history["name"] = history.get(
                    "name", None) or history.setdefault(
                    "name", dict(zip(("firstname", "middlename", "lastname"),
                                     get_name("{:35s}".format("Firstname [Middlename] Lastname:")))))

                history["nickname"] = history.get(
                    "nickname", None) if "nickname" in history else history.setdefault(
                    "nickname", input("{:35s}".format("\r[Nickname]:")).strip() or None)

                history["address"] = history.get("address", None) or history.get(
                    "address",
                    try_get_input("{:35s}".format("Address:"), lambda x: len(x) < 5,
                                  "The address can't have less than 5 characters"))

                history["phone"] = history.get(
                    "phone", None) if "phone" in history else history.setdefault(
                    "phone", try_get_input("{:35s}".format("[Phone]:"),
                                           "|\+?[0-9 ]+/?[0-9 -]+\d",
                                           "thats not a proper phone number") or None)

                history["email"] = history.get(
                    "email", None) if "email" in history else history.setdefault(
                    "email", get_email("{:35s}".format("[Email]:")))

                history["comment"] = history.get(
                    "comment", None) if "comment" in history else history.setdefault(
                    "comment", input("{:35s}".format("\r[Comment]:")) or None)

                history["init_pay"] = history.get(
                    "init_pay", None) or history.setdefault(
                    "init_pay", get_payment("{:35s}".format("Initial Payment in €:")))
                print()

                # write the stuff into the db
                player = Player(**history["name"],
                                **dict([(k, v) for k, v in history.items() if
                                        k in {"nickname", "address", "phone", "email", "comment"}])
                                )
                self.session.add(player)
                self.session.flush()
                pid = player.pid
                self.session.add(Account(pid=pid,
                                         comment="initial",
                                         deposit=history["init_pay"],
                                         date=date.today(),
                                         last_modified=datetime.now()))
                self.session.commit()
                info('Added Player "%s"' % pid)
                history.clear()
            except EOFError:
                if history:
                    print("\033[F" + 80 * " ", end="")
                    history.popitem()
                else:
                    return

    def createtally(self, turnierseq: List[int]):
        if not turnierseq:
            turnierseq = self.infer_turniernumbers()

        players = self.get_active_players()
        ordercode = self.ordercode(set(players))
        existing_tids = set(chain.from_iterable(self.session.query(Tournament.tid).all()))
        for tid in filter(lambda x: x not in existing_tids, turnierseq):
            self.session.add(Tournament(tid=tid, ordercode=ordercode))
        if set(turnierseq) - existing_tids:
            self.session.commit()
            print('Created tallies with the numbers {} and ordercode "{}"'.format(str(turnierseq), ordercode))

    def transfer(self):
        print("\nApportion cost from a player among a set of players:\n\tPress ctrl + c to finish input\n")
        history = OrderedDict()
        while True:
            try:
                history["event"] = history.get(
                    "event", None) or history.setdefault(
                    "event", try_get_input("{:35s}".format("For what occasion:"), ".{2,}", "Please provide a event"))

                history["date"] = history.get(
                    "date", None) or history.setdefault(
                    "date", get_date("{:35s}".format("When was it:")))

                history["from_player"] = history.get(
                    "from_player", None) or history.setdefault(
                    "from_player",
                    self.get_user(
                        "{:35s}".format("Player that payed the event\n(leave empty if payment from Flunkykasse): "),
                        True))

                getother = partial(self.get_user, "{:35s}".format("Players that consumed:"))
                history["to_players"] = history.get(
                    "to_players", None) or history.setdefault(
                    "to_players", OrderedSet([getother()]))
                while True:
                    try:
                        history["to_players"].add(getother())
                    except EOFError:
                        break
                history["transfer"] = history.get(
                    "transfer", None) or history.setdefault(
                    "transfer", get_payment("Amount of money to transfer from {} to {}: ".format(
                        history["to_players"], history["from_player"] or "Flunkykasse")))
                # the transfer is split as evenly as possible.
                # it must properly sum up, but we can only use 2 decimal places
                # to achieve that we will calculate the correct fraction and than cut rounded parts from the sum,
                # in order to get junks as similar as possible. the amounts will not differ by more than 1 cent
                fraction = history["transfer"] / len(history["to_players"])

                for i, player in enumerate(history["to_players"]):
                    fair_amount = round(round(fraction * (i + 1), 2) - round(fraction * i, 2), 2)

                    self.session.add(
                        Account(pid=player.pid,
                                comment=history["event"] + ": payment to {}".format(
                                    history["from_player"] or "Flunkykasse"),
                                deposit=-fair_amount,
                                show_in_billing=False,
                                date=history["date"],
                                last_modified=datetime.now()))

                if history["from_player"]:
                    # the payment was not taken from the flunkykasse, but some player payed the event
                    self.session.add(Account(pid=history["from_player"].pid,
                                             comment="Payed " + history["event"],
                                             deposit=history["transfer"],
                                             show_in_billing=False,
                                             date=history["date"],
                                             last_modified=datetime.now()))
                self.session.commit()
                print()
                break
            except EOFError:
                if history:
                    print("\033[F" + 80 * " ", end="")
                    last = list(history.values())[-1]
                    if hasattr(last, "__len__") and len(last) > 1:
                        # last element is a container, so we pop single elements
                        if isinstance(last, (OrderedSet, OrderedDict)):
                            last.popitem()
                        elif isinstance(last, list):
                            last.pop()
                        else:
                            debug("Couldnt interpret history item, therefore it has been poped completely")
                            history.popitem()
                    else:
                        history.popitem()

    def tally(self, turnierseq: list):
        viewmodel = TallyVM(self.session, self.config, self)
        viewmodel.main(turnierseq)

    def deposit(self, date=None):
        print("\nAdding deposit for players:\n\tPress ctrl + d to finish input\n")
        history = OrderedDict()
        while True:
            try:
                history["pid"] = history.get(
                    "pid", None) or history.setdefault(
                    "pid", self.get_user().pid)

                history["deposit"] = history.get(
                    "deposit", None) or history.setdefault(
                    "deposit", get_payment("{:35s}".format("Deposit in €:")))

                history["date"] = date or history.get(
                    "date", None) or history.setdefault(
                    "date", get_date("{:35s}".format("When did he pay:")))

                history["comment"] = history.get(
                    "comment", None) or history.setdefault(
                    "comment", input("\r{:35s}".format("[Comment]:")) or None)

                self.session.add(Account(**history,
                                         last_modified=datetime.now()))
                print()
                self.session.commit()
                history.clear()
            except EOFError:
                if history:
                    print("\033[F" + 80 * " ", end="")
                    history.popitem()
                else:
                    return

    @lru_cache(128)
    def balance(self, player):
        return sum((v[0] for v in self.session.query(
            Account.deposit).filter(Account.pid == player.pid).all()))

    def bill_tallymarks(self):
        beerprice = self.config.getfloat("billing", "beerprice")
        for mark in self.session.query(Tallymarks).filter(Tallymarks.accounted == False).all():
            date = self.session.query(Tournament).filter(Tournament.tid == mark.tid).first().date
            self.session.add(Account(pid=mark.pid, deposit=-beerprice * mark.beers, show_in_billing=False,
                                     comment="{} beers for {:.2f}€ each".format(mark.beers, beerprice),
                                     date=date, last_modified=datetime.now()))
            mark.accounted = True
        self.session.commit()

    def is_large_debtor(self, player: Player) -> bool:
        return self.balance(player) < self.config.getint("billing", "debt_threshold")

    def billing(self):
        # print balance for active and inactive players each sorted alphabtically

        self.bill_tallymarks()

        send_mail = get_bool("Send account balance to each user with email [Y/n]: ")
        if send_mail:
            server = self.config.get("email", "smtp_server")
            usr = self.config.get("email", "smtp_username")
            sender = self.config.get("email", "sender_email")
            pwd = getpass('Email Password for account "{}": '.format(sender))
            with open(self.config.get("email", "letter_body_file")) as f:
                body = f.read()

            pool = Pool(16)

        def print_balance(player, send=send_mail):
            depo = self.balance(player)
            if send and player.email:
                pool.apply_async(sendmail, (server, usr, pwd, sender, player.email, body, depo))
            return ("{:" + str(longest_name) + "s} " + str(" " * 10) + " {:-7.2f}€\n").format(str(player), depo)

        wall_of_shame = list(
            sorted(filter(is_large_debtor,
                          self.session.query(
                              Player).all()), key=self.balance))[:self.config.getint("billing",
                                                                                     "n_largest_debtors")]
        active_players = set(self.get_active_players())
        all_players = set(self.session.query(Player).all())

        longest_name = max(map(lambda p: len(repr(p)), active_players | all_players))
        heading = "### {:^" + str(longest_name + 19 - 6) + "s}###\n"

        string = ""
        if wall_of_shame:
            string += heading.format("Wall of Shame")
            for player in wall_of_shame:
                string += print_balance(player, false)

        if active_players:
            if string:
                string += "\n"
            string += heading.format("Aktive Spieler")
            for player in sorted(active_players, key=lambda p: str(p)):
                string += print_balance(player)

        if all_players:
            if string:
                string += "\n"
            string += heading.format("Alle Spieler")
            for player in sorted(all_players, key=lambda p: str(p)):
                string += print_balance(player)

        n_last_deposits = self.config.getint("billing", "n_last_deposits")
        if n_last_deposits > 0:
            deposits = self.session.query(Account).filter(
                Account.show_in_billing == True).order_by(
                Account.date.desc()).limit(n_last_deposits).all()
            if deposits:
                if string:
                    string += "\n"
                string += heading.format("Letzte Einzahlungen")
                for deposit in reversed(deposits):
                    string += ("{:" + str(longest_name) + "s} {} {:-7.2f}€\n").format(
                        str(self.session.query(Player).filter(Player.pid == deposit.pid).first()),
                        deposit.date.strftime("%d.%m.%Y"), deposit.deposit)

        print("<pre>\n" + string + "</pre>")

    def printtally(self, print_target: str):
        # prints all unprinted tallys. if there are none, it will ask, which tallys to print

        try:
            filename = self.create_tally_pdf()
        except CalledProcessError:
            error("Tally generation failed. LaTeX template could not be compiled.")
            return

        info("pdf has been created, all tallys are printed")

        if print_target is None:
            print("You didn't request printing, therefore only the pdf was built")
        elif print_target == "asta":
            logins = [(str(usr), str(pwd)) for usr, pwd in eval(self.config.get("print", "asta_logins")).items()]
            upload = partial(asta_upload, display_filename=filename,
                             filepath=path.join(self.config.get("print", "tex_folder"), filename))
            with Pool() as p:
                p.map_async(upload, logins)
        elif print_target == "local":
            try:
                print("Printing on default printer using lpr")
                run(["lpr", filename], stdout=DEVNULL, cwd=self.config.get("print", "tex_folder"), check=True)
            except CalledProcessError:
                print("Printing failed. Make sure you call this on linux with lpr properly configured.")

    def infer_turniernumbers(self) -> List[int]:
        # retrieve tallynumbers by looking at the
        last_number = self.session.query(Tournament.tid).order_by(Tournament.tid.desc()).first()
        if last_number:
            start = last_number[0] + 1
        else:
            # there are no tournaments in the database
            start = int(try_get_input("What is the number of the next tournament? ",
                                      "\d+",
                                      "You did not provide a number!"))
        return list(range(start, start + self.config.getint("print", "n")))

    def get_active_players(self) -> List[Player]:
        # retrieve at most the n most active players using an exponentialy weighted average

        limit, alpha, n = self.config.getint("print", "cutoff"), \
                          self.config.getfloat("print", "alpha"), \
                          self.config.getint("print", "n_active_players")

        player_activity = defaultdict(lambda: (None, 0))

        for tournament in reversed(self.session.query(Tournament).order_by(Tournament.date.desc()).limit(limit).all()):
            # starting with the latest date
            players_at_tournament = self.session.query(Player).filter(
                Player.pid == Tallymarks.pid).filter(Tallymarks.tid == tournament.tid).all()
            # discount history
            for pid, v in player_activity.items():
                player_activity[pid] = (v[0], (1 - alpha) * player_activity[pid][1])
            for player in players_at_tournament:
                # actually "alpha * 1" for the current + the history
                player_activity[player.pid] = (player, alpha + player_activity[player.pid][1])

        # get the "n" most active players
        n_most_active = list(reversed(sorted(player_activity.items(), key=lambda x: x[1][1])))[:n]
        if len(n_most_active) < n:
            info("There where not enough active players to fill the list")
        # return the players in alphabetical order
        return list(sorted(map(lambda x: x[1][0], n_most_active)))

    def ordercode(self, players: Set[Player]) -> str:
        if not players:
            return ""
        playerIDs = {player.pid for player in players}
        for ordercode, group in groupby(self.session.query(TournamentPlayerLists).all(), key=lambda x: x.id):
            playerSet = set([tournamentplayer.pid for tournamentplayer in group])
            if playerIDs == playerSet:
                return ordercode

        # create new ordercode
        while True:
            ordercode = self.gen_new_ordercode()
            if ordercode not in chain.from_iterable(self.session.query(TournamentPlayerLists.id).all()):
                break
        self.session.add_all([TournamentPlayerLists(id=ordercode, pid=player) for player in playerIDs])
        self.session.commit()

        return ordercode

    def get_user(self, prompt="{:35s}".format("Input User: "), allow_empty=False) -> Union[Player, None]:
        players = self.session.query(Player).all()
        completer = Completer(players)
        old_completer = readline.get_completer()
        readline.set_completer(completer.complete_str)
        readline.parse_and_bind('tab: complete')
        try:
            while True:
                prefix = input("\r" + prompt)
                first, second = completer.complete(prefix, 0), completer.complete(prefix, 1)
                if prefix == "" and allow_empty:
                    return None
                if first is not None and second is None:
                    # there is no second element in the completion
                    # therefore we take the first
                    result = first
                    result.n = None
                    # autocomplete the console output (the trailing whitespaces are needed to clear the previous line)
                    print("\033[F{}{}    ".format(prompt, repr(result)))
                    break
                else:
                    completes = list(filter(None, [completer.complete_str(prefix, i) for i in range(20)]))
                    if len(completes) > 0:
                        print("    ".join(completes))
                    else:
                        print("Couldn't interpret input")
        finally:
            readline.set_completer(old_completer)
        return result.player

    @staticmethod
    def gen_new_ordercode():
        vowel = set("a e i o u".split())
        consonant = set(map(chr, range(97, 123))) - vowel

        code = ""
        for i in range(6):
            code += sample(vowel, 1)[0] if i % 2 == 0 else sample(consonant, 1)[0]

        return code.capitalize()

    def create_tally_pdf(self):
        n = self.config.getint("print", "n")
        start = self.predict_next_tournament_number()
        tids = list(range(start, start + n))
        self.createtally(tids)
        are_tids_ok = get_bool("You are about to print [{}] [Y/n]: ".format(", ".join(map(str, tids))))

        # get tournaments to print
        if are_tids_ok:
            tids_to_print = tids
        else:
            tids_to_print = get_tournaments("Which Tournaments to print? ")
        if not tids_to_print:
            return None

        tallys_to_print = [self.session.query(Tournament).filter(Tournament.tid == tid).first()
                           for tid in tids_to_print]

        code = ""
        for tally in tallys_to_print:
            playerlist = self.session.query(Player).join(TournamentPlayerLists).filter(
                TournamentPlayerLists.id == tally.ordercode).all()
            playerstrings = [
                p.short_str() + (" {\scriptsize(%.2f€)}" % self.balance(p) if self.is_large_debtor(p) else "")
                for p in playerlist]
            date = tally.date or self.predict_or_retrieve_tournament_date(tally.tid)
            responsible = re.split(",\s*", self.config.get("print", "responsible"))
            code += create_tally_latex_code(tally.tid, date, tally.ordercode, playerstrings, responsible)

            with open("latex/content.tex", "w") as f:
                print(code, file=f)

            # compile document
            run("pdflatex -interaction=nonstopmode".split() + [self.config.get("print", "tex_template")]
                , stdout=DEVNULL, cwd=self.config.get("print", "tex_folder"), check=True)

        self.session.commit()
        return "Flunkylisten {}".format(", ".join(map(str, tallys_to_print)))

    def predict_next_tournament_number(self) -> int:
        last_tournament_wdate = self.last_tid_with_date()
        next_tuesday = date.today() + timedelta(days=(2 - date.today().weekday()) % 7)
        weeks_passed = int(ceil((next_tuesday - last_tournament_wdate.date).days // 7))
        return last_tournament_wdate.tid + weeks_passed

    def last_tid_with_date(self) -> Tournament:
        return self.session.query(Tournament).filter(
            Tournament.date != None).order_by(Tournament.date.desc()).first()

    def predict_or_retrieve_tournament_date(self, tid) -> date:
        # retrieve last tournament with date
        tournament = self.session.query(Tournament).filter(Tournament.tid == tid).first()
        if tournament.date:
            return tournament.date
        last_tournament_wdate = self.last_tid_with_date()
        if last_tournament_wdate:
            # this will also be called if tid < last_tournament_wdate
            # but this doesn't matter, as this case is rare and even than its not wrong
            delta_tournament_n = tid - last_tournament_wdate.tid
            return last_tournament_wdate.date + timedelta(weeks=delta_tournament_n)


def sendmail(server, usr, pwd, sender, receiver, body, depo):
    try:
        with SMTP(host=server) as smtp:
            smtp.starttls()
            smtp.login(usr, pwd)
            msg = Message()
            msg["subject"] = "Flunky Kontostand (Stand: {})".format(
                date.today().strftime("%d.%m.%Y"))
            msg["from"] = sender
            msg["to"] = receiver
            msg.set_payload(body.format(depo), charset="utf-8")
            smtp.send_message(msg, sender, receiver)
    except SMTPAuthenticationError:
        error("EmailAuthentication Failed. No emails sent.")
    except socket.gaierror:
        warning("No network connection ({})".format(receiver))
