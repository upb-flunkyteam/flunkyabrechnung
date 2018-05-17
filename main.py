from argparser import ArgumentParser
from configparser import ConfigParser
import os
from glob import glob
from commands import *
from datetime import datetime
from shutil import copy2
from logging import *
from sqlalchemy.orm import Session
import warnings
from sqlalchemy import exc as sa_exc

def backupdb():
    fileprefix, suffix = re.fullmatch("(.*)\.(\w+)", os.path.basename(config.get("DEFAULT", "dbpath"))).groups()
    os.makedirs(config.get("DEFAULT", "dbbackupfolder"), exist_ok=True)
    time_stamps = list(sorted(map(lambda s: re.search("\d{4}-\d{2}-\d{2}", s)[0],
                                  glob(os.path.join(
                                      config.get("DEFAULT", "dbbackupfolder"), "*" + fileprefix + "*." + suffix)))))
    if time_stamps:
        last_date = datetime.strptime(max(time_stamps), "%Y-%m-%d")
        do_backup = last_date - datetime.today() >= timedelta(days=config.getint("DEFAULT", "backup-n-days"))
    else:
        do_backup = True
    if do_backup:
        copy2(config.get("DEFAULT", "dbpath"),
              os.path.join(
                  config.get("DEFAULT", "dbbackupfolder"),
                  "{}_{}.{}".format(fileprefix, date.today().isoformat(), suffix)
              ))


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
            except AttributeError:
                pass
    except KeyboardInterrupt:
        pass
