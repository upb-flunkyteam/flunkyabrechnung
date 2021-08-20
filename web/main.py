import io
import os
import pathlib
from configparser import ConfigParser

import requests
from flask import Flask, send_file, request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from flunkyabrechnung import CommandProvider, Base

app = Flask(__name__)


# app.jinja_env.add_extension('pypugjs.ext.jinja.PyPugJSExtension')


@app.route("/liste.pdf")
def images():
    # number of pages to create
    n = int(request.form.get('pages', 4))
    
    # Load config
    config = ConfigParser()
    config.read('main.conf')

    # Create SQLalchemy engine (initialize vars and so on)
    os.makedirs(os.path.dirname(config.get('DEFAULT', 'dbpath')), exist_ok=True)
    url = os.environ.get("DB_FILE_URL")
    r = requests.get(url)
    pathlib.Path(config.get('DEFAULT', 'dbpath')).write_bytes(io.BytesIO(r.content).getbuffer().tobytes())

    engine = create_engine(f"sqlite:///{config.get('DEFAULT', 'dbpath')}")
    Base.metadata.create_all(engine)
    sess = Session(bind=engine)

    command_provider = CommandProvider(sess, config)
    command_provider.create_tally_pdf(n, check_dates=False)

    return send_file(f'{config.get("print", "tex_folder")}/{config.get("print", "tex_template")[:-4]}.pdf',
                     mimetype='application/pdf')
