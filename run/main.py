#!/usr/bin/env python
import os
import re
import warnings
from configparser import ConfigParser
from datetime import date, datetime, timedelta
from glob import glob
from logging import getLogger, debug, info
from shutil import copy2
from subprocess import DEVNULL, run

import pandas as pd
from sqlalchemy import exc as sa_exc, create_engine
from sqlalchemy.orm import Session

from flunkyabrechnung import *


def backupdb():
    fileprefix, suffix = re.fullmatch("(.*)\.(\w+)", os.path.basename(config.get("DEFAULT", "dbpath"))).groups()
    os.makedirs(config.get("DEFAULT", "dbbackupfolder"), exist_ok=True)
    time_stamps = list(sorted(map(lambda s: re.search("\d{4}-\d{2}-\d{2}", s)[0],
                                  glob(os.path.join(
                                      config.get("DEFAULT", "dbbackupfolder"), "*" + fileprefix + "*." + suffix)))))
    if time_stamps:
        last_date = datetime.strptime(max(time_stamps), "%Y-%m-%d")
        do_backup = datetime.today() - last_date >= timedelta(days=config.getint("DEFAULT", "backup-n-days"))
    else:
        do_backup = True
    if do_backup:
        copy2(config.get("DEFAULT", "dbpath"),
              os.path.join(
                  config.get("DEFAULT", "dbbackupfolder"),
                  "{}_{}.{}".format(fileprefix, date.today().isoformat(), suffix)
              ))


def export_players():
    template = r"""\documentclass[a4]{{scrartcl}}
    \usepackage[utf8]{{inputenc}}
    \usepackage[top=1.5cm,bottom=1.5cm,left=1cm,right=1cm,
    footskip=.5cm]{{geometry}}
    \usepackage{{booktabs,longtable}}
    \begin{{document}}
    \centering
    {}
    \end{{document}}
    """

    tmpfile = "/tmp/players.tex"

    df = pd.read_sql(sess.query(Player).statement, sess.bind).sort_values(["firstname", "middlename", "lastname"])
    with open(tmpfile, "w") as f:
        print(template.format(
            pd.concat([df.loc[:, "firstname":"lastname"], df.loc[:, "email":"comment"]], axis=1).to_latex(
                na_rep="", longtable=True, index=False, column_format="l" + "|l" * 4)), file=f)
    run("latexmk -pdf -quiet".split() + [tmpfile], stdout=DEVNULL, stderr=DEVNULL,
        cwd=config.get("print", "tex_folder"))
    run("latexmk -c -quiet".split() + [tmpfile], stdout=DEVNULL, cwd=config.get("print", "tex_folder"))


if __name__ == "__main__":
    try:
        # Load config
        config = ConfigParser()
        config.read("main.conf")

        # Create SQLalchemy engine (initialize vars and so on)
        warnings.simplefilter("ignore", category=sa_exc.SAWarning)
        os.makedirs(os.path.dirname(config.get("DEFAULT", "dbpath")), exist_ok=True)
        engine = create_engine("sqlite:///" + config.get("DEFAULT", "dbpath"))
        Base.metadata.create_all(engine)
        sess = Session(bind=engine)

        # update beerprice
        last_price = sess.query(Prices).order_by(Prices.date_from.desc()).first()
        current_price = config.getfloat("billing", "beer_price")
        if not last_price or float(last_price.beer_price) != current_price:
            sess.add(Prices(beer_price=current_price, date_from=date.today()))
        sess.commit()

        # Load argparser get arguments
        argparser = ArgumentParser(sess, config)
        args = argparser.getargs()
        getLogger().setLevel(30 - 10 * (args.verbose or 0))
        command_order = eval(config.get("DEFAULT", "command_order"))
        commands = list(filter(lambda x: x[0] in command_order, vars(args).items()))

        # backup db
        backupdb()

        # call commands one by one
        command_provider = CommandProvider(sess, config)
        for cmd, arg in sorted(commands, key=lambda x: command_order.index(x[0])):
            try:
                func = getattr(command_provider, cmd)
                debug("Executing \"{}\" with args: {}".format(cmd, arg))
                if not isinstance(arg, bool):
                    func(arg)
                else:
                    func()
            except AttributeError as e:
                info(e)

        export_players()
    except KeyboardInterrupt:
        pass
