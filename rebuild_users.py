import json, time

users = {
    "6684244590": ("MishraCo", "MISHRA"),
    "7530034609": ("AbhiMlshra", "MISHRA"),
    "7859617687": ("Iaakshaay", "lakshaay"),
    "8593345434": ("gohi116", "AB116"),
    "1357211776": ("diosnas", "Diona"),
    "739729822":  ("Kinglionzz", "Rudy"),
    "7814638688": ("riflerx", "RIFLE"),
    "5683520023": ("taekeys", "Tae"),
    "6947448341": ("shanglee69", "\u20bf"),
    "491613151":  ("Kasperx0", "Cam"),
    "1402167837": ("fastmoneydulap", "Fast"),
    "6870438833": ("vyedime_doc", "Doc bowls"),
    "5537039876": ("valid0147", "Valid247"),
    "754786539":  ("theindigokid", "Indigokid"),
    "5874697465": ("blackmania784", "Black"),
    "1384145302": ("Chally01", "Simple"),
    "6492923512": ("officialklark", "Klark"),
    "7647018652": ("oboist", "Spike"),
    "5860177023": ("CCyoshi", "Yoshi"),
    "5523007531": ("dominikules_g", "Dominikules"),
    "5225079138": ("TrackHawkFrank_New", "Frank"),
    "7562176584": (None, "Raj singh"),
    "7070353643": (None, "Sec"),
    "6578079322": ("traviso", "Snappy"),
    "1820177597": ("titanextacy1", "Titan"),
    "6168264643": ("legalremoval", "Destro ( copyright unbans )"),
    "1619424668": ("Dooables", "DooAbles"),
    "678742772":  ("Bigbrrrddd", "Big"),
    "7628069503": (None, "Julie"),
    "8394635616": ("carnageceo", "carnage"),
    "5636731072": ("j0bss", "JOBS"),
    "6030054453": ("flame6s", "Flame \u2022 Active 24x7"),
    "5731618329": ("qoe8s", "Qoe8s"),
    "8117608120": ("Bazzigang", "Bazzi(Recovery, Lookup's, )"),
    "6270016289": ("G0dz0", "Godz"),
}

data = {"users": {}}
for uid, (uname, fname) in users.items():
    data["users"][uid] = {"username": uname, "first_name": fname, "ts": time.time()}

with open("users.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Restored {len(data['users'])} users.")
