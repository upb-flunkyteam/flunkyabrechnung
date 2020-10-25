FROM tiangolo/uwsgi-nginx:python3.8

COPY . /app
COPY run /app
# this overwrites the main.py from the run folder
COPY web /app

# noninteractive is needed to install texlive without a dialog
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y latexmk texlive-latex-extra

RUN pip install -r /app/requirements.txt