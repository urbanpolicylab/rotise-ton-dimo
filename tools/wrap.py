"""Φτιάχνει τον φάκελο _site/ για GitHub Pages: τυλίγει το site/index.html σε πλήρες έγγραφο
(doctype, charset, viewport) και αντιγράφει τα δεδομένα. Το site/index.html μένει ως έχει,
ώστε να δημοσιεύεται και ως Artifact στο claude.ai."""
import pathlib, shutil
root = pathlib.Path(__file__).resolve().parent.parent
src, out = root / "site", root / "_site"
if out.exists(): shutil.rmtree(out)
shutil.copytree(src, out)
body = (src / "index.html").read_text(encoding="utf-8")
head = ('<!doctype html><html lang="el"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
        'body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>')
(out / "index.html").write_text(head + body + "</body></html>", encoding="utf-8")
print("έτοιμο:", out)
