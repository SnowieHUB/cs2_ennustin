"""
Yhteinen apufunktio verkkopyyntöihin.

Kaikki datalähteet hakevat datansa tämän kautta, joten User-Agent,
pakkaus ja aikakatkaisu on määritelty yhdessä paikassa.
"""

import gzip
import os
import urllib.request

# Hyvä tapa (ja Liquipedian sääntö): kerro, kuka hakee dataa.
# Halutessasi lisää yhteystieto:  export CS2_ENNUSTIN_CONTACT="oma@sahkoposti.fi"
_contact = os.environ.get("CS2_ENNUSTIN_CONTACT")
USER_AGENT = "cs2-ennustin/0.2 (personal learning project" + (f"; {_contact}" if _contact else "") + ")"


def get_text(url: str, headers: dict | None = None, timeout: int = 30) -> str:
    """Hakee osoitteen sisällön tekstinä.

    Pyydetään gzip-pakattu vastaus (Liquipedia vaatii tämän) ja puretaan
    se tarvittaessa.
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8")
