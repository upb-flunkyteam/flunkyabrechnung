from dbo import *
from complete import Completer
import readline
from datetime import datetime, timedelta
from itertools import chain, groupby
from input_funcs import *
from multiprocessing import Pool
from functools import partial, lru_cache
from collections import defaultdict, OrderedDict
from uploader import asta_upload
from random import sample
from os import path
from tally_gen import *
import socket
from smtplib import SMTP, SMTPAuthenticationError
from email.message import Message
from getpass import getpass
from subprocess import run, DEVNULL, CalledProcessError
from tally_viewmodel import TallyVM
from typing import Set, List


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
                    "nickname", None) or history.setdefault(
                    "nickname", input("{:35s}".format("\r[Nickname]:")).strip() or None)

                history["address"] = history.get("address", None) or history.get(
                    "address",
                    try_get_input("{:35s}".format("Address:"), lambda x: len(x) < 5,
                                  "The address can't have less than 5 characters"))

                history["phone"] = history.get(
                    "phone", None) or history.setdefault(
                    "phone", try_get_input("{:35s}".format("[Phone]:"),
                                           "|\+?[0-9 ]+/?[0-9 -]+\d",
                                           "thats not a proper phone number") or None)

                history["email"] = history.get(
                    "email", None) or history.setdefault(
                    "email", get_email("{:35s}".format("[Email]:")))

                history["comment"] = history.get(
                    "comment", None) or history.setdefault(
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

    def createtally(self, turnierseq: list):
        if not turnierseq:
            # strip of tourniercodes
            turnierseq = self.infer_turniernumbers()

        players = self.get_active_players()
        ordercode = self.ordercode(set(players))
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
                    "from_player", self.get_user("{:35s}".format("Player that payed:")))

                getother = partial(self.get_user, "{:35s}".format("Other players:"))
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
                        history["to_players"], history["from_player"])))
                # the transfer is split as evenly as possible.
                # it must properly sum up, but we can only use 2 decimal places
                # to achieve that we will calculate the correct fraction and than cut rounded parts from the sum,
                # in order to get junks as similar as possible. the amounts will not differ by more than 1 cent
                fraction = history["transfer"] / len(history["to_players"])

                for i, player in enumerate(history["to_players"]):
                    fair_amount = round(round(fraction * (i + 1), 2) - round(fraction * i, 2), 2)
                    self.session.add(Account(pid=player.pid,
                                             comment=self.config.get("constants", "transaction_code")
                                                     + " " + history["event"]
                                                     + ": payment to {}".format(history["from_player"]),
                                             deposit=-fair_amount,
                                             date=history["date"],
                                             last_modified=datetime.now()))

                self.session.add(Account(pid=history["from_player"].pid,
                                         comment=self.config.get("constants", "transaction_code")
                                                 + " " + history["event"],
                                         deposit=history["transfer"],
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

    def deposit(self):
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

                history["date"] = history.get(
                    "date", None) or history.setdefault(
                    "date", get_date("{:35s}".format("When did he pay:")))

                history["comment"] = history.get(
                    "comment", None) or history.setdefault(
                    "comment",
                    self.config.get("constants", "deposit_code") + " " + input("\r{:35s}".format("[Comment]:")) or None)

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

    def billing(self):
        # print balance for active and inactive players each sorted alphabtically

        send_mail = get_bool("Send account balance to each user with email [Y/n]: ")
        if send_mail:
            server = self.config.get("email", "smtp_server")
            usr = self.config.get("email", "smtp_username")
            sender = self.config.get("email", "sender_email")
            pwd = getpass('Email Password for account "{}": '.format(sender))
            with open(self.config.get("email", "letter_body_file")) as f:
                body = f.read()

            pool = Pool(16)

        @lru_cache(128)
        def balance(player):
            return sum((v[0] for v in self.session.query(
                Account.deposit).filter(Account.pid == player.pid).all()))

        def print_balance(player, send=send_mail):
            depo = balance(player)
            if send and player.email:
                pool.apply_async(sendmail, (server, usr, pwd, sender, player.email, body, depo))
            return ("{:" + str(longest_name) + "s} " + str(" " * 10) + " {:-7.2f}€\n").format(str(player), depo)

        wall_of_shame = list(
            sorted(filter(
                lambda p: balance(p) < self.config.getint("billing", "dept_threshold"),
                self.session.query(
                    Player).all()), key=balance))[:self.config.getint("billing",
                                                                      "n_largest_deptors")]
        active_players = set(self.get_active_players())
        inactive_players = set(self.session.query(Player).all()) - active_players

        longest_name = max(map(lambda p: len(repr(p)), active_players | inactive_players))
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

        if inactive_players:
            if string:
                string += "\n"
            string += heading.format("Inaktive Spieler")
            for player in sorted(inactive_players, key=lambda p: str(p)):
                string += print_balance(player)

        n_last_deposits = self.config.getint("billing", "n_last_deposits")
        if n_last_deposits > 0:
            deposits = self.session.query(Account).filter(
                Account.comment.like(self.config.get("constants", "deposit_code") + "%")).order_by(
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

        filename = None
        try:
            filename = self.create_tally_pdf()
        except CalledProcessError:
            error("Tally generation failed. LaTeX template could not be compiled.")

        if filename is None:
            print("No unprinted tallies found. Try --createtally option")
            return

        info("pdf has been created, all tallys are printed")

        if print_target is None:
            print("You didn't request printing, therefore only the pdf was built")
        elif print_target == "asta":
            logins = [(str(usr), str(pwd)) for usr, pwd in eval(self.config.get("print", "asta_logins")).items()]
            upload = partial(asta_upload, display_filename=filename,
                             filepath=path.join(self.config.get("print", "tex_folder"),
                                                self.config.get("print", "tex_template")))
            with Pool() as p:
                p.map_async(upload, logins)
        elif print_target == "local":
            # TODO call a lpr subprocess
            pass

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

    def get_active_players(self) -> List[Player]:
        # retrieve at most the n most active players using an exponentialy weighted average

        limit, alpha, n = self.config.getint("createtally", "cutoff"), \
                          self.config.getfloat("createtally", "alpha"), \
                          self.config.getint("createtally", "n_active_players")

        player_activity = defaultdict(lambda: (None, 0))

        for tournament in self.session.query(Tournament).order_by(Tournament.date.desc()).limit(limit).all():
            # starting with the latest date
            players_at_tournament = self.session.query(Player).filter(
                Player.pid == Tallymarks.pid).filter(Tallymarks.tid == tournament.tid).all()
            for player in players_at_tournament:
                # actually "alpha * 1" for the current + the history
                player_activity[player.pid] = (player, alpha + (1 - alpha) * player_activity[player.pid][1])

        # get the "n" most active players
        n_most_active = list(sorted(player_activity.items(), key=lambda x: x[1][1]))[:n]
        if len(n_most_active) < n:
            info("There where not enough active players to fill the list")
        # return the players in alphabetical order
        return list(sorted(map(lambda x: x[1][0], n_most_active)))

    def ordercode(self, players: Set[Player]) -> str:
        if not players:
            return ""
        playerIDs = [player.pid for player in players]
        for ordercode, group in groupby(self.session.query(TournamentPlayerLists).all(), key=lambda x: x.id):
            if playerIDs == set([tournamentplayer.pid for tournamentplayer in group]):
                return ordercode

        # create new ordercode
        while True:
            ordercode = self.gen_new_ordercode()
            if ordercode not in chain.from_iterable(self.session.query(TournamentPlayerLists.id).all()):
                break
        self.session.add_all([TournamentPlayerLists(id=ordercode, pid=player) for player in playerIDs])
        self.session.commit()

        return ordercode

    def get_user(self, prompt="{:35s}".format("Input User: ")) -> Player:
        players = self.session.query(Player).all()
        completer = Completer(players)
        old_completer = readline.get_completer()
        readline.set_completer(completer.complete_str)
        readline.parse_and_bind('tab: complete')
        try:
            while True:
                prefix = input("\r" + prompt)
                first, second = completer.complete(prefix, 0), completer.complete(prefix, 1)
                if first is not None and second is None:
                    # there is no second element in the completion
                    # therefore we take the first
                    result = first
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
        # get all non printed tournaments
        unprinted_tallys = self.session.query(Tournament).filter(Tournament.printed == False).order_by(
            Tournament.tid).all()
        if not unprinted_tallys:
            return None

        latest_printed = self.session.query(Tournament).filter(Tournament.printed == True).order_by(
            Tournament.tid.desc()).first()
        # if not empty we retrieve the value, otherwise we assume zero
        if latest_printed:
            latest_printed = latest_printed.tid
        else:
            latest_printed = 0

        old_tallys = list(filter(lambda tally: tally.tid < latest_printed, unprinted_tallys))
        if old_tallys:
            print("There are old tallies that are not printed:\n ", ", ".join(map(str, old_tallys)))
            docreate = get_bool("Should they be printed? [Y/n]: ")
            if docreate or get_bool("Should they be marked printed? [Y/n]: "):
                for t in old_tallys:
                    t.printed = True

            if not docreate:
                unprinted_tallys = list(sorted(set(unprinted_tallys) - set(old_tallys)))

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
            responsible = re.split(",\s*", self.config.get("createtally", "responsible"))
            code += create_tally_latex_code(tally.tid, date, tally.ordercode, [repr(p) for p in playerlist],
                                            responsible)
            tally.printed = True

            with open("latex/content.tex", "w") as f:
                print(code, file=f)

            # compile document
            run("pdflatex -interaction=nonstopmode".split() + [self.config.get("print", "tex_template")]
                , stdout=DEVNULL, cwd=self.config.get("print", "tex_folder"), check=True)

        self.session.commit()
        return "Flunkylisten {}".format(", ".join(map(str, unprinted_tallys)))

    def predict_tournament_date(self, tid) -> date:
        # retrieve last tournament with date
        last_tournament_wdate = self.session.query(Tournament).filter(
            Tournament.date != None).order_by(Tournament.date.desc()).first()
        if last_tournament_wdate:
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
