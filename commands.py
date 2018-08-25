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
from util import *


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
        self.db = session
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
                    "nickname", input("{:35s}".format("\r[Nickname]:")).strip())

                history["address"] = history.get("address", None) or history.get(
                    "address", input("{:35s}".format("Address:")))

                history["phone"] = history.get(
                    "phone", None) if "phone" in history else history.setdefault(
                    "phone", try_get_input("{:35s}".format("[Phone]:"),
                                           "|\+?[0-9 ]+/?[0-9 -]+\d",
                                           "thats not a proper phone number"))

                history["email"] = history.get(
                    "email", None) if "email" in history else history.setdefault(
                    "email", get_email("{:35s}".format("[Email]:")))

                history["comment"] = history.get(
                    "comment", None) if "comment" in history else history.setdefault(
                    "comment", input("{:35s}".format("\r[Comment]:")))

                history["init_pay"] = history.get(
                    "init_pay", None) or history.setdefault(
                    "init_pay", get_payment("{:35s}".format("Initial Payment in €:")))
                print()

                # write the stuff into the db
                player = Player(**history["name"],
                                **dict([(k, v) for k, v in history.items() if
                                        k in {"nickname", "address", "phone", "email", "comment"}])
                                )
                self.db.add(player)
                self.db.flush()
                pid = player.pid
                self.db.add(Account(pid=pid,
                                    comment="initial",
                                    deposit=history["init_pay"],
                                    date=date.today(),
                                    last_modified=datetime.now()))
                self.db.commit()
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
        existing_tids = set(chain.from_iterable(self.db.query(Tournament.tid).all()))
        for tid in filter(lambda x: x not in existing_tids, turnierseq):
            self.db.add(Tournament(tid=tid, ordercode=ordercode))
        if set(turnierseq) - existing_tids:
            self.db.flush()
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

                history["to_players"] = history.get(
                    "to_players", None) or history.setdefault(
                    "to_players",
                    self.get_user("{:45s}".format("Players that consumed (comma separated):"), allow_multiple=True))

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

                    self.db.add(
                        Account(pid=player.pid,
                                comment=history["event"] + ": payment to {}".format(
                                    history["from_player"] or "Flunkykasse"),
                                deposit=-fair_amount,
                                show_in_billing=False,
                                date=history["date"],
                                last_modified=datetime.now()))

                if history["from_player"]:
                    # the payment was not taken from the flunkykasse, but some player payed the event
                    self.db.add(Account(pid=history["from_player"].pid,
                                        comment="Payed " + history["event"],
                                        deposit=history["transfer"],
                                        show_in_billing=False,
                                        date=history["date"],
                                        last_modified=datetime.now()))
                self.db.commit()
                print()
                break
            except EOFError:
                if history:
                    print("\033[F" + 80 * " ", end="")
                    last = list(history.values())[-1]
                    if hasattr(last, "__len__") and len(last) > 1:
                        # last element is a container, so we pop single elements
                        if isinstance(last, (OrderedDict)):
                            last.popitem()
                        elif isinstance(last, list):
                            last.pop()
                        else:
                            debug("Couldnt interpret history item, therefore it has been poped completely")
                            history.popitem()
                    else:
                        history.popitem()

    def tally(self, turnierseq: list):
        viewmodel = TallyVM(self.db, self.config, self)
        viewmodel.main(turnierseq)

    def gettally(self, turnierseq: list):
        if not turnierseq:
            turnierseq = [(t.tid, None) for t in
                          reversed(self.db.query(Tournament).order_by(Tournament.tid.desc()).limit(5).all())]
        for i, tid in enumerate(dict(turnierseq).keys()):
            if i != 0:
                print()
            tournament = self.db.query(Tournament).filter(Tournament.tid == tid).first()
            print("Tournament", tid, "at {}".format(tournament.date) if tournament else "")
            for tallymarks, p in sortedplayers(self.db.query(Tallymarks, Player).join(Player).filter(
                    Tallymarks.tid == int(tid)).all(), 1):
                print("  {:<35s} {:3d}".format(str(p), tallymarks.beers))

    def deposit(self, date=None):
        print("\nAdding deposit for players:\n\tPress ctrl + d to finish input\n")
        history = OrderedDict()
        while True:
            try:
                history["pid"] = history.get(
                    "pid", None) if "pid" in history else history.setdefault(
                    "pid", self.get_user().pid)

                history["deposit"] = history.get(
                    "deposit", None) if "deposit" in history else history.setdefault(
                    "deposit", get_payment("{:35s}".format("Deposit in €:")))

                history["date"] = date or history.get(
                    "date", None) or history.setdefault(
                    "date", get_date("{:35s}".format("When did he pay:")))

                history["comment"] = history.get(
                    "comment", None) if "comment" in history else history.setdefault(
                    "comment", input("\r{:35s}".format("[Comment]:")) or None)

                self.db.add(Account(**history,
                                    last_modified=datetime.now()))
                print()
                self.db.commit()
                history.clear()
            except EOFError:
                if history:
                    print("\033[F" + 80 * " ", end="")
                    history.popitem()
                else:
                    return

    def billing_info(self, player):
        lastdate = date.today() - timedelta(
            weeks=self.config.getint("billing", "n_weeks_deposits_of_last_in_email"))
        payments = self.db.query(Account).filter(
            Account.pid == player.pid, Account.date > lastdate).order_by(
            Account.date.desc()).all()
        return self.balance(player), payments

    @lru_cache(128)
    def balance(self, player):
        result = 0

        marks_tournament = self.db.query(Tallymarks, Tournament).join(Tournament).filter(
            Tallymarks.pid == player.pid).order_by(Tournament.date).all()
        prices = self.db.query(Prices).order_by(Prices.date_from).all()
        i = 0
        # only go in for loop if marks_tournament not None
        for mark, tournament in marks_tournament or []:
            if len(prices) > i + 1 and prices[i + 1].date_from <= tournament.date:
                if prices[i].date_from > tournament.date:
                    error("There are Tallymarks with no valid price."
                          " Please check that the prices table has a"
                          " beerprice for dates from {}".format(tournament.date.strftime("%d.%m.%Y")))
                    break
                i += 1
            result -= prices[i].beer_price * mark.beers

        return result + sum((v[0] for v in self.db.query(
            Account.deposit).filter(Account.pid == player.pid).all()))

    def is_large_debtor(self, player: Player) -> bool:
        return self.balance(player) < self.config.getint("billing", "debt_threshold")

    def billing(self, playerstring=None):
        # print balance for active and inactive players each sorted alphabtically

        def print_balance(player):
            depo = self.balance(player)
            return ("{:" + str(longest_name) + "s} " + str(" " * 10) + " {:-7.2f}€\n").format(str(player), depo)

        wall_of_shame = list(
            sorted(filter(self.is_large_debtor,
                          self.db.query(
                              Player).all()), key=self.balance))[:self.config.getint("billing",
                                                                                     "n_largest_debtors")]
        active_players = set(self.get_active_players())
        all_players = set(self.db.query(Player).all())

        if playerstring is not None:
            playerstring = " ".join(playerstring)
            completer = Completer(all_players)
            for i, playerexpr in enumerate(map(lambda s: s.strip(), playerstring.split(","))):
                if i != 0:
                    print("\n")
                result = self.fillprefix(completer, playerexpr)
                if result is None:
                    print("Could not find unique player matching:", playerexpr)
                    player = self.get_user()
                else:
                    player = result.player
                balance, payments = self.billing_info(player)

                print("Aktuelles Flunky Guthaben von {} beträgt {:.2f}€".format(player, balance))
                if payments:
                    print("\nSeine letzten Kontobewegungen:")
                    print("\n".join(map(str, payments)))
            return

        self.sendmails(all_players, wall_of_shame)

        longest_name = max(map(lambda p: len(repr(p)), active_players | all_players))
        heading = "### {:^" + str(longest_name + 19 - 6) + "s}###\n"

        string = ""
        if wall_of_shame:
            string += heading.format("Wall of Shame")
            for player in wall_of_shame:
                string += print_balance(player)

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
            deposits = self.db.query(Account).filter(
                Account.show_in_billing == True).order_by(
                Account.date.desc()).limit(n_last_deposits).all()
            if deposits:
                if string:
                    string += "\n"
                string += heading.format("Letzte Einzahlungen")
                for deposit in reversed(deposits):
                    string += ("{:" + str(longest_name) + "s} {}\n").format(
                        str(self.db.query(Player).filter(Player.pid == deposit.pid).first()),
                        deposit)

        print("<pre>\n" + string + "</pre>")

        print("\nTotal balance: {:.2f}€".format(sum(map(self.balance, all_players))))

    def sendmails(self, all_players, wall_of_shame):
        if get_bool("Send account balance to each user with email [Y/n]: "):
            host = self.config.get("email", "smtp_server")
            usr = self.config.get("email", "smtp_username")
            sender = self.config.get("email", "sender_email")
            pwd = getpass('Email Password for account "{}": '.format(sender))
            mailsender = MailSender(host, usr, pwd, sender, self)
            print("\nSending Emails", end="")
            try:
                with mailsender:
                    for player in all_players:
                        mailsender.sendmail(player, player in wall_of_shame)
            except SMTPAuthenticationError:
                error("EmailAuthentication Failed. No emails sent.")
            except socket.gaierror:
                warning("No network connection")
            print("\rEmails sent   ")

    def printtally(self, print_target: str):
        # prints all unprinted tallys. if there are none, it will ask, which tallys to print

        try:
            filename, displayname = self.create_tally_pdf()
        except CalledProcessError:
            error("Tally generation failed. LaTeX template could not be compiled.")
            return

        info("pdf has been created, all tallys are printed")

        if print_target is None:
            print("You didn't request printing, therefore only the pdf was built")
        elif print_target == "asta":
            logins = [(str(usr), str(pwd)) for usr, pwd in eval(self.config.get("print", "asta_logins")).items()]
            upload = partial(asta_upload, display_filename=displayname,
                             filepath=path.join(self.config.get("print", "tex_folder"), filename))
            with Pool() as p:
                p.map_async(upload, logins)
        elif print_target == "local":
            try:
                print("Printing on default printer using lpr")
                run(["lpr", filename], cwd=self.config.get("print", "tex_folder"), check=True)
            except CalledProcessError:
                print("Printing failed. Make sure you call this on linux with lpr properly configured.")

    def infer_turniernumbers(self) -> List[int]:
        # retrieve tallynumbers by looking at the
        last_number = self.db.query(Tournament.tid).order_by(Tournament.tid.desc()).first()
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

        for tournament in reversed(self.db.query(Tournament).order_by(Tournament.date.desc()).limit(limit).all()):
            # starting with the latest date
            players_at_tournament = self.db.query(Player) \
                .filter(Player.pid == Tallymarks.pid) \
                .filter(Tallymarks.tid == tournament.tid) \
                .filter(Tallymarks.beers > 0).all()
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
        debug(n_most_active)
        return list(sorted(map(lambda x: x[1][0], n_most_active)))

    def ordercode(self, players: Set[Player]) -> str:
        if not players:
            return ""
        playerIDs = {player.pid for player in players}
        for ordercode, group in groupby(self.db.query(TournamentPlayerLists).all(), key=lambda x: x.id):
            playerSet = set([tournamentplayer.pid for tournamentplayer in group])
            if playerIDs == playerSet:
                return ordercode

        # create new ordercode
        while True:
            ordercode = self.gen_new_ordercode()
            if ordercode not in chain.from_iterable(self.db.query(TournamentPlayerLists.id).all()):
                break
        self.db.add_all([TournamentPlayerLists(id=ordercode, pid=player) for player in playerIDs])
        self.db.commit()

        return ordercode

    def get_user(self, prompt="{:35s}".format("Input User: "), allow_empty=False, allow_multiple=False) -> Union[
        Player, None]:
        """
        :param from_string: if its none, the user will be prompted
        :param prompt:
        :param allow_empty:
        :param allow_multiple:
        :return:
        """
        dlm = ","
        players = self.db.query(Player).all()
        completer = Completer(players)
        old_completer = readline.get_completer()
        readline.set_completer(completer.complete_str)
        readline.set_completer_delims(dlm)
        readline.parse_and_bind('tab: complete')
        results = []
        failed = True
        try:
            while not results or failed:
                failed = False
                results = []
                prefixes = input("\r" + prompt)
                if prefixes == "" and allow_empty:
                    return None
                prefixes = prefixes.split(dlm)
                if len(prefixes) > 1 and not allow_multiple:
                    return None
                for i, prefix in enumerate(prefixes):
                    result = self.fillprefix(completer, prefix)

                    if result is not None:
                        # autocomplete the console output (the trailing whitespaces are needed to clear the previous line)
                        results.append(result)
                    else:
                        failed = True
                        print("input " + str(i + 1))
                        completes = list(filter(None, [completer.complete_str(prefix, i) for i in range(20)]))
                        if len(completes) > 0:
                            print("    ".join(completes))
                        else:
                            print("Couldn't interpret input")

                if not failed:
                    print("\033[F{}{}    ".format(prompt, ", ".join(str(result) for result in results)))
        finally:
            readline.set_completer(old_completer)
        results = [result.player for result in results]
        return results if allow_multiple else results[0]

    @staticmethod
    def fillprefix(completer, prefix):
        first, second = completer.complete(prefix, 0), completer.complete(prefix, 1)
        if first is not None and second is None:
            # there is no second element in the completion
            # therefore we take the first
            result = first
            result.n = None
            return result

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
        are_tids_ok = get_bool("You are about to print [{}] [Y/n]: ".format(", ".join(map(str, tids))))

        # get tournaments to print
        if are_tids_ok:
            tids = tids
        else:
            tids = get_tournaments("Which Tournaments to print? ")
        if not tids:
            return None

        self.createtally(tids)

        tallys_to_print = [self.db.query(Tournament).filter(Tournament.tid == tid).first()
                           for tid in sorted(tids)]

        code, date = "", None
        for i, tally in enumerate(tallys_to_print):
            playerlist = self.db.query(Player).join(TournamentPlayerLists).filter(
                TournamentPlayerLists.id == tally.ordercode).all()
            playerstrings = [
                p.short_str() + (" {\scriptsize(%.2f\,€)}" % self.balance(p) if self.is_large_debtor(p) else "")
                for p in sortedplayers(playerlist)]
            date = tally.date or self.predict_or_retrieve_tournament_date(
                tally.tid)
            responsible = re.split(",\s*", self.config.get("print", "responsible"))
            code += create_tally_latex_code(tally.tid, date, tally.ordercode, playerstrings, responsible)

            with open("latex/content.tex", "w") as f:
                print(code, file=f)

            # compile document
            run("latexmk -pdf -quiet".split() + [self.config.get("print", "tex_template")], stdout=DEVNULL,
                stderr=DEVNULL,
                cwd=self.config.get("print", "tex_folder"), check=True)
            run("latexmk -c -quiet".split() + [self.config.get("print", "tex_template")], stdout=DEVNULL,
                cwd=self.config.get("print", "tex_folder"))

        self.db.commit()
        return (re.sub(".tex$", ".pdf", self.config.get("print", "tex_template")),
                "Flunkylisten {}".format(", ".join(map(str, tallys_to_print))))

    def update_beers(self, beers: int, player: Player, tid: int):
        if isinstance(beers, int):
            if beers > 0:
                self.db.merge(
                    Tallymarks(pid=player.pid, tid=tid, beers=beers, last_modified=datetime.now()))
            elif beers == 0:
                self.db.query(Tallymarks).filter(Tallymarks.pid == player.pid,
                                                 Tallymarks.tid == tid).delete()
            self.db.commit()
            return
        # was not handled, therefore we warn
        warning("negative or none integer tallymarks detected")

    def predict_next_tournament_number(self) -> int:
        last_tournament_wdate = self.last_tid_with_date()
        if last_tournament_wdate:
            weeks_passed = int(ceil((self.next_flunkyday() - last_tournament_wdate.date).days / 7))
            return last_tournament_wdate.tid + weeks_passed
        else:
            return int(
                try_get_input("What is the number of the next tournament: ", "\d+", "Please provide an integer!"))

    def last_tid_with_date(self, before_tid=None) -> Tournament:
        query = self.db.query(Tournament).filter(
            Tournament.date != None).order_by(Tournament.date.desc())
        if before_tid:
            query = query.filter(Tournament.tid < before_tid)
        return query.first()

    def predict_or_retrieve_tournament_date(self, tid) -> date:
        # retrieve last tournament with date
        tournament = self.db.query(Tournament).filter(Tournament.tid == tid).first()
        if tournament.date:
            return tournament.date
        last_tournament_wdate = self.last_tid_with_date(tid)
        if last_tournament_wdate:
            # this will also be called if tid < last_tournament_wdate
            # but this doesn't matter, as this case is rare and even than its not wrong
            return self.next_flunkyday(last_tournament_wdate.date, tid - last_tournament_wdate.tid)
        else:
            return get_date("Date of the tournament {}: ".format(tid), default=self.next_flunkyday())

    def next_flunkyday(self, startdate=date.today(), min_weeks=0):
        offset = timedelta(days=(self.config.getint("print", "flunkyday") - startdate.weekday()) % 7) + timedelta(
            weeks=min_weeks)
        return startdate + offset


class MailSender:
    def __init__(self, host, usr, pwd, sender, controller):
        self.host = host
        self.usr = usr
        self.pwd = pwd
        self.sender = sender
        self.ctrl = controller

    def __enter__(self):
        self.smtp = SMTP(host=self.host)
        self.smtp.starttls()
        self.smtp.login(self.usr, self.pwd)

    def sendmail(self, player, shame=False):
        if player.email:
            msg = Message()
            msg["subject"] = "Flunky Kontostand (Stand: {})".format(
                date.today().strftime("%d.%m.%Y"))
            msg["from"] = self.sender
            msg["to"] = player.email
            balance, payments = self.ctrl.billing_info(player)
            body = "Dein aktuelles Flunky Guthaben beträgt {:.2f}€\n".format(balance)
            if shame:
                body += "Du hast es auf die Wall of Shame geschafft. Wird Zeit wieder mal die Schulden zu begleichen :D\n"
            if payments:
                body += "\nDeine letzten Kontobewegungen:\n"
                body += "\n".join(map(str, payments))

            msg.set_payload(body, charset="utf-8")
            self.smtp.send_message(msg, self.sender, player.email)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.smtp.quit()
