import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder


def asta_upload(sn_pin, filepath="Flunkyliste.pdf", display_filename='Flunkyliste.pdf'):
    server_url = 'https://copyclient.uni-paderborn.de/go?json=1'
    sn, pin = tuple(map(str, sn_pin))
    m = MultipartEncoder(
        fields={'sn': sn,
                'pin': pin,
                'document': (display_filename, open(filepath, 'rb'), 'application/pdf'),
                'colormode': "grayscale",
                'pageorientation': "portrait",
                'duplexmode': "noduplex",
                "nup": "1up",
                "pageselection": "oddandeven",
                "firstpage": "",
                "lastpage": "",
                "documentpassword": "",
                "cmd": "Hochladen"
                }
    )

    r = requests.post(server_url, data=m, headers={'Content-Type': m.content_type})

    print("Print sent to", sn)

    if "errormessage" in r.json():
        print("Print for" + sn + " failed")
        return False

    redirect = r.json()["redirectjson"]
    r = requests.get(redirect)
    while r.json()["refresh"] != 0:
        r = requests.get(redirect)
    print(r.json()["currentstatus"])
    return True
