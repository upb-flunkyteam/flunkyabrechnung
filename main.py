from argparser import getargs
from configparser import ConfigParser
import sys, os
from commands import *
from logging import *

if __name__ == "__main__":
    # Load config
    config = ConfigParser()
    config.read("main.conf")
    # TODO validate that all entries in the config are actually given

    # Load argparser get arguments
    args = getargs(sys.argv[1:] or config["DEFAULT"]["defaultcommand"].split())
    getLogger().setLevel(30 - 10 * (args.verbose or 0))
    commands = args.commands

    # Create SQLalchemy engine (initialize vars and so on)
    os.makedirs(os.path.dirname(config["DEFAULT"]["dbpath"]), exist_ok=True)
    engine = create_engine("sqlite:///" + config["DEFAULT"]["dbpath"])
    Base.metadata.create_all(engine)
    sess = Session(bind=engine)

    # call commands one by one
    command_provider = CommandProvider(sess, config)
    for cmd, arg in commands:
        debug("Executing \"{}\" with args: {}".format(cmd, arg))
        func = getattr(command_provider, cmd)
        if arg and not bool(arg):
            func(*arg)
        else:
            func()
