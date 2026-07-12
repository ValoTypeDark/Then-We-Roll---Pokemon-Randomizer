"""
Then We Roll - Pokémon Randomizer
Roll random abilities, Pokémon, typings, stat spreads and natures for
challenge runs — with accurate per-game pools and dramatic reveals.
─────────────────────────────────────────────────────────────────────────────────────
Abilities are loaded from  data/abilities.json  (relative to this script).
Run with --update-abilities to fetch fresh data from PokéAPI.
The app works fully offline once the cache exists.
"""

import json
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from urllib.request import urlopen, Request

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR       = os.path.join(SCRIPT_DIR, "data")
ABILITIES_FILE      = os.path.join(DATA_DIR, "abilities.json")
SETTINGS_FILE       = os.path.join(DATA_DIR, "settings.json")
AVATAR_FILE         = os.path.join(DATA_DIR, "avatar.png")
ICONS_DIR           = os.path.join(DATA_DIR, "icons")
POKEMON_FILE        = os.path.join(DATA_DIR, "pokemon.json")
POKEMON_SPRITES_DIR = os.path.join(DATA_DIR, "pokemon_sprites")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(POKEMON_SPRITES_DIR, exist_ok=True)

APP_TITLE    = "Then We Roll - Pokémon Randomizer"
POKEAPI_BASE = "https://pokeapi.co/api/v2"

VERSION    = "1.1.0"
GITHUB_API = "https://api.github.com/repos/ValoTypeDark/Ability-Randomiser/releases/latest"
# Note: legacy clients (≤1.0.1) update from the old script path, so a copy of
# this file is kept at pokemon_ability_randomizer.py in the repo — it hands
# them off to this URL on their next update.
GITHUB_RAW = "https://raw.githubusercontent.com/ValoTypeDark/Ability-Randomiser/refs/heads/main/then_we_roll.py"

GENERATIONS = ["GEN III", "GEN IV", "GEN V", "GEN VI", "GEN VII", "GEN VIII", "GEN IX"]
GEN_ORDER   = {g: i for i, g in enumerate(GENERATIONS)}

POKEAPI_GEN_MAP = {
    "generation-iii":  "GEN III", "generation-iv":   "GEN IV",
    "generation-v":    "GEN V",   "generation-vi":   "GEN VI",
    "generation-vii":  "GEN VII", "generation-viii": "GEN VIII",
    "generation-ix":   "GEN IX",
}

GAME_PRESETS = {
    "Ruby / Sapphire / Emerald":         "GEN III",
    "FireRed / LeafGreen":               "GEN III",
    "Diamond / Pearl / Platinum":        "GEN IV",
    "HeartGold / SoulSilver":            "GEN IV",
    "Black / White":                     "GEN V",
    "Black 2 / White 2":                 "GEN V",
    "X / Y":                             "GEN VI",
    "Omega Ruby / Alpha Sapphire":       "GEN VI",
    "Sun / Moon":                        "GEN VII",
    "Ultra Sun / Ultra Moon":            "GEN VII",
    "Sword / Shield":                    "GEN VIII",
    "Brilliant Diamond / Shining Pearl": "GEN IV",
    "Scarlet / Violet":                  "GEN IX",
    "Pokémon Champions":                 "GEN IX",
    "Custom":                            None,
}

# Abilities that only exist in Pokémon Champions (new Mega Evolution
# abilities) — hidden from every other game preset's ability pool.
CHAMPIONS_EXCLUSIVE = {
    "piercing-drill",   # Mega Excadrill
    "dragonize",        # Mega Feraligatr
    "mega-sol",         # Mega Meganium
    "spicy-spray",      # Mega Scovillain
    "eelevate",         # Mega Eelektross
    "fire-mane",        # Mega Pyroar
}

GEN_COLORS = {
    "GEN III": "#ff6b6b", "GEN IV": "#ffa94d", "GEN V":  "#ffe066",
    "GEN VI":  "#69db7c", "GEN VII": "#4dabf7", "GEN VIII": "#cc5de8",
    "GEN IX":  "#f783ac",
}

# National Dex ID ranges per generation (inclusive)
PARADOX_IDS = frozenset({
    984, 985, 986, 987, 988, 989,
    990, 991, 992, 993, 994, 995,
    1005, 1006,
    1009, 1010,
    1020, 1021, 1022, 1023,
})

CATEGORY_FILTER_OPTIONS = ["Any", "Only", "Exclude"]
CATEGORY_FILTERS = [
    ("baby",      "Baby"),
    ("base",      "Base Form"),
    ("stage1",    "Stage 1"),
    ("stage2",    "Stage 2+"),
    ("legendary", "Legendary"),
    ("mythical",  "Mythical"),
    ("paradox",   "Paradox"),
]

POKEMON_GEN_RANGES = {
    "GEN I":    (1,   151),
    "GEN II":   (152, 251),
    "GEN III":  (252, 386),
    "GEN IV":   (387, 493),
    "GEN V":    (494, 649),
    "GEN VI":   (650, 721),
    "GEN VII":  (722, 809),
    "GEN VIII": (810, 905),
    "GEN IX":   (906, 1025),
}

# Regional Pokédex slugs on PokéAPI for each game preset.
GAME_POKEDEX_SLUGS = {
    "Ruby / Sapphire / Emerald":         ["hoenn"],
    "FireRed / LeafGreen":               ["kanto"],
    "Diamond / Pearl / Platinum":        ["original-sinnoh", "extended-sinnoh"],
    "HeartGold / SoulSilver":            ["updated-johto"],
    "Black / White":                     ["original-unova"],
    "Black 2 / White 2":                 ["updated-unova"],
    "X / Y":                             ["kalos-central", "kalos-coastal", "kalos-mountain"],
    "Omega Ruby / Alpha Sapphire":       ["updated-hoenn"],
    "Sun / Moon":                        ["original-alola"],
    "Ultra Sun / Ultra Moon":            ["updated-alola"],
    "Sword / Shield":                    ["galar", "isle-of-armor", "crown-tundra"],
    "Brilliant Diamond / Shining Pearl": ["original-sinnoh"],
    "Scarlet / Violet":                  ["paldea", "kitakami", "blueberry"],
    "Pokémon Champions":                 ["champions"],
}

# PokéAPI version names per preset. Per-version encounter data adds wild/static
# availability the regional dex misses: post-game areas (Sevii Islands, HGSS
# Kanto, BW eastern Unova), roamers, ORAS soaring and USUM wormhole legendaries.
# Games newer than USUM have no encounter data on PokéAPI (dex + supplements only).
GAME_VERSIONS = {
    "Ruby / Sapphire / Emerald":   ["ruby", "sapphire", "emerald"],
    "FireRed / LeafGreen":         ["firered", "leafgreen"],
    "Diamond / Pearl / Platinum":  ["diamond", "pearl", "platinum"],
    "HeartGold / SoulSilver":      ["heartgold", "soulsilver"],
    "Black / White":               ["black", "white"],
    "Black 2 / White 2":           ["black-2", "white-2"],
    "X / Y":                       ["x", "y"],
    "Omega Ruby / Alpha Sapphire": ["omega-ruby", "alpha-sapphire"],
    "Sun / Moon":                  ["sun", "moon"],
    "Ultra Sun / Ultra Moon":      ["ultra-sun", "ultra-moon"],
}

POKEMON_CACHE_SCHEMA = 3   # bump when the pokemon.json layout changes

# Legendaries & mythicals confirmed obtainable in SV without transferring from another game:
# Legendaries confirmed catchable in SV via BB Academy (Snacksworth) + Tera Raid events:
SV_CONFIRMED_EXTRA_IDS = frozenset({
    # ── Mythicals available in Scarlet/Violet ──────────────────────────────
    151,       # Mew             — Mystery Gift event code
    385,       # Jirachi         — BB Academy / event
    386,       # Deoxys          — BB Academy / event (all forms share this ID)
    489,       # Phione          — BB Academy
    490,       # Manaphy         — BB Academy
    491,       # Darkrai         — BB Academy
    492,       # Shaymin         — BB Academy (Land form; Sky form ID > 1025, not in pool)
    493,       # Arceus          — BB Academy (forms share this ID)
    647,       # Keldeo          — BB Academy (all forms share this ID)
    648,       # Meloetta        — BB Academy (all forms share this ID)
    719,       # Diancie         — BB Academy
    720,       # Hoopa           — BB Academy (Confined/Unbound share this ID)
    721,       # Volcanion       — BB Academy
    801,       # Magearna        — BB Academy (Original Color form ID > 1025)
    893,       # Zarude          — BB Academy (Dada form ID > 1025)
    # 1025 Pecharunt — already covered by Gen IX range (906–1025)

    # ── Non-mythical Legendaries — BB Academy Snacksworth + Tera Raid ─────
    150,       # Mewtwo          — Tera Raid distribution event
    144, 145, 146,               # Kanto birds
    243, 244, 245, 249, 250,     # Johto beasts + Lugia/Ho-Oh
    377, 378, 379, 380, 381,     # Hoenn Regis + Lati@s
    382, 383, 384,               # Kyogre, Groudon, Rayquaza
    480, 481, 482, 483, 484,     # Sinnoh lake trio + Dialga/Palkia
    485, 486, 487, 488,          # Heatran, Regigigas, Giratina, Cresselia
    638, 639, 640, 641, 642, 643, 644, 645, 646,  # Unova legendaries
    # NOT in SV (per serebii.net/scarletviolet/unobtainable.shtml):
    # Kalos legendaries (716-718), Type:Null/Silvally (772-773), Tapus (785-788)
    789, 790, 791, 792, 800,            # Cosmog line + Necrozma
    888, 889, 890, 891, 892,            # Zacian, Zamazenta, Eternatus, Kubfu, Urshifu
    894, 895, 896, 897, 898,            # Regieleki, Regidrago, Glastrier, Spectrier, Calyrex
    905,       # Enamorus — Indigo Disk Terarium (after obtaining the genie trio)
})

# Crown Tundra makes all Dynamax Adventure legendaries available in SwSh
# (Mewtwo 150 excluded: its Dynamax Adventure event was battle-only, 0% catch
# rate — it can only enter SwSh via HOME, i.e. with transfers enabled)
SWSH_CONFIRMED_EXTRA_IDS = frozenset({
    144, 145, 146,                         # Kanto birds
    243, 244, 245, 249, 250,               # Johto
    377, 378, 379, 380, 381, 382, 383, 384,  # Hoenn
    480, 481, 482, 483, 484, 485, 486, 487, 488,  # Sinnoh
    638, 639, 640, 641, 642, 643, 644, 645, 646,  # Unova
    716, 717, 718,                         # Kalos
    772, 773, 785, 786, 787, 788, 789, 790, 791, 792, 800,  # Alola
})

# Scarlet/Violet 7★ Tera Raid event Pokémon (past-gen starters etc.).
SV_RAID_EVENT_IDS = frozenset({
    3, 6, 9,        # Kanto starters
    154, 157,       # Meganium, Typhlosion
    395,            # Empoleon
    500, 503,       # Emboar, Samurott
    652, 655, 658,  # Chesnaught, Delphox, Greninja
    724, 730,       # Decidueye, Primarina
    812, 815, 818,  # Rillaboom, Cinderace, Inteleon
})

# Extra IDs added on top of the regional dex + encounter data: in-game gifts
# and event/distribution Pokémon obtainable without transferring from another
# game. Applied at roll time, so this list can be extended without re-fetching.
GAME_POOL_SUPPLEMENTS: dict = {
    # Mew (Faraway Is.), Johto starters (Prof. Birch), Lugia/Ho-Oh (Navel Rock),
    # Jirachi (bonus disc), Deoxys (Birth Is.)
    "Ruby / Sapphire / Emerald": {151, 152, 155, 158, 249, 250, 385, 386},
    # Lugia/Ho-Oh (Navel Rock), Deoxys (Birth Is.)
    "FireRed / LeafGreen": {249, 250, 386},
    # Manaphy (Ranger) + Phione, Darkrai, Shaymin, Arceus events
    "Diamond / Pearl / Platinum": {489, 490, 491, 492, 493},
    # Kanto starters (Oak), Hoenn starters (Steven), Kanto birds + Mewtwo,
    # Lati@s + weather trio, Mew/Celebi/Jirachi events
    "HeartGold / SoulSilver": {1, 4, 7, 144, 145, 146, 150, 151, 251,
                               252, 255, 258, 380, 381, 382, 383, 384, 385},
    # Victini (Liberty Pass), Keldeo/Meloetta/Genesect events
    "Black / White": {494, 647, 648, 649},
    "Black 2 / White 2": {647, 648, 649},
    # Kanto birds + Mewtwo (in-game), Diancie/Hoopa/Volcanion events
    "X / Y": {144, 145, 146, 150, 719, 720, 721},
    # Deoxys (Delta Episode), soaring/Mirage Spot legendaries,
    # Diancie/Hoopa/Volcanion events
    "Omega Ruby / Alpha Sapphire": {243, 244, 245, 249, 250,
                                    377, 378, 379, 386,
                                    480, 481, 482, 483, 484, 485, 486, 487, 488,
                                    638, 639, 640, 641, 642, 643, 644, 645, 646,
                                    719, 720, 721},
    # Magearna (QR), Marshadow event
    "Sun / Moon": {801, 802},
    # Ultra Wormhole legendaries (all non-mythical legendaries Gen I–VI),
    # Magearna/Marshadow/Zeraora events
    "Ultra Sun / Ultra Moon": {144, 145, 146, 150, 243, 244, 245, 249, 250,
                               377, 378, 379, 380, 381, 382, 383, 384,
                               480, 481, 482, 483, 484, 485, 486, 487, 488,
                               638, 639, 640, 641, 642, 643, 644, 645, 646,
                               716, 717, 718, 801, 802, 807},
    "Sword / Shield": set(SWSH_CONFIRMED_EXTRA_IDS),
    # Grand Underground + Ramanas Park + gifts/events cover the whole National
    # Dex up to Arceus, except Celebi and Deoxys which are unobtainable.
    "Brilliant Diamond / Shining Pearl": set(range(1, 494)) - {251, 386},
    # All Gen IX are SV-native; plus confirmed legendary/mythical + raid events
    "Scarlet / Violet": set(range(906, 1026)) | set(SV_CONFIRMED_EXTRA_IDS)
                        | set(SV_RAID_EVENT_IDS),
}

# Evolution-family closure is capped at the game's generation. SwSh needs a
# lower cap so Legends: Arceus evolutions (Wyrdeer…Enamorus, 899-905) of
# catchable Galar families don't leak in.
POOL_CLOSURE_MAX_OVERRIDE = {"Sword / Shield": 898}


def _parse_id_ranges(spec: str) -> frozenset:
    """Parse a compact "1-12,25,30-45" ID range string into a frozenset."""
    ids = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            ids |= set(range(int(a), int(b) + 1))
        else:
            ids.add(int(part))
    return frozenset(ids)


# Species that can exist in Sword/Shield via Pokémon HOME (the "dex cut" —
# 664 species with in-game data, derived from PokéAPI learnset data).
SWSH_HOME_IDS = _parse_id_ranges(
    "1-12,25-45,50-55,58-68,72-73,77-83,90-95,98-99,102-151,163-164,"
    "169-178,182-186,194-197,199,202,206,208,211-215,220-227,230,233,"
    "236-260,263-264,270-275,278-282,290-295,298,302-306,309-310,315,"
    "318-321,324,328-330,333-334,337-350,355-356,359-365,369,371-385,"
    "403-407,415-416,420-423,425-428,434-440,442-454,458-468,470-471,"
    "473-475,477-488,494,506-510,517-521,524-539,543-579,582-584,"
    "587-593,595-601,605-647,649,659-663,674-675,677-719,721-730,"
    "736-738,742-773,776-778,780-898")

# Species that can exist in Scarlet/Violet via Pokémon HOME
# (733 species after The Indigo Disk, derived from PokéAPI learnset data).
SV_HOME_IDS = _parse_id_ranges(
    "1-9,23-28,35-40,43-45,48-62,69-76,79-82,84-94,96-97,100-103,"
    "106-107,109-113,116-117,123,125-126,128-137,143-164,167-168,"
    "170-174,179-200,203-207,209-212,214-221,225,227-237,239-240,"
    "242-250,252-262,270-275,278-289,296-299,302,307-308,311-314,"
    "316-317,322-326,328-336,339-342,349-350,353-358,361-362,370-398,"
    "401-405,408-411,415-419,422-426,429-430,433-438,440,442-450,"
    "453-454,456-457,459-462,464,466-467,469-493,495-503,522-523,"
    "529-530,532-534,540-542,546-553,559-560,570-581,585-586,590-591,"
    "594-596,602-604,607-615,619-620,622-625,627-630,633-648,650-658,"
    "661-673,677-678,686-687,690-693,700-709,712-715,719-745,747-754,"
    "757-758,761-766,769-770,774-775,778-779,782-784,789-792,800-801,"
    "810-823,833-834,837-849,854-861,863,868-879,884-1025")

# Everything that can be brought INTO each game via transfers (Pal Park,
# Poké Transfer, Bank/Transporter, HOME) or Mystery Gift — used when the
# "Include transfers" option is on. Gen 3 has no down-transfer, but trading
# between RSE/FRLG/Colosseum/XD plus events covers the whole generation.
GAME_TRANSFER_POOLS: dict = {
    "Ruby / Sapphire / Emerald":         frozenset(range(1, 387)),
    "FireRed / LeafGreen":               frozenset(range(1, 387)),
    "Diamond / Pearl / Platinum":        frozenset(range(1, 494)),
    "HeartGold / SoulSilver":            frozenset(range(1, 494)),
    "Black / White":                     frozenset(range(1, 650)),
    "Black 2 / White 2":                 frozenset(range(1, 650)),
    "X / Y":                             frozenset(range(1, 722)),
    "Omega Ruby / Alpha Sapphire":       frozenset(range(1, 722)),
    "Sun / Moon":                        frozenset(range(1, 803)),
    "Ultra Sun / Ultra Moon":            frozenset(range(1, 808)),
    "Sword / Shield":                    SWSH_HOME_IDS,
    "Brilliant Diamond / Shining Pearl": frozenset(range(1, 494)),
    "Scarlet / Violet":                  SV_HOME_IDS,
    # Pokémon Champions: the regulation roster is fixed regardless of transfers
}

# Pokémon form variants we explicitly want in the pool (IDs > 1025 in PokéAPI).
# Arceus forms are intentionally excluded (too many plate variants).
EXTRA_FORM_SLUGS = frozenset({
    # Deoxys forms
    "deoxys-attack", "deoxys-defense", "deoxys-speed",
    # Galarian birds (SwSh Crown Tundra, transferable to SV via Home)
    "articuno-galar", "zapdos-galar", "moltres-galar",
    # Forces of Nature — Therian forms (Reveal Glass, introduced in B2W2)
    "tornadus-therian", "thundurus-therian", "landorus-therian",
    "enamorus-therian",
    # Mythical alternate forms
    "shaymin-sky",
    "keldeo-resolute",
    "meloetta-pirouette",
    "hoopa-unbound",
    "magearna-original",
    "zarude-dada",
})

FORM_TO_BASE_ID: dict = {
    "deoxys-attack":      386,
    "deoxys-defense":     386,
    "deoxys-speed":       386,
    "articuno-galar":     144,
    "zapdos-galar":       145,
    "moltres-galar":      146,
    "tornadus-therian":   641,
    "thundurus-therian":  642,
    "landorus-therian":   645,
    "enamorus-therian":   905,
    "shaymin-sky":        492,
    "keldeo-resolute":    647,
    "meloetta-pirouette": 648,
    "hoopa-unbound":      720,
    "magearna-original":  801,
    "zarude-dada":        893,
}

# Form variants only obtainable in specific games (all others allow any game
# whose pool contains the base species)
_THERIAN_GAMES = {
    # Therian forms don't exist in original Black/White (introduced in B2W2)
    "Black 2 / White 2", "X / Y", "Omega Ruby / Alpha Sapphire",
    "Sun / Moon", "Ultra Sun / Ultra Moon", "Sword / Shield",
    "Scarlet / Violet",
}
FORM_GAME_RESTRICT: dict = {
    "articuno-galar":    {"Sword / Shield", "Scarlet / Violet"},
    "zapdos-galar":      {"Sword / Shield", "Scarlet / Violet"},
    "moltres-galar":     {"Sword / Shield", "Scarlet / Violet"},
    "tornadus-therian":  _THERIAN_GAMES,
    "thundurus-therian": _THERIAN_GAMES,
    "landorus-therian":  _THERIAN_GAMES,
    "enamorus-therian":  {"Scarlet / Violet"},
    # Original Color Magearna was a HOME gift (Gen VIII era) — can't go back
    "magearna-original": {"Sword / Shield", "Scarlet / Violet"},
}

# Pokémon Champions roster (Regulation update, July 2026) — offline fallback
# only; the live roster is fetched from PokéAPI's "champions" pokédex.
CHAMPIONS_ROSTER_NAMES = frozenset({
    "abomasnow", "absol", "aegislash-shield", "aerodactyl", "aggron",
    "alakazam", "alcremie", "altaria", "ampharos", "annihilape",
    "appletun", "araquanid", "arbok", "arcanine", "archaludon", "ariados",
    "armarouge", "aromatisse", "audino", "aurorus", "avalugg", "azumarill",
    "banette", "barbaracle", "basculegion-male", "bastiodon", "beartic",
    "beedrill", "bellibolt", "blastoise", "blaziken", "camerupt",
    "castform", "ceruledge", "chandelure", "charizard", "chesnaught",
    "chimecho", "clawitzer", "clefable", "cofagrigus", "conkeldurr",
    "corviknight", "crabominable", "decidueye", "dedenne", "delphox",
    "diggersby", "ditto", "dragalge", "dragapult", "dragonite", "drampa",
    "eelektross", "emboar", "emolga", "empoleon", "espathra", "espeon",
    "excadrill", "falinks", "farigiraf", "feraligatr", "flapple",
    "flareon", "floette", "florges", "forretress", "froslass", "furfrou",
    "gallade", "garbodor", "garchomp", "gardevoir", "garganacl", "gengar",
    "gholdengo", "glaceon", "glalie", "glimmora", "gliscor", "golurk",
    "goodra", "gourgeist-average", "greninja", "grimmsnarl", "gyarados",
    "hatterene", "hawlucha", "heliolisk", "heracross", "hippowdon",
    "houndoom", "houndstone", "hydrapple", "hydreigon", "incineroar",
    "infernape", "jolteon", "kangaskhan", "kingambit", "kleavor", "klefki",
    "kommo-o", "krookodile", "leafeon", "liepard", "lopunny", "lucario",
    "luxray", "lycanroc-midday", "machamp", "malamar", "mamoswine",
    "manectric", "maushold-family-of-four", "mawile", "medicham",
    "meganium", "meowscarada", "meowstic-male", "metagross", "milotic",
    "mimikyu-disguised", "morpeko-full-belly", "mr-rime", "mudsdale",
    "musharna", "ninetales", "noivern", "oranguru", "orthworm", "overqwil",
    "palafin-zero", "pangoro", "passimian", "pelipper", "pidgeot",
    "pikachu", "pinsir", "politoed", "polteageist", "primarina",
    "pyroar-male", "quaquaval", "qwilfish", "raichu", "rampardos",
    "reuniclus", "rhyperior", "roserade", "rotom", "runerigus", "sableye",
    "salazzle", "samurott", "sandaconda", "sceptile", "scizor",
    "scolipede", "scovillain", "scrafty", "serperior", "sharpedo",
    "simipour", "simisage", "simisear", "sinistcha", "skarmory",
    "skeledirge", "slowbro", "slowking", "slurpuff", "sneasler", "snorlax",
    "spiritomb", "staraptor", "starmie", "steelix", "stunfisk", "swampert",
    "sylveon", "talonflame", "tauros", "tinkaton", "torkoal", "torterra",
    "toucannon", "toxapex", "toxicroak", "trevenant", "tsareena",
    "typhlosion", "tyranitar", "tyrantrum", "umbreon", "vanilluxe",
    "vaporeon", "venusaur", "victreebel", "vileplume", "vivillon",
    "volcarona", "watchog", "weavile", "whimsicott", "wyrdeer", "zoroark",
})

# ── Types ──────────────────────────────────────────────────────────────────────
TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice",
    "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug",
    "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy",
]

TERA_TYPES = TYPES + ["Stellar"]

TYPE_COLORS = {
    "Normal":   "#A8A878", "Fire":     "#F08030", "Water":    "#6890F0",
    "Electric": "#F8D030", "Grass":    "#78C850", "Ice":      "#98D8D8",
    "Fighting": "#C03028", "Poison":   "#A040A0", "Ground":   "#E0C068",
    "Flying":   "#A890F0", "Psychic":  "#F85888", "Bug":      "#A8B820",
    "Rock":     "#B8A038", "Ghost":    "#705898", "Dragon":   "#7038F8",
    "Dark":     "#705848", "Steel":    "#B8B8D0", "Fairy":    "#EE99AC",
    "Stellar":  "#D4A040",
}

# ── Natures ────────────────────────────────────────────────────────────────────
# (name, boosted_stat, reduced_stat) — neutral natures have None for both
NATURES = [
    ("Hardy",   None,    None),    ("Lonely",  "Atk",  "Def"),
    ("Brave",   "Atk",  "Spe"),   ("Adamant", "Atk",  "SpA"),
    ("Naughty", "Atk",  "SpD"),   ("Bold",    "Def",  "Atk"),
    ("Docile",  None,   None),    ("Relaxed", "Def",  "Spe"),
    ("Impish",  "Def",  "SpA"),   ("Lax",     "Def",  "SpD"),
    ("Timid",   "Spe",  "Atk"),   ("Hasty",   "Spe",  "Def"),
    ("Serious", None,   None),    ("Jolly",   "Spe",  "SpA"),
    ("Naive",   "Spe",  "SpD"),   ("Modest",  "SpA",  "Atk"),
    ("Mild",    "SpA",  "Def"),   ("Quiet",   "SpA",  "Spe"),
    ("Bashful", None,   None),    ("Rash",    "SpA",  "SpD"),
    ("Calm",    "SpD",  "Atk"),   ("Gentle",  "SpD",  "Def"),
    ("Sassy",   "SpD",  "Spe"),   ("Careful", "SpD",  "SpA"),
    ("Quirky",  None,   None),
]

STAT_NAMES = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
STAT_DISPLAY_NAMES = {
    "HP":  "HP",
    "Atk": "Attack",
    "Def": "Defense",
    "SpA": "Special Attack",
    "SpD": "Special Defense",
    "Spe": "Speed",
    "BST": "Base Stat Total",
}

# ══════════════════════════════════════════════════════════════════════════════
#  Themes
# ══════════════════════════════════════════════════════════════════════════════

def _theme(bg_root, bg_panel, bg_field, bg_result, bg_banned,
           fg_main, fg_sub, acc1, acc2, acc3, fg_banned,
           roll_bg, roll_hover, profile_bg, profile_rim):
    return dict(
        bg_root=bg_root, bg_panel=bg_panel, bg_field=bg_field,
        bg_result=bg_result, bg_banned=bg_banned,
        fg_main=fg_main, fg_sub=fg_sub,
        fg_accent1=acc1, fg_accent2=acc2, fg_accent3=acc3, fg_banned=fg_banned,
        roll_bg=roll_bg, roll_hover=roll_hover,
        profile_bg=profile_bg, profile_rim=profile_rim,
    )

THEMES = {
    "Pokédex (Default)": _theme(
        "#1a1a2e", "#0f3460", "#16213e", "#071a2e", "#3a0a0a",
        "#f0f0f0", "#a0a8b8", "#f5a623", "#4fc3f7", "#f5a623", "#ff6b6b",
        "#e94560", "#c73048", "#0a2040", "#f5a623"),
    "🔥 Charizard": _theme(
        "#1a0800", "#2a1200", "#2a1200", "#0e0600", "#3a0000",
        "#fff0d0", "#c8956a", "#ff9500", "#ffcc44", "#ff9500", "#ff5555",
        "#cc3300", "#aa2200", "#1a0800", "#ff9500"),
    "🌿 Bulbasaur": _theme(
        "#0a1a0a", "#193519", "#112211", "#060e06", "#2a0808",
        "#e8f5e0", "#80b870", "#7ecf3f", "#b0e870", "#7ecf3f", "#ff7070",
        "#3a8c10", "#2d7008", "#081208", "#7ecf3f"),
    "💧 Blastoise": _theme(
        "#031520", "#0b3550", "#072030", "#020c18", "#2a0808",
        "#d8f4ff", "#6aadcc", "#30c0e0", "#80dff5", "#30c0e0", "#ff7070",
        "#0878b8", "#0660a0", "#021020", "#30c0e0"),
    "👻 Gengar": _theme(
        "#100618", "#280e40", "#1c0a2e", "#080010", "#2e0030",
        "#f0e0ff", "#9070b8", "#c060e8", "#e0a8ff", "#c060e8", "#ff6060",
        "#7818b8", "#6010a0", "#0c0418", "#c060e8"),
    "⚡ Pikachu": _theme(
        "#181400", "#3a3000", "#262000", "#0e0c00", "#2a0808",
        "#fff8cc", "#b8a840", "#f8d800", "#ffe860", "#f8d800", "#ff6060",
        "#c89800", "#a87800", "#121000", "#f8d800"),
    "❄️ Glaceon": _theme(
        "#060e18", "#102038", "#0a1828", "#04080e", "#2a0000",
        "#d8f0ff", "#7098b8", "#80d8ff", "#b8ecff", "#80d8ff", "#ff8888",
        "#2890c0", "#1878a8", "#040a14", "#80d8ff"),
    "🌙 Umbreon": _theme(
        "#080808", "#141414", "#0e0e0e", "#040404", "#280000",
        "#e8e8e8", "#707070", "#f8c800", "#3898d8", "#f8c800", "#ff6060",
        "#2060a0", "#184880", "#060606", "#f8c800"),
    "🌸 Sylveon": _theme(
        "#1e0818", "#3c1430", "#2a0e22", "#100510", "#2a0808",
        "#ffe8f8", "#c888b8", "#ff80c0", "#80d0ff", "#ff80c0", "#ff6060",
        "#c83080", "#a82060", "#180510", "#ff80c0"),
    "🖤 Team Rocket": _theme(
        "#0a0a0a", "#1a1a1a", "#111111", "#050505", "#200000",
        "#ffffff", "#888888", "#cc0000", "#ff4444", "#cc0000", "#ff6666",
        "#880000", "#660000", "#080808", "#cc0000"),
}

THEME_NAMES = list(THEMES.keys())

TAB_ICONS = {
    "abilities": os.path.join(ICONS_DIR, "tab_abilities.png"),
    "typing":    os.path.join(ICONS_DIR, "tab_typing.png"),
    "stats":     os.path.join(ICONS_DIR, "tab_stats.png"),
    "pokemon":   os.path.join(ICONS_DIR, "tab_pokemon.png"),
    "settings":  os.path.join(ICONS_DIR, "tab_settings.png"),
}

# ══════════════════════════════════════════════════════════════════════════════
#  PokeAPI helpers
# ══════════════════════════════════════════════════════════════════════════════

def _api_get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "ThenWeRoll/2.0"})
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def fetch_all_abilities(progress_cb=None) -> list:
    index   = _api_get(f"{POKEAPI_BASE}/ability?limit=10000")
    entries = index["results"]
    total   = len(entries)
    abilities = []
    for i, entry in enumerate(entries, 1):
        try:
            data       = _api_get(entry["url"])
            generation = POKEAPI_GEN_MAP.get(data.get("generation", {}).get("name", ""))
            if generation is None:
                continue
            effect_text = "No effect description available."
            for ent in data.get("effect_entries", []):
                if ent.get("language", {}).get("name") == "en":
                    effect_text = ent.get("short_effect") or ent.get("effect", effect_text)
                    break
            display_name = entry["name"].replace("-", " ").title()
            for name_entry in data.get("names", []):
                if name_entry.get("language", {}).get("name") == "en":
                    display_name = name_entry["name"]
                    break
            abilities.append({
                "name": entry["name"], "display_name": display_name,
                "effect": effect_text, "generation": generation,
                "is_main_series": data.get("is_main_series", False),
            })
        except Exception:
            pass
        if progress_cb:
            progress_cb(i, total, entry["name"])
    abilities.sort(key=lambda a: a["display_name"].lower())
    return abilities


def save_abilities_json(abilities: list):
    with open(ABILITIES_FILE, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "source": "PokeAPI",
                   "count": len(abilities), "abilities": abilities},
                  f, ensure_ascii=False, indent=2)


def load_abilities_json() -> list:
    if not os.path.exists(ABILITIES_FILE):
        return []
    with open(ABILITIES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("abilities", [])


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _lerp_colour(c1: str, c2: str, t: float) -> str:
    r1,g1,b1 = _hex_to_rgb(c1); r2,g2,b2 = _hex_to_rgb(c2)
    t = max(0.0, min(1.0, t))
    return "#{:02x}{:02x}{:02x}".format(
        int(r1+(r2-r1)*t), int(g1+(g2-g1)*t), int(b1+(b2-b1)*t))

def _darken(hex_col: str, amount: int = 40) -> str:
    r,g,b = _hex_to_rgb(hex_col)
    return "#{:02x}{:02x}{:02x}".format(
        max(0,r-amount), max(0,g-amount), max(0,b-amount))

_FONT_FILE_CACHE: dict = {}

def _resolve_font_file(family: str, bold: bool = False):
    """Find the font file for a family name via the Windows font registry.
    Returns a path or None (None → fall back to plain canvas text)."""
    key = (family.strip().lower(), bold)
    if key in _FONT_FILE_CACHE:
        return _FONT_FILE_CACHE[key]
    path = None
    try:
        import winreg
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        entries = {}
        for root, sub in (
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER,
                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")):
            try:
                with winreg.OpenKey(root, sub) as k:
                    for i in range(winreg.QueryInfoKey(k)[1]):
                        name, val, _t = winreg.EnumValue(k, i)
                        clean = (name.replace(" (TrueType)", "")
                                     .replace(" (OpenType)", "").strip().lower())
                        full = val if os.path.isabs(val) else os.path.join(fonts_dir, val)
                        entries.setdefault(clean, full)
            except OSError:
                pass
        fam = key[0]
        candidates = [f"{fam} bold", fam] if bold else [fam]
        for cand in candidates:
            fp = entries.get(cand)
            if fp and os.path.exists(fp):
                path = fp
                break
        if path is None:
            for cand in candidates:
                for nm, fp in entries.items():
                    if nm.startswith(cand) and os.path.exists(fp):
                        path = fp
                        break
                if path:
                    break
    except Exception:
        pass
    _FONT_FILE_CACHE[key] = path
    return path


def _lighten(hex_col: str, amount: int = 30) -> str:
    r,g,b = _hex_to_rgb(hex_col)
    return "#{:02x}{:02x}{:02x}".format(
        min(255,r+amount), min(255,g+amount), min(255,b+amount))


# ══════════════════════════════════════════════════════════════════════════════
#  Main application
# ══════════════════════════════════════════════════════════════════════════════

class AbilityRandomizerApp:

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1320x820")
        self.root.minsize(1000, 600)
        self._set_app_icon()

        # Abilities state
        self.abilities:          list = []
        self.filtered_abilities: list = []
        self.banned_abilities:   set  = set()
        self._rolled:            list = []

        # Typing state
        self._rolled_types:      list = []   # list of dicts with type info
        self.banned_types:       set  = set()

        # Stats state
        self._rolled_stats:      dict = {}
        self._rolled_nature:     tuple = None

        # Pokemon state
        self._rolled_pokemon:    list = []
        self._rolled_shiny:      list = []
        self._pokemon_all:       list = []
        self._pokemon_types:     dict = {}   # pid -> [type1, type2]
        self._pokemon_species:   dict = {}   # pid -> {baby, legendary, mythical, evo_stage}
        self._pokemon_game_pools: dict = {}  # game_name -> [id, ...] (regional dex)
        self._pokemon_encounter_pools: dict = {}  # game_name -> [id, ...] (wild/static)
        self._pokemon_photos:    list = []   # keep PhotoImage refs alive
        self._pokemon_loading:   bool = False

        # Profile
        self._user_name               = ""
        self._avatar_photo            = None

        # Theme
        self._theme_name = THEME_NAMES[0]
        self._t          = THEMES[self._theme_name]
        self._tw:        list = []

        # Tab
        self._active_tab = "abilities"
        self._tab_frames = {}
        self._tab_btns   = {}
        self._tab_icons  = {}

        # Vars
        self.status_var           = tk.StringVar(value="Loading abilities…")
        self.draw_count_var       = tk.IntVar(value=3)
        self.search_var           = tk.StringVar()
        self.custom_ban_var       = tk.StringVar()
        self.include_banned_var   = tk.BooleanVar(value=False)
        self.main_series_only_var = tk.BooleanVar(value=True)
        self.generation_vars      = {g: tk.BooleanVar(value=True) for g in GENERATIONS}
        self.game_var             = tk.StringVar(value="Custom")
        self.theme_var            = tk.StringVar(value=self._theme_name)

        # Typing vars
        self.type_mode_var        = tk.StringVar(value="Mixed")
        self.type_split_var       = tk.IntVar(value=50)   # % chance of Single (0=all Dual, 100=all Single)
        self.tera_enabled_var     = tk.BooleanVar(value=False)
        self.tera_ban_sync_var    = tk.BooleanVar(value=False)
        self.tera_no_match_var    = tk.BooleanVar(value=True)
        self.type_ban_vars        = {t: tk.BooleanVar(value=False) for t in TYPES}

        # Stats vars
        self.stat_mode_var        = tk.StringVar(value="Free")
        self.bst_var              = tk.IntVar(value=500)
        self.bst_min_var          = tk.IntVar(value=200)
        self.bst_max_var          = tk.IntVar(value=600)
        self.use_stat_minmax_var  = tk.BooleanVar(value=False)
        self.stat_min_vars        = {s: tk.IntVar(value=1)   for s in STAT_NAMES}
        self.stat_max_vars        = {s: tk.IntVar(value=255) for s in STAT_NAMES}

        # Settings vars
        self.reveal_font_var         = tk.StringVar(value="Segoe UI")
        self.reveal_fade_var         = tk.StringVar(value="Medium")
        self.reveal_font_size_var    = tk.IntVar(value=44)       # base name size (pt)
        self.reveal_title_col_var    = tk.StringVar(value="")    # "" = use theme fg_accent1
        self.reveal_sub_col_var      = tk.StringVar(value="")    # "" = use theme fg_sub
        self.reveal_preview_type_var = tk.StringVar(value="abilities")
        self.reveal_bg_global_var    = tk.StringVar(value="")
        self.reveal_bg_stretch_var   = tk.StringVar(value="Fit")
        self.reveal_bg_per_var       = tk.BooleanVar(value=False)
        # Text outline
        self.reveal_outline_var      = tk.BooleanVar(value=True)
        self.reveal_outline_size_var = tk.IntVar(value=2)
        self.reveal_outline_col_var  = tk.StringVar(value="#000000")
        # Sub text outline
        self.reveal_sub_outline_var      = tk.BooleanVar(value=True)
        self.reveal_sub_outline_size_var = tk.IntVar(value=1)
        self.reveal_sub_outline_col_var  = tk.StringVar(value="#000000")
        # Text glow
        self.reveal_glow_var         = tk.BooleanVar(value=False)
        self.reveal_glow_size_var    = tk.IntVar(value=4)
        self.reveal_glow_col_var     = tk.StringVar(value="")
        self.reveal_bg_abilities_var = tk.StringVar(value="")
        self.reveal_bg_typing_var    = tk.StringVar(value="")
        self.reveal_bg_stats_var     = tk.StringVar(value="")
        self.reveal_bg_nature_var    = tk.StringVar(value="")
        self.reveal_bg_pokemon_var   = tk.StringVar(value="")
        self.reveal_typing_override_var = tk.BooleanVar(value=False)
        self.win_width_var           = tk.IntVar(value=1320)
        self.win_height_var          = tk.IntVar(value=820)
        self.win_maximised_var       = tk.BooleanVar(value=False)
        self.default_tab_var         = tk.StringVar(value="abilities")
        # Pokemon vars
        self.pokemon_game_var        = tk.StringVar(value="Custom")
        self.pokemon_count_var       = tk.IntVar(value=3)
        self.pokemon_transfers_var   = tk.BooleanVar(value=True)
        self.reveal_pokemon_sprite_var = tk.IntVar(value=220)  # large sprite px at 1320px wide
        # Shiny vars
        self.pokemon_shiny_var       = tk.BooleanVar(value=False)
        self.pokemon_shiny_mode_var  = tk.StringVar(value="odds")   # "odds" or "percent"
        self.pokemon_shiny_odds_var  = tk.IntVar(value=8192)
        self.pokemon_shiny_pct_var   = tk.StringVar(value="0.01")   # percent string
        # Type filter vars (one BooleanVar per type, all True = no filter)
        self.pokemon_type_filter_all_var = tk.BooleanVar(value=True)
        self._pokemon_type_vars: dict    = {}   # type_name -> BooleanVar
        # Category filter vars (key -> StringVar with "Any"/"Only"/"Exclude")
        self._pokemon_cat_vars: dict     = {k: tk.StringVar(value="Any")
                                            for k, _ in CATEGORY_FILTERS}
        # Cached background photos keyed by path
        self._reveal_bg_photos: dict = {}
        self._loading = True   # suppress _save_settings until _load_settings completes

        self._build_ui()
        self._apply_theme()
        self._load_abilities()
        self._load_settings()   # clears _loading at the end
        self._update_status()
        self._refresh_ability_views()
        # Apply window geometry from settings
        if self.win_maximised_var.get():
            self.root.state("zoomed")
        else:
            w = self.win_width_var.get()
            h = self.win_height_var.get()
            self.root.geometry(f"{w}x{h}")
        # Switch to default tab
        self._switch_tab(self.default_tab_var.get())
        self.root.after(100, self._maybe_first_launch)
        self.root.after(1500, self._check_for_update)

    # ══════════════════════════════════════════════════════════════════════════
    #  Theme engine
    # ══════════════════════════════════════════════════════════════════════════

    def _set_app_icon(self):
        """Draw a Poké Ball window icon (replaces the default Tk feather)."""
        if not _PIL_OK:
            return
        try:
            size = 64
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            pad = 4
            d.ellipse([pad, pad, size - pad, size - pad], fill="#e63946")
            d.pieslice([pad, pad, size - pad, size - pad], 0, 180, fill="#f1faee")
            band = 5
            d.rectangle([pad, size // 2 - band, size - pad, size // 2 + band],
                        fill="#1d3557")
            d.ellipse([size // 2 - 11, size // 2 - 11,
                       size // 2 + 11, size // 2 + 11], fill="#1d3557")
            d.ellipse([size // 2 - 7, size // 2 - 7,
                       size // 2 + 7, size // 2 + 7], fill="#f1faee")
            self._app_icon = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

    def _r(self, widget, role: str):
        self._tw.append((widget, role))
        if role.startswith("btn"):
            widget.configure(cursor="hand2")
            widget.bind("<Enter>", self._on_btn_hover)
            widget.bind("<Leave>", self._on_btn_unhover)
        return widget

    def _on_btn_hover(self, event):
        w = event.widget
        try:
            if str(w.cget("state")) == "disabled":
                return
            w._hover_restore = w.cget("bg")
            w.configure(bg=_lighten(w._hover_restore, 25))
        except tk.TclError:
            pass

    def _on_btn_unhover(self, event):
        w = event.widget
        try:
            restore = getattr(w, "_hover_restore", None)
            if restore:
                w.configure(bg=restore)
                w._hover_restore = None
        except tk.TclError:
            pass

    def _switch_theme(self, _event=None):
        name = self.theme_var.get()
        if name in THEMES:
            self._theme_name = name
            self._t = THEMES[name]
            self._apply_theme()
            self._save_settings()

    def _apply_theme(self):
        t = self._t
        self.root.configure(bg=t["bg_root"])

        def _btn(bg_key, fg_key, act_bg_key=None, act_fg_key="bg_root"):
            act_bg = t[act_bg_key or bg_key]
            return dict(bg=t[bg_key], fg=t[fg_key],
                        activebackground=act_bg, activeforeground=t[act_fg_key])

        for w, role in self._tw:
            try:
                if   role == "bg_root":          w.configure(bg=t["bg_root"])
                elif role == "bg_panel":         w.configure(bg=t["bg_panel"])
                elif role == "bg_field":         w.configure(bg=t["bg_field"])
                elif role == "lbl_title":        w.configure(bg=t["bg_root"],  fg=t["fg_accent1"])
                elif role == "lbl_status":       w.configure(bg=t["bg_root"],  fg=t["fg_accent2"])
                elif role == "lbl_theme":        w.configure(bg=t["bg_root"],  fg=t["fg_sub"])
                elif role == "lbl_main":         w.configure(bg=t["bg_panel"], fg=t["fg_main"])
                elif role == "lbl_sub":          w.configure(bg=t["bg_panel"], fg=t["fg_sub"])
                elif role == "lbl_detail_title": w.configure(bg=t["bg_panel"], fg=t["fg_accent2"])
                elif role == "lf_accent1":       w.configure(bg=t["bg_panel"], fg=t["fg_accent1"])
                elif role == "lf_accent2":       w.configure(bg=t["bg_panel"], fg=t["fg_accent2"])
                elif role == "lf_banned":        w.configure(bg=t["bg_panel"], fg=t["fg_banned"])
                elif role == "lf_result":        w.configure(bg=t["bg_panel"], fg=t["fg_accent1"])
                elif role == "field":
                    w.configure(bg=t["bg_field"], fg=t["fg_main"],
                                insertbackground=t["fg_main"],
                                disabledbackground=t["bg_field"],
                                disabledforeground=t["fg_sub"])
                elif role == "field_search":
                    w.configure(bg=t["bg_field"], fg=t["fg_main"],
                                insertbackground=t["fg_main"],
                                highlightbackground=t["fg_accent2"], highlightthickness=1)
                elif role == "field_ban":
                    w.configure(bg=t["bg_field"], fg=t["fg_main"],
                                insertbackground=t["fg_main"],
                                highlightbackground=t["fg_banned"], highlightthickness=1)
                elif role == "spinbox":
                    w.configure(bg=t["bg_field"], fg=t["fg_main"],
                                buttonbackground=t["bg_field"],
                                insertbackground=t["fg_main"],
                                disabledbackground=t["bg_root"],
                                disabledforeground=t["fg_sub"],
                                readonlybackground=t["bg_field"],
                                highlightbackground=t["fg_accent2"], highlightthickness=1)
                elif role == "listbox":
                    w.configure(bg=t["bg_field"], fg=t["fg_main"],
                                selectbackground=t["fg_accent2"],
                                selectforeground=t["bg_root"],
                                highlightthickness=1,
                                highlightbackground=t["bg_panel"],
                                highlightcolor=t["fg_accent2"])
                elif role == "listbox_banned":
                    w.configure(bg=t["bg_banned"], fg=t["fg_banned"],
                                selectbackground=t["fg_banned"],
                                selectforeground=t["bg_root"],
                                highlightthickness=1,
                                highlightbackground=t["bg_panel"],
                                highlightcolor=t["fg_banned"])
                elif role == "scrollbar":
                    w.configure(bg=t["bg_panel"], troughcolor=t["bg_field"])
                elif role == "btn_roll":
                    w.configure(**_btn("roll_bg", "fg_main", "roll_hover", "fg_main"))
                elif role == "btn_accent1":
                    w.configure(**_btn("bg_field", "fg_accent1", "fg_accent1"))
                elif role == "btn_accent2":
                    w.configure(**_btn("bg_field", "fg_accent2", "fg_accent2"))
                elif role == "btn_banned":
                    w.configure(**_btn("bg_field", "fg_banned", "fg_banned"))
                elif role == "btn_unban":
                    w.configure(bg=t["bg_field"], fg="#69db7c",
                                activebackground="#69db7c",
                                activeforeground=t["bg_root"])
                elif role == "btn_small":
                    w.configure(**_btn("bg_field", "fg_main", "fg_accent2"))
                elif role == "btn_dramatic":
                    w.configure(**_btn("profile_bg", "fg_accent1", "fg_accent1"))
                elif role == "check":
                    w.configure(bg=t["bg_panel"], fg=t["fg_main"],
                                selectcolor=t["bg_field"],
                                activebackground=t["bg_panel"],
                                activeforeground=t["fg_main"])
                elif role == "check_gen":
                    w.configure(bg=t["bg_panel"], selectcolor=t["bg_field"],
                                activebackground=t["bg_panel"])
                elif role == "result_text":
                    w.configure(bg=t["bg_result"], fg=t["fg_main"],
                                highlightthickness=0, borderwidth=0)
                    w.tag_configure("header",       foreground=t["fg_accent1"])
                    w.tag_configure("ability_name", foreground=t["fg_accent2"])
                    w.tag_configure("gen_tag",      foreground=t["fg_accent3"])
                    w.tag_configure("effect_text",  foreground=t["fg_main"])
                    w.tag_configure("divider",      foreground=t["bg_panel"])
                    w.tag_configure("meta",         foreground=t["fg_sub"])
                elif role == "detail_text":
                    w.configure(bg=t["bg_field"], fg=t["fg_main"],
                                highlightthickness=0, borderwidth=0)
                    w.tag_configure("key",          foreground=t["fg_accent3"])
                    w.tag_configure("val",          foreground=t["fg_main"])
                    w.tag_configure("banned_val",   foreground=t["fg_banned"])
                    w.tag_configure("effect_label", foreground=t["fg_accent2"])
                elif role == "profile_card":     w.configure(bg=t["profile_bg"])
                elif role == "lbl_welcome":      w.configure(bg=t["profile_bg"], fg=t["fg_accent1"])
                elif role == "lbl_welcome_sub":  w.configure(bg=t["profile_bg"], fg=t["fg_sub"])
                elif role == "tab_bar":          w.configure(bg=t["bg_root"])
                elif role == "tab_content":      w.configure(bg=t["bg_panel"])
            except tk.TclError:
                pass

        # Re-colour banned rows in ability listbox
        for idx, ability in enumerate(self.filtered_abilities):
            try:
                banned = ability["name"] in self.banned_abilities
                self.ability_listbox.itemconfig(
                    idx,
                    fg=t["fg_banned"] if banned else t["fg_main"],
                    bg=t["bg_banned"] if banned else t["bg_field"])
            except Exception:
                pass

        self._style_tab_buttons()

        try:
            self._draw_avatar()
        except AttributeError:
            pass

        try:
            self._draw_radar()
        except AttributeError:
            pass

        try:
            self._redraw_typing_canvas()
        except AttributeError:
            pass

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox",
                        fieldbackground=t["bg_field"], background=t["bg_field"],
                        foreground=t["fg_main"],
                        selectbackground=t["bg_field"], selectforeground=t["fg_main"],
                        arrowcolor=t["fg_main"],
                        bordercolor=t["bg_field"],
                        darkcolor=t["bg_field"], lightcolor=t["bg_field"],
                        insertcolor=t["fg_main"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", t["bg_field"]),
                                   ("disabled", t["bg_panel"])],
                  foreground=[("readonly", t["fg_main"])],
                  selectbackground=[("readonly", t["bg_field"])],
                  selectforeground=[("readonly", t["fg_main"])],
                  background=[("active", _lighten(t["bg_field"], 20))])
        # The combobox dropdown is a separate popup Listbox — style via options
        # (for not-yet-created popdowns) and directly (for existing ones)
        self.root.option_add("*TCombobox*Listbox.background", t["bg_field"])
        self.root.option_add("*TCombobox*Listbox.foreground", t["fg_main"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", t["fg_accent2"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", t["bg_root"])
        self._style_combobox_popdowns(self.root)
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar",
                            background=t["bg_field"], troughcolor=t["bg_root"],
                            arrowcolor=t["fg_sub"], bordercolor=t["bg_panel"],
                            darkcolor=t["bg_field"], lightcolor=t["bg_field"],
                            relief="flat")
            style.map(f"{orient}.TScrollbar",
                      background=[("active", _lighten(t["bg_field"], 25))])

        # Refresh preview canvas and swatches to reflect new theme colours
        try: self._update_colour_swatches()
        except Exception: pass
        try: self._refresh_reveal_preview()
        except Exception: pass

    def _style_combobox_popdowns(self, widget):
        """Recolour every combobox's popup list to match the theme.
        The popdown is a Tcl-side widget with no Python wrapper, so it must
        be configured through raw Tcl calls."""
        t = self._t
        for c in widget.winfo_children():
            if isinstance(c, ttk.Combobox):
                try:
                    pd = c.tk.call("ttk::combobox::PopdownWindow", c)
                    c.tk.call(f"{pd}.f.l", "configure",
                              "-background", t["bg_field"],
                              "-foreground", t["fg_main"],
                              "-selectbackground", t["fg_accent2"],
                              "-selectforeground", t["bg_root"],
                              "-borderwidth", 0)
                except Exception:
                    pass
            self._style_combobox_popdowns(c)

    # ══════════════════════════════════════════════════════════════════════════
    #  Tab system
    # ══════════════════════════════════════════════════════════════════════════

    def _load_tab_icon(self, key, colour):
        """Load a tab icon PNG and recolour it, or return None."""
        if not _PIL_OK:
            return None
        path = TAB_ICONS.get(key, "")
        if not os.path.exists(path):
            return None
        try:
            img  = Image.open(path).convert("RGBA")
            img  = img.resize((28, 28), Image.LANCZOS)
            r, g, b = _hex_to_rgb(colour)
            data = img.load()
            for y in range(img.height):
                for x in range(img.width):
                    pr, pg, pb, pa = data[x, y]
                    data[x, y] = (r, g, b, pa)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _style_tab_buttons(self):
        t = self._t
        for key, btn in self._tab_btns.items():
            active = key == self._active_tab
            bg     = t["bg_panel"] if active else t["bg_root"]
            relief = "flat"
            bd     = 0
            btn.configure(bg=bg, activebackground=t["bg_panel"],
                          relief=relief, bd=bd)
            col = t["fg_accent1"] if active else t["fg_sub"]
            photo = self._load_tab_icon(key, col)
            if photo:
                self._tab_icons[key] = photo
                btn.configure(image=photo, text="")
            else:
                btn.configure(image="", text=key[:3].title())

    def _switch_tab(self, key):
        self._active_tab = key
        for k, f in self._tab_frames.items():
            if k == key or k == key + "_right":
                f.grid()
            else:
                f.grid_remove()
        self._style_tab_buttons()

    def _build_tab_bar(self, parent):
        bar = self._r(tk.Frame(parent, width=52), "tab_bar")
        bar.grid(row=0, column=0, sticky="ns")
        bar.grid_propagate(False)

        for i, (key, label) in enumerate([
            ("abilities", "Abilities"),
            ("typing",    "Typing"),
            ("stats",     "Stats"),
            ("pokemon",   "Pokémon"),
            ("settings",  "Settings"),
        ]):
            btn = tk.Button(bar, text=label[:3],
                            relief="flat", bd=0, cursor="hand2",
                            font=("Segoe UI", 8),
                            width=52, height=52,
                            command=lambda k=key: self._switch_tab(k))
            btn.pack(fill="x", pady=(0, 2))
            self._tab_btns[key] = btn

        # Thin right border on the bar
        tk.Frame(bar, width=1, bg="#444").pack(side="right", fill="y")

    # ══════════════════════════════════════════════════════════════════════════
    #  Build UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.root.columnconfigure(0, weight=0)   # tab bar
        self.root.columnconfigure(1, weight=0, minsize=315)  # left content
        self.root.columnconfigure(2, weight=1)   # right content
        self.root.rowconfigure(1, weight=1)

        self._build_header()

        # Tab bar
        tab_bar_frame = self._r(tk.Frame(self.root), "tab_bar")
        tab_bar_frame.grid(row=1, column=0, sticky="ns", padx=(8, 0), pady=(0, 12))
        self._build_tab_bar(tab_bar_frame)

        # Content container — left panels swap per tab
        content = self._r(tk.Frame(self.root), "bg_root")
        content.grid(row=1, column=1, sticky="nsew", padx=(4, 4), pady=(0, 12))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        # Right panel container — also swaps per tab
        self.right_container = self._r(tk.Frame(self.root), "bg_root")
        self.right_container.grid(row=1, column=2, sticky="nsew", padx=(0, 12), pady=(0, 12))
        self.right_container.columnconfigure(0, weight=1)
        self.right_container.rowconfigure(0, weight=1)

        # Build all three tab left-panels
        self._build_abilities_tab(content)
        self._build_typing_tab(content)
        self._build_stats_tab(content)
        self._build_pokemon_tab(content)
        self._build_settings_tab(content)

        # Build all three tab right-panels
        self._build_abilities_right(self.right_container)
        self._build_typing_right(self.right_container)
        self._build_stats_right(self.right_container)
        self._build_pokemon_right(self.right_container)
        self._build_settings_right(self.right_container)

        # Show default tab
        self._switch_tab("abilities")

    def _build_header(self):
        hdr = self._r(tk.Frame(self.root, pady=10), "bg_root")
        hdr.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16)

        self._r(tk.Label(hdr, text="🎲 Then We Roll - Pokémon Randomizer",
                         font=("Segoe UI", 20, "bold")),
                "lbl_title").pack(side="left")

        # Theme picker lives top-right (where the ability stats used to be)
        theme_row = self._r(tk.Frame(hdr), "bg_root")
        theme_row.pack(side="right")
        self._r(tk.Label(theme_row, text="Theme:", font=("Segoe UI", 9)),
                "lbl_theme").pack(side="left", padx=(0, 5))
        cb = ttk.Combobox(theme_row, textvariable=self.theme_var,
                          values=THEME_NAMES, state="readonly",
                          width=17, font=("Segoe UI", 9))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._switch_theme)

        # Transient status messages (fetch progress, updates) sit beside it
        self._r(tk.Label(hdr, textvariable=self.status_var,
                         font=("Segoe UI", 9, "italic")),
                "lbl_status").pack(side="right", padx=(8, 16))

    # ── Abilities tab ──────────────────────────────────────────────────────────

    def _build_abilities_tab(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(3, weight=1)
        self._tab_frames["abilities"] = f

        self._build_game_selector(f)
        self._build_roll_settings(f)
        self._build_ban_panel(f)

    def _build_abilities_right(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=0)
        f.rowconfigure(1, weight=2)
        f.rowconfigure(2, weight=3)
        self._tab_frames["abilities_right"] = f

        self._build_profile_card(f)
        self._build_results_panel(f)
        self._build_ability_browser(f)

    def _build_game_selector(self, parent):
        pf = self._r(
            tk.LabelFrame(parent, text=" 🎮  Game Preset ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        pf.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        pf.columnconfigure(0, weight=1)

        self._r(tk.Label(pf, text="Select your game to auto-set generations:",
                         font=("Segoe UI", 9)), "lbl_sub").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(pf, textvariable=self.game_var,
                          values=list(GAME_PRESETS.keys()), state="readonly", width=30)
        cb.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        cb.bind("<<ComboboxSelected>>", self._on_game_selected)

        self.update_btn = self._r(
            tk.Button(pf, text="🔄 Update from PokéAPI", command=self._start_api_update,
                      relief="flat", font=("Segoe UI", 9), padx=8, pady=4, cursor="hand2"),
            "btn_accent2")
        self.update_btn.grid(row=2, column=0, sticky="ew")

    def _build_roll_settings(self, parent):
        pf = self._r(
            tk.LabelFrame(parent, text=" 🎲  Roll Settings ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=10),
            "lf_accent1")
        pf.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        pf.columnconfigure(1, weight=1)

        self._r(tk.Label(pf, text="Abilities to draw:", font=("Segoe UI", 10)),
                "lbl_main").grid(row=0, column=0, sticky="w")
        self._r(
            tk.Spinbox(pf, from_=1, to=99, textvariable=self.draw_count_var,
                       width=5, relief="flat", font=("Consolas", 12, "bold")),
            "spinbox").grid(row=0, column=1, sticky="w", padx=(10, 0))

        cf = self._r(tk.Frame(pf), "bg_panel")
        cf.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        for text, var in [("Allow cringe abilities in roll", self.include_banned_var),
                          ("Main-series abilities only",     self.main_series_only_var)]:
            self._r(
                tk.Checkbutton(cf, text=text, variable=var,
                               command=self._on_filter_changed, font=("Segoe UI", 9)),
                "check").pack(anchor="w", pady=1)

        gf = self._r(
            tk.LabelFrame(pf, text=" Generations ",
                          font=("Segoe UI", 9, "bold"), relief="flat", bd=0, padx=6, pady=6),
            "lf_accent2")
        gf.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for i, gen in enumerate(GENERATIONS):
            self._r(
                tk.Checkbutton(gf, text=gen, variable=self.generation_vars[gen],
                               command=self._on_filter_changed,
                               fg=GEN_COLORS[gen], font=("Segoe UI", 9, "bold")),
                "check_gen").grid(row=i // 4, column=i % 4, sticky="w", padx=4, pady=1)

        br = self._r(tk.Frame(gf), "bg_panel")
        br.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for text, cmd in [("All", self.select_all_generations),
                          ("None", self.clear_all_generations)]:
            self._r(
                tk.Button(br, text=text, command=cmd, relief="flat",
                          font=("Segoe UI", 8), padx=8, pady=2, cursor="hand2"),
                "btn_small").pack(side="left", padx=(0, 4))

        self.roll_btn = self._r(
            tk.Button(pf, text="⚡  ROLL ABILITIES", command=self.roll_abilities,
                      relief="flat", font=("Segoe UI", 13, "bold"), padx=0, pady=10,
                      cursor="hand2"),
            "btn_roll")
        self.roll_btn.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        self.dramatic_roll_btn = self._r(
            tk.Button(pf, text="🎭  ROLL DRAMATICALLY", command=self._roll_dramatically,
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=0, pady=7,
                      cursor="hand2"),
            "btn_dramatic")
        self.dramatic_roll_btn.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    def _build_ban_panel(self, parent):
        pf = self._r(
            tk.LabelFrame(parent, text=" 🚫  Cringe / Banned Abilities ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_banned")
        pf.grid(row=3, column=0, sticky="nsew")
        pf.columnconfigure(0, weight=1)
        pf.rowconfigure(2, weight=1)

        self._r(tk.Label(pf, text="Type an ability name and press Add, or\n"
                         "select one in the browser below.",
                         font=("Segoe UI", 8), justify="left"),
                "lbl_sub").grid(row=0, column=0, sticky="w")

        er = self._r(tk.Frame(pf), "bg_panel")
        er.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        er.columnconfigure(0, weight=1)

        self.custom_ban_entry = self._r(
            tk.Entry(er, textvariable=self.custom_ban_var, relief="flat", font=("Segoe UI", 10)),
            "field_ban")
        self.custom_ban_entry.grid(row=0, column=0, sticky="ew")
        self.custom_ban_entry.bind("<Return>", lambda _: self.add_ban_from_entry())

        for col, (text, cmd, role) in enumerate([
            ("Add",       self.add_ban_from_entry,  "btn_accent2"),
            ("Remove",    self.remove_selected_ban, "btn_accent1"),
            ("Clear All", self.clear_bans,          "btn_banned"),
        ], start=1):
            self._r(
                tk.Button(er, text=text, command=cmd, relief="flat",
                          font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                role).grid(row=0, column=col, padx=(4, 0))

        lf = self._r(tk.Frame(pf), "bg_panel")
        lf.grid(row=2, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)

        self.ban_listbox = self._r(
            tk.Listbox(lf, relief="flat", font=("Segoe UI", 9),
                       selectmode=tk.EXTENDED, activestyle="none", height=8),
            "listbox_banned")
        self.ban_listbox.grid(row=0, column=0, sticky="nsew")
        scr = self._r(ttk.Scrollbar(lf, orient="vertical", command=self.ban_listbox.yview),
                      "scrollbar")
        scr.grid(row=0, column=1, sticky="ns")
        self.ban_listbox.configure(yscrollcommand=scr.set)

    # ── Typing tab ─────────────────────────────────────────────────────────────

    def _build_typing_tab(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)
        self._tab_frames["typing"] = f

        # Mode selector
        mf = self._r(
            tk.LabelFrame(f, text=" 🎨  Type Mode ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        mf.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        mf.columnconfigure(0, weight=1)

        radio_row = self._r(tk.Frame(mf), "bg_panel")
        radio_row.grid(row=0, column=0, sticky="w")
        for mode in ["Single", "Dual", "Mixed", "%"]:
            self._r(
                tk.Radiobutton(radio_row, text=mode, variable=self.type_mode_var, value=mode,
                               command=self._on_type_mode_changed, font=("Segoe UI", 10)),
                "check").pack(side="left", padx=(0, 14))

        # % slider — shown only when % mode selected
        self._type_split_frame = self._r(tk.Frame(mf), "bg_panel")
        self._type_split_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._type_split_frame.columnconfigure(0, weight=1)

        split_lbl_row = self._r(tk.Frame(self._type_split_frame), "bg_panel")
        split_lbl_row.grid(row=0, column=0, sticky="ew")
        split_lbl_row.columnconfigure(1, weight=1)

        self._r(tk.Label(split_lbl_row, text="Single", font=("Segoe UI", 8, "bold")),
                "lbl_main").pack(side="left")
        self._r(tk.Label(split_lbl_row, text="Dual", font=("Segoe UI", 8, "bold")),
                "lbl_main").pack(side="right")

        self._type_slider = ttk.Scale(self._type_split_frame, from_=100, to=0,
                                      orient="horizontal", variable=self.type_split_var,
                                      command=lambda _: self._update_split_label())
        self._type_slider.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.split_label_var = tk.StringVar()
        self._r(tk.Label(self._type_split_frame, textvariable=self.split_label_var,
                         font=("Segoe UI", 8, "italic")),
                "lbl_sub").grid(row=2, column=0)

        self._on_type_mode_changed()   # set initial visibility

        # Tera Type options
        tf = self._r(
            tk.LabelFrame(f, text=" ✨  Tera Type ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent2")
        tf.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        for text, var in [
            ("Roll Tera Type",               self.tera_enabled_var),
            ("Apply type bans to Tera Type", self.tera_ban_sync_var),
            ("Avoid matching primary type",  self.tera_no_match_var),
        ]:
            self._r(
                tk.Checkbutton(tf, text=text, variable=var, font=("Segoe UI", 9)),
                "check").pack(anchor="w", pady=1)

        # Type ban checklist
        bf = self._r(
            tk.LabelFrame(f, text=" 🚫  Banned Types ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_banned")
        bf.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        bf.columnconfigure(0, weight=1)
        bf.columnconfigure(1, weight=1)

        for i, typ in enumerate(TYPES):
            col_hex = TYPE_COLORS.get(typ, "#888888")
            self._r(
                tk.Checkbutton(bf, text=typ, variable=self.type_ban_vars[typ],
                               fg=col_hex, font=("Segoe UI", 9, "bold"),
                               command=self._save_settings),
                "check_gen").grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=1)

        # Roll buttons
        rbf = self._r(tk.Frame(f), "bg_root")
        rbf.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        rbf.columnconfigure(0, weight=1)

        self._r(
            tk.Button(rbf, text="🎨  ROLL TYPING", command=self.roll_typing,
                      relief="flat", font=("Segoe UI", 13, "bold"), padx=0, pady=10,
                      cursor="hand2"),
            "btn_roll").grid(row=0, column=0, sticky="ew")

        self._r(
            tk.Button(rbf, text="🎭  ROLL DRAMATICALLY", command=self._roll_typing_dramatically,
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=0, pady=7,
                      cursor="hand2"),
            "btn_dramatic").grid(row=1, column=0, sticky="ew", pady=(4, 0))

    def _canvas_outlined_text(self, c, x, y, text, fill, font,
                               outline="#000000", osize=1, **kwargs):
        """Draw text with an 8-direction outline on a canvas widget."""
        dirs8 = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]
        for dx, dy in dirs8:
            c.create_text(x + dx*osize, y + dy*osize,
                          text=text, fill=outline, font=font, **kwargs)
        c.create_text(x, y, text=text, fill=fill, font=font, **kwargs)

    def _build_typing_right(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self._tab_frames["typing_right"] = f

        pf = self._r(
            tk.LabelFrame(f, text=" 🎨  Rolled Typing ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_result")
        pf.grid(row=0, column=0, sticky="nsew")
        pf.columnconfigure(0, weight=1)
        pf.rowconfigure(0, weight=1)

        self.typing_canvas = tk.Canvas(pf, highlightthickness=0)
        self.typing_canvas.grid(row=0, column=0, sticky="nsew")
        self._r(self.typing_canvas, "bg_root")
        self.typing_canvas.bind("<Configure>", lambda _: self._redraw_typing_canvas())
        self._draw_typing_placeholder()

    def _redraw_typing_canvas(self):
        """Redraw whichever typing state is current."""
        if self._rolled_types and not getattr(self, "_typing_hide_result", False):
            self._draw_typing_result()
        else:
            self._draw_typing_placeholder()

    def _draw_typing_placeholder(self):
        t = self._t
        c = self.typing_canvas
        c.configure(bg=t["bg_result"])
        c.delete("all")
        c.update_idletasks()
        w, h = c.winfo_width() or 400, c.winfo_height() or 300
        c.create_text(w//2, h//2, text="Press 🎨 Roll Typing to get started!",
                      fill=t["fg_sub"], font=("Segoe UI", 12), anchor="center")

    def _draw_typing_result(self):
        if not self._rolled_types:
            self._draw_typing_placeholder()
            return
        t = self._t
        c = self.typing_canvas
        c.delete("all")
        c.update_idletasks()
        W = c.winfo_width()  or 400
        H = c.winfo_height() or 300

        types     = self._rolled_types
        primary   = types[0]
        secondary = types[1] if len(types) > 1 else None
        tera      = types[2] if len(types) > 2 else None

        p_col = TYPE_COLORS.get(primary, "#888888")
        s_col = TYPE_COLORS.get(secondary, "#888888") if secondary else None

        # Background: gradient if dual, solid if single/N/A
        if secondary and secondary != "N/A":
            for x in range(W):
                ratio = x / W
                col   = _lerp_colour(p_col, s_col, ratio)
                c.create_line(x, 0, x, H, fill=col)
        else:
            c.configure(bg=_darken(p_col, 60))
            c.create_rectangle(0, 0, W, H, fill=_darken(p_col, 60), outline="")

        text_col = "#ffffff"
        out_col  = "#000000"

        # Primary type
        self._canvas_outlined_text(c, W//2, int(H*0.28), primary,
                                   fill=text_col, font=("Segoe UI", 36, "bold"),
                                   outline=out_col, osize=2, anchor="center")

        # Divider
        c.create_line(W//4, H//2, 3*W//4, H//2, fill=text_col, width=1)

        # Secondary type
        sec_text = secondary if secondary else "N/A"
        sec_col  = text_col if secondary else "#cccccc"
        self._canvas_outlined_text(c, W//2, int(H*0.62), sec_text,
                                   fill=sec_col, font=("Segoe UI", 36, "bold"),
                                   outline=out_col, osize=2, anchor="center")

        # Tera type
        if tera:
            tera_col = TYPE_COLORS.get(tera, "#888888")
            self._canvas_outlined_text(c, W//2, int(H*0.84), f"Tera: {tera}",
                                       fill=tera_col, font=("Segoe UI", 16, "bold"),
                                       outline=out_col, osize=1, anchor="center")

    # ── Stats tab ──────────────────────────────────────────────────────────────

    def _build_stats_tab(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        self._tab_frames["stats"] = f

        # Stat Spread
        sf = self._r(
            tk.LabelFrame(f, text=" 🎲  Roll Settings ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        sf.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        sf.columnconfigure(1, weight=1)

        # Mode radio buttons
        for i, (mode, label) in enumerate([
            ("Free",  "Free roll"),
            ("Range", "BST range"),
            ("Fixed", "Fixed BST"),
        ]):
            self._r(
                tk.Radiobutton(sf, text=label, variable=self.stat_mode_var, value=mode,
                               command=self._on_stat_mode_changed, font=("Segoe UI", 9)),
                "check").grid(row=i, column=0, sticky="w", pady=1)

        # Range controls (min – max)
        range_row = self._r(tk.Frame(sf), "bg_panel")
        range_row.grid(row=0, column=1, rowspan=2, sticky="ew", padx=(8, 0))
        range_row.columnconfigure(0, weight=1)

        self._r(tk.Label(range_row, text="Min:", font=("Segoe UI", 8)),
                "lbl_sub").grid(row=0, column=0, sticky="w")
        self.bst_min_spin = self._r(
            tk.Spinbox(range_row, from_=6, to=1530, textvariable=self.bst_min_var,
                       width=5, relief="flat", font=("Consolas", 11, "bold")),
            "spinbox")
        self.bst_min_spin.grid(row=1, column=0, sticky="ew")

        self._r(tk.Label(range_row, text="Max:", font=("Segoe UI", 8)),
                "lbl_sub").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.bst_max_spin = self._r(
            tk.Spinbox(range_row, from_=6, to=1530, textvariable=self.bst_max_var,
                       width=5, relief="flat", font=("Consolas", 11, "bold")),
            "spinbox")
        self.bst_max_spin.grid(row=3, column=0, sticky="ew")

        # Fixed BST control
        fixed_row = self._r(tk.Frame(sf), "bg_panel")
        fixed_row.grid(row=2, column=1, sticky="ew", padx=(8, 0))
        self._r(tk.Label(fixed_row, text="BST:", font=("Segoe UI", 8)),
                "lbl_sub").pack(anchor="w")
        self.bst_fixed_spin = self._r(
            tk.Spinbox(fixed_row, from_=6, to=1530, textvariable=self.bst_var,
                       width=5, relief="flat", font=("Consolas", 11, "bold")),
            "spinbox")
        self.bst_fixed_spin.pack(anchor="w")

        self._r(
            tk.Button(sf, text="📊  ROLL STAT SPREAD", command=self.roll_stats,
                      relief="flat", font=("Segoe UI", 12, "bold"), padx=0, pady=9,
                      cursor="hand2"),
            "btn_roll").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        self._r(
            tk.Button(sf, text="🎭  ROLL DRAMATICALLY", command=self._roll_stats_dramatically,
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=0, pady=6,
                      cursor="hand2"),
            "btn_dramatic").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Per-stat min/max
        minmax_check = self._r(
            tk.Checkbutton(sf, text="Use min/max per stat",
                           variable=self.use_stat_minmax_var,
                           command=self._on_stat_minmax_toggled,
                           font=("Segoe UI", 9)),
            "check")
        minmax_check.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Grid frame — hidden until ticked
        self._stat_minmax_frame = self._r(tk.Frame(sf), "bg_panel")
        self._stat_minmax_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Header row
        self._r(tk.Label(self._stat_minmax_frame, text="",      width=5, font=("Segoe UI", 8)),
                "lbl_sub").grid(row=0, column=0)
        self._r(tk.Label(self._stat_minmax_frame, text="Min",   width=5, font=("Segoe UI", 8, "bold")),
                "lbl_sub").grid(row=0, column=1)
        self._r(tk.Label(self._stat_minmax_frame, text="Max",   width=5, font=("Segoe UI", 8, "bold")),
                "lbl_sub").grid(row=0, column=2)

        self._stat_min_spins = {}
        self._stat_max_spins = {}
        for i, stat in enumerate(STAT_NAMES):
            self._r(
                tk.Label(self._stat_minmax_frame, text=stat + ":",
                         width=5, font=("Segoe UI", 9, "bold"), anchor="e"),
                "lbl_main").grid(row=i+1, column=0, sticky="e", padx=(0, 4), pady=1)
            mn = self._r(
                tk.Spinbox(self._stat_minmax_frame, from_=1, to=255,
                           textvariable=self.stat_min_vars[stat],
                           width=4, relief="flat", font=("Consolas", 9)),
                "spinbox")
            mn.grid(row=i+1, column=1, padx=(0, 4), pady=1)
            self._stat_min_spins[stat] = mn

            mx = self._r(
                tk.Spinbox(self._stat_minmax_frame, from_=1, to=255,
                           textvariable=self.stat_max_vars[stat],
                           width=4, relief="flat", font=("Consolas", 9)),
                "spinbox")
            mx.grid(row=i+1, column=2, pady=1)
            self._stat_max_spins[stat] = mx

        self._on_stat_minmax_toggled()   # hide grid initially

        self._on_stat_mode_changed()   # set initial widget states

        # Nature
        nf = self._r(
            tk.LabelFrame(f, text=" 🌿  Nature ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent2")
        nf.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        nf.columnconfigure(0, weight=1)

        self._r(
            tk.Button(nf, text="🌿  ROLL NATURE", command=self.roll_nature,
                      relief="flat", font=("Segoe UI", 12, "bold"), padx=0, pady=9,
                      cursor="hand2"),
            "btn_roll").grid(row=0, column=0, sticky="ew")

        self._r(
            tk.Button(nf, text="🎭  ROLL DRAMATICALLY", command=self._roll_nature_dramatically,
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=0, pady=6,
                      cursor="hand2"),
            "btn_dramatic").grid(row=1, column=0, sticky="ew", pady=(4, 0))

    def _build_stats_right(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=0, minsize=200)  # stat table — fixed
        f.columnconfigure(1, weight=1)               # nature — takes remainder
        f.rowconfigure(0, weight=0)                  # top panels — fixed height
        f.rowconfigure(1, weight=1)                  # radar chart — expands
        self._tab_frames["stats_right"] = f

        # ── Stat spread panel (top left) ───────────────────────────────────────
        spf = self._r(
            tk.LabelFrame(f, text=" 📊  Stat Spread ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        spf.grid(row=0, column=0, sticky="new", padx=(0, 6))
        spf.columnconfigure(0, weight=0)
        spf.columnconfigure(1, weight=0)

        self.stat_value_vars = {}
        for i, stat in enumerate(STAT_NAMES):
            self._r(
                tk.Label(spf, text=stat + ":", font=("Segoe UI", 11, "bold"), anchor="e",
                         width=5),
                "lbl_main").grid(row=i, column=0, sticky="e", pady=3, padx=(0, 8))
            var = tk.StringVar(value="—")
            self.stat_value_vars[stat] = var
            self._r(
                tk.Label(spf, textvariable=var, font=("Consolas", 14, "bold"), anchor="w",
                         width=5),
                "lbl_title").grid(row=i, column=1, sticky="w", pady=3)

        # Divider + total
        self._r(tk.Frame(spf, height=1), "lf_accent2").grid(
            row=len(STAT_NAMES), column=0, columnspan=2, sticky="ew", pady=(6, 3))
        self._r(
            tk.Label(spf, text="Total:", font=("Segoe UI", 11, "bold"), anchor="e", width=5),
            "lbl_main").grid(row=len(STAT_NAMES)+1, column=0, sticky="e", padx=(0, 8))
        self.stat_total_var = tk.StringVar(value="—")
        self._r(
            tk.Label(spf, textvariable=self.stat_total_var,
                     font=("Consolas", 14, "bold"), anchor="w", width=5),
            "lbl_title").grid(row=len(STAT_NAMES)+1, column=1, sticky="w")

        # ── Nature panel (top right) ───────────────────────────────────────────
        npf = self._r(
            tk.LabelFrame(f, text=" 🌿  Nature ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent2")
        npf.grid(row=0, column=1, sticky="new", padx=(6, 0))
        npf.columnconfigure(0, weight=1)

        self.nature_name_var = tk.StringVar(value="—")
        self._r(
            tk.Label(npf, textvariable=self.nature_name_var,
                     font=("Segoe UI", 22, "bold"), anchor="center"),
            "lbl_title").grid(row=0, column=0, sticky="ew", pady=(10, 6))

        self.nature_boost_var  = tk.StringVar(value="")
        self.nature_reduce_var = tk.StringVar(value="")

        self._r(
            tk.Label(npf, text="Boosts:", font=("Segoe UI", 9, "bold"), anchor="w"),
            "lbl_sub").grid(row=1, column=0, sticky="w")
        self._r(
            tk.Label(npf, textvariable=self.nature_boost_var,
                     font=("Segoe UI", 13, "bold"), anchor="w", fg="#69db7c"),
            "lbl_main").grid(row=2, column=0, sticky="w", pady=(0, 8))

        self._r(
            tk.Label(npf, text="Reduces:", font=("Segoe UI", 9, "bold"), anchor="w"),
            "lbl_sub").grid(row=3, column=0, sticky="w")
        self._r(
            tk.Label(npf, textvariable=self.nature_reduce_var,
                     font=("Segoe UI", 13, "bold"), anchor="w", fg="#ff6b6b"),
            "lbl_main").grid(row=4, column=0, sticky="w")

        self.nature_neutral_lbl = self._r(
            tk.Label(npf, text="", font=("Segoe UI", 9, "italic"), anchor="center"),
            "lbl_sub")
        self.nature_neutral_lbl.grid(row=5, column=0, sticky="ew", pady=(8, 0))

        # ── Radar chart (bottom, spans both columns) ───────────────────────────
        radar_frame = self._r(
            tk.LabelFrame(f, text=" 🕸  Stat Web ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=4, pady=4),
            "lf_accent1")
        radar_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        radar_frame.columnconfigure(0, weight=1)
        radar_frame.rowconfigure(0, weight=1)

        self.radar_canvas = self._r(
            tk.Canvas(radar_frame, highlightthickness=0),
            "bg_root")
        self.radar_canvas.grid(row=0, column=0, sticky="nsew")
        self.radar_canvas.bind("<Configure>", lambda _: self._draw_radar())
        self._draw_radar()

        self.radar_canvas.bind("<Configure>", lambda _: self._draw_radar())
        self._draw_radar()

    # ── Pokémon Randomiser tab ─────────────────────────────────────────────────

    def _load_pokemon_data(self) -> tuple:
        """Return (all_list, game_pools, encounter_pools, types, species, schema)."""
        if not os.path.exists(POKEMON_FILE):
            return [], {}, {}, {}, {}, 0
        try:
            with open(POKEMON_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data, {}, {}, {}, {}, 0
            types_raw   = {int(k): v for k, v in data.get("types", {}).items()}
            species_raw = {int(k): v for k, v in data.get("species", {}).items()}
            return (data.get("all", []), data.get("game_pools", {}),
                    data.get("encounter_pools", {}), types_raw, species_raw,
                    int(data.get("schema", 1)))
        except Exception:
            return [], {}, {}, {}, {}, 0

    def _save_pokemon_data(self, all_list: list, game_pools: dict,
                            encounter_pools: dict = None,
                            types: dict = None, species: dict = None):
        with open(POKEMON_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "schema":     POKEMON_CACHE_SCHEMA,
                "all":        all_list,
                "game_pools": game_pools,
                "encounter_pools": encounter_pools or {},
                "types":     {str(k): v for k, v in (types   or {}).items()},
                "species":   {str(k): v for k, v in (species or {}).items()},
            }, f, ensure_ascii=False)

    def _fetch_pokedex_ids(self, slug: str) -> set:
        """Fetch species IDs from a PokéAPI pokedex slug."""
        data = _api_get(f"{POKEAPI_BASE}/pokedex/{slug}")
        ids = set()
        for entry in data.get("pokemon_entries", []):
            url = entry.get("pokemon_species", {}).get("url", "")
            try:
                pid = int(url.rstrip("/").rsplit("/", 1)[-1])
                if 1 <= pid <= 1025:
                    ids.add(pid)
            except ValueError:
                pass
        return ids

    def _fetch_and_cache_pokemon(self):
        """Download full Pokémon roster + per-game dex pools, then cache."""
        self._pokemon_loading = True
        self.root.after(0, lambda: self.pokemon_status_var.set("Fetching Pokémon roster…"))
        self.root.after(0, lambda: self.pokemon_roll_btn.configure(state="disabled"))
        try:
            # 1. Full roster (IDs 1–1025)
            data    = _api_get(f"{POKEAPI_BASE}/pokemon?limit=2000&offset=0")
            results = data.get("results", [])
            all_list = []
            for entry in results:
                url  = entry["url"]
                slug = entry["name"]
                try:
                    pid = int(url.rstrip("/").rsplit("/", 1)[-1])
                except ValueError:
                    continue
                # Always include explicitly desired form variants
                if slug in EXTRA_FORM_SLUGS:
                    name = slug.replace("-", " ").title()
                    all_list.append({"id": pid, "name": name, "slug": slug})
                elif pid < 1 or pid > 1025:
                    continue
                else:
                    name = slug.replace("-", " ").title()
                    all_list.append({"id": pid, "name": name, "slug": slug})
            all_list.sort(key=lambda p: p["id"])

            # 2. Per-game regional dex pools (gift/event supplements are
            #    applied at roll time, see GAME_POOL_SUPPLEMENTS)
            game_pools = {}
            for game, slugs in GAME_POKEDEX_SLUGS.items():
                self.root.after(0, lambda g=game: self.pokemon_status_var.set(
                    f"Fetching {g} Pokédex…"))
                ids = set()
                for slug in slugs:
                    try:
                        ids |= self._fetch_pokedex_ids(slug)
                    except Exception:
                        pass
                game_pools[game] = sorted(ids)

            self._save_pokemon_data(all_list, game_pools)
            self._pokemon_all        = all_list
            self._pokemon_game_pools = game_pools
            # Fall back to the name-matched roster if the champions dex
            # isn't available on the API yet
            if not game_pools.get("Pokémon Champions"):
                game_pools["Pokémon Champions"] = self._champions_pool_ids()

            # 3. Fetch types for all pokemon (18 type API calls)
            self.root.after(0, lambda: self.pokemon_status_var.set("Fetching type data…"))
            type_map = {}   # pid -> [type1, type2]
            # Include form-variant IDs (>1025) so type filters work on them too
            roster_ids = {p["id"] for p in all_list}
            all_types = [
                "normal","fire","water","electric","grass","ice",
                "fighting","poison","ground","flying","psychic","bug",
                "rock","ghost","dragon","dark","steel","fairy",
            ]
            for tname in all_types:
                try:
                    tdata = _api_get(f"{POKEAPI_BASE}/type/{tname}")
                    for entry in tdata.get("pokemon", []):
                        url = entry.get("pokemon", {}).get("url", "")
                        try:
                            pid = int(url.rstrip("/").rsplit("/", 1)[-1])
                        except ValueError:
                            continue
                        if pid in roster_ids:
                            type_map.setdefault(pid, [])
                            if tname.title() not in type_map[pid]:
                                type_map[pid].append(tname.title())
                except Exception:
                    pass
            self._pokemon_types = type_map
            self._save_pokemon_data(all_list, game_pools, None, type_map)

            # 4. Fetch species data (baby/legendary/mythical/evo_stage) and
            #    per-version encounter availability in parallel
            self.root.after(0, lambda: self.pokemon_status_var.set(
                "Fetching species & encounter data (this may take a few minutes)…"))

            slug_to_pid = {p["slug"]: p["id"] for p in all_list if "slug" in p}

            def _fetch_one_species(slug, pid):
                info = None
                # Step 1: try species endpoint directly
                try:
                    d = _api_get(f"{POKEAPI_BASE}/pokemon-species/{slug}")
                    parent = d.get("evolves_from_species") or {}
                    info = {
                        "baby":       bool(d.get("is_baby", False)),
                        "legendary":  bool(d.get("is_legendary", False)),
                        "mythical":   bool(d.get("is_mythical", False)),
                        "parent":     parent.get("name") if parent else None,
                        "species_slug": d.get("name", slug),
                    }
                except Exception:
                    pass
                # Step 2: form variant fallback — get species URL via pokemon endpoint
                if info is None:
                    try:
                        pdata = _api_get(f"{POKEAPI_BASE}/pokemon/{slug}")
                        species_url = (pdata.get("species") or {}).get("url", "")
                        if species_url:
                            d = _api_get(species_url)
                            parent = d.get("evolves_from_species") or {}
                            info = {
                                "baby":       bool(d.get("is_baby", False)),
                                "legendary":  bool(d.get("is_legendary", False)),
                                "mythical":   bool(d.get("is_mythical", False)),
                                "parent":     parent.get("name") if parent else None,
                                "species_slug": d.get("name", slug),
                            }
                    except Exception:
                        pass
                # Which game versions this pokemon appears in (wild/static)
                versions = []
                if pid and 1 <= pid <= 1025:
                    try:
                        enc = _api_get(f"{POKEAPI_BASE}/pokemon/{pid}/encounters")
                        seen = set()
                        for loc in enc:
                            for vd in loc.get("version_details", []):
                                vname = (vd.get("version") or {}).get("name")
                                if vname:
                                    seen.add(vname)
                        versions = sorted(seen)
                    except Exception:
                        pass
                return slug, info, versions

            raw_species: dict = {}   # slug -> {baby, legendary, mythical, parent}
            version_ids: dict = {}   # version name -> {pid, ...}
            slugs = [p["slug"] for p in all_list if "slug" in p]
            done  = 0
            with ThreadPoolExecutor(max_workers=20) as pool:
                futs = {pool.submit(_fetch_one_species, s, slug_to_pid.get(s)): s
                        for s in slugs}
                for fut in as_completed(futs):
                    slug, info, versions = fut.result()
                    done += 1
                    if info:
                        raw_species[slug] = info
                    pid = slug_to_pid.get(slug)
                    if pid:
                        for v in versions:
                            version_ids.setdefault(v, set()).add(pid)
                    if done % 100 == 0:
                        pct = int(done / len(slugs) * 100)
                        self.root.after(0, lambda p=pct: self.pokemon_status_var.set(
                            f"Fetching species & encounter data… {p}%"))

            # Collapse per-version encounter sets into per-game pools
            encounter_pools = {}
            for game, versions in GAME_VERSIONS.items():
                ids = set()
                for v in versions:
                    ids |= version_ids.get(v, set())
                encounter_pools[game] = sorted(ids)
            self._pokemon_encounter_pools = encounter_pools

            # Derive evo_stage by following parent chain, with form-variant fallback
            def _base_info(slug):
                """Return species info for slug, with fallbacks for form variants."""
                if slug in raw_species:
                    return raw_species[slug]
                # Check if any entry has this as its species_slug
                for info in raw_species.values():
                    if info and info.get("species_slug") == slug:
                        return info
                # Progressive suffix stripping (e.g. basculegion-male → basculegion)
                if "-" in slug:
                    parts = slug.split("-")
                    for n in range(len(parts) - 1, 0, -1):
                        base = "-".join(parts[:n])
                        if base in raw_species:
                            return raw_species[base]
                        for info in raw_species.values():
                            if info and info.get("species_slug") == base:
                                return info
                return None

            def _evo_stage(slug, depth=0):
                if depth > 4:
                    return 2
                info = _base_info(slug)
                if info is None or info["parent"] is None:
                    return 0
                parent_stage = _evo_stage(info["parent"], depth + 1)
                return min(parent_stage + 1, 2)

            # Evolution-family root (lowest member's ID) — used at roll time to
            # expand game pools to whole families (breed down / evolve up)
            species_slug_to_pid: dict = {}
            for slug, info in raw_species.items():
                pid = slug_to_pid.get(slug)
                if pid is not None and info.get("species_slug"):
                    species_slug_to_pid.setdefault(info["species_slug"], pid)

            def _family_root_pid(slug, pid):
                cur, depth = slug, 0
                while depth <= 5:
                    info = _base_info(cur)
                    if not info or not info.get("parent"):
                        break
                    cur = info["parent"]
                    depth += 1
                root = species_slug_to_pid.get(cur)
                if root is None:
                    root = slug_to_pid.get(cur, pid)
                return root

            species_map: dict = {}  # pid -> {baby, legendary, mythical, evo_stage, family}
            for slug, info in raw_species.items():
                pid = slug_to_pid.get(slug)
                if pid is None:
                    continue
                species_map[pid] = {
                    "baby":       info["baby"],
                    "legendary":  info["legendary"],
                    "mythical":   info["mythical"],
                    "evo_stage":  _evo_stage(slug),
                    "family":     _family_root_pid(slug, pid),
                }
            self._pokemon_species = species_map
            self._save_pokemon_data(all_list, game_pools, encounter_pools,
                                    type_map, species_map)

            n = len(all_list)
            self.root.after(0, lambda: self.pokemon_status_var.set(
                f"{n} Pokémon loaded — ready to roll!"))
            self.root.after(0, lambda: self.pokemon_roll_btn.configure(state="normal"))
        except Exception as e:
            self.root.after(0, lambda: self.pokemon_status_var.set(
                f"Fetch failed: {e}"))
        finally:
            self._pokemon_loading = False

    def _champions_pool_ids(self) -> list:
        """Derive Champions roster IDs by matching names against the full list."""
        ids = []
        for p in self._pokemon_all:
            slug = p.get("slug", p["name"].lower().replace(" ", "-"))
            # Strip regional suffix for matching (e.g. "ninetales-alola" → "ninetales")
            base_slug = slug.split("-")[0] if "-" in slug else slug
            if slug in CHAMPIONS_ROSTER_NAMES or base_slug in CHAMPIONS_ROSTER_NAMES:
                if p["id"] not in ids:
                    ids.append(p["id"])
        return sorted(ids)

    def _extra_forms_for_pool(self, base_ids: set, game: str = None) -> list:
        """Return extra form variants from _pokemon_all whose base species is in base_ids."""
        extras = []
        for p in self._pokemon_all:
            slug = p.get("slug", "")
            base = FORM_TO_BASE_ID.get(slug)
            if not base or base not in base_ids:
                continue
            allowed_games = FORM_GAME_RESTRICT.get(slug)
            if allowed_games and game is not None and game not in allowed_games \
                    and game != "Custom":
                continue
            extras.append(p)
        return extras

    def _game_max_id(self, game: str) -> int:
        """Highest National Dex ID for the game's generation."""
        target_gen = GAME_PRESETS.get(game)
        if target_gen is None:
            return 1025
        max_id = 1025
        for gen in ["GEN I", "GEN II", "GEN III", "GEN IV", "GEN V",
                    "GEN VI", "GEN VII", "GEN VIII", "GEN IX"]:
            max_id = POKEMON_GEN_RANGES[gen][1]
            if gen == target_gen:
                break
        return max_id

    def _family_closure(self, ids: set, max_id: int) -> set:
        """Expand ids to whole evolution families (breed down / evolve up),
        capped at max_id so cross-gen relatives don't leak into older games."""
        species = self._pokemon_species
        if not species:
            return set(ids)

        def fam(pid):
            return (species.get(pid) or {}).get("family", pid)

        fams = {fam(i) for i in ids}
        out = set(ids)
        for p in self._pokemon_all:
            pid = p["id"]
            if pid <= max_id and fam(pid) in fams:
                out.add(pid)
        return out

    def _get_pokemon_pool(self) -> list:
        """Return the eligible Pokémon list for the currently selected game."""
        game = self.pokemon_game_var.get()

        if game == "Custom":
            base_ids = {p["id"] for p in self._pokemon_all if p["id"] <= 1025}
            pool = list(self._pokemon_all)
            pool += [p for p in self._extra_forms_for_pool(base_ids)
                     if p not in pool]
            return pool

        # Champions is an exact roster — no gift supplements or family closure
        if game == "Pokémon Champions":
            ids = set(self._pokemon_game_pools.get(game)
                      or self._champions_pool_ids())
            pool = [p for p in self._pokemon_all if p["id"] in ids]
            pool += self._extra_forms_for_pool(ids, game)
            return pool

        include_transfers = (self.pokemon_transfers_var.get()
                             and game in GAME_TRANSFER_POOLS)

        # Regional dex + wild/static encounters + gift/event supplements,
        # expanded to whole evolution families
        dex_ids = set(self._pokemon_game_pools.get(game, []))
        enc_ids = set(self._pokemon_encounter_pools.get(game, []))
        if dex_ids or enc_ids:
            allowed = dex_ids | enc_ids | GAME_POOL_SUPPLEMENTS.get(game, set())
            max_id  = POOL_CLOSURE_MAX_OVERRIDE.get(game, self._game_max_id(game))
            allowed = self._family_closure(allowed, max_id)
            if include_transfers:
                allowed |= GAME_TRANSFER_POOLS[game]
            pool = [p for p in self._pokemon_all if p["id"] in allowed]
            pool += self._extra_forms_for_pool(allowed, game)
            return pool

        # Fallback when no fetched pools exist (stale cache)
        if GAME_PRESETS.get(game) is None:
            return self._pokemon_all
        if include_transfers:
            allowed = set(GAME_TRANSFER_POOLS[game])
            pool = [p for p in self._pokemon_all if p["id"] in allowed]
            pool += self._extra_forms_for_pool(allowed, game)
            return pool
        max_id    = self._game_max_id(game)
        base_pool = [p for p in self._pokemon_all if p["id"] <= max_id]
        base_ids  = {p["id"] for p in base_pool}
        return base_pool + self._extra_forms_for_pool(base_ids, game)

    def _on_shiny_toggled(self):
        """Show or hide shiny options based on checkbox state."""
        try:
            if self.pokemon_shiny_var.get():
                self._shiny_opts_frame.grid()
            else:
                self._shiny_opts_frame.grid_remove()
            self._on_shiny_mode_changed()
        except AttributeError:
            pass

    def _on_shiny_mode_changed(self):
        """Show the correct odds/pct input row."""
        try:
            if self.pokemon_shiny_mode_var.get() == "odds":
                self._shiny_odds_row.grid()
                self._shiny_pct_row.grid_remove()
            else:
                self._shiny_odds_row.grid_remove()
                self._shiny_pct_row.grid()
        except AttributeError:
            pass

    def _shiny_probability(self) -> float:
        """Return the per-Pokémon shiny probability as a float 0–1."""
        if self.pokemon_shiny_mode_var.get() == "odds":
            odds = max(1, self.pokemon_shiny_odds_var.get())
            return 1.0 / odds
        else:
            try:
                pct = float(self.pokemon_shiny_pct_var.get())
            except ValueError:
                pct = 0.01
            return max(0.0, min(1.0, pct / 100.0))

    def _roll_shiny_flags(self, count: int) -> list:
        """Return a list of bools (one per Pokémon) for whether each is shiny."""
        if not self.pokemon_shiny_var.get():
            return [False] * count
        p = self._shiny_probability()
        return [random.random() < p for _ in range(count)]

    def _on_type_filter_all_toggled(self):
        """When 'All types' is ticked, tick every individual type too."""
        if self.pokemon_type_filter_all_var.get():
            for var in self._pokemon_type_vars.values():
                var.set(True)

    def _on_type_filter_changed(self):
        """When individual types change, update the 'All' master checkbox."""
        all_on = all(v.get() for v in self._pokemon_type_vars.values())
        self.pokemon_type_filter_all_var.set(all_on)

    def _type_filter_select_none(self):
        """Untick all individual types and the master checkbox."""
        for var in self._pokemon_type_vars.values():
            var.set(False)
        self.pokemon_type_filter_all_var.set(False)

    def _apply_type_filter(self, pool: list) -> list:
        """Filter pool to only Pokémon matching any selected type, then apply category filters."""
        if not self.pokemon_type_filter_all_var.get():
            selected = {t for t, v in self._pokemon_type_vars.items() if v.get()}
            if selected and self._pokemon_types:
                pool = [p for p in pool
                        if bool(set(self._pokemon_types.get(p["id"], [])) & selected)]
        return self._apply_category_filters(pool)

    def _apply_category_filters(self, pool: list) -> list:
        """Apply baby/base/stage/legendary/mythical/paradox filters."""
        cats = {k: v.get() for k, v in self._pokemon_cat_vars.items()}
        if all(v == "Any" for v in cats.values()):
            return pool

        has_data = bool(self._pokemon_species)

        # Build a slug→pid and species_slug→pid lookup for form-variant fallback
        _slug_to_pid = {p.get("slug", ""): p["id"]
                        for p in self._pokemon_all if p.get("slug")}

        def _flags(pid):
            paradox = pid in PARADOX_IDS
            sp      = self._pokemon_species.get(pid, {})

            # For any form variant (slug contains "-"), attempt a more authoritative
            # lookup via the species_slug stored during fetch, or via slug stripping.
            # This fixes cases like basculegion-male whose direct fetch failed.
            poke = next((p for p in self._pokemon_all if p["id"] == pid), None)
            if poke:
                slug = poke.get("slug", "")
                # Known form variants: use the base species' flags directly
                base_id = FORM_TO_BASE_ID.get(slug)
                if base_id and self._pokemon_species.get(base_id):
                    sp = self._pokemon_species[base_id]
                elif "-" in slug:
                    # Try species_slug stored in any companion form's cached data
                    def _try_slug(test_slug):
                        test_pid = _slug_to_pid.get(test_slug)
                        if test_pid:
                            return self._pokemon_species.get(test_pid, {})
                        # Search by species_slug field across all cached entries
                        for p2 in self._pokemon_all:
                            sp2 = self._pokemon_species.get(p2["id"], {})
                            if sp2.get("species_slug") == test_slug:
                                return sp2
                        return {}

                    # Try stripping suffixes progressively
                    parts = slug.split("-")
                    for n in range(len(parts) - 1, 0, -1):
                        base = "-".join(parts[:n])
                        candidate = _try_slug(base)
                        if candidate:
                            # Use candidate if it has richer data (evo_stage > 0 or flags set)
                            if (candidate.get("evo_stage", 0) > 0
                                    or candidate.get("baby") or candidate.get("legendary")
                                    or candidate.get("mythical")):
                                sp = candidate
                                break

            return {
                "baby":      sp.get("baby",      False),
                "legendary": sp.get("legendary", False),
                "mythical":  sp.get("mythical",  False),
                "evo_stage": sp.get("evo_stage",  0),
                "paradox":   paradox,
            }

        def _matches(pid):
            fl = _flags(pid)
            stage = fl["evo_stage"]
            checks = {
                "baby":      fl["baby"],
                "base":      stage == 0 and not fl["baby"] and not fl["paradox"]
                             and not fl["legendary"] and not fl["mythical"],
                "stage1":    stage == 1,
                "stage2":    stage >= 2,
                "legendary": fl["legendary"],
                "mythical":  fl["mythical"],
                "paradox":   fl["paradox"],
            }
            only_keys = [k for k, v in cats.items() if v == "Only"]
            if only_keys and not any(checks[k] for k in only_keys):
                return False
            for k, v in cats.items():
                if v == "Exclude" and checks[k]:
                    return False
            return True

        if not has_data:
            # No species data: only paradox filter works (hardcoded IDs)
            paradox_mode = cats.get("paradox", "Any")
            if paradox_mode == "Only":
                return [p for p in pool if p["id"] in PARADOX_IDS]
            if paradox_mode == "Exclude":
                return [p for p in pool if p["id"] not in PARADOX_IDS]
            return pool

        return [p for p in pool if _matches(p["id"])]

    def _make_collapsible(self, parent, title: str, accent_key: str,
                           start_collapsed: bool = True) -> tuple:
        """Create a collapsible section. Returns (outer_frame, content_frame)."""
        t = self._t
        accent_col = t.get(accent_key, t["fg_accent1"])

        outer = tk.Frame(parent, bg=t["bg_root"])
        self._r(outer, "bg_root")

        # Header — uses field bg with accent border/text so it reads as a section header
        hdr = tk.Frame(outer, bg=t["bg_field"],
                       highlightbackground=accent_col,
                       highlightthickness=1,
                       padx=8, pady=4)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)
        self._r(hdr, "bg_field")     # theme: re-colours bg on theme switch

        arrow_var = tk.StringVar(value="▶" if start_collapsed else "▼")
        arrow_lbl = tk.Label(hdr, textvariable=arrow_var,
                             font=("Segoe UI", 9, "bold"),
                             bg=t["bg_field"], fg=accent_col, cursor="hand2", width=2)
        arrow_lbl.grid(row=0, column=0, sticky="w")
        self._r(arrow_lbl, "bg_field")

        title_lbl = tk.Label(hdr, text=title,
                             font=("Segoe UI", 10, "bold"),
                             bg=t["bg_field"], fg=accent_col, cursor="hand2")
        title_lbl.grid(row=0, column=1, sticky="w")
        self._r(title_lbl, "bg_field")

        # Content area
        content = tk.Frame(outer, bg=t["bg_panel"], padx=10, pady=8)
        content.columnconfigure(0, weight=1)
        self._r(content, "bg_panel")

        # Arrow colour isn't tracked by _r, so re-set it after theme changes via trace
        collapsed = [start_collapsed]

        def _toggle(event=None):
            if collapsed[0]:
                content.grid(row=1, column=0, sticky="ew")
                arrow_var.set("▼")
            else:
                content.grid_remove()
                arrow_var.set("▶")
            collapsed[0] = not collapsed[0]

        for w in (hdr, arrow_lbl, title_lbl):
            w.bind("<Button-1>", _toggle)

        if not start_collapsed:
            content.grid(row=1, column=0, sticky="ew")

        return outer, content

    def _build_pokemon_tab(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        self._tab_frames["pokemon"] = f

        # Game preset selector
        pf = self._r(
            tk.LabelFrame(f, text=" 🎮  Game Preset ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        pf.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        pf.columnconfigure(0, weight=1)

        self._r(tk.Label(pf, text="Select your game to filter the Pokémon pool:",
                         font=("Segoe UI", 9)), "lbl_sub").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(pf, textvariable=self.pokemon_game_var,
                          values=list(GAME_PRESETS.keys()), state="readonly", width=30)
        cb.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        # Roll settings
        rf = self._r(
            tk.LabelFrame(f, text=" 🎲  Roll Settings ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=10),
            "lf_accent1")
        rf.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        rf.columnconfigure(1, weight=1)

        self._r(tk.Label(rf, text="Pokémon to draw:", font=("Segoe UI", 10)),
                "lbl_main").grid(row=0, column=0, sticky="w")
        self._r(
            tk.Spinbox(rf, from_=1, to=6, textvariable=self.pokemon_count_var,
                       width=5, relief="flat", font=("Consolas", 12, "bold")),
            "spinbox").grid(row=0, column=1, sticky="w", padx=(10, 0))

        self._r(
            tk.Checkbutton(rf, text="Include transfers (HOME / Pal Park / Bank / events)",
                           variable=self.pokemon_transfers_var,
                           font=("Segoe UI", 9),
                           command=self._save_settings),
            "check").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.pokemon_roll_btn = self._r(
            tk.Button(rf, text="🎲  ROLL POKÉMON", command=self._roll_pokemon,
                      relief="flat", font=("Segoe UI", 13, "bold"), padx=0, pady=10,
                      cursor="hand2"),
            "btn_roll")
        self.pokemon_roll_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        self._r(
            tk.Button(rf, text="🎭  ROLL DRAMATICALLY", command=self._pokemon_roll_dramatically,
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=0, pady=7,
                      cursor="hand2"),
            "btn_dramatic").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Type Filter (collapsible)
        tf_outer, tf = self._make_collapsible(f, "🎨  Type Filter", "fg_accent1",
                                               start_collapsed=True)
        tf_outer.grid(row=2, column=0, sticky="ew", pady=(0, 4))

        # "All" toggle + label
        top_row = self._r(tk.Frame(tf), "bg_panel")
        top_row.grid(row=0, column=0, sticky="ew")
        self._r(
            tk.Checkbutton(top_row, text="All types", font=("Segoe UI", 9, "bold"),
                           variable=self.pokemon_type_filter_all_var,
                           command=self._on_type_filter_all_toggled),
            "check").pack(side="left")
        self._r(
            tk.Button(top_row, text="None", font=("Segoe UI", 8), padx=6, pady=2,
                      relief="flat", cursor="hand2",
                      command=self._type_filter_select_none),
            "btn_small").pack(side="left", padx=(8, 0))

        # Grid of type checkboxes (2 columns, coloured by type)
        self._type_grid_frame = self._r(tk.Frame(tf), "bg_panel")
        self._type_grid_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self._type_grid_frame.columnconfigure(0, weight=1)
        self._type_grid_frame.columnconfigure(1, weight=1)

        TYPE_ORDER = [
            "Normal","Fire","Water","Electric","Grass","Ice",
            "Fighting","Poison","Ground","Flying","Psychic","Bug",
            "Rock","Ghost","Dragon","Dark","Steel","Fairy",
        ]
        for i, tname in enumerate(TYPE_ORDER):
            var = tk.BooleanVar(value=True)
            self._pokemon_type_vars[tname] = var
            col_hex = TYPE_COLORS.get(tname, "#888888")
            self._r(
                tk.Checkbutton(self._type_grid_frame, text=tname,
                               variable=var, font=("Segoe UI", 9, "bold"),
                               fg=col_hex, selectcolor=self._t["bg_panel"],
                               activeforeground=col_hex,
                               command=self._on_type_filter_changed),
                "check").grid(row=i // 2, column=i % 2, sticky="w", pady=1)

        # Category Filters (collapsible)
        cf_outer, cf = self._make_collapsible(f, "🏷  Category Filters", "fg_accent2",
                                               start_collapsed=True)
        cf_outer.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        cf.columnconfigure(1, weight=1)

        self._r(tk.Label(cf,
                         text="Any = include all  |  Only = must be this  |  Exclude = skip",
                         font=("Segoe UI", 7, "italic")),
                "lbl_sub").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        for i, (key, label) in enumerate(CATEGORY_FILTERS):
            var = self._pokemon_cat_vars[key]
            self._r(tk.Label(cf, text=f"{label}:", font=("Segoe UI", 9)),
                    "lbl_main").grid(row=i + 1, column=0, sticky="w", pady=2)
            row_f = self._r(tk.Frame(cf), "bg_panel")
            row_f.grid(row=i + 1, column=1, sticky="w", padx=(10, 0), pady=2)
            for opt in CATEGORY_FILTER_OPTIONS:
                self._r(
                    tk.Radiobutton(row_f, text=opt, variable=var, value=opt,
                                   font=("Segoe UI", 9)),
                    "check").pack(side="left", padx=(0, 8))

        # Shiny Chance (collapsible)
        shf_outer, shf = self._make_collapsible(f, "✨  Shiny Chance", "fg_accent1",
                                                 start_collapsed=True)
        shf_outer.grid(row=4, column=0, sticky="ew", pady=(0, 4))
        shf.columnconfigure(1, weight=1)

        self._r(
            tk.Checkbutton(shf, text="Enable shiny chance",
                           variable=self.pokemon_shiny_var,
                           font=("Segoe UI", 9, "bold"),
                           command=self._on_shiny_toggled),
            "check").grid(row=0, column=0, columnspan=2, sticky="w")

        self._shiny_opts_frame = self._r(tk.Frame(shf), "bg_panel")
        self._shiny_opts_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._shiny_opts_frame.columnconfigure(1, weight=1)

        # Mode radio buttons
        mode_row = self._r(tk.Frame(self._shiny_opts_frame), "bg_panel")
        mode_row.grid(row=0, column=0, columnspan=2, sticky="w")
        for mode, label in [("odds", "Odds (1 in X)"), ("percent", "Percentage (%)")]:
            self._r(
                tk.Radiobutton(mode_row, text=label, variable=self.pokemon_shiny_mode_var,
                               value=mode, font=("Segoe UI", 9),
                               command=self._on_shiny_mode_changed),
                "check").pack(side="left", padx=(0, 12))

        # Odds row
        self._shiny_odds_row = self._r(tk.Frame(self._shiny_opts_frame), "bg_panel")
        self._shiny_odds_row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._r(tk.Label(self._shiny_odds_row, text="1 in", font=("Segoe UI", 10)),
                "lbl_main").pack(side="left")
        self._r(
            tk.Spinbox(self._shiny_odds_row, from_=1, to=100000,
                       textvariable=self.pokemon_shiny_odds_var,
                       width=7, relief="flat", font=("Consolas", 11, "bold")),
            "spinbox").pack(side="left", padx=(8, 6))
        self._r(tk.Label(self._shiny_odds_row,
                         text="chance per Pokémon", font=("Segoe UI", 9)),
                "lbl_sub").pack(side="left")

        # Percent row
        self._shiny_pct_row = self._r(tk.Frame(self._shiny_opts_frame), "bg_panel")
        self._shiny_pct_row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        pct_entry = self._r(
            tk.Entry(self._shiny_pct_row, textvariable=self.pokemon_shiny_pct_var,
                     width=8, relief="flat", font=("Consolas", 11, "bold"),
                     justify="right"),
            "spinbox")
        pct_entry.pack(side="left")
        self._r(tk.Label(self._shiny_pct_row, text="%  per Pokémon  (0.01 = 1/10 000)",
                         font=("Segoe UI", 9)), "lbl_sub").pack(side="left", padx=(6, 0))

        self._on_shiny_toggled()   # set initial visibility

        # Status line (always visible) + collapsed maintenance section
        self.pokemon_status_var = tk.StringVar(value="Initialising…")
        self._r(tk.Label(f, textvariable=self.pokemon_status_var,
                         font=("Segoe UI", 9, "italic"), wraplength=280,
                         justify="left"),
                "lbl_theme").grid(row=5, column=0, sticky="w", pady=(2, 6))

        df_outer, df = self._make_collapsible(f, "ℹ️  Pokémon Data", "fg_accent2",
                                              start_collapsed=True)
        df_outer.grid(row=6, column=0, sticky="ew", pady=(0, 8))

        self._r(
            tk.Button(df, text="🔄  Fetch / Refresh Pokémon Data",
                      command=self._start_pokemon_fetch,
                      relief="flat", font=("Segoe UI", 9), padx=6, pady=4, cursor="hand2"),
            "btn_accent2").grid(row=0, column=0, sticky="ew")

        self._r(tk.Label(df,
                         text="Rebuilds the Pokémon data (game pools, types,\n"
                              "species) from PokéAPI. Takes a few minutes and\n"
                              "⚠ overwrites the currently saved data.\n"
                              "Not normally needed — data ships with the app\n"
                              "and updates alongside it.",
                         font=("Segoe UI", 8), justify="left"),
                "lbl_sub").grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Kick off loading from cache
        self.root.after(50, self._init_pokemon_data)

    def _init_pokemon_data(self):
        """Load Pokémon data from cache on startup."""
        (all_list, game_pools, encounter_pools,
         types, species, schema) = self._load_pokemon_data()
        self._pokemon_all             = all_list
        self._pokemon_game_pools      = game_pools
        self._pokemon_encounter_pools = encounter_pools
        self._pokemon_types           = types
        self._pokemon_species         = species
        if all_list and not game_pools.get("Pokémon Champions"):
            self._pokemon_game_pools["Pokémon Champions"] = self._champions_pool_ids()
        if all_list:
            if schema < POKEMON_CACHE_SCHEMA:
                self.pokemon_status_var.set(
                    f"{len(all_list)} Pokémon loaded — cached data is from an "
                    "older version. Fetch/Refresh for accurate per-game pools.")
            else:
                self.pokemon_status_var.set(f"{len(all_list)} Pokémon loaded.")
        else:
            self.pokemon_status_var.set(
                "No Pokémon data found. Open 'Pokémon Data' below and "
                "click Fetch to download it from PokéAPI.")

    def _start_pokemon_fetch(self):
        if self._pokemon_loading:
            return
        if self._pokemon_all and not messagebox.askyesno(
                APP_TITLE,
                "This will re-download all Pokémon data from PokéAPI and "
                "overwrite the currently saved data (game pools, types, "
                "species info).\n\n"
                "It takes a few minutes. Your settings and ban lists are "
                "not affected.\n\nContinue?",
                icon="warning"):
            return
        threading.Thread(target=self._fetch_and_cache_pokemon, daemon=True).start()

    def _roll_pokemon(self):
        """Pick random Pokémon from the game-appropriate pool and display cards."""
        if not self._pokemon_all:
            messagebox.showinfo(APP_TITLE,
                "No Pokémon data available.\nUse 'Fetch / Refresh Pokémon Data' first.")
            return

        game = self.pokemon_game_var.get()
        pool = self._apply_type_filter(self._get_pokemon_pool())
        if not pool:
            messagebox.showinfo(APP_TITLE,
                "No Pokémon match the selected type filter for this game.\n"
                "Try selecting more types or a different game preset.")
            return

        count = min(self.pokemon_count_var.get(), len(pool))
        self._rolled_pokemon = random.sample(pool, count)
        self._rolled_shiny   = self._roll_shiny_flags(count)

        threading.Thread(target=self._load_sprites_and_refresh, daemon=True).start()

    def _get_pokemon_sprite(self, pid: int, shiny: bool = False):
        """Return a 96×96 PhotoImage for the given Pokémon ID."""
        pil = self._get_pokemon_sprite_pil(pid, 96, 96, shiny=shiny)
        if pil is None:
            return None
        try:
            return ImageTk.PhotoImage(pil)
        except Exception:
            return None

    def _load_sprites_and_refresh(self):
        """Download/load sprites for rolled Pokémon then update the UI."""
        photos      = []
        shiny_flags = self._rolled_shiny
        for i, poke in enumerate(self._rolled_pokemon):
            is_shiny = shiny_flags[i] if i < len(shiny_flags) else False
            photo = self._get_pokemon_sprite(poke["id"], shiny=is_shiny)
            photos.append(photo)
        self._pokemon_photos = photos
        self.root.after(0, lambda: self._refresh_pokemon_cards(photos))

    def _refresh_pokemon_cards(self, photos):
        """Rebuild the Pokémon cards in the right panel."""
        if not hasattr(self, "_pokemon_card_frame"):
            return
        # Hide placeholder, show card frame
        try:
            self._pokemon_placeholder.grid_remove()
        except Exception:
            pass
        # Clear old cards
        for w in self._pokemon_card_frame.winfo_children():
            w.destroy()

        t      = self._t
        count  = len(self._rolled_pokemon)
        all_gens_ordered = [
            "GEN I", "GEN II", "GEN III", "GEN IV", "GEN V",
            "GEN VI", "GEN VII", "GEN VIII", "GEN IX",
        ]

        def _gen_for_id(pid):
            for gname in all_gens_ordered:
                lo, hi = POKEMON_GEN_RANGES[gname]
                if lo <= pid <= hi:
                    return gname
            return "???"

        COLS = 3

        shiny_flags = self._rolled_shiny

        for i, (poke, photo) in enumerate(zip(self._rolled_pokemon, photos)):
            row      = i // COLS
            col      = i % COLS
            is_shiny = shiny_flags[i] if i < len(shiny_flags) else False
            card = self._r(
                tk.Frame(self._pokemon_card_frame,
                         bg=t["bg_panel"],
                         highlightbackground=t["fg_sub"], highlightthickness=1,
                         padx=10, pady=10),
                "bg_panel")
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self._pokemon_card_frame.columnconfigure(col, weight=1)

            # Sprite image or placeholder
            if photo:
                img_lbl = tk.Label(card, image=photo, bg=t["bg_panel"])
                img_lbl.image = photo   # extra GC guard
                img_lbl.pack(pady=(4, 0))
            else:
                tk.Label(card, text="🔴", font=("Segoe UI", 40),
                         bg=t["bg_panel"], fg=t["fg_sub"]).pack(pady=(4, 0))

            # National Dex number
            self._r(
                tk.Label(card, text=f"#{poke['id']:04d}",
                         font=("Consolas", 9), bg=t["bg_panel"], fg=t["fg_sub"]),
                "bg_panel").pack()

            # Pokémon name
            self._r(
                tk.Label(card, text=poke["name"],
                         font=("Segoe UI", 13, "bold"),
                         bg=t["bg_panel"], fg=t["fg_accent1"],
                         wraplength=140, justify="center"),
                "bg_panel").pack(pady=(2, 0 if is_shiny else 4))

            # Shiny badge
            if is_shiny:
                tk.Label(card, text="✨ Shiny",
                         font=("Segoe UI", 9, "bold"),
                         bg=t["bg_panel"], fg="#ffd700").pack(pady=(2, 4))

    def _get_pokemon_sprite_sized(self, pid: int, w: int = 96, h: int = 96,
                                   shiny: bool = False):
        """Return a PhotoImage at an arbitrary size, downloading to cache if needed."""
        pil = self._get_pokemon_sprite_pil(pid, w, h, shiny=shiny)
        if pil is None:
            return None
        try:
            return ImageTk.PhotoImage(pil)
        except Exception:
            return None

    def _get_pokemon_sprite_pil(self, pid: int, w: int, h: int, shiny: bool = False):
        """Return a PIL RGBA Image at the given size, downloading to cache if needed."""
        if not _PIL_OK:
            return None
        suffix      = f"shiny_{pid}" if shiny else str(pid)
        sprite_path = os.path.join(POKEMON_SPRITES_DIR, f"{suffix}.png")
        if not os.path.exists(sprite_path):
            try:
                variant = "shiny/" if shiny else ""
                url = (f"https://raw.githubusercontent.com/PokeAPI/sprites/"
                       f"master/sprites/pokemon/{variant}{pid}.png")
                req = Request(url, headers={"User-Agent": "ThenWeRoll/" + VERSION})
                with urlopen(req, timeout=8) as r:
                    data = r.read()
                with open(sprite_path, "wb") as f:
                    f.write(data)
            except Exception:
                return None
        try:
            img = Image.open(sprite_path).convert("RGBA")
            return img.resize((w, h), Image.NEAREST)
        except Exception:
            return None

    def _pokemon_roll_dramatically(self):
        """Roll random Pokémon and immediately show the dramatic reveal."""
        if not self._pokemon_all:
            messagebox.showinfo(APP_TITLE,
                "No Pokémon data available.\nUse 'Fetch / Refresh Pokémon Data' first.")
            return
        pool = self._apply_type_filter(self._get_pokemon_pool())
        if not pool:
            messagebox.showinfo(APP_TITLE,
                "No Pokémon match the selected type filter for this game.")
            return
        count = min(self.pokemon_count_var.get(), len(pool))
        self._rolled_pokemon = random.sample(pool, count)
        self._rolled_shiny   = self._roll_shiny_flags(count)
        # The result cards are populated when the reveal closes (see the
        # overlay's finish handler) so they don't spoil the reveal
        threading.Thread(target=self._prepare_pokemon_dramatic_reveal, daemon=True).start()

    def _prepare_pokemon_dramatic_reveal(self):
        """Load sprites and pre-blend background frames, then hand off to the UI thread."""
        pokemon     = list(self._rolled_pokemon)
        shiny_flags = list(self._rolled_shiny)
        W           = self.root.winfo_width()
        H           = self.root.winfo_height()
        scale       = min(W / 1320, H / 820)
        base_sprite = self.reveal_pokemon_sprite_var.get()
        large_sz    = max(40, int(base_sprite * scale))
        small_sz    = max(30, int(base_sprite * 0.64 * scale))
        large = [self._get_pokemon_sprite_pil(p["id"], large_sz, large_sz,
                     shiny=shiny_flags[i] if i < len(shiny_flags) else False)
                 for i, p in enumerate(pokemon)]
        small = [self._get_pokemon_sprite_pil(p["id"], small_sz, small_sz,
                     shiny=shiny_flags[i] if i < len(shiny_flags) else False)
                 for i, p in enumerate(pokemon)]

        # Pre-blend background frames from black → full image (PIL only, no tkinter objects)
        STEPS, _ = self._get_reveal_fade()
        bg_full  = self._get_reveal_bg_pil_raw("pokemon", W, H)
        bg_pil_frames = None
        if bg_full is not None:
            black = Image.new("RGB", (W, H), (0, 0, 0))
            bg_pil_frames = [
                Image.blend(black, bg_full, min(step / max(STEPS, 1), 1.0))
                for step in range(STEPS + 2)
            ]

        self.root.after(0, lambda: self._show_pokemon_dramatic_overlay(
            pokemon, large, small, bg_pil_frames, shiny_flags))

    def _show_pokemon_dramatic_overlay(self, pokemon, large_photos, small_photos,
                                        bg_pil_frames=None, shiny_flags=None):
        t         = self._t
        BLACK     = "#000000"
        total     = len(pokemon)
        STEPS, MS = self._get_reveal_fade()

        ov, W, H  = self._make_overlay(BLACK)
        scale     = min(W / 1320, H / 820)
        fam       = self.reveal_font_var.get()

        sz_counter  = max(8,  int(11 * scale))
        sz_dex      = max(8,  int(10 * scale))
        sz_name     = max(14, int(self.reveal_font_size_var.get() * scale))
        sz_gen      = max(9,  int(13 * scale))
        sz_btn      = max(8,  int(10 * scale))
        btn_pady    = max(4,  int(8  * scale))
        btn_padx    = max(8,  int(18 * scale))
        fin_sz_name = max(10, int(22 * scale))
        fin_sz_gen  = max(8,  int(11 * scale))
        fin_sz_dex  = max(7,  int(9  * scale))

        all_gens = ["GEN I", "GEN II", "GEN III", "GEN IV", "GEN V",
                    "GEN VI", "GEN VII", "GEN VIII", "GEN IX"]

        def _gen_for(pid):
            for g in all_gens:
                lo, hi = POKEMON_GEN_RANGES[g]
                if lo <= pid <= hi:
                    return g
            return "???"

        cv = tk.Canvas(ov, highlightthickness=0, bg=BLACK)
        cv.place(x=0, y=0, width=W, height=H)

        bg_id    = cv.create_image(0, 0, anchor="nw")

        if shiny_flags is None:
            shiny_flags = [False] * total
        SHINY_COL = "#ffd700"
        sz_shiny  = max(8, int(12 * scale))

        # ── Individual-card canvas items ────────────────────────────────────────
        counter_fx  = self._create_fx_text(cv, W//2, int(H*0.09), text="",
                                            font=(fam, sz_counter, "bold"),
                                            anchor="center", state="normal", sub=True)
        sprite_id   = cv.create_image(W//2, int(H*0.40), anchor="center",
                                      state="normal")
        dex_fx      = self._create_fx_text(cv, W//2, int(H*0.62), text="",
                                            font=("Consolas", sz_dex), sub=True,
                                            anchor="center", state="normal")
        name_fx     = self._create_fx_text(cv, W//2, int(H*0.71), text="",
                                            font=(fam, sz_name, "bold"), anchor="center",
                                            width=int(W*0.80), justify="center",
                                            state="normal")
        shiny_fx    = self._create_fx_text(cv, W//2, int(H*0.82), text="✨  Shiny",
                                            font=(fam, sz_shiny, "bold"), anchor="center",
                                            state="hidden", sub=True)

        # ── Finale canvas items (all Pokémon together) ──────────────────────────
        fin_title_fx = self._create_fx_text(cv, W//2, int(H*0.11), text="Your Pokémon!",
                                             font=(fam, sz_counter, "bold"),
                                             anchor="center", state="hidden", sub=True)
        slot_w = W // max(total, 1)
        fin_sprites, fin_names, fin_dex_fxs, fin_shiny_ids = [], [], [], []
        for i, poke in enumerate(pokemon):
            cx = slot_w * i + slot_w // 2
            fin_sprites.append(cv.create_image(cx, int(H*0.40), anchor="center",
                                               state="hidden"))
            fin_dex_fxs.append(self._create_fx_text(cv, cx, int(H*0.60),
                                                      text=f"#{poke['id']:04d}",
                                                      font=("Consolas", fin_sz_dex),
                                                      anchor="center", state="hidden", sub=True))
            fin_names.append(cv.create_text(cx, int(H*0.68), text=poke["name"],
                                            fill=BLACK, font=(fam, fin_sz_name, "bold"),
                                            anchor="center",
                                            width=slot_w - 16, justify="center",
                                            state="hidden"))
            # Per-slot shiny label in finale (only shown when shiny)
            sh_id = cv.create_text(cx, int(H*0.77), text="✨ Shiny",
                                   fill=BLACK, font=(fam, sz_shiny, "bold"),
                                   anchor="center", state="hidden")
            fin_shiny_ids.append(sh_id)

        nav_y = int(H * 0.92)

        # PIL image aliases (large_photos / small_photos are PIL Images in this reveal)
        large_pil_imgs = large_photos
        small_pil_imgs = small_photos

        # Mutable state
        idx_ref    = [0]
        phase_ref  = ["cards"]
        fading_ref = [False]

        def _card_items():
            return ([sprite_id] +
                    self._fx_all_ids(counter_fx) +
                    self._fx_all_ids(dex_fx) +
                    self._fx_all_ids(name_fx) +
                    self._fx_all_ids(shiny_fx))

        def _finale_items():
            all_dex_ids = [id_ for fx in fin_dex_fxs for id_ in self._fx_all_ids(fx)]
            return (self._fx_all_ids(fin_title_fx) + fin_sprites + fin_names +
                    all_dex_ids + fin_shiny_ids)

        # Photo cache — keeps the current frame's PhotoImages alive (prevents GC mid-fade)
        _photo_cache: dict = {}

        def _composite_sprite(pil_img, alpha, _bg_hex=None):
            """Return a PhotoImage of pil_img with its alpha channel scaled by alpha.
            Transparent pixels remain transparent so the canvas background shows through."""
            if pil_img is None or alpha <= 0:
                return None
            rc, gc_ch, bc, ac = pil_img.split()
            a_scaled = ac.point(lambda x: int(x * alpha))
            return ImageTk.PhotoImage(Image.merge("RGBA", (rc, gc_ch, bc, a_scaled)))

        def apply_alpha(alpha):
            bg_c = _lerp_colour(BLACK, t["bg_root"], alpha)
            ov.configure(bg=bg_c)
            cv.configure(bg=bg_c)
            # Background: fade frame if available, otherwise nothing
            if bg_pil_frames:
                step_idx = min(round(alpha * STEPS), len(bg_pil_frames) - 1)
                cache_key = f"_bg_{step_idx}"
                if cache_key not in _photo_cache:
                    _photo_cache[cache_key] = ImageTk.PhotoImage(bg_pil_frames[step_idx])
                cv.itemconfigure(bg_id, image=_photo_cache[cache_key])
            else:
                cv.itemconfigure(bg_id, image="")

            if phase_ref[0] == "cards":
                # Hide finale items entirely
                for fid in _finale_items():
                    cv.itemconfigure(fid, state="hidden")
                # Fade card text items
                self._set_fx_state(cv, counter_fx, "normal")
                self._update_fx_text(cv, counter_fx, alpha, self._reveal_sub_col(),   BLACK, sub=True)
                self._set_fx_state(cv, dex_fx, "normal")
                self._update_fx_text(cv, dex_fx,  alpha, self._reveal_sub_col(),   BLACK, sub=True)
                self._set_fx_state(cv, name_fx, "normal")
                self._update_fx_text(cv, name_fx, alpha, self._reveal_title_col(), BLACK)
                # Shiny label — only shown for shiny pokemon
                cur_shiny = shiny_flags[idx_ref[0]] if idx_ref[0] < len(shiny_flags) else False
                if cur_shiny:
                    self._set_fx_state(cv, shiny_fx, "normal")
                    self._update_fx_text(cv, shiny_fx, alpha, SHINY_COL, BLACK, sub=True)
                else:
                    self._set_fx_state(cv, shiny_fx, "hidden")
                # Composite the large sprite
                pil = large_pil_imgs[idx_ref[0]] if idx_ref[0] < len(large_pil_imgs) else None
                photo = _composite_sprite(pil, alpha)
                _photo_cache["sprite"] = photo
                cv.itemconfigure(sprite_id, state="normal",
                                 image=photo if photo else "")
            else:
                # Hide card items entirely
                for cid in _card_items():
                    cv.itemconfigure(cid, state="hidden")
                # Fade finale text items
                self._set_fx_state(cv, fin_title_fx, "normal")
                self._update_fx_text(cv, fin_title_fx, alpha, self._reveal_sub_col(), BLACK, sub=True)
                for nid in fin_names:
                    cv.itemconfigure(nid, state="normal",
                                     fill=_lerp_colour(BLACK, self._reveal_title_col(), alpha))
                for fx in fin_dex_fxs:
                    self._set_fx_state(cv, fx, "normal")
                    self._update_fx_text(cv, fx, alpha, self._reveal_sub_col(), BLACK, sub=True)
                # Finale shiny labels
                for i, sh_id in enumerate(fin_shiny_ids):
                    if i < len(shiny_flags) and shiny_flags[i]:
                        cv.itemconfigure(sh_id, state="normal",
                                         fill=_lerp_colour(BLACK, SHINY_COL, alpha))
                    else:
                        cv.itemconfigure(sh_id, state="hidden")
                # Composite each small sprite
                for i, sid in enumerate(fin_sprites):
                    pil   = small_pil_imgs[i] if i < len(small_pil_imgs) else None
                    photo = _composite_sprite(pil, alpha)
                    _photo_cache[f"fin_{i}"] = photo
                    cv.itemconfigure(sid, state="normal",
                                     image=photo if photo else "")

        def fade_in(then=None):
            fading_ref[0] = True
            def tick(step=0):
                if not ov.winfo_exists(): return
                if step > STEPS:
                    apply_alpha(1.0); fading_ref[0] = False
                    if then: then()
                    return
                apply_alpha(step / STEPS)
                ov.after(MS, lambda: tick(step + 1))
            tick()

        def fade_out(then=None):
            fading_ref[0] = True
            def tick(step=0):
                if not ov.winfo_exists(): return
                if step > STEPS:
                    apply_alpha(0.0)
                    if then: then()
                    return
                apply_alpha(1.0 - step / STEPS)
                ov.after(MS, lambda: tick(step + 1))
            tick()

        def load_card(i):
            poke = pokemon[i]
            idx_ref[0]   = i
            phase_ref[0] = "cards"
            cv.itemconfigure(counter_fx["main"],  text=f"{i + 1}  /  {total}")
            for oid in counter_fx["outline"]:      cv.itemconfigure(oid, text=f"{i + 1}  /  {total}")
            cv.itemconfigure(dex_fx["main"],   text=f"#{poke['id']:04d}")
            for oid in dex_fx["outline"]:      cv.itemconfigure(oid, text=f"#{poke['id']:04d}")
            cv.itemconfigure(name_fx["main"],  text=poke["name"])
            for oid in name_fx["outline"]:     cv.itemconfigure(oid, text=poke["name"])
            for gid, _ in name_fx["glow"]:     cv.itemconfigure(gid, text=poke["name"])
            build_nav_cards(i)
        def build_nav_cards(i):
            bkw = dict(relief="flat", bd=0, padx=btn_padx, pady=btn_pady, cursor="hand2")
            btns = []
            if i > 0:
                btns.append(tk.Button(cv, text="◀  Previous",
                          command=lambda: go_card(i - 1),
                          bg=t["bg_field"], fg=t["fg_main"],
                          activebackground=t["fg_accent2"], activeforeground=t["bg_root"],
                          font=(fam, sz_btn), **bkw))
            last = (i == total - 1)
            btns.append(tk.Button(cv,
                      text="Show All  ▶" if last else "Next  ▶",
                      command=(lambda: go_finale()) if last else (lambda: go_card(i + 1)),
                      bg=t["roll_bg"], fg=t["fg_main"],
                      activebackground=t["roll_hover"], activeforeground=t["fg_main"],
                      font=(fam, sz_btn, "bold"), **bkw))
            btns.append(tk.Button(cv, text="✕  Skip reveal", command=finish,
                      bg=t["bg_field"], fg=t["fg_sub"],
                      activebackground=t["fg_banned"], activeforeground=t["bg_root"],
                      font=(fam, sz_btn), **bkw))
            self._canvas_nav_buttons(cv, W // 2, nav_y, btns)

        def build_nav_finale():
            bkw = dict(relief="flat", bd=0, padx=btn_padx, pady=btn_pady, cursor="hand2")
            btns = [
                tk.Button(cv, text="◀  Back",
                      command=lambda: go_card(total - 1),
                      bg=t["bg_field"], fg=t["fg_main"],
                      activebackground=t["fg_accent2"], activeforeground=t["bg_root"],
                      font=(fam, sz_btn), **bkw),
                tk.Button(cv, text="✅  Done", command=finish,
                      bg=t["roll_bg"], fg=t["fg_main"],
                      activebackground=t["roll_hover"], activeforeground=t["fg_main"],
                      font=(fam, sz_btn, "bold"), **bkw),
            ]
            self._canvas_nav_buttons(cv, W // 2, nav_y, btns)

        def show_card(i):
            load_card(i); fade_in()

        def show_finale():
            phase_ref[0] = "finale"
            build_nav_finale()
            fade_in()

        def go_card(i):
            if fading_ref[0]: return
            fade_out(then=lambda: show_card(i))

        def go_finale():
            if fading_ref[0]: return
            fade_out(then=show_finale)

        def finish():
            if fading_ref[0]: return
            def _close():
                if ov.winfo_exists():
                    ov.grab_release(); ov.destroy()
                # Populate the result cards now the reveal is over
                # (sprites are already cached from the reveal itself)
                threading.Thread(target=self._load_sprites_and_refresh,
                                 daemon=True).start()
            fade_out(then=_close)

        def on_key(event):
            i = idx_ref[0]
            if event.keysym in ("Right", "space", "Return"):
                if phase_ref[0] == "cards":
                    go_card(i + 1) if i < total - 1 else go_finale()
                else:
                    finish()
            elif event.keysym == "Left":
                if phase_ref[0] == "finale": go_card(total - 1)
                elif i > 0: go_card(i - 1)
            elif event.keysym == "Escape":
                finish()

        ov.bind("<KeyPress>", on_key)
        ov.focus_set()
        show_card(0)

    def _build_pokemon_right(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self._tab_frames["pokemon_right"] = f

        pf = self._r(
            tk.LabelFrame(f, text=" 🎲  Rolled Pokémon ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_result")
        pf.grid(row=0, column=0, sticky="nsew")
        pf.columnconfigure(0, weight=1)
        pf.rowconfigure(1, weight=1)

        # Placeholder text (replaced when a roll happens)
        self._pokemon_placeholder = self._r(
            tk.Label(pf, text="Press 🎲 Roll Pokémon to get started!",
                     font=("Segoe UI", 12), justify="center"),
            "lbl_sub")
        self._pokemon_placeholder.grid(row=0, column=0, pady=40)

        # Card container (hidden until first roll)
        self._pokemon_card_frame = tk.Frame(pf, bg=self._t["bg_panel"])
        self._r(self._pokemon_card_frame, "bg_panel")
        self._pokemon_card_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self._pokemon_card_frame.columnconfigure(0, weight=1)

    # ── Settings tab ───────────────────────────────────────────────────────────

    def _build_settings_tab(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        self._tab_frames["settings"] = f

        # Scrollable left panel
        canvas = tk.Canvas(f, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        f.rowconfigure(0, weight=1)
        scr = self._r(ttk.Scrollbar(f, orient="vertical", command=canvas.yview), "scrollbar")
        scr.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scr.set)
        self._r(canvas, "bg_root")

        inner = self._r(tk.Frame(canvas), "bg_root")
        inner.columnconfigure(0, weight=1)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(event):
            canvas.itemconfig(win_id, width=event.width)
        canvas.bind("<Configure>", _on_resize)
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        # ── Section 1: Dramatic Reveal ─────────────────────────────────────────
        dr = self._r(
            tk.LabelFrame(inner, text=" 🎭  Dramatic Reveal ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        dr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        dr.columnconfigure(1, weight=1)

        # Font
        self._r(tk.Label(dr, text="Font:", font=("Segoe UI", 9)), "lbl_main"
                ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        from tkinter.font import families as _font_families
        all_fonts = sorted(set(_font_families()), key=str.lower)
        self.font_cb = ttk.Combobox(dr, textvariable=self.reveal_font_var,
                                    values=all_fonts, width=22, font=("Segoe UI", 9))
        self.font_cb.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        self.font_cb.bind("<<ComboboxSelected>>", lambda _: (
            self._update_font_preview(), self._save_settings()))
        self.font_cb.bind("<KeyRelease>", self._filter_fonts)

        # Fade speed
        self._r(tk.Label(dr, text="Fade speed:", font=("Segoe UI", 9)), "lbl_main"
                ).grid(row=1, column=0, sticky="w", pady=(4, 4))
        speed_row = self._r(tk.Frame(dr), "bg_panel")
        speed_row.grid(row=1, column=1, sticky="w", padx=(8, 0))
        for spd in ["Slow", "Medium", "Fast"]:
            self._r(
                tk.Radiobutton(speed_row, text=spd, variable=self.reveal_fade_var,
                               value=spd, font=("Segoe UI", 9),
                               command=self._save_settings),
                "check").pack(side="left", padx=(0, 10))

        # Global BG image
        self._r(tk.Label(dr, text="Background image:", font=("Segoe UI", 9)), "lbl_main"
                ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        bg_row = self._r(tk.Frame(dr), "bg_panel")
        bg_row.grid(row=2, column=1, sticky="ew", padx=(8, 0))
        bg_row.columnconfigure(0, weight=1)
        self.global_bg_lbl = self._r(
            tk.Label(bg_row, textvariable=self.reveal_bg_global_var,
                     font=("Segoe UI", 8), anchor="w"),
            "lbl_sub")
        self.global_bg_lbl.grid(row=0, column=0, sticky="ew")
        bf2 = self._r(tk.Frame(bg_row), "bg_panel")
        bf2.grid(row=1, column=0, sticky="w")
        self._r(tk.Button(bf2, text="Browse…",
                           command=lambda: self._pick_reveal_bg("global"),
                           relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_small").pack(side="left", padx=(0, 4))
        self._r(tk.Button(bf2, text="Clear",
                           command=lambda: self._clear_reveal_bg("global"),
                           relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_banned").pack(side="left")

        # Stretch mode
        self._r(tk.Label(dr, text="Stretch mode:", font=("Segoe UI", 9)), "lbl_main"
                ).grid(row=3, column=0, sticky="w", pady=(4, 0))
        stretch_row = self._r(tk.Frame(dr), "bg_panel")
        stretch_row.grid(row=3, column=1, sticky="w", padx=(8, 0))
        for mode in ["Tile", "Fit", "Fill"]:
            self._r(
                tk.Radiobutton(stretch_row, text=mode, variable=self.reveal_bg_stretch_var,
                               value=mode, font=("Segoe UI", 9),
                               command=self._save_settings),
                "check").pack(side="left", padx=(0, 10))

        # Typing gradient override
        self._r(
            tk.Checkbutton(dr, text="Override typing gradient with image",
                           variable=self.reveal_typing_override_var,
                           font=("Segoe UI", 9), command=self._save_settings),
            "check").grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # Per-reveal override toggle
        per_check = self._r(
            tk.Checkbutton(dr, text="Customise per reveal type",
                           variable=self.reveal_bg_per_var,
                           font=("Segoe UI", 9),
                           command=self._on_per_reveal_toggled),
            "check")
        per_check.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self._per_reveal_frame = self._r(tk.Frame(dr), "bg_panel")
        self._per_reveal_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._per_reveal_frame.columnconfigure(1, weight=1)

        for i, (key, label, var) in enumerate([
            ("abilities", "Abilities:", self.reveal_bg_abilities_var),
            ("typing",    "Typing:",    self.reveal_bg_typing_var),
            ("stats",     "Stats:",     self.reveal_bg_stats_var),
            ("nature",    "Nature:",    self.reveal_bg_nature_var),
            ("pokemon",   "Pokémon:",   self.reveal_bg_pokemon_var),
        ]):
            self._r(tk.Label(self._per_reveal_frame, text=label, font=("Segoe UI", 9)),
                    "lbl_main").grid(row=i*2, column=0, sticky="w", pady=(4, 0))
            self._r(tk.Label(self._per_reveal_frame, textvariable=var,
                             font=("Segoe UI", 8), anchor="w"),
                    "lbl_sub").grid(row=i*2, column=1, sticky="ew", padx=(8, 0))
            pbf = self._r(tk.Frame(self._per_reveal_frame), "bg_panel")
            pbf.grid(row=i*2+1, column=0, columnspan=2, sticky="w", pady=(2, 0))
            _k = key
            _v = var
            self._r(tk.Button(pbf, text="Browse…",
                               command=lambda k=_k: self._pick_reveal_bg(k),
                               relief="flat", font=("Segoe UI", 8), padx=6, pady=2,
                               cursor="hand2"),
                    "btn_small").pack(side="left", padx=(0, 4))
            self._r(tk.Button(pbf, text="Clear",
                               command=lambda k=_k: self._clear_reveal_bg(k),
                               relief="flat", font=("Segoe UI", 8), padx=6, pady=2,
                               cursor="hand2"),
                    "btn_banned").pack(side="left")

        self._on_per_reveal_toggled()

        # ── Section 2: Window ──────────────────────────────────────────────────
        wf = self._r(
            tk.LabelFrame(inner, text=" 🖥  Window ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent2")
        wf.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        wf.columnconfigure(1, weight=1)

        # Start maximised
        self._r(
            tk.Checkbutton(wf, text="Start maximised",
                           variable=self.win_maximised_var,
                           font=("Segoe UI", 9),
                           command=self._on_maximised_toggled),
            "check").grid(row=0, column=0, columnspan=2, sticky="w")

        # Width / height
        size_row = self._r(tk.Frame(wf), "bg_panel")
        size_row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._r(tk.Label(size_row, text="Size:", font=("Segoe UI", 9)), "lbl_main"
                ).pack(side="left")
        self.win_w_spin = self._r(
            tk.Spinbox(size_row, from_=800, to=3840, textvariable=self.win_width_var,
                       width=5, relief="flat", font=("Consolas", 10)),
            "spinbox")
        self.win_w_spin.pack(side="left", padx=(8, 0))
        self._r(tk.Label(size_row, text="×", font=("Segoe UI", 9)), "lbl_main"
                ).pack(side="left", padx=4)
        self.win_h_spin = self._r(
            tk.Spinbox(size_row, from_=600, to=2160, textvariable=self.win_height_var,
                       width=5, relief="flat", font=("Consolas", 10)),
            "spinbox")
        self.win_h_spin.pack(side="left")
        self._r(tk.Label(size_row, text="(applied on next launch)",
                         font=("Segoe UI", 8, "italic")), "lbl_sub"
                ).pack(side="left", padx=(8, 0))

        # Default tab
        self._r(tk.Label(wf, text="Default tab on launch:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=2, column=0, sticky="w", pady=(8, 0))
        tab_row = self._r(tk.Frame(wf), "bg_panel")
        tab_row.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        for key, label in [("abilities", "Abilities"), ("typing", "Typing"), ("stats", "Stats")]:
            self._r(
                tk.Radiobutton(tab_row, text=label, variable=self.default_tab_var,
                               value=key, font=("Segoe UI", 9),
                               command=self._save_settings),
                "check").pack(side="left", padx=(0, 10))

        self._on_maximised_toggled()

        # ── Section 3: Export / Import ─────────────────────────────────────────
        ef = self._r(
            tk.LabelFrame(inner, text=" 💾  Export / Import ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        ef.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ef.columnconfigure(0, weight=1)
        ef.columnconfigure(1, weight=1)

        self._r(tk.Label(ef, text="Settings", font=("Segoe UI", 9, "bold")),
                "lbl_main").grid(row=0, column=0, sticky="w")
        self._r(tk.Label(ef, text="Ban List", font=("Segoe UI", 9, "bold")),
                "lbl_main").grid(row=0, column=1, sticky="w", padx=(8, 0))

        self._r(
            tk.Button(ef, text="⬆  Export Settings", command=self._export_settings,
                      relief="flat", font=("Segoe UI", 9), padx=6, pady=4, cursor="hand2"),
            "btn_accent2").grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._r(
            tk.Button(ef, text="⬆  Export Ban List", command=self._export_bans,
                      relief="flat", font=("Segoe UI", 9), padx=6, pady=4, cursor="hand2"),
            "btn_accent2").grid(row=1, column=1, sticky="ew", pady=(4, 0), padx=(8, 0))
        self._r(
            tk.Button(ef, text="⬇  Import Settings", command=self._import_settings,
                      relief="flat", font=("Segoe UI", 9), padx=6, pady=4, cursor="hand2"),
            "btn_accent1").grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self._r(
            tk.Button(ef, text="⬇  Import Ban List", command=self._import_bans,
                      relief="flat", font=("Segoe UI", 9), padx=6, pady=4, cursor="hand2"),
            "btn_accent1").grid(row=2, column=1, sticky="ew", pady=(4, 0), padx=(8, 0))

    def _build_settings_right(self, parent):
        f = self._r(tk.Frame(parent), "bg_root")
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        self._tab_frames["settings_right"] = f

        # ── Top controls ───────────────────────────────────────────────────────
        ctrl = self._r(
            tk.LabelFrame(f, text=" 🎭  Dramatic Roll Appearance ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctrl.columnconfigure(1, weight=1)

        def _refresh_fx(*_):
            self._save_settings()
            self._refresh_reveal_preview()

        # Preview type selector
        self._r(tk.Label(ctrl, text="Preview style:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=0, column=0, sticky="w")
        pt_row = self._r(tk.Frame(ctrl), "bg_panel")
        pt_row.grid(row=0, column=1, sticky="w", padx=(10, 0))
        for key, label in [("abilities", "Ability"), ("typing", "Typing"),
                            ("stats", "Stats"), ("pokemon", "Pokémon")]:
            self._r(
                tk.Radiobutton(pt_row, text=label,
                               variable=self.reveal_preview_type_var, value=key,
                               font=("Segoe UI", 9),
                               command=self._refresh_reveal_preview),
                "check").pack(side="left", padx=(0, 8))

        # Font size
        self._r(tk.Label(ctrl, text="Font size:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=1, column=0, sticky="w", pady=(6, 0))
        size_row = self._r(tk.Frame(ctrl), "bg_panel")
        size_row.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self._r(
            tk.Spinbox(size_row, from_=14, to=80, textvariable=self.reveal_font_size_var,
                       width=4, relief="flat", font=("Consolas", 10),
                       command=lambda: (self._save_settings(), self._refresh_reveal_preview())),
            "spinbox").pack(side="left")
        self._r(tk.Label(size_row, text="pt", font=("Segoe UI", 9)),
                "lbl_sub").pack(side="left", padx=(4, 0))
        self.reveal_font_size_var.trace_add("write",
            lambda *_: (self._save_settings(), self._refresh_reveal_preview()))

        # Title colour
        self._r(tk.Label(ctrl, text="Title colour:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=2, column=0, sticky="w", pady=(6, 0))
        tc_row = self._r(tk.Frame(ctrl), "bg_panel")
        tc_row.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self.reveal_title_swatch = tk.Label(tc_row, width=3, relief="solid", bd=1, cursor="hand2")
        self.reveal_title_swatch.pack(side="left")
        self._r(tk.Button(tc_row, text="Pick…",
                          command=lambda: self._pick_reveal_colour("title"),
                          relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_small").pack(side="left", padx=(6, 4))
        self._r(tk.Button(tc_row, text="Reset",
                          command=lambda: self._reset_reveal_colour("title"),
                          relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_banned").pack(side="left")
        self._r(tk.Label(tc_row, text="(blank = use theme colour)",
                         font=("Segoe UI", 8, "italic")),
                "lbl_sub").pack(side="left", padx=(8, 0))

        # Secondary colour
        self._r(tk.Label(ctrl, text="Secondary colour:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=3, column=0, sticky="w", pady=(6, 0))
        sc_row = self._r(tk.Frame(ctrl), "bg_panel")
        sc_row.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self.reveal_sub_swatch = tk.Label(sc_row, width=3, relief="solid", bd=1, cursor="hand2")
        self.reveal_sub_swatch.pack(side="left")
        self._r(tk.Button(sc_row, text="Pick…",
                          command=lambda: self._pick_reveal_colour("sub"),
                          relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_small").pack(side="left", padx=(6, 4))
        self._r(tk.Button(sc_row, text="Reset",
                          command=lambda: self._reset_reveal_colour("sub"),
                          relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_banned").pack(side="left")
        self._r(tk.Label(sc_row, text="(blank = use theme colour)",
                         font=("Segoe UI", 8, "italic")),
                "lbl_sub").pack(side="left", padx=(8, 0))

        # Font family + Pokémon sprite size (inline, sprite only shown for Pokémon preview)
        self._r(tk.Label(ctrl, text="Font:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=4, column=0, sticky="w", pady=(6, 0))
        font_spr_row = self._r(tk.Frame(ctrl), "bg_panel")
        font_spr_row.grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=(6, 0))
        font_spr_row.columnconfigure(0, weight=1)
        from tkinter.font import families as _font_families
        all_fonts = sorted(set(_font_families()), key=str.lower)
        self.font_cb = ttk.Combobox(font_spr_row, textvariable=self.reveal_font_var,
                                    values=all_fonts, width=14, font=("Segoe UI", 9))
        self.font_cb.grid(row=0, column=0, sticky="ew")
        self.font_cb.bind("<<ComboboxSelected>>", lambda _: (
            self._update_font_preview(), self._save_settings(),
            self._refresh_reveal_preview()))
        self.font_cb.bind("<KeyRelease>", self._filter_fonts)

        # Pokémon sprite inline controls (hidden unless Pokémon preview selected)
        self._sprite_inline = self._r(tk.Frame(font_spr_row), "bg_panel")
        self._sprite_inline.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._r(tk.Label(self._sprite_inline, text="Sprite:", font=("Segoe UI", 8)),
                "lbl_sub").pack(side="left")
        self._r(
            tk.Spinbox(self._sprite_inline, from_=40, to=400,
                       textvariable=self.reveal_pokemon_sprite_var,
                       width=4, relief="flat", font=("Consolas", 9),
                       command=lambda: (self._save_settings(), self._refresh_reveal_preview())),
            "spinbox").pack(side="left", padx=(4, 2))
        self._r(tk.Label(self._sprite_inline, text="px", font=("Segoe UI", 8)),
                "lbl_sub").pack(side="left")
        self.reveal_pokemon_sprite_var.trace_add("write",
            lambda *_: (self._save_settings(), self._refresh_reveal_preview()))

        # ── Text Effects ───────────────────────────────────────────────────────
        # Outline
        self._r(tk.Label(ctrl, text="Outline:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=5, column=0, sticky="w", pady=(10, 0))
        out_row = self._r(tk.Frame(ctrl), "bg_panel")
        out_row.grid(row=5, column=1, sticky="w", padx=(10, 0), pady=(10, 0))
        self._r(
            tk.Checkbutton(out_row, text="On", variable=self.reveal_outline_var,
                           font=("Segoe UI", 9), command=_refresh_fx),
            "check").pack(side="left", padx=(0, 8))
        self._r(tk.Label(out_row, text="Size:", font=("Segoe UI", 9)), "lbl_sub"
                ).pack(side="left")
        self._r(
            tk.Spinbox(out_row, from_=1, to=8, textvariable=self.reveal_outline_size_var,
                       width=3, relief="flat", font=("Consolas", 9),
                       command=_refresh_fx),
            "spinbox").pack(side="left", padx=(4, 8))
        self.reveal_outline_swatch = tk.Label(out_row, width=3, relief="solid", bd=1, cursor="hand2")
        self.reveal_outline_swatch.pack(side="left")
        self._r(tk.Button(out_row, text="Pick…",
                          command=lambda: self._pick_reveal_colour("outline"),
                          relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_small").pack(side="left", padx=(6, 0))
        self.reveal_outline_size_var.trace_add("write", _refresh_fx)

        # Glow
        self._r(tk.Label(ctrl, text="Glow:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=6, column=0, sticky="w", pady=(6, 0))
        glow_row = self._r(tk.Frame(ctrl), "bg_panel")
        glow_row.grid(row=6, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self._r(
            tk.Checkbutton(glow_row, text="On", variable=self.reveal_glow_var,
                           font=("Segoe UI", 9), command=_refresh_fx),
            "check").pack(side="left", padx=(0, 8))
        self._r(tk.Label(glow_row, text="Size:", font=("Segoe UI", 9)), "lbl_sub"
                ).pack(side="left")
        self._r(
            tk.Spinbox(glow_row, from_=1, to=12, textvariable=self.reveal_glow_size_var,
                       width=3, relief="flat", font=("Consolas", 9),
                       command=_refresh_fx),
            "spinbox").pack(side="left", padx=(4, 8))
        self.reveal_glow_swatch = tk.Label(glow_row, width=3, relief="solid", bd=1, cursor="hand2")
        self.reveal_glow_swatch.pack(side="left")
        self._r(tk.Button(glow_row, text="Pick…",
                          command=lambda: self._pick_reveal_colour("glow"),
                          relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_small").pack(side="left", padx=(6, 0))
        self._r(tk.Label(glow_row, text="(blank = title colour)",
                         font=("Segoe UI", 8, "italic")),
                "lbl_sub").pack(side="left", padx=(8, 0))
        self.reveal_glow_size_var.trace_add("write", _refresh_fx)

        # Subtext Outline
        self._r(tk.Label(ctrl, text="Subtext outline:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=7, column=0, sticky="w", pady=(6, 0))
        sub_out_row = self._r(tk.Frame(ctrl), "bg_panel")
        sub_out_row.grid(row=7, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self._r(
            tk.Checkbutton(sub_out_row, text="On", variable=self.reveal_sub_outline_var,
                           font=("Segoe UI", 9), command=_refresh_fx),
            "check").pack(side="left", padx=(0, 8))
        self._r(tk.Label(sub_out_row, text="Size:", font=("Segoe UI", 9)), "lbl_sub"
                ).pack(side="left")
        self._r(
            tk.Spinbox(sub_out_row, from_=1, to=8, textvariable=self.reveal_sub_outline_size_var,
                       width=3, relief="flat", font=("Consolas", 9),
                       command=_refresh_fx),
            "spinbox").pack(side="left", padx=(4, 8))
        self.reveal_sub_outline_swatch = tk.Label(sub_out_row, width=3, relief="solid", bd=1,
                                                   cursor="hand2")
        self.reveal_sub_outline_swatch.pack(side="left")
        self._r(tk.Button(sub_out_row, text="Pick…",
                          command=lambda: self._pick_reveal_colour("sub_outline"),
                          relief="flat", font=("Segoe UI", 8), padx=6, pady=2, cursor="hand2"),
                "btn_small").pack(side="left", padx=(6, 0))
        self._r(tk.Label(sub_out_row, text="(applies to secondary text)",
                         font=("Segoe UI", 8, "italic")),
                "lbl_sub").pack(side="left", padx=(8, 0))
        self.reveal_sub_outline_size_var.trace_add("write", _refresh_fx)

        # ── Live preview canvas ────────────────────────────────────────────────
        pf = self._r(
            tk.LabelFrame(f, text=" 👁  Live Preview ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=0, pady=0),
            "lf_accent2")
        pf.grid(row=1, column=0, sticky="nsew")
        pf.columnconfigure(0, weight=1)
        pf.rowconfigure(0, weight=1)

        self._preview_canvas = tk.Canvas(pf, highlightthickness=0, bg="#000000")
        self._preview_canvas.grid(row=0, column=0, sticky="nsew")
        self._preview_canvas.bind("<Configure>", lambda _: self._refresh_reveal_preview())

        # Init swatches after widgets exist
        self.root.after(50, self._update_colour_swatches)
        self.root.after(100, self._refresh_reveal_preview)

    # ── Settings helpers ────────────────────────────────────────────────────────

    # ── Text effects helpers ────────────────────────────────────────────────────

    def _parse_font_kwarg(self, font):
        """Split a tk font tuple into (family, size, bold) or (None, 0, False)."""
        try:
            fam  = str(font[0])
            size = int(font[1])
            bold = len(font) > 2 and "bold" in str(font[2]).lower()
            return fam, size, bold
        except Exception:
            return None, 0, False

    def _create_fx_text(self, cv, x, y, fill="#000000", state="normal", sub=False, **kwargs):
        """Create glow + outline + main text layers. Returns an fx dict.
        sub=True uses the subtext outline settings; glow only applies to title text.

        Title text is rendered as a PIL image with a true alpha channel when
        possible (smooth outline + blurred glow layered over any background);
        the stacked-canvas-text approach below is the fallback."""
        if not sub and _PIL_OK:
            fam, size, bold = self._parse_font_kwarg(kwargs.get("font"))
            if fam and size > 0 and _resolve_font_file(fam, bold):
                anchor  = kwargs.get("anchor", "center")
                main_id = cv.create_text(x, y, fill="", state=state, **kwargs)
                img_id  = cv.create_image(x, y, anchor=anchor, state=state)
                if not hasattr(cv, "_fx_photos"):
                    cv._fx_photos = {}
                return {"main": main_id, "outline": [], "glow": [],
                        "img": img_id, "font": (fam, size, bold),
                        "wrap": kwargs.get("width"), "sig": None, "base": None}

        dirs8 = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]
        glow_ids    = []
        outline_ids = []

        # Glow layers — title text only
        if not sub and self.reveal_glow_var.get():
            gsize = max(1, self.reveal_glow_size_var.get())
            for ring in range(gsize, 0, -1):
                intensity = (gsize - ring + 1) / gsize
                for dx, dy in dirs8:
                    gid = cv.create_text(x + dx * ring, y + dy * ring,
                                         fill=fill, state=state, **kwargs)
                    glow_ids.append((gid, intensity))

        # Outline layers
        out_on   = self.reveal_sub_outline_var.get() if sub else self.reveal_outline_var.get()
        out_size = self.reveal_sub_outline_size_var.get() if sub else self.reveal_outline_size_var.get()
        if out_on:
            osize = max(1, out_size)
            for dx, dy in dirs8:
                oid = cv.create_text(x + dx * osize, y + dy * osize,
                                     fill=fill, state=state, **kwargs)
                outline_ids.append(oid)

        # Main text (top layer)
        main_id = cv.create_text(x, y, fill=fill, state=state, **kwargs)

        return {"main": main_id, "outline": outline_ids, "glow": glow_ids}

    def _fx_all_ids(self, fx: dict) -> list:
        """Return every canvas item ID in an fx dict, ordered back-to-front."""
        ids = ([gid for gid, _ in fx["glow"]] +
               fx["outline"] +
               [fx["main"]])
        if "img" in fx:
            ids.append(fx["img"])
        return ids

    def _set_fx_state(self, cv, fx: dict, state: str):
        """Set state= on every layer of an fx dict."""
        for id_ in self._fx_all_ids(fx):
            cv.itemconfigure(id_, state=state)

    def _wrap_text_pil(self, text: str, font, max_w: int, stroke: int) -> str:
        """Word-wrap text to max_w pixels for PIL rendering."""
        lines = []
        for para in text.split("\n"):
            cur = ""
            for wd in para.split():
                test = (cur + " " + wd).strip()
                if not cur or font.getlength(test) + stroke * 2 <= max_w:
                    cur = test
                else:
                    lines.append(cur)
                    cur = wd
            lines.append(cur)
        return "\n".join(lines)

    def _render_fx_pil(self, text, fam, size, bold, main_col, wrap_w=None):
        """Render title text with outline + glow into a transparent RGBA image."""
        font_path = _resolve_font_file(fam, bold)
        if not font_path:
            return None
        try:
            font = ImageFont.truetype(font_path, size)
        except Exception:
            return None
        out_on   = self.reveal_outline_var.get()
        out_size = max(1, self.reveal_outline_size_var.get()) if out_on else 0
        out_col  = self.reveal_outline_col_var.get() or "#000000"
        glow_on  = self.reveal_glow_var.get()
        gsize    = max(1, self.reveal_glow_size_var.get()) if glow_on else 0
        glow_col = self.reveal_glow_col_var.get() or main_col

        if wrap_w:
            text = self._wrap_text_pil(text, font, int(wrap_w), out_size)

        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        l, t, r, b = probe.multiline_textbbox((0, 0), text, font=font,
                                              stroke_width=out_size, align="center")
        pad = gsize * 3 + 4
        w = int(r - l) + pad * 2
        h = int(b - t) + pad * 2
        origin = (pad - int(l), pad - int(t))

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if glow_on:
            glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            gd.multiline_text(origin, text, font=font, fill=glow_col,
                              stroke_width=out_size, stroke_fill=glow_col,
                              align="center")
            glow = glow.filter(ImageFilter.GaussianBlur(radius=max(2, gsize)))
            a = glow.getchannel("A").point(lambda v: min(255, int(v * 2.5)))
            glow.putalpha(a)
            img.alpha_composite(glow)
        d = ImageDraw.Draw(img)
        d.multiline_text(origin, text, font=font, fill=main_col,
                         stroke_width=out_size, stroke_fill=out_col,
                         align="center")
        return img

    def _update_fx_image(self, cv, fx: dict, alpha: float, main_col: str):
        """Refresh an image-mode fx item: re-render if inputs changed, then
        apply the fade by scaling the image's alpha channel."""
        text = cv.itemcget(fx["main"], "text")
        if not text.strip():
            cv.itemconfigure(fx["img"], image="")
            return
        sig = (text, main_col,
               self.reveal_outline_var.get(), self.reveal_outline_size_var.get(),
               self.reveal_outline_col_var.get(),
               self.reveal_glow_var.get(), self.reveal_glow_size_var.get(),
               self.reveal_glow_col_var.get())
        if fx["base"] is None or fx["sig"] != sig:
            fam, size, bold = fx["font"]
            fx["base"] = self._render_fx_pil(text, fam, size, bold,
                                             main_col, fx["wrap"])
            fx["sig"] = sig
        if fx["base"] is None:
            raise RuntimeError("fx image render failed")
        if alpha <= 0.001:
            cv.itemconfigure(fx["img"], image="")
            return
        if alpha >= 0.999:
            frame = fx["base"]
        else:
            frame = fx["base"].copy()
            a = frame.getchannel("A").point(lambda v: int(v * alpha))
            frame.putalpha(a)
        photo = ImageTk.PhotoImage(frame)
        cv._fx_photos[fx["img"]] = photo   # keep a live reference
        cv.itemconfigure(fx["img"], image=photo)

    def _update_fx_text(self, cv, fx: dict, alpha: float,
                         main_col: str, bg: str = "#000000", sub=False):
        """Fade all layers of an fx text dict toward their target colours."""
        if "img" in fx:
            try:
                self._update_fx_image(cv, fx, alpha, main_col)
                return
            except Exception:
                # Degrade to plain coloured text (no effects) if rendering fails
                try:
                    cv.itemconfigure(fx["img"], image="")
                except tk.TclError:
                    pass
        cv.itemconfigure(fx["main"],
                         fill=_lerp_colour(bg, main_col, alpha))
        if fx["outline"]:
            out_col = (self.reveal_sub_outline_col_var.get() if sub
                       else self.reveal_outline_col_var.get()) or "#000000"
            for oid in fx["outline"]:
                cv.itemconfigure(oid, fill=_lerp_colour(bg, out_col, alpha))
        if fx["glow"]:
            glow_col = self.reveal_glow_col_var.get() or main_col
            for gid, intensity in fx["glow"]:
                cv.itemconfigure(gid,
                    fill=_lerp_colour(bg, glow_col, alpha * intensity))

    def _update_colour_swatches(self):
        """Sync the colour swatch labels to current var values."""
        try:
            tc = self.reveal_title_col_var.get() or self._t["fg_accent1"]
            sc = self.reveal_sub_col_var.get()   or self._t["fg_sub"]
            self.reveal_title_swatch.configure(bg=tc)
            self.reveal_sub_swatch.configure(bg=sc)
        except Exception:
            pass
        try:
            oc = self.reveal_outline_col_var.get() or "#000000"
            self.reveal_outline_swatch.configure(bg=oc)
        except Exception:
            pass
        try:
            soc = self.reveal_sub_outline_col_var.get() or "#000000"
            self.reveal_sub_outline_swatch.configure(bg=soc)
        except Exception:
            pass
        try:
            gc = self.reveal_glow_col_var.get() or self._reveal_title_col()
            self.reveal_glow_swatch.configure(bg=gc)
        except Exception:
            pass

    def _pick_reveal_colour(self, which: str):
        from tkinter.colorchooser import askcolor
        var = {"title":       self.reveal_title_col_var,
               "sub":         self.reveal_sub_col_var,
               "outline":     self.reveal_outline_col_var,
               "glow":        self.reveal_glow_col_var,
               "sub_outline": self.reveal_sub_outline_col_var}.get(which)
        if var is None:
            return
        colour = askcolor(color=var.get() or None, title="Choose colour")[1]
        if colour:
            var.set(colour)
            self._update_colour_swatches()
            self._save_settings()
            self._refresh_reveal_preview()

    def _reset_reveal_colour(self, which: str):
        var = {"title":   self.reveal_title_col_var,
               "sub":     self.reveal_sub_col_var}.get(which)
        if var is not None:
            var.set("")
        self._update_colour_swatches()
        self._save_settings()
        self._refresh_reveal_preview()

    def _refresh_reveal_preview(self):
        """Redraw the live preview canvas to reflect current settings."""
        # Grey out title colour controls for typing (type colours are fixed)
        is_typing = self.reveal_preview_type_var.get() == "typing"
        is_pokemon = self.reveal_preview_type_var.get() == "pokemon"
        try:
            state = "disabled" if is_typing else "normal"
            self.reveal_title_swatch.configure(state=state,
                bg=self._t["bg_panel"] if is_typing else (self.reveal_title_col_var.get() or self._t["fg_accent1"]))
            for w in self.reveal_title_swatch.master.winfo_children():
                try: w.configure(state=state)
                except Exception: pass
        except Exception:
            pass
        # Show Pokémon sprite controls only when Pokémon preview is active
        try:
            if is_pokemon:
                self._sprite_inline.grid()
            else:
                self._sprite_inline.grid_remove()
        except Exception:
            pass
        try:
            cv = self._preview_canvas
        except AttributeError:
            return
        if not cv.winfo_exists():
            return
        cv.update_idletasks()
        W = cv.winfo_width()
        H = cv.winfo_height()
        if W < 10 or H < 10:
            return

        cv.delete("all")
        cv._fx_photos = {}   # drop image refs from the previous preview render
        t      = self._t
        BLACK  = "#000000"
        fam    = self.reveal_font_var.get()
        scale  = min(W / 1320, H / 820)
        base   = max(10, int(self.reveal_font_size_var.get() * scale))
        title_col = self.reveal_title_col_var.get() or t["fg_accent1"]
        sub_col   = self.reveal_sub_col_var.get()   or t["fg_sub"]
        acc2_col  = t["fg_accent2"]
        bg_col    = t["bg_root"]

        # Background
        ptype = self.reveal_preview_type_var.get()
        bg_key = ptype if self.reveal_bg_per_var.get() else "global"
        bg_img = self._get_reveal_bg_pil_raw(bg_key, W, H)
        if bg_img is None and self.reveal_bg_per_var.get():
            bg_img = self._get_reveal_bg_pil_raw("global", W, H)
        if bg_img:
            try:
                self._preview_bg_photo = ImageTk.PhotoImage(bg_img)
                cv.create_image(0, 0, anchor="nw", image=self._preview_bg_photo)
            except Exception:
                cv.configure(bg=bg_col)
        else:
            cv.configure(bg=bg_col)

        sz_counter = max(7,  int(11 * scale))
        sz_sub     = max(7,  int(10 * scale))
        sz_name    = base
        sz_effect  = max(7,  int(13 * scale))

        if ptype == "abilities":
            self._preview_fx_text(cv, W//2, int(H*0.09), sub_col, bg_col, sub=True,
                                  text="1  /  3", font=(fam, sz_counter, "bold"), anchor="center")
            self._preview_fx_text(cv, W//2, int(H*0.45), title_col, bg_col,
                                  text="Intimidate",
                                  font=(fam, sz_name, "bold"), anchor="center",
                                  width=int(W*0.80), justify="center")
            dw = int(W * 0.42)
            cv.create_line(W//2 - dw//2, int(H*0.57), W//2 + dw//2, int(H*0.57),
                           fill=acc2_col, width=max(1, int(2*scale)))
            self._preview_fx_text(cv, W//2, int(H*0.67), t["fg_main"], bg_col, sub=True,
                                  text="Lowers the foe's Attack one stage upon\nentering battle.",
                                  font=(fam, sz_effect),
                                  anchor="center", width=int(W*0.72), justify="center")

        elif ptype == "typing":
            cv.create_text(W//2, int(H*0.09),
                           text="Your Typing", fill=sub_col,
                           font=(fam, sz_counter), anchor="center")
            dw = int(W * 0.42)
            cv.create_line(W//2 - dw//2, int(H*0.18), W//2 + dw//2, int(H*0.18),
                           fill=acc2_col, width=max(1, int(2*scale)))
            for i, (typ, col) in enumerate([("Fire", "#f08030"), ("Flying", "#a890f0")]):
                yp = 0.32 + i * 0.20
                self._preview_fx_text(cv, W//2, int(H*yp), col, bg_col,
                                      text=typ, font=(fam, sz_name, "bold"), anchor="center")

        elif ptype == "stats":
            self._preview_fx_text(cv, W//2, int(H*0.09), sub_col, bg_col, sub=True,
                                  text="Jolly Nature", font=(fam, sz_counter, "bold"), anchor="center")
            for i, (stat, val, col) in enumerate([
                ("HP",  252, title_col), ("ATK", 31,  "#69db7c"),
                ("DEF", 252, title_col), ("SPA", 0,   title_col),
                ("SPD", 4,   title_col), ("SPE", 31,  "#69db7c"),
            ]):
                yp = 0.25 + i * 0.10
                self._preview_fx_text(cv, int(W*0.35), int(H*yp), sub_col, bg_col, sub=True,
                                      text=stat, font=(fam, sz_sub), anchor="e")
                self._preview_fx_text(cv, int(W*0.38), int(H*yp), col, bg_col,
                                      text=str(val), font=(fam, sz_sub, "bold"), anchor="w")

        elif ptype == "pokemon":
            self._preview_fx_text(cv, W//2, int(H*0.09), sub_col, bg_col, sub=True,
                                  text="2  /  3", font=(fam, sz_counter, "bold"), anchor="center")
            self._preview_fx_text(cv, W//2, int(H*0.62), sub_col, bg_col, sub=True,
                                  text="#0006", font=("Consolas", sz_sub), anchor="center")
            self._preview_fx_text(cv, W//2, int(H*0.71), title_col, bg_col,
                                  text="Charizard",
                                  font=(fam, sz_name, "bold"), anchor="center",
                                  width=int(W*0.80), justify="center")
            # Placeholder sprite box
            bsz = max(40, int(80 * scale))
            cx, cy = W//2, int(H*0.40)
            cv.create_rectangle(cx-bsz, cy-bsz, cx+bsz, cy+bsz,
                                 outline=sub_col, width=max(1, int(2*scale)),
                                 dash=(4, 4))
            cv.create_text(cx, cy, text="🔥", font=("Segoe UI", max(16, bsz//2)),
                           anchor="center")

    def _preview_fx_text(self, cv, x, y, colour: str, bg: str,
                          sub: bool = False, **kwargs):
        """Create fx text and immediately colour it at alpha=1.0 for static previews."""
        fx = self._create_fx_text(cv, x, y, fill=colour, sub=sub, **kwargs)
        self._update_fx_text(cv, fx, 1.0, colour, bg, sub=sub)
        return fx

    def _filter_fonts(self, event=None):
        """Filter font combobox list as user types."""
        query = self.reveal_font_var.get().lower()
        from tkinter.font import families as _font_families
        all_fonts = sorted(set(_font_families()), key=str.lower)
        filtered  = [f for f in all_fonts if query in f.lower()]
        self.font_cb["values"] = filtered or all_fonts

    def _update_font_preview(self):
        """Update font preview — delegates to the live preview canvas."""
        self._refresh_reveal_preview()

    def _on_per_reveal_toggled(self):
        show = self.reveal_bg_per_var.get()
        for w in self._per_reveal_frame.winfo_children():
            try:
                if show: w.grid()
                else:    w.grid_remove()
            except Exception:
                pass
        self._save_settings()

    def _on_maximised_toggled(self):
        state = "disabled" if self.win_maximised_var.get() else "normal"
        try:
            self.win_w_spin.configure(state=state)
            self.win_h_spin.configure(state=state)
        except AttributeError:
            pass
        self._save_settings()

    def _pick_reveal_bg(self, key: str):
        path = filedialog.askopenfilename(
            title="Choose background image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp *.gif"),
                       ("All files", "*.*")])
        if not path:
            return
        var_map = {
            "global":    self.reveal_bg_global_var,
            "abilities": self.reveal_bg_abilities_var,
            "typing":    self.reveal_bg_typing_var,
            "stats":     self.reveal_bg_stats_var,
            "nature":    self.reveal_bg_nature_var,
            "pokemon":   self.reveal_bg_pokemon_var,
        }
        if key in var_map:
            var_map[key].set(path)
            self._reveal_bg_photos.pop(path, None)  # invalidate cache
        self._save_settings()

    def _clear_reveal_bg(self, key: str):
        var_map = {
            "global":    self.reveal_bg_global_var,
            "abilities": self.reveal_bg_abilities_var,
            "typing":    self.reveal_bg_typing_var,
            "stats":     self.reveal_bg_stats_var,
            "nature":    self.reveal_bg_nature_var,
            "pokemon":   self.reveal_bg_pokemon_var,
        }
        if key in var_map:
            var_map[key].set("")
        self._save_settings()

    def _get_reveal_bg_photo(self, key: str, W: int, H: int):
        """Return a pre-rendered ImageTk.PhotoImage for the given reveal key, or None."""
        if not _PIL_OK:
            return None
        var_map = {
            "abilities": self.reveal_bg_abilities_var,
            "typing":    self.reveal_bg_typing_var,
            "stats":     self.reveal_bg_stats_var,
            "nature":    self.reveal_bg_nature_var,
            "pokemon":   self.reveal_bg_pokemon_var,
        }
        path = var_map.get(key, tk.StringVar()).get() or self.reveal_bg_global_var.get()
        if not path or not os.path.exists(path):
            return None
        cache_key = (path, W, H, self.reveal_bg_stretch_var.get())
        if cache_key in self._reveal_bg_photos:
            return self._reveal_bg_photos[cache_key]
        try:
            img  = Image.open(path).convert("RGB")
            mode = self.reveal_bg_stretch_var.get()
            if mode == "Fill":
                img = img.resize((W, H), Image.LANCZOS)
            elif mode == "Fit":
                img.thumbnail((W, H), Image.LANCZOS)
                bg  = Image.new("RGB", (W, H), (0, 0, 0))
                ox  = (W - img.width)  // 2
                oy  = (H - img.height) // 2
                bg.paste(img, (ox, oy))
                img = bg
            else:  # Tile
                tiled = Image.new("RGB", (W, H))
                for y in range(0, H, img.height):
                    for x in range(0, W, img.width):
                        tiled.paste(img, (x, y))
                img = tiled
            photo = ImageTk.PhotoImage(img)
            self._reveal_bg_photos[cache_key] = photo
            return photo
        except Exception:
            return None

    def _reveal_title_col(self) -> str:
        """Return the effective title colour for reveals (custom or theme fg_accent1)."""
        c = self.reveal_title_col_var.get()
        return c if c else self._t["fg_accent1"]

    def _reveal_sub_col(self) -> str:
        """Return the effective secondary colour for reveals (custom or theme fg_sub)."""
        c = self.reveal_sub_col_var.get()
        return c if c else self._t["fg_sub"]

    def _get_reveal_fade(self):
        """Return (STEPS, MS) for the current fade speed setting."""
        return {"Slow": (30, 20), "Fast": (10, 10)}.get(
            self.reveal_fade_var.get(), (20, 16))

    def _get_reveal_bg_pil_raw(self, key: str, W: int, H: int):
        """Return the reveal background as a PIL RGB Image (no caching), or None.
        Safe to call from a background thread (no tkinter object creation)."""
        if not _PIL_OK:
            return None
        var_map = {
            "abilities": self.reveal_bg_abilities_var,
            "typing":    self.reveal_bg_typing_var,
            "stats":     self.reveal_bg_stats_var,
            "nature":    self.reveal_bg_nature_var,
            "pokemon":   self.reveal_bg_pokemon_var,
        }
        path = var_map.get(key, tk.StringVar()).get() or self.reveal_bg_global_var.get()
        if not path or not os.path.exists(path):
            return None
        try:
            img  = Image.open(path).convert("RGB")
            mode = self.reveal_bg_stretch_var.get()
            if mode == "Fill":
                img = img.resize((W, H), Image.LANCZOS)
            elif mode == "Fit":
                img.thumbnail((W, H), Image.LANCZOS)
                bg  = Image.new("RGB", (W, H), (0, 0, 0))
                ox  = (W - img.width)  // 2
                oy  = (H - img.height) // 2
                bg.paste(img, (ox, oy))
                img = bg
            else:  # Tile
                tiled = Image.new("RGB", (W, H))
                for y in range(0, H, img.height):
                    for x in range(0, W, img.width):
                        tiled.paste(img, (x, y))
                img = tiled
            return img
        except Exception:
            return None

    def _export_settings(self):
        path = filedialog.asksaveasfilename(
            title="Export Settings",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # Strip banned abilities from settings export
            data.pop("banned_abilities", None)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo(APP_TITLE, f"Settings exported to:\n{path}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Export failed:\n{e}")

    def _export_bans(self):
        path = filedialog.asksaveasfilename(
            title="Export Ban List",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"banned_abilities": sorted(self.banned_abilities)},
                          f, ensure_ascii=False, indent=2)
            messagebox.showinfo(APP_TITLE,
                f"Exported {len(self.banned_abilities)} banned abilities to:\n{path}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Export failed:\n{e}")

    def _import_settings(self):
        path = filedialog.askopenfilename(
            title="Import Settings",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Write to settings file (preserving current bans) then reload
            current_bans = sorted(self.banned_abilities)
            data["banned_abilities"] = current_bans
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._load_settings()
            self._update_status()
            self._refresh_ability_views()
            messagebox.showinfo(APP_TITLE, "Settings imported successfully.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Import failed:\n{e}")

    def _import_bans(self):
        path = filedialog.askopenfilename(
            title="Import Ban List",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            bans = set(data.get("banned_abilities", []))
            if not messagebox.askyesno(APP_TITLE,
                    f"This will replace your current {len(self.banned_abilities)} banned "
                    f"abilities with {len(bans)} from the imported file.\n\nContinue?"):
                return
            self.banned_abilities = bans
            self._save_settings()
            self._update_status()
            self._refresh_ability_views()
            messagebox.showinfo(APP_TITLE,
                f"Imported {len(bans)} banned abilities.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Import failed:\n{e}")

    # ── Profile card ────────────────────────────────────────────────────────────

    def _build_profile_card(self, parent):
        t    = self._t
        card = self._r(tk.Frame(parent, pady=6, padx=10), "profile_card")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self._avatar_size  = 56
        self.avatar_canvas = tk.Canvas(card, width=56, height=56,
                                       highlightthickness=0, cursor="hand2")
        self.avatar_canvas.configure(bg=t["profile_bg"])
        self.avatar_canvas.pack(side="left", padx=(0, 14))
        self.avatar_canvas.bind("<Button-1>", lambda _: self._pick_avatar())

        text_col = self._r(tk.Frame(card), "profile_card")
        text_col.pack(side="left", fill="y", expand=False)

        self.welcome_var = tk.StringVar(value="Welcome Back!")
        self.welcome_lbl = self._r(
            tk.Label(text_col, textvariable=self.welcome_var,
                     font=("Segoe UI", 15, "bold"), anchor="w"),
            "lbl_welcome")
        self.welcome_lbl.pack(anchor="w")
        self.welcome_lbl.bind("<Button-1>", lambda _: self._edit_name())
        self.welcome_lbl.configure(cursor="hand2")

        self._r(
            tk.Label(text_col,
                     text="Click your avatar to change it  •  Click your name to edit",
                     font=("Segoe UI", 8), anchor="w"),
            "lbl_welcome_sub").pack(anchor="w")

        self._draw_avatar()

    def _build_results_panel(self, parent):
        pf = self._r(
            tk.LabelFrame(parent, text=" ✨  Rolled Abilities ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_result")
        pf.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        pf.columnconfigure(0, weight=3)
        pf.rowconfigure(0, weight=1)

        self.result_text = self._r(
            tk.Text(pf, wrap="word", relief="flat", font=("Consolas", 10), padx=8, pady=6),
            "result_text")
        self.result_text.grid(row=0, column=0, sticky="nsew")
        for tag, fnt in [
            ("header",       ("Segoe UI",  10, "bold")),
            ("ability_name", ("Consolas",  11, "bold")),
            ("gen_tag",      ("Consolas",   9)),
            ("effect_text",  ("Consolas",  10)),
            ("divider",      ("Consolas",  10)),
            ("meta",         ("Consolas",   9, "italic")),
        ]:
            self.result_text.tag_configure(tag, font=fnt)

        scr = self._r(ttk.Scrollbar(pf, orient="vertical", command=self.result_text.yview),
                      "scrollbar")
        scr.grid(row=0, column=1, sticky="ns")
        self.result_text.configure(yscrollcommand=scr.set)

        self.result_text.configure(state="normal")
        self.result_text.insert("1.0",
            "Press ⚡ Roll Abilities to get started!\n\n"
            "Select your game, adjust the settings on the left,\n"
            "then roll to see your random abilities here.", "meta")
        self.result_text.configure(state="disabled")

        side = self._r(tk.Frame(pf, padx=6), "bg_panel")
        side.grid(row=0, column=2, sticky="nsew")
        side.rowconfigure(1, weight=1)

        self._r(tk.Label(side, text="Select to act on:", font=("Segoe UI", 8)),
                "lbl_sub").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.rolled_listbox = self._r(
            tk.Listbox(side, relief="flat", font=("Segoe UI", 9),
                       selectmode=tk.SINGLE, activestyle="none",
                       width=20, exportselection=False),
            "listbox")
        self.rolled_listbox.grid(row=1, column=0, sticky="nsew")
        scr2 = self._r(ttk.Scrollbar(side, orient="vertical", command=self.rolled_listbox.yview),
                       "scrollbar")
        scr2.grid(row=1, column=1, sticky="ns")
        self.rolled_listbox.configure(yscrollcommand=scr2.set)

        bf = self._r(tk.Frame(side), "bg_panel")
        bf.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        bf.columnconfigure(0, weight=1)
        for row, (text, cmd, role) in enumerate([
            ("🚫  Ban",            self._ban_selected,    "btn_banned"),
            ("🎲  Reroll",         self._reroll_selected, "btn_accent2"),
            ("🚫🎲  Ban & Reroll", self._ban_and_reroll,  "btn_accent1"),
        ]):
            pady = (0, 3) if row < 2 else 0
            self._r(
                tk.Button(bf, text=text, command=cmd, relief="flat",
                          font=("Segoe UI", 9, "bold"), padx=6, pady=5, cursor="hand2"),
                role).grid(row=row, column=0, sticky="ew", pady=pady)

    def _build_ability_browser(self, parent):
        pf = self._r(
            tk.LabelFrame(parent, text=" 📖  Ability Browser ",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=10, pady=8),
            "lf_accent1")
        pf.grid(row=2, column=0, sticky="nsew")
        pf.columnconfigure(0, weight=1, minsize=200)
        pf.columnconfigure(1, weight=2)
        pf.rowconfigure(1, weight=1)

        sf = self._r(tk.Frame(pf), "bg_panel")
        sf.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        sf.columnconfigure(1, weight=1)
        self._r(tk.Label(sf, text="🔍 Search:", font=("Segoe UI", 9)),
                "lbl_main").grid(row=0, column=0, sticky="w")
        self._r(
            tk.Entry(sf, textvariable=self.search_var, relief="flat", font=("Segoe UI", 10)),
            "field_search").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.search_var.trace_add("write", lambda *_: self._refresh_ability_views())

        lf = self._r(tk.Frame(pf), "bg_panel")
        lf.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)

        self.ability_listbox = self._r(
            tk.Listbox(lf, relief="flat", font=("Segoe UI", 9),
                       exportselection=False, activestyle="none"),
            "listbox")
        self.ability_listbox.grid(row=0, column=0, sticky="nsew")
        self.ability_listbox.bind("<<ListboxSelect>>", self.show_selected_ability)
        scr = self._r(ttk.Scrollbar(lf, orient="vertical", command=self.ability_listbox.yview),
                      "scrollbar")
        scr.grid(row=0, column=1, sticky="ns")
        self.ability_listbox.configure(yscrollcommand=scr.set)

        df = self._r(tk.Frame(pf), "bg_panel")
        df.grid(row=1, column=1, sticky="nsew")
        df.columnconfigure(0, weight=1)
        df.rowconfigure(1, weight=1)

        self.detail_title_var = tk.StringVar(value="← Select an ability")
        self._r(
            tk.Label(df, textvariable=self.detail_title_var,
                     font=("Segoe UI", 14, "bold"), anchor="w"),
            "lbl_detail_title").grid(row=0, column=0, sticky="ew")

        self.detail_text = self._r(
            tk.Text(df, wrap="word", relief="flat", font=("Segoe UI", 10),
                    padx=8, pady=6, height=6),
            "detail_text")
        self.detail_text.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        for tag, fnt in [
            ("key",          ("Segoe UI",  9, "bold")),
            ("val",          ("Segoe UI", 10)),
            ("banned_val",   ("Segoe UI", 10, "bold")),
            ("effect_label", ("Segoe UI", 10, "bold")),
        ]:
            self.detail_text.tag_configure(tag, font=fnt)

        dt_scr = self._r(
            ttk.Scrollbar(df, orient="vertical", command=self.detail_text.yview), "scrollbar")
        dt_scr.grid(row=1, column=1, sticky="ns", pady=(6, 6))
        self.detail_text.configure(yscrollcommand=dt_scr.set)

        br = self._r(tk.Frame(df), "bg_panel")
        br.grid(row=2, column=0, sticky="w")
        for text, cmd, role in [
            ("🚫 Ban (Cringe)", self.ban_selected_ability,   "btn_banned"),
            ("✅ Unban",        self.unban_selected_ability, "btn_unban"),
        ]:
            self._r(
                tk.Button(br, text=text, command=cmd, relief="flat",
                          font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2"),
                role).pack(side="left", padx=(0, 8))

    # ══════════════════════════════════════════════════════════════════════════
    #  Tab switching — right panel
    # ══════════════════════════════════════════════════════════════════════════

    def _switch_tab(self, key):
        self._active_tab = key
        # Left panels
        for k, f in self._tab_frames.items():
            if "_right" in k:
                continue
            if k == key:
                f.grid()
            else:
                f.grid_remove()
        # Right panels
        for k, f in self._tab_frames.items():
            if "_right" not in k:
                continue
            if k == key + "_right":
                f.grid()
            else:
                f.grid_remove()
        self._style_tab_buttons()

    # ══════════════════════════════════════════════════════════════════════════
    #  Avatar / profile
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_avatar(self):
        t    = self._t
        size = self._avatar_size
        self.avatar_canvas.configure(bg=t["profile_bg"])
        self.avatar_canvas.delete("all")
        if _PIL_OK and os.path.exists(AVATAR_FILE):
            try:
                img = Image.open(AVATAR_FILE).convert("RGBA").resize(
                    (size, size), Image.LANCZOS)
                self._avatar_photo = ImageTk.PhotoImage(img)
                self.avatar_canvas.create_image(0, 0, anchor="nw", image=self._avatar_photo)
                return
            except Exception:
                pass
        self.avatar_canvas.create_rectangle(
            0, 0, size, size, fill=_lighten(t["profile_bg"], 30), outline="")
        self.avatar_canvas.create_text(
            size // 2, size // 2, text="📷", font=("Segoe UI", 18), fill=t["fg_sub"])

    def _pick_avatar(self):
        path = filedialog.askopenfilename(
            title="Choose profile picture",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("All files", "*.*")])
        if not path:
            return
        if not _PIL_OK:
            messagebox.showwarning(APP_TITLE,
                "Pillow is not installed.\n"
                "Install it with:  pip install Pillow\n"
                "Then restart the app to use custom avatars.")
            return
        try:
            img  = Image.open(path).convert("RGBA")
            w, h = img.size
            side = min(w, h)
            img  = img.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
            img.save(AVATAR_FILE, "PNG")
            self._draw_avatar()
            self._save_settings()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not load image:\n{e}")

    def _edit_name(self):
        t   = self._t
        dlg = tk.Toplevel(self.root)
        dlg.title("Edit name")
        dlg.resizable(False, False)
        dlg.configure(bg=t["bg_panel"])
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="Your name:", bg=t["bg_panel"], fg=t["fg_main"],
                 font=("Segoe UI", 10)).grid(row=0, column=0, padx=14, pady=(14, 4), sticky="w")
        name_var = tk.StringVar(value=self._user_name)
        entry = tk.Entry(dlg, textvariable=name_var, bg=t["bg_field"], fg=t["fg_main"],
                         insertbackground=t["fg_main"], relief="flat",
                         font=("Segoe UI", 12), width=22,
                         highlightbackground=t["fg_accent1"], highlightthickness=1)
        entry.grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 10), sticky="ew")
        entry.focus_set()
        entry.select_range(0, tk.END)

        def save(_e=None):
            name = name_var.get().strip()
            if name:
                self._user_name = name
                self.welcome_var.set(f"Welcome Back, {name}!")
                self._save_settings()
            dlg.destroy()

        entry.bind("<Return>", save)
        tk.Button(dlg, text="Save", command=save,
                  bg=t["roll_bg"], fg=t["fg_main"], relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=14, pady=5,
                  activebackground=t["roll_hover"], cursor="hand2"
                  ).grid(row=2, column=0, columnspan=2, padx=14, pady=(0, 14), sticky="ew")

        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width()  - dlg.winfo_reqwidth())  // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_reqheight()) // 2
        dlg.geometry(f"+{x}+{y}")

    def _maybe_first_launch(self):
        if self._user_name:
            return
        t   = self._t
        dlg = tk.Toplevel(self.root)
        dlg.title("Welcome! 👋")
        dlg.resizable(False, False)
        dlg.configure(bg=t["bg_panel"])
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="Welcome to\nThen We Roll!",
                 bg=t["bg_panel"], fg=t["fg_accent1"],
                 font=("Segoe UI", 14, "bold"), justify="center"
                 ).grid(row=0, column=0, columnspan=2, padx=24, pady=(18, 6))
        tk.Label(dlg, text="What's your name, Trainer?",
                 bg=t["bg_panel"], fg=t["fg_main"], font=("Segoe UI", 10)
                 ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 4))

        name_var = tk.StringVar()
        entry = tk.Entry(dlg, textvariable=name_var, bg=t["bg_field"], fg=t["fg_main"],
                         insertbackground=t["fg_main"], relief="flat",
                         font=("Segoe UI", 12), width=22,
                         highlightbackground=t["fg_accent1"], highlightthickness=1)
        entry.grid(row=2, column=0, columnspan=2, padx=24, pady=(0, 10), sticky="ew")
        entry.focus_set()

        avatar_path_var = tk.StringVar()

        def pick_pic():
            if not _PIL_OK:
                messagebox.showwarning(APP_TITLE,
                    "Pillow is not installed.\n"
                    "Install it with:  pip install Pillow\n"
                    "Custom avatars need Pillow – you can skip for now.", parent=dlg)
                return
            path = filedialog.askopenfilename(
                parent=dlg, title="Choose a profile picture",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                           ("All files", "*.*")])
            if path:
                avatar_path_var.set(path)
                pic_btn.configure(text="✅ Picture chosen!")

        pic_btn = tk.Button(dlg, text="📷  Choose profile picture  (optional)",
                            command=pick_pic,
                            bg=t["bg_field"], fg=t["fg_accent2"], relief="flat",
                            font=("Segoe UI", 9), padx=10, pady=5, cursor="hand2",
                            activebackground=t["fg_accent2"], activeforeground=t["bg_root"])
        pic_btn.grid(row=3, column=0, columnspan=2, padx=24, pady=(0, 14), sticky="ew")

        def confirm(_e=None):
            name = name_var.get().strip() or "Trainer"
            self._user_name = name
            self.welcome_var.set(f"Welcome, {name}!")
            if avatar_path_var.get() and _PIL_OK:
                try:
                    img  = Image.open(avatar_path_var.get()).convert("RGBA")
                    w, h = img.size
                    side = min(w, h)
                    img  = img.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
                    img.save(AVATAR_FILE, "PNG")
                except Exception:
                    pass
            self._draw_avatar()
            self._save_settings()
            dlg.destroy()

        entry.bind("<Return>", confirm)
        tk.Button(dlg, text="Let's go! ⚡", command=confirm,
                  bg=t["roll_bg"], fg=t["fg_main"], relief="flat",
                  font=("Segoe UI", 11, "bold"), padx=14, pady=8, cursor="hand2",
                  activebackground=t["roll_hover"]
                  ).grid(row=4, column=0, columnspan=2, padx=24, pady=(0, 18), sticky="ew")

        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width()  - dlg.winfo_reqwidth())  // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_reqheight()) // 2
        dlg.geometry(f"+{x}+{y}")

    # ══════════════════════════════════════════════════════════════════════════
    #  Data loading / API update
    # ══════════════════════════════════════════════════════════════════════════

    def _load_abilities(self):
        loaded = load_abilities_json()
        if loaded:
            self.abilities = loaded
            self.status_var.set(f"Loaded {len(self.abilities)} abilities from cache.")
        else:
            self.status_var.set("No ability cache found — use 'Update from PokéAPI' to fetch.")

    def _start_api_update(self):
        if not messagebox.askyesno(APP_TITLE,
                "This will fetch all abilities from PokéAPI and overwrite "
                "the currently saved ability data.\n"
                "It may take 1–3 minutes depending on your connection.\n\n"
                "Your ban list and settings are not affected.\n\nContinue?",
                icon="warning"):
            return
        self.update_btn.configure(state="disabled", text="⏳ Updating…")
        self.status_var.set("Connecting to PokéAPI…")

        def worker():
            try:
                def progress(cur, tot, name):
                    pct = int(cur / tot * 100)
                    self.root.after(0, lambda: self.status_var.set(
                        f"Fetching from PokéAPI… {cur}/{tot}  ({pct}%)  — {name}"))
                abilities = fetch_all_abilities(progress_cb=progress)
                save_abilities_json(abilities)
                self.root.after(0, lambda: self._on_update_complete(abilities))
            except Exception as e:
                self.root.after(0, lambda: self._on_update_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_complete(self, abilities):
        self.abilities = abilities
        self.update_btn.configure(state="normal", text="🔄 Update from PokéAPI")
        self._update_status()
        self._refresh_ability_views()
        messagebox.showinfo(APP_TITLE,
            f"Updated! {len(abilities)} abilities fetched and saved to data/abilities.json")

    def _on_update_error(self, msg):
        self.update_btn.configure(state="normal", text="🔄 Update from PokéAPI")
        self.status_var.set(f"Update failed: {msg}")
        messagebox.showerror(APP_TITLE, f"Failed to fetch from PokéAPI:\n{msg}")

    # ══════════════════════════════════════════════════════════════════════════
    #  Filters / settings
    # ══════════════════════════════════════════════════════════════════════════

    def _normalize_name(self, name: str) -> str:
        return name.strip().lower().replace("_", "-").replace(" ", "-")

    def _display_name(self, internal: str) -> str:
        for a in self.abilities:
            if a["name"] == internal:
                return a["display_name"]
        return internal.replace("-", " ").title()

    def _selected_generations(self) -> set:
        return {g for g, v in self.generation_vars.items() if v.get()}

    def _get_visible_pool(self) -> list:
        sel  = self._selected_generations()
        pool = [a for a in self.abilities if a.get("generation") in sel]
        if self.main_series_only_var.get():
            pool = [a for a in pool if a.get("is_main_series", True)]
        if self.game_var.get() != "Pokémon Champions":
            pool = [a for a in pool if a["name"] not in CHAMPIONS_EXCLUSIVE]
        return pool

    def _update_status(self):
        # Ability counts are no longer shown in the header — the status label
        # is kept for transient messages (PokéAPI fetch progress, updates).
        self.status_var.set("")

    def _on_filter_changed(self):
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()

    def select_all_generations(self):
        for g in GENERATIONS: self.generation_vars[g].set(True)
        self.game_var.set("Custom")
        self._on_filter_changed()

    def clear_all_generations(self):
        for g in GENERATIONS: self.generation_vars[g].set(False)
        self.game_var.set("Custom")
        self._on_filter_changed()

    def _on_game_selected(self, _event=None):
        max_gen = GAME_PRESETS.get(self.game_var.get())
        if max_gen is None:
            return
        max_idx = GEN_ORDER[max_gen]
        for gen in GENERATIONS:
            self.generation_vars[gen].set(GEN_ORDER[gen] <= max_idx)
        self._on_filter_changed()

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            self._loading = False
            return
        self._loading = True
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                p = json.load(f)
        except Exception:
            self._loading = False
            return

        try:
            self._apply_loaded_settings(p)
        except Exception:
            import traceback
            try:
                with open(os.path.join(DATA_DIR, "settings_error.log"), "w") as lf:
                    lf.write(traceback.format_exc())
            except Exception:
                pass
        finally:
            self._loading = False

    def _apply_loaded_settings(self, p: dict):
        # Core settings — all safe, no UI calls
        self.banned_abilities = set(p.get("banned_abilities", []))
        self.include_banned_var.set(bool(p.get("include_banned", False)))
        self.main_series_only_var.set(bool(p.get("main_series_only", True)))
        game = p.get("selected_game", "Custom")
        self.game_var.set(game if game in GAME_PRESETS else "Custom")
        saved_gens = p.get("selected_generations")
        if saved_gens:
            saved_gens = set(saved_gens)
            for g in GENERATIONS:
                self.generation_vars[g].set(g in saved_gens)
        saved_theme = p.get("theme", THEME_NAMES[0])
        if saved_theme in THEMES:
            self._theme_name = saved_theme
            self._t = THEMES[saved_theme]
            self.theme_var.set(saved_theme)
            self._apply_theme()
        saved_name = p.get("user_name", "")
        if saved_name:
            self._user_name = saved_name
            self.welcome_var.set(f"Welcome Back, {saved_name}!")
            self._draw_avatar()

        # Typing settings
        for typ in TYPES:
            if typ in p.get("banned_types", []):
                self.type_ban_vars[typ].set(True)
        self.type_mode_var.set(p.get("type_mode", "Mixed"))
        self.type_split_var.set(int(p.get("type_split", 50)))
        self.tera_enabled_var.set(bool(p.get("tera_enabled", False)))
        self.tera_ban_sync_var.set(bool(p.get("tera_ban_sync", False)))
        self.tera_no_match_var.set(bool(p.get("tera_no_match", True)))

        # Stats settings
        self.stat_mode_var.set(p.get("stat_mode", "Free"))
        self.bst_var.set(int(p.get("bst_budget", 500)))
        self.bst_min_var.set(int(p.get("bst_min", 200)))
        self.bst_max_var.set(int(p.get("bst_max", 600)))
        self.use_stat_minmax_var.set(bool(p.get("use_stat_minmax", False)))
        for s in STAT_NAMES:
            self.stat_min_vars[s].set(int(p.get(f"stat_min_{s}", 1)))
            self.stat_max_vars[s].set(int(p.get(f"stat_max_{s}", 255)))

        # Settings tab vars
        self.reveal_font_var.set(p.get("reveal_font", "Segoe UI"))
        self.reveal_fade_var.set(p.get("reveal_fade", "Medium"))
        self.reveal_font_size_var.set(int(p.get("reveal_font_size", 44)))
        self.reveal_title_col_var.set(p.get("reveal_title_col", ""))
        self.reveal_sub_col_var.set(p.get("reveal_sub_col", ""))
        self.reveal_outline_var.set(bool(p.get("reveal_outline", True)))
        self.reveal_outline_size_var.set(int(p.get("reveal_outline_size", 2)))
        self.reveal_outline_col_var.set(p.get("reveal_outline_col", "#000000"))
        self.reveal_sub_outline_var.set(bool(p.get("reveal_sub_outline", True)))
        self.reveal_sub_outline_size_var.set(int(p.get("reveal_sub_outline_size", 1)))
        self.reveal_sub_outline_col_var.set(p.get("reveal_sub_outline_col", "#000000"))
        self.reveal_glow_var.set(bool(p.get("reveal_glow", False)))
        self.reveal_glow_size_var.set(int(p.get("reveal_glow_size", 4)))
        self.reveal_glow_col_var.set(p.get("reveal_glow_col", ""))
        self.reveal_pokemon_sprite_var.set(int(p.get("reveal_pokemon_sprite", 220)))
        self.pokemon_transfers_var.set(bool(p.get("pokemon_transfers", True)))
        self.pokemon_shiny_var.set(bool(p.get("pokemon_shiny", False)))
        self.pokemon_shiny_mode_var.set(p.get("pokemon_shiny_mode", "odds"))
        self.pokemon_shiny_odds_var.set(int(p.get("pokemon_shiny_odds", 8192)))
        self.pokemon_shiny_pct_var.set(p.get("pokemon_shiny_pct", "0.01"))
        self.reveal_bg_global_var.set(p.get("reveal_bg_global", ""))
        self.reveal_bg_stretch_var.set(p.get("reveal_bg_stretch", "Fit"))
        self.reveal_bg_per_var.set(bool(p.get("reveal_bg_per", False)))
        self.reveal_bg_abilities_var.set(p.get("reveal_bg_abilities", ""))
        self.reveal_bg_typing_var.set(p.get("reveal_bg_typing", ""))
        self.reveal_bg_stats_var.set(p.get("reveal_bg_stats", ""))
        self.reveal_bg_nature_var.set(p.get("reveal_bg_nature", ""))
        self.reveal_bg_pokemon_var.set(p.get("reveal_bg_pokemon", ""))
        self.reveal_typing_override_var.set(bool(p.get("reveal_typing_override", False)))
        self.win_width_var.set(int(p.get("win_width", 1320)))
        self.win_height_var.set(int(p.get("win_height", 820)))
        self.win_maximised_var.set(bool(p.get("win_maximised", False)))
        self.default_tab_var.set(p.get("default_tab", "abilities"))

        # UI-touching calls — each wrapped individually so one failure can't block the rest
        try: self._on_stat_mode_changed()
        except Exception: pass
        try: self._on_stat_minmax_toggled()
        except Exception: pass
        try: self._on_type_mode_changed()
        except Exception: pass
        try: self._on_per_reveal_toggled()
        except Exception: pass
        try: self._on_maximised_toggled()
        except Exception: pass
        try: self._update_font_preview()
        except Exception: pass
        try: self._update_colour_swatches()
        except Exception: pass
        try: self._refresh_reveal_preview()
        except Exception: pass

    def _save_settings(self):
        if self._loading:
            return

        def g(var, default):
            """Read a tk variable, falling back when the widget holds an
            invalid value (e.g. a spinbox that is currently empty)."""
            try:
                return var.get()
            except Exception:
                return default

        # Build the payload fully BEFORE touching the file, and write it to a
        # temp file swapped in atomically — a failure can never truncate the
        # existing settings.json (which previously wiped all settings).
        try:
            payload = {
                "banned_abilities":     sorted(self.banned_abilities),
                "include_banned":       g(self.include_banned_var, False),
                "main_series_only":     g(self.main_series_only_var, True),
                "selected_game":        g(self.game_var, "Custom"),
                "selected_generations": [gen for gen in GENERATIONS
                                        if g(self.generation_vars[gen], True)],
                "theme":                self._theme_name,
                "user_name":            self._user_name,
                "banned_types":         [t for t in TYPES
                                         if g(self.type_ban_vars[t], False)],
                "type_mode":            g(self.type_mode_var, "Mixed"),
                "type_split":           int(g(self.type_split_var, 50)),
                "tera_enabled":         g(self.tera_enabled_var, False),
                "tera_ban_sync":        g(self.tera_ban_sync_var, False),
                "tera_no_match":        g(self.tera_no_match_var, True),
                "stat_mode":            g(self.stat_mode_var, "Free"),
                "bst_budget":           g(self.bst_var, 500),
                "bst_min":              g(self.bst_min_var, 200),
                "bst_max":              g(self.bst_max_var, 600),
                "use_stat_minmax":      g(self.use_stat_minmax_var, False),
                **{f"stat_min_{s}": g(self.stat_min_vars[s], 1)   for s in STAT_NAMES},
                **{f"stat_max_{s}": g(self.stat_max_vars[s], 255) for s in STAT_NAMES},
                "reveal_font":            g(self.reveal_font_var, "Segoe UI"),
                "reveal_fade":            g(self.reveal_fade_var, "Medium"),
                "reveal_font_size":       g(self.reveal_font_size_var, 44),
                "reveal_title_col":       g(self.reveal_title_col_var, ""),
                "reveal_sub_col":         g(self.reveal_sub_col_var, ""),
                "reveal_outline":         g(self.reveal_outline_var, True),
                "reveal_outline_size":    g(self.reveal_outline_size_var, 2),
                "reveal_outline_col":     g(self.reveal_outline_col_var, "#000000"),
                "reveal_sub_outline":     g(self.reveal_sub_outline_var, True),
                "reveal_sub_outline_size": g(self.reveal_sub_outline_size_var, 1),
                "reveal_sub_outline_col": g(self.reveal_sub_outline_col_var, "#000000"),
                "reveal_glow":            g(self.reveal_glow_var, False),
                "reveal_glow_size":       g(self.reveal_glow_size_var, 4),
                "reveal_glow_col":        g(self.reveal_glow_col_var, ""),
                "reveal_pokemon_sprite":  g(self.reveal_pokemon_sprite_var, 220),
                "pokemon_transfers":      g(self.pokemon_transfers_var, True),
                "pokemon_shiny":          g(self.pokemon_shiny_var, False),
                "pokemon_shiny_mode":     g(self.pokemon_shiny_mode_var, "odds"),
                "pokemon_shiny_odds":     g(self.pokemon_shiny_odds_var, 8192),
                "pokemon_shiny_pct":      g(self.pokemon_shiny_pct_var, "0.01"),
                "reveal_bg_global":       g(self.reveal_bg_global_var, ""),
                "reveal_bg_stretch":      g(self.reveal_bg_stretch_var, "Fit"),
                "reveal_bg_per":          g(self.reveal_bg_per_var, False),
                "reveal_bg_abilities":    g(self.reveal_bg_abilities_var, ""),
                "reveal_bg_typing":       g(self.reveal_bg_typing_var, ""),
                "reveal_bg_stats":        g(self.reveal_bg_stats_var, ""),
                "reveal_bg_nature":       g(self.reveal_bg_nature_var, ""),
                "reveal_bg_pokemon":      g(self.reveal_bg_pokemon_var, ""),
                "reveal_typing_override": g(self.reveal_typing_override_var, False),
                "win_width":              g(self.win_width_var, 1320),
                "win_height":             g(self.win_height_var, 820),
                "win_maximised":          g(self.win_maximised_var, False),
                "default_tab":            g(self.default_tab_var, "abilities"),
            }
            import tempfile
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=DATA_DIR)
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, SETTINGS_FILE)
            except Exception:
                try: os.unlink(tmp_path)
                except Exception: pass
                raise
        except Exception:
            import traceback
            try:
                log = os.path.join(DATA_DIR, "settings_error.log")
                with open(log, "w") as lf:
                    lf.write(traceback.format_exc())
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Ability list / detail
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_ability_views(self):
        t     = self._t
        query = self.search_var.get().strip().lower()
        self.filtered_abilities = [
            a for a in self._get_visible_pool()
            if query in a["display_name"].lower() or query in a["effect"].lower()
        ]
        self.ability_listbox.delete(0, tk.END)
        for ability in self.filtered_abilities:
            banned = ability["name"] in self.banned_abilities
            label  = f"  {'🚫 ' if banned else ''}{ability['display_name']}  [{ability['generation']}]"
            self.ability_listbox.insert(tk.END, label)
            if banned:
                self.ability_listbox.itemconfig(tk.END, fg=t["fg_banned"], bg=t["bg_banned"])
        self._refresh_ban_list()

    def show_selected_ability(self, _event=None):
        sel = self.ability_listbox.curselection()
        if not sel:
            return
        ability   = self.filtered_abilities[sel[0]]
        is_banned = ability["name"] in self.banned_abilities
        self.detail_title_var.set(ability["display_name"])
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", tk.END)
        for key, val, tag in [
            ("Generation:  ", ability["generation"],                        "val"),
            ("Main series: ", "Yes" if ability["is_main_series"] else "No", "val"),
            ("Status:      ", "🚫 CRINGE / BANNED" if is_banned else "✅ Allowed",
             "banned_val" if is_banned else "val"),
        ]:
            self.detail_text.insert(tk.END, key, "key")
            self.detail_text.insert(tk.END, val + "\n", tag)
        self.detail_text.insert(tk.END, "\nEffect:\n", "effect_label")
        self.detail_text.insert(tk.END, ability["effect"] + "\n", "val")
        self.detail_text.configure(state="disabled")

    # ══════════════════════════════════════════════════════════════════════════
    #  Ban management (abilities)
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_ban_list(self):
        self.ban_listbox.delete(0, tk.END)
        for name in sorted(self.banned_abilities, key=lambda n: self._display_name(n)):
            self.ban_listbox.insert(tk.END, f"  {self._display_name(name)}")

    def add_ban_from_entry(self):
        raw = self.custom_ban_var.get().strip()
        if not raw:
            return
        norm  = self._normalize_name(raw)
        match = next((a for a in self.abilities
                      if a["name"] == norm or a["display_name"].lower() == raw.lower()), None)
        self.banned_abilities.add(match["name"] if match else norm)
        self.custom_ban_var.set("")
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()

    def ban_selected_ability(self):
        sel = self.ability_listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "Select an ability in the browser first.")
            return
        self.banned_abilities.add(self.filtered_abilities[sel[0]]["name"])
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()
        self.show_selected_ability()

    def unban_selected_ability(self):
        sel = self.ability_listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "Select an ability in the browser first.")
            return
        self.banned_abilities.discard(self.filtered_abilities[sel[0]]["name"])
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()
        self.show_selected_ability()

    def remove_selected_ban(self):
        sel = self.ban_listbox.curselection()
        if not sel:
            return
        name_map = {a["display_name"]: a["name"] for a in self.abilities}
        for dn in [self.ban_listbox.get(i).strip() for i in sel]:
            self.banned_abilities.discard(name_map.get(dn) or self._normalize_name(dn))
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()

    def clear_bans(self):
        if not self.banned_abilities:
            return
        if not messagebox.askyesno(APP_TITLE,
                f"Clear all {len(self.banned_abilities)} banned abilities?"):
            return
        self.banned_abilities.clear()
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.configure(state="disabled")

    # ══════════════════════════════════════════════════════════════════════════
    #  Roll — abilities
    # ══════════════════════════════════════════════════════════════════════════

    def _get_roll_pool(self):
        pool = self._get_visible_pool()
        if not self.include_banned_var.get():
            pool = [a for a in pool if a["name"] not in self.banned_abilities]
        return pool

    def _validate_roll(self):
        if not self._selected_generations():
            messagebox.showerror(APP_TITLE, "Select at least one generation first.")
            return None, None
        try:
            count = int(self.draw_count_var.get())
        except Exception:
            messagebox.showerror(APP_TITLE, "Enter a valid number of abilities to draw.")
            return None, None
        pool = self._get_roll_pool()
        if not pool:
            messagebox.showerror(APP_TITLE, "No abilities available with the current filters.")
            return None, None
        if count < 1:
            messagebox.showerror(APP_TITLE, "Draw at least 1 ability.")
            return None, None
        if count > len(pool):
            messagebox.showerror(APP_TITLE,
                f"You asked for {count}, but only {len(pool)} abilities are available.")
            return None, None
        return count, pool

    def _sort_key(self, a):
        return (GEN_ORDER.get(a["generation"], 99), a["display_name"])

    def _render_results(self):
        rolled   = self._rolled
        gen_list = ", ".join(g.replace("GEN ", "Gen ") for g in GENERATIONS
                             if self.generation_vars[g].get())
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END,
            f"⚡  {len(rolled)} Abilit{'y' if len(rolled) == 1 else 'ies'} Rolled", "header")
        self.result_text.insert(tk.END, f"\n{'─'*52}\n", "divider")
        self.result_text.insert(tk.END, f"  Game:        {self.game_var.get()}\n", "meta")
        self.result_text.insert(tk.END, f"  Generations: {gen_list}\n", "meta")
        self.result_text.insert(tk.END,
            f"  Cringe incl: {'Yes' if self.include_banned_var.get() else 'No'}\n", "meta")
        self.result_text.insert(tk.END, f"{'─'*52}\n\n", "divider")
        for i, ability in enumerate(rolled, 1):
            self.result_text.insert(tk.END, f"  {i:>2}.  ", "meta")
            self.result_text.insert(tk.END, ability["display_name"], "ability_name")
            self.result_text.insert(tk.END, f"  [{ability['generation']}]\n", "gen_tag")
            self.result_text.insert(tk.END, f"       {ability['effect']}\n\n", "effect_text")
        self.result_text.see("1.0")
        self.result_text.configure(state="disabled")
        self.rolled_listbox.delete(0, tk.END)
        for ability in rolled:
            self.rolled_listbox.insert(tk.END, f"  {ability['display_name']}")

    def roll_abilities(self):
        count, pool = self._validate_roll()
        if count is None:
            return
        self._rolled = sorted(random.sample(pool, count), key=self._sort_key)
        self._render_results()
        self._update_status()

    def _roll_dramatically(self):
        count, pool = self._validate_roll()
        if count is None:
            return
        self._rolled = sorted(random.sample(pool, count), key=self._sort_key)
        self._update_status()
        self._dramatic_reveal(on_close=self._render_results)

    # ══════════════════════════════════════════════════════════════════════════
    #  Rolled ability actions
    # ══════════════════════════════════════════════════════════════════════════

    def _get_selected_rolled(self):
        sel = self.rolled_listbox.curselection()
        if not sel or not self._rolled:
            messagebox.showinfo(APP_TITLE,
                "Select an ability from the list on the right first.")
            return None, None
        return sel[0], self._rolled[sel[0]]

    def _do_reroll(self, idx):
        current = {a["name"] for a in self._rolled}
        pool    = [a for a in self._get_roll_pool() if a["name"] not in current]
        if not pool:
            self._rolled.pop(idx)
            self._render_results()
            return None
        replacement       = random.choice(pool)
        self._rolled[idx] = replacement
        self._rolled.sort(key=self._sort_key)
        self._render_results()
        new_idx = next((i for i, a in enumerate(self._rolled)
                        if a["name"] == replacement["name"]), 0)
        self.rolled_listbox.selection_clear(0, tk.END)
        self.rolled_listbox.selection_set(new_idx)
        self.rolled_listbox.see(new_idx)
        return replacement

    def _ban_selected(self):
        idx, target = self._get_selected_rolled()
        if target is None:
            return
        self.banned_abilities.add(target["name"])
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()
        self._render_results()

    def _reroll_selected(self):
        idx, target = self._get_selected_rolled()
        if target is None:
            return
        if self._do_reroll(idx) is None:
            messagebox.showinfo(APP_TITLE, "No replacement available with the current filters.")

    def _ban_and_reroll(self):
        idx, target = self._get_selected_rolled()
        if target is None:
            return
        self.banned_abilities.add(target["name"])
        self._save_settings()
        self._update_status()
        self._refresh_ability_views()
        if self._do_reroll(idx) is None:
            messagebox.showinfo(APP_TITLE,
                f"{target['display_name']} was banned.\n"
                "No replacement available with the current filters.")

    # ══════════════════════════════════════════════════════════════════════════
    #  Roll — typing
    # ══════════════════════════════════════════════════════════════════════════

    def _get_available_types(self):
        return [t for t in TYPES if not self.type_ban_vars[t].get()]

    def _on_type_mode_changed(self):
        show = self.type_mode_var.get() == "%"
        for w in self._type_split_frame.winfo_children():
            try:
                if show: w.grid()
                else:    w.grid_remove()
            except Exception:
                pass
        if show:
            self._update_split_label()

    def _update_split_label(self):
        s = int(self.type_split_var.get())
        self.split_label_var.set(f"{s}% Single  /  {100 - s}% Dual")

    def roll_typing(self, render: bool = True):
        pool = self._get_available_types()
        if not pool:
            messagebox.showerror(APP_TITLE, "No types available — unban some types first.")
            return

        mode = self.type_mode_var.get()
        if mode == "Single":
            primary   = random.choice(pool)
            secondary = None
        elif mode == "Dual":
            if len(pool) < 2:
                messagebox.showerror(APP_TITLE, "Need at least 2 unbanned types for Dual mode.")
                return
            primary, secondary = random.sample(pool, 2)
        elif mode == "%":
            single_pct = int(self.type_split_var.get())
            go_single  = random.randint(1, 100) <= single_pct
            if go_single:
                primary   = random.choice(pool)
                secondary = None
            else:
                if len(pool) < 2:
                    primary   = random.choice(pool)
                    secondary = None
                else:
                    primary, secondary = random.sample(pool, 2)
        else:  # Mixed
            primary = random.choice(pool)
            if len(pool) >= 2 and random.random() < 0.5:
                remaining = [t for t in pool if t != primary]
                secondary = random.choice(remaining)
            else:
                secondary = None

        result = [primary, secondary if secondary else "N/A"]

        if self.tera_enabled_var.get():
            tera_pool = list(TERA_TYPES)
            if self.tera_ban_sync_var.get():
                tera_pool = [t for t in tera_pool
                             if t == "Stellar" or not self.type_ban_vars.get(t, tk.BooleanVar()).get()]
            if self.tera_no_match_var.get():
                tera_pool = [t for t in tera_pool if t != primary]
            if tera_pool:
                result.append(random.choice(tera_pool))

        self._rolled_types = result
        self._typing_hide_result = not render
        if render:
            self._draw_typing_result()
        self._save_settings()

    def _roll_typing_dramatically(self):
        pool = self._get_available_types()
        if not pool:
            messagebox.showerror(APP_TITLE, "No types available — unban some types first.")
            return

        def _show_result():
            self._typing_hide_result = False
            self._draw_typing_result()

        # Don't draw the result on the main canvas until the reveal is done
        self.roll_typing(render=False)
        if self._rolled_types:
            self._dramatic_reveal_typing(on_close=_show_result)

    # ══════════════════════════════════════════════════════════════════════════
    #  Roll — stats
    # ══════════════════════════════════════════════════════════════════════════

    def _on_stat_minmax_toggled(self):
        show = self.use_stat_minmax_var.get()
        for w in self._stat_minmax_frame.winfo_children():
            try:
                if show:
                    w.grid()
                else:
                    w.grid_remove()
            except Exception:
                pass

    def _on_stat_mode_changed(self):
        mode = self.stat_mode_var.get()
        range_state = "normal" if mode == "Range" else "disabled"
        fixed_state = "normal" if mode == "Fixed" else "disabled"
        try:
            self.bst_min_spin.configure(state=range_state)
            self.bst_max_spin.configure(state=range_state)
            self.bst_fixed_spin.configure(state=fixed_state)
        except AttributeError:
            pass

    def roll_stats(self, render: bool = True):
        use_mm = self.use_stat_minmax_var.get()
        floors = {s: max(1,   min(255, self.stat_min_vars[s].get())) for s in STAT_NAMES} \
                 if use_mm else {s: 1   for s in STAT_NAMES}
        ceils  = {s: max(floors[s], min(255, self.stat_max_vars[s].get())) for s in STAT_NAMES} \
                 if use_mm else {s: 255 for s in STAT_NAMES}

        mode = self.stat_mode_var.get()
        if mode == "Fixed":
            budget = max(6, min(1530, self.bst_var.get()))
            stats  = self._distribute_bst(budget, floors, ceils)
        elif mode == "Range":
            lo = max(6,    min(1530, self.bst_min_var.get()))
            hi = max(lo,   min(1530, self.bst_max_var.get()))
            target = random.randint(lo, hi)
            stats  = self._distribute_bst(target, floors, ceils)
        else:  # Free
            stats = {s: random.randint(floors[s], ceils[s]) for s in STAT_NAMES}

        self._rolled_stats = stats
        self._stats_hide_result = not render
        if render:
            self._render_stats()

    def _distribute_bst(self, budget: int,
                        floors: dict = None, ceils: dict = None) -> dict:
        """Distribute budget across 6 stats respecting per-stat floors and ceilings."""
        if floors is None: floors = {s: 1   for s in STAT_NAMES}
        if ceils  is None: ceils  = {s: 255 for s in STAT_NAMES}

        # Clamp budget to achievable range given floors/ceilings
        min_total = sum(floors.values())
        max_total = sum(ceils.values())
        budget = max(min_total, min(max_total, budget))

        # Start every stat at its floor; distribute remaining points
        stats     = dict(floors)
        remaining = budget - min_total
        rooms     = {s: ceils[s] - floors[s] for s in STAT_NAMES}

        # Stars-and-bars with per-stat caps: try random cut-points first
        for _ in range(500):
            cuts = sorted(random.randint(0, remaining) for _ in range(len(STAT_NAMES) - 1))
            cuts = [0] + cuts + [remaining]
            vals = [cuts[i+1] - cuts[i] for i in range(len(STAT_NAMES))]
            if all(vals[i] <= rooms[s] for i, s in enumerate(STAT_NAMES)):
                keys = list(STAT_NAMES)
                random.shuffle(keys)
                for i, s in enumerate(keys):
                    stats[s] = floors[s] + vals[i]
                return stats

        # Fallback: greedy shuffle
        keys = list(STAT_NAMES)
        random.shuffle(keys)
        left = remaining
        for s in keys:
            give    = random.randint(0, min(left, rooms[s]))
            stats[s] = floors[s] + give
            left   -= give
        # Dump any remainder
        for s in keys:
            if left == 0: break
            add = min(left, ceils[s] - stats[s])
            stats[s] += add
            left -= add
        return stats

    def _draw_radar(self):
        """Draw a hexagonal stat web on self.radar_canvas."""
        import math
        c = self.radar_canvas
        c.delete("all")
        c.update_idletasks()
        W = c.winfo_width()
        H = c.winfo_height()
        if W < 10 or H < 10:
            return

        t      = self._t
        cx, cy = W // 2, H // 2
        # Leave fixed pixel margin for labels so they never clip
        LABEL_MARGIN = 42
        radius = min(W, H) // 2 - LABEL_MARGIN
        if radius < 20:
            return
        stats  = STAT_NAMES
        n      = len(stats)

        angles = [math.radians(-90 + 360 / n * i) for i in range(n)]

        def point(r_frac, i):
            a = angles[i]
            return (cx + r_frac * radius * math.cos(a),
                    cy + r_frac * radius * math.sin(a))

        grid_col = _lerp_colour(t["bg_result"], t["fg_sub"], 0.25)
        for ring in range(1, 6):
            frac   = ring / 5
            pts    = [point(frac, i) for i in range(n)]
            coords = []
            for p in pts:
                coords += list(p)
            coords += list(pts[0])
            c.create_line(*coords, fill=grid_col, width=1)

        for i in range(n):
            ox, oy = point(0, i)
            ex, ey = point(1.0, i)
            c.create_line(ox, oy, ex, ey, fill=grid_col, width=1)

        hide = getattr(self, "_stats_hide_result", False)
        if self._rolled_stats and not hide:
            data_pts = []
            for i, stat in enumerate(stats):
                val  = self._rolled_stats.get(stat, 0)
                frac = max(0.0, min(1.0, val / 255))
                data_pts.append(point(frac, i))
            coords = []
            for p in data_pts:
                coords += list(p)
            coords += list(data_pts[0])
            fill_col = _lerp_colour(t["fg_accent2"], t["bg_result"], 0.55)
            c.create_polygon(*coords[:-2], fill=fill_col, outline="", smooth=False)
            c.create_line(*coords, fill=t["fg_accent2"], width=2)
            for px, py in data_pts:
                c.create_oval(px-4, py-4, px+4, py+4,
                              fill=t["fg_accent1"], outline="")

        # Labels: fixed pixel offset outside the web edge
        LABEL_OFFSET = radius + 22
        label_col = t["fg_main"]
        for i, stat in enumerate(stats):
            a  = angles[i]
            lx = cx + LABEL_OFFSET * math.cos(a)
            ly = cy + LABEL_OFFSET * math.sin(a)
            val_str = (str(self._rolled_stats.get(stat, ""))
                       if self._rolled_stats and not hide else "")
            display = f"{stat}\n{val_str}" if val_str else stat
            c.create_text(lx, ly, text=display, fill=label_col,
                          font=("Segoe UI", 8, "bold"), anchor="center", justify="center")

    def _render_stats(self):
        if not self._rolled_stats:
            return
        self._stats_hide_result = False
        for stat, var in self.stat_value_vars.items():
            var.set(str(self._rolled_stats.get(stat, "—")))
        total = sum(self._rolled_stats.values())
        self.stat_total_var.set(str(total))
        self._draw_radar()

    def roll_nature(self, render: bool = True):
        self._rolled_nature = random.choice(NATURES)
        if render:
            self._render_nature()

    def _render_nature(self):
        if not self._rolled_nature:
            return
        name, boost, reduce = self._rolled_nature
        self.nature_name_var.set(name)
        if boost:
            self.nature_boost_var.set(boost)
            self.nature_reduce_var.set(reduce)
            self.nature_neutral_lbl.configure(text="")
        else:
            self.nature_boost_var.set("—")
            self.nature_reduce_var.set("—")
            self.nature_neutral_lbl.configure(text="Neutral nature")

    def _roll_stats_dramatically(self):
        self.roll_stats(render=False)
        if self._rolled_stats:
            self._dramatic_reveal_stats(on_close=self._render_stats)

    def _roll_nature_dramatically(self):
        self.roll_nature(render=False)
        if self._rolled_nature:
            self._dramatic_reveal_nature(on_close=self._render_nature)

    # ══════════════════════════════════════════════════════════════════════════
    #  Dramatic Reveal — shared fade engine
    # ══════════════════════════════════════════════════════════════════════════

    def _canvas_nav_buttons(self, cv, x, y, buttons, gap=16):
        """Place buttons directly on a canvas, centred as a group at (x, y),
        with no backing frame (so nothing boxes them in over the background).
        Replaces any nav buttons previously placed on this canvas."""
        for item, btn in getattr(cv, "_nav_btns", []):
            try:
                cv.delete(item)
                btn.destroy()
            except Exception:
                pass
        cv._nav_btns = []
        if not buttons:
            return
        widths = []
        for b in buttons:
            b.update_idletasks()
            widths.append(b.winfo_reqwidth())
        total_w = sum(widths) + gap * (len(buttons) - 1)
        cur = x - total_w / 2
        for b, w in zip(buttons, widths):
            item = cv.create_window(int(cur), y, window=b, anchor="w")
            cv._nav_btns.append((item, b))
            cur += w + gap

    def _make_overlay(self, bg_colour="#000000"):
        """Create a window-sized borderless overlay over the app."""
        self.root.update_idletasks()
        W, H   = self.root.winfo_width(), self.root.winfo_height()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        ov = tk.Toplevel(self.root)
        ov.configure(bg=bg_colour)
        ov.geometry(f"{W}x{H}+{rx}+{ry}")
        ov.resizable(False, False)
        ov.overrideredirect(True)
        ov.grab_set()
        return ov, W, H

    @staticmethod
    def _fade_loop(ov, steps, ms, colour_fn, on_done):
        """Generic fade: calls colour_fn(alpha) each step, then on_done()."""
        def tick(step=0):
            if not ov.winfo_exists():
                return
            if step > steps:
                colour_fn(1.0)
                if on_done:
                    on_done()
                return
            colour_fn(step / steps)
            ov.after(ms, lambda: tick(step + 1))
        tick()

    @staticmethod
    def _fade_out_loop(ov, steps, ms, colour_fn, on_done):
        def tick(step=0):
            if not ov.winfo_exists():
                return
            if step > steps:
                colour_fn(0.0)
                if on_done:
                    on_done()
                return
            colour_fn(1.0 - step / steps)
            ov.after(ms, lambda: tick(step + 1))
        tick()

    # ── Abilities dramatic reveal ───────────────────────────────────────────────

    def _dramatic_reveal(self, on_close=None):
        if not self._rolled:
            messagebox.showinfo(APP_TITLE, "Roll some abilities first!")
            return

        t         = self._t
        BLACK     = "#000000"
        abilities = list(self._rolled)
        total     = len(abilities)
        STEPS, MS = self._get_reveal_fade()

        ov, W, H = self._make_overlay(BLACK)
        scale    = min(W / 1320, H / 820)
        fam      = self.reveal_font_var.get()
        sz_counter = max(8,  int(11 * scale))
        sz_name    = max(14, int(self.reveal_font_size_var.get() * scale))
        sz_effect  = max(9,  int(13 * scale))
        sz_btn     = max(8,  int(10 * scale))
        wrap_name  = int(W * 0.80)
        wrap_eff   = int(W * 0.72)
        div_w      = int(W * 0.42)
        btn_pady   = max(4, int(8 * scale))
        btn_padx   = max(8, int(18 * scale))

        # Single full-window canvas — all text drawn on it
        cv = tk.Canvas(ov, highlightthickness=0, bg=BLACK)
        cv.place(x=0, y=0, width=W, height=H)

        # Pre-blend background frames from black → full image (same pattern as other reveals)
        _bg_cache: dict = {}
        bg_frames = None
        bg_full_pil = self._get_reveal_bg_pil_raw("abilities", W, H)
        if bg_full_pil is not None and _PIL_OK:
            try:
                black_img = Image.new("RGB", (W, H), (0, 0, 0))
                bg_frames = [
                    Image.blend(black_img, bg_full_pil, min(step / max(STEPS, 1), 1.0))
                    for step in range(STEPS + 2)
                ]
            except Exception:
                bg_frames = None

        bg_img_id = cv.create_image(0, 0, anchor="nw")

        counter_fx = self._create_fx_text(cv, W//2, int(H*0.09), text="",
                                           font=(fam, sz_counter, "bold"),
                                           anchor="center", sub=True)
        name_fx    = self._create_fx_text(cv, W//2, int(H*0.45), text="",
                                          font=(fam, sz_name, "bold"),
                                          anchor="center", width=wrap_name, justify="center")
        div_id     = cv.create_line(int(W*0.5 - div_w/2), int(H*0.57),
                                    int(W*0.5 + div_w/2), int(H*0.57),
                                    fill=BLACK, width=2)
        effect_fx  = self._create_fx_text(cv, W//2, int(H*0.67), text="",
                                           font=(fam, sz_effect), sub=True,
                                           anchor="center", width=wrap_eff, justify="center")

        nav_y   = int(H * 0.90)
        idx_ref = [0]
        fading_ref = [False]

        def apply_alpha(alpha):
            bg_c = _lerp_colour(BLACK, t["bg_root"], alpha)
            ov.configure(bg=bg_c)
            cv.configure(bg=bg_c)
            if bg_frames:
                step_idx = min(round(alpha * STEPS), len(bg_frames) - 1)
                if step_idx not in _bg_cache:
                    _bg_cache[step_idx] = ImageTk.PhotoImage(bg_frames[step_idx])
                cv.itemconfigure(bg_img_id, image=_bg_cache[step_idx])
            else:
                cv.itemconfigure(bg_img_id, image="")
            self._update_fx_text(cv, counter_fx, alpha, self._reveal_sub_col(), BLACK, sub=True)
            self._update_fx_text(cv, name_fx,    alpha, self._reveal_title_col(), BLACK)
            self._update_fx_text(cv, effect_fx,  alpha, t["fg_main"],             BLACK, sub=True)
            cv.itemconfigure(div_id, fill=_lerp_colour(BLACK, t["fg_accent2"], alpha))

        def fade_in(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(1.0); fading_ref[0] = False
                if then: then()
                return
            apply_alpha(step / STEPS)
            ov.after(MS, lambda: fade_in(step + 1, then))

        def fade_out(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(0.0)
                if then: then()
                return
            apply_alpha(1.0 - step / STEPS)
            ov.after(MS, lambda: fade_out(step + 1, then))

        def build_nav(i):
            bkw = dict(relief="flat", bd=0, padx=btn_padx, pady=btn_pady, cursor="hand2")
            btns = []
            if i > 0:
                btns.append(tk.Button(cv, text="◀  Previous", command=lambda: go(i - 1),
                          bg=t["bg_field"], fg=t["fg_main"],
                          activebackground=t["fg_accent2"], activeforeground=t["bg_root"],
                          font=(fam, sz_btn), **bkw))
            next_or_done = i < total - 1
            btns.append(tk.Button(cv,
                      text="Next  ▶" if next_or_done else "✅  Done",
                      command=(lambda: go(i + 1)) if next_or_done else finish,
                      bg=t["roll_bg"], fg=t["fg_main"],
                      activebackground=t["roll_hover"], activeforeground=t["fg_main"],
                      font=(fam, sz_btn, "bold"), **bkw))
            btns.append(tk.Button(cv, text="✕  Skip reveal", command=finish,
                      bg=t["bg_field"], fg=t["fg_sub"],
                      activebackground=t["fg_banned"], activeforeground=t["bg_root"],
                      font=(fam, sz_btn), **bkw))
            self._canvas_nav_buttons(cv, W // 2, nav_y, btns)

        def load_card(i):
            a = abilities[i]
            idx_ref[0] = i
            cv.itemconfigure(counter_fx["main"],  text=f"{i + 1}  /  {total}")
            for oid in counter_fx["outline"]:      cv.itemconfigure(oid, text=f"{i + 1}  /  {total}")
            cv.itemconfigure(name_fx["main"],    text=a["display_name"])
            for oid in name_fx["outline"]:       cv.itemconfigure(oid, text=a["display_name"])
            for gid, _ in name_fx["glow"]:       cv.itemconfigure(gid, text=a["display_name"])
            cv.itemconfigure(effect_fx["main"],  text=a["effect"])
            for oid in effect_fx["outline"]:     cv.itemconfigure(oid, text=a["effect"])
            build_nav(i)

        def show_card(i):
            load_card(i); fading_ref[0] = True; fade_in()

        def go(i):
            if fading_ref[0]: return
            fading_ref[0] = True
            fade_out(then=lambda: show_card(i))

        def finish():
            if fading_ref[0]: return
            fading_ref[0] = True
            def _close():
                if ov.winfo_exists():
                    ov.grab_release(); ov.destroy()
                if on_close: on_close()
            fade_out(then=_close)

        def on_key(event):
            i = idx_ref[0]
            if event.keysym in ("Right", "space", "Return"):
                if i < total - 1: go(i + 1)
                else: finish()
            elif event.keysym == "Left" and i > 0:
                go(i - 1)
            elif event.keysym == "Escape":
                finish()

        ov.bind("<KeyPress>", on_key)
        ov.focus_set()
        show_card(0)

    # ── Typing dramatic reveal ─────────────────────────────────────────────────

    def _dramatic_reveal_typing(self, on_close=None):
        if not self._rolled_types:
            return

        BLACK  = "#000000"
        types  = self._rolled_types
        primary   = types[0]
        secondary = types[1] if len(types) > 1 and types[1] != "N/A" else None
        tera      = types[2] if len(types) > 2 else None

        p_col = TYPE_COLORS.get(primary, "#888888")
        s_col = TYPE_COLORS.get(secondary, p_col) if secondary else p_col

        ov, W, H = self._make_overlay(BLACK)
        STEPS, MS = self._get_reveal_fade()
        t = self._t

        scale    = min(W / 1320, H / 820)
        fam      = self.reveal_font_var.get()
        base_sz  = self.reveal_font_size_var.get()
        sz_pri   = max(20, int(base_sz * scale * 1.20))
        sz_sec   = max(16, int(base_sz * scale))
        sz_tera  = max(10, int(18 * scale))
        sz_btn   = max(8,  int(10 * scale))
        btn_pady = max(4, int(8 * scale))
        btn_padx = max(8, int(18 * scale))

        # Build the full-resolution background PIL image (gradient or custom)
        bg_full_pil = None
        use_image   = self.reveal_typing_override_var.get() and _PIL_OK
        if use_image:
            bg_pil = self._get_reveal_bg_pil_raw("typing", W, H)
            if bg_pil is None:
                bg_pil = self._get_reveal_bg_pil_raw("global", W, H)
            if bg_pil is not None:
                bg_full_pil = bg_pil
            else:
                use_image = False  # fall back to gradient

        if not use_image and _PIL_OK:
            try:
                grad_img = Image.new("RGB", (W, H))
                px = grad_img.load()
                pr, pg, pb = _hex_to_rgb(p_col)
                sr, sg, sb = _hex_to_rgb(s_col)
                for x in range(W):
                    ratio = x / max(W - 1, 1)
                    r = max(0, int(pr + (sr - pr) * ratio) - 50)
                    g = max(0, int(pg + (sg - pg) * ratio) - 50)
                    b = max(0, int(pb + (sb - pb) * ratio) - 50)
                    for y in range(H):
                        px[x, y] = (r, g, b)
                bg_full_pil = grad_img
            except Exception:
                pass

        # Pre-blend STEPS+2 frames from black → full background (same approach as pokemon reveal)
        bg_frames = None
        if bg_full_pil is not None and _PIL_OK:
            try:
                black_img = Image.new("RGB", (W, H), (0, 0, 0))
                bg_frames = [
                    Image.blend(black_img, bg_full_pil, min(step / max(STEPS, 1), 1.0))
                    for step in range(STEPS + 2)
                ]
            except Exception:
                pass

        # Photo cache for blended background frames (prevents GC mid-fade)
        _bg_cache: dict = {}

        # Single full-window canvas
        cv = tk.Canvas(ov, highlightthickness=0, bg=BLACK)
        cv.place(x=0, y=0, width=W, height=H)

        bg_img_id = cv.create_image(0, 0, anchor="nw")

        # Text items
        pri_fx  = self._create_fx_text(cv, W//2, int(H*0.30), text=primary,
                                        font=(fam, sz_pri, "bold"), anchor="center")
        div_id  = cv.create_line(int(W*0.3), int(H*0.50),
                                 int(W*0.7), int(H*0.50),
                                 fill=BLACK, width=2)
        sec_text = types[1] if len(types) > 1 else "N/A"
        sec_fx   = self._create_fx_text(cv, W//2, int(H*0.65), text=sec_text,
                                         font=(fam, sz_sec, "bold"), anchor="center")
        tera_fx  = None
        if tera:
            tera_fx = self._create_fx_text(cv, W//2, int(H*0.82),
                                           text=f"Tera Type: {tera}",
                                           font=(fam, sz_tera, "bold"),
                                           anchor="center", sub=True)

        fading_ref = [False]

        def apply_alpha(alpha):
            bg_c = _lerp_colour(BLACK, _darken(p_col, 50) if not use_image else t["bg_root"], alpha)
            ov.configure(bg=bg_c)
            cv.configure(bg=bg_c)
            # Fade background frame
            if bg_frames:
                step_idx = min(round(alpha * STEPS), len(bg_frames) - 1)
                if step_idx not in _bg_cache:
                    _bg_cache[step_idx] = ImageTk.PhotoImage(bg_frames[step_idx])
                cv.itemconfigure(bg_img_id, image=_bg_cache[step_idx])
            else:
                cv.itemconfigure(bg_img_id, image="")
            sub_c          = self._reveal_sub_col()
            has_custom_sub = bool(self.reveal_sub_col_var.get())
            sec_col        = s_col if secondary else (sub_c if has_custom_sub else "#aaaaaa")
            self._update_fx_text(cv, pri_fx, alpha, p_col, BLACK)
            self._update_fx_text(cv, sec_fx, alpha, sec_col, BLACK)
            cv.itemconfigure(div_id, fill=_lerp_colour(BLACK, "#ffffff", alpha * 0.5))
            if tera_fx:
                self._update_fx_text(cv, tera_fx, alpha,
                    TYPE_COLORS.get(tera, "#ffffff"), BLACK, sub=True)

        def fade_in(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(1.0); fading_ref[0] = False
                if then: then()
                return
            apply_alpha(step / STEPS)
            ov.after(MS, lambda: fade_in(step + 1, then))

        def fade_out(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(0.0)
                if then: then()
                return
            apply_alpha(1.0 - step / STEPS)
            ov.after(MS, lambda: fade_out(step + 1, then))

        def finish():
            if fading_ref[0]: return
            fading_ref[0] = True
            def _close():
                if ov.winfo_exists():
                    ov.grab_release(); ov.destroy()
                if on_close: on_close()
            fade_out(then=_close)

        def build_nav():
            # Buttons live directly on the canvas so no frame background
            # shows over the gradient
            bkw = dict(relief="flat", bd=0, padx=btn_padx, pady=btn_pady,
                       cursor="hand2")
            done_b = tk.Button(cv, text="✅  Done", command=finish,
                               bg=t["roll_bg"], fg=t["fg_main"],
                               activebackground=t["roll_hover"],
                               activeforeground=t["fg_main"],
                               font=(fam, sz_btn, "bold"), **bkw)
            close_b = tk.Button(cv, text="✕  Close", command=finish,
                                bg=t["bg_field"], fg=t["fg_sub"],
                                activebackground=t["fg_banned"],
                                activeforeground=t["bg_root"],
                                font=(fam, sz_btn), **bkw)
            cv.create_window(W // 2 - 8, int(H * 0.92), window=done_b, anchor="e")
            cv.create_window(W // 2 + 8, int(H * 0.92), window=close_b, anchor="w")
        build_nav()

        def on_key(event):
            if event.keysym in ("Return", "space", "Escape"):
                finish()
        ov.bind("<KeyPress>", on_key)
        ov.focus_set()
        fading_ref[0] = True
        fade_in()

    # ── Stats dramatic reveal ──────────────────────────────────────────────────

    def _dramatic_reveal_stats(self, on_close=None):
        if not self._rolled_stats:
            return

        t      = self._t
        BLACK  = "#000000"
        bst    = sum(self._rolled_stats[s] for s in STAT_NAMES)
        stats  = [(s, self._rolled_stats[s]) for s in STAT_NAMES]
        stats.append(("BST", bst))
        total  = len(stats)
        STEPS, MS = self._get_reveal_fade()

        ov, W, H = self._make_overlay(BLACK)
        scale    = min(W / 1320, H / 820)
        fam      = self.reveal_font_var.get()
        sz_label = max(14, int(26 * scale))
        sz_val   = max(28, int(64 * scale))
        sz_btn   = max(8,  int(10 * scale))
        btn_pady = max(4, int(8 * scale))
        btn_padx = max(8, int(18 * scale))

        cv2 = tk.Canvas(ov, highlightthickness=0, bg=BLACK)
        cv2.place(x=0, y=0, width=W, height=H)

        _bg_cache2: dict = {}
        bg_frames2 = None
        bg_full_pil2 = self._get_reveal_bg_pil_raw("stats", W, H)
        if bg_full_pil2 is not None and _PIL_OK:
            try:
                black_img2 = Image.new("RGB", (W, H), (0, 0, 0))
                bg_frames2 = [
                    Image.blend(black_img2, bg_full_pil2, min(step / max(STEPS, 1), 1.0))
                    for step in range(STEPS + 2)
                ]
            except Exception:
                bg_frames2 = None
        bg_img2   = cv2.create_image(0, 0, anchor="nw")

        counter_fx2 = self._create_fx_text(cv2, W//2, int(H*0.10), text="",
                                             font=(fam, max(8, int(11*scale)), "bold"),
                                             anchor="center", sub=True)
        stat_fx     = self._create_fx_text(cv2, W//2, int(H*0.38), text="",
                                            font=(fam, sz_label, "bold"), sub=True,
                                            anchor="center")
        val_fx      = self._create_fx_text(cv2, W//2, int(H*0.52), text="",
                                            font=(fam, sz_val, "bold"), anchor="center")
        div2_id     = cv2.create_line(int(W*0.5 - W*0.175), int(H*0.63),
                                      int(W*0.5 + W*0.175), int(H*0.63),
                                      fill=BLACK, width=2)

        idx_ref    = [0]
        fading_ref = [False]

        nav_y = int(H * 0.90)

        def apply_alpha(alpha):
            bg_c = _lerp_colour(BLACK, t["bg_root"], alpha)
            ov.configure(bg=bg_c)
            cv2.configure(bg=bg_c)
            if bg_frames2:
                idx2 = min(round(alpha * STEPS), len(bg_frames2) - 1)
                if idx2 not in _bg_cache2:
                    _bg_cache2[idx2] = ImageTk.PhotoImage(bg_frames2[idx2])
                cv2.itemconfigure(bg_img2, image=_bg_cache2[idx2])
            else:
                cv2.itemconfigure(bg_img2, image="")
            self._update_fx_text(cv2, counter_fx2, alpha, self._reveal_sub_col(), BLACK, sub=True)
            self._update_fx_text(cv2, stat_fx,     alpha, t["fg_accent3"], BLACK, sub=True)
            self._update_fx_text(cv2, val_fx,  alpha, self._reveal_title_col(), BLACK)
            cv2.itemconfigure(div2_id,     fill=_lerp_colour(BLACK, t["fg_accent2"],          alpha))

        def fade_in(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(1.0); fading_ref[0] = False
                if then: then()
                return
            apply_alpha(step / STEPS)
            ov.after(MS, lambda: fade_in(step + 1, then))

        def fade_out(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(0.0)
                if then: then()
                return
            apply_alpha(1.0 - step / STEPS)
            ov.after(MS, lambda: fade_out(step + 1, then))

        def build_nav(i):
            bkw = dict(relief="flat", bd=0, padx=btn_padx, pady=btn_pady, cursor="hand2")
            btns = []
            if i > 0:
                btns.append(tk.Button(cv2, text="◀  Previous", command=lambda: go(i-1),
                          bg=t["bg_field"], fg=t["fg_main"],
                          activebackground=t["fg_accent2"], activeforeground=t["bg_root"],
                          font=(fam, sz_btn), **bkw))
            next_or_done = i < total - 1
            btns.append(tk.Button(cv2,
                      text="Next  ▶" if next_or_done else "✅  Done",
                      command=(lambda: go(i+1)) if next_or_done else finish,
                      bg=t["roll_bg"], fg=t["fg_main"],
                      activebackground=t["roll_hover"], activeforeground=t["fg_main"],
                      font=(fam, sz_btn, "bold"), **bkw))
            btns.append(tk.Button(cv2, text="✕  Skip", command=finish,
                      bg=t["bg_field"], fg=t["fg_sub"],
                      activebackground=t["fg_banned"], activeforeground=t["bg_root"],
                      font=(fam, sz_btn), **bkw))
            self._canvas_nav_buttons(cv2, W // 2, nav_y, btns)

        def load_card(i):
            s, v = stats[i]
            idx_ref[0] = i
            full_name = STAT_DISPLAY_NAMES.get(s, s)
            cv2.itemconfigure(counter_fx2["main"],   text=f"{i+1}  /  {total}")
            for oid in counter_fx2["outline"]:        cv2.itemconfigure(oid, text=f"{i+1}  /  {total}")
            cv2.itemconfigure(stat_fx["main"],     text=full_name)
            for oid in stat_fx["outline"]:         cv2.itemconfigure(oid, text=full_name)
            cv2.itemconfigure(val_fx["main"],      text=str(v))
            for oid in val_fx["outline"]:          cv2.itemconfigure(oid, text=str(v))
            for gid, _ in val_fx["glow"]:          cv2.itemconfigure(gid, text=str(v))
            build_nav(i)

        def show_card(i):
            load_card(i); fading_ref[0] = True; fade_in()

        def go(i):
            if fading_ref[0]: return
            fading_ref[0] = True
            fade_out(then=lambda: show_card(i))

        def finish():
            if fading_ref[0]: return
            fading_ref[0] = True
            def _close():
                if ov.winfo_exists():
                    ov.grab_release(); ov.destroy()
                if on_close: on_close()
            fade_out(then=_close)

        def on_key(event):
            i = idx_ref[0]
            if event.keysym in ("Right", "space", "Return"):
                if i < total - 1: go(i+1)
                else: finish()
            elif event.keysym == "Left" and i > 0:
                go(i-1)
            elif event.keysym == "Escape":
                finish()

        ov.bind("<KeyPress>", on_key)
        ov.focus_set()
        show_card(0)

    # ── Nature dramatic reveal ─────────────────────────────────────────────────

    def _dramatic_reveal_nature(self, on_close=None):
        if not self._rolled_nature:
            return

        t      = self._t
        BLACK  = "#000000"
        name, boost, reduce = self._rolled_nature
        STEPS, MS = self._get_reveal_fade()

        ov, W, H = self._make_overlay(BLACK)
        scale    = min(W / 1320, H / 820)
        fam      = self.reveal_font_var.get()
        sz_name  = max(18, int(self.reveal_font_size_var.get() * scale))
        sz_stat  = max(10, int(18 * scale))
        sz_btn   = max(8,  int(10 * scale))
        btn_pady = max(4, int(8 * scale))
        btn_padx = max(8, int(18 * scale))

        cv3 = tk.Canvas(ov, highlightthickness=0, bg=BLACK)
        cv3.place(x=0, y=0, width=W, height=H)

        _bg_cache3: dict = {}
        bg_frames3 = None
        bg_full_pil3 = self._get_reveal_bg_pil_raw("nature", W, H)
        if bg_full_pil3 is not None and _PIL_OK:
            try:
                black_img3 = Image.new("RGB", (W, H), (0, 0, 0))
                bg_frames3 = [
                    Image.blend(black_img3, bg_full_pil3, min(step / max(STEPS, 1), 1.0))
                    for step in range(STEPS + 2)
                ]
            except Exception:
                bg_frames3 = None
        bg_img3  = cv3.create_image(0, 0, anchor="nw")

        name_fx3   = self._create_fx_text(cv3, W//2, int(H*0.38), text=name,
                                           font=(fam, sz_name, "bold"), anchor="center")
        div3_id    = cv3.create_line(int(W*0.5 - W*0.15), int(H*0.52),
                                     int(W*0.5 + W*0.15), int(H*0.52),
                                     fill=BLACK, width=2)
        boost_text  = f"Boosts  {boost}"  if boost  else "Neutral nature"
        reduce_text = f"Reduces  {reduce}" if reduce else ""
        boost_fx   = self._create_fx_text(cv3, W//2, int(H*0.60), text=boost_text,
                                           font=(fam, sz_stat, "bold"), sub=True,
                                           anchor="center")
        reduce_fx  = self._create_fx_text(cv3, W//2, int(H*0.70), text=reduce_text,
                                           font=(fam, sz_stat, "bold"), sub=True,
                                           anchor="center")

        fading_ref = [False]
        nav_y = int(H * 0.90)

        def apply_alpha(alpha):
            bg_c = _lerp_colour(BLACK, t["bg_root"], alpha)
            ov.configure(bg=bg_c)
            cv3.configure(bg=bg_c)
            if bg_frames3:
                idx3 = min(round(alpha * STEPS), len(bg_frames3) - 1)
                if idx3 not in _bg_cache3:
                    _bg_cache3[idx3] = ImageTk.PhotoImage(bg_frames3[idx3])
                cv3.itemconfigure(bg_img3, image=_bg_cache3[idx3])
            else:
                cv3.itemconfigure(bg_img3, image="")
            self._update_fx_text(cv3, name_fx3,  alpha, self._reveal_title_col(), BLACK)
            cv3.itemconfigure(div3_id,  fill=_lerp_colour(BLACK, t["fg_accent2"], alpha))
            self._update_fx_text(cv3, boost_fx,  alpha,
                                 "#69db7c" if boost else self._reveal_sub_col(), BLACK, sub=True)
            self._update_fx_text(cv3, reduce_fx, alpha,
                                 "#ff6b6b" if reduce else self._reveal_sub_col(), BLACK, sub=True)

        def fade_in(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(1.0); fading_ref[0] = False
                if then: then()
                return
            apply_alpha(step / STEPS)
            ov.after(MS, lambda: fade_in(step + 1, then))

        def fade_out(step=0, then=None):
            if not ov.winfo_exists(): return
            if step > STEPS:
                apply_alpha(0.0)
                if then: then()
                return
            apply_alpha(1.0 - step / STEPS)
            ov.after(MS, lambda: fade_out(step + 1, then))

        def finish():
            if fading_ref[0]: return
            fading_ref[0] = True
            def _close():
                if ov.winfo_exists():
                    ov.grab_release(); ov.destroy()
                if on_close: on_close()
            fade_out(then=_close)

        def build_nav():
            bkw = dict(relief="flat", bd=0, padx=btn_padx, pady=btn_pady, cursor="hand2")
            btns = [
                tk.Button(cv3, text="✅  Done", command=finish,
                      bg=t["roll_bg"], fg=t["fg_main"],
                      activebackground=t["roll_hover"], activeforeground=t["fg_main"],
                      font=(fam, sz_btn, "bold"), **bkw),
                tk.Button(cv3, text="✕  Close", command=finish,
                      bg=t["bg_field"], fg=t["fg_sub"],
                      activebackground=t["fg_banned"], activeforeground=t["bg_root"],
                      font=(fam, sz_btn), **bkw),
            ]
            self._canvas_nav_buttons(cv3, W // 2, nav_y, btns)
        build_nav()

        def on_key(event):
            if event.keysym in ("Return", "space", "Escape"):
                finish()
        ov.bind("<KeyPress>", on_key)
        ov.focus_set()
        fading_ref[0] = True
        fade_in()

    # ══════════════════════════════════════════════════════════════════════════
    #  Auto-update
    # ══════════════════════════════════════════════════════════════════════════

    def _check_for_update(self):
        def worker():
            try:
                req = Request(GITHUB_API,
                              headers={"User-Agent": "ThenWeRoll/" + VERSION,
                                       "Accept": "application/vnd.github+json"})
                with urlopen(req, timeout=8) as r:
                    data = json.loads(r.read().decode())
                tag = data.get("tag_name", "").lstrip("vV")

                def _ver(v):
                    try:
                        return tuple(int(x) for x in v.strip().split("."))
                    except Exception:
                        return ()

                # Only prompt for genuinely newer releases (never downgrades)
                if tag and _ver(tag) > _ver(VERSION):
                    self.root.after(0, lambda: self._prompt_update(tag))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _prompt_update(self, new_version: str):
        if not messagebox.askyesno(
                APP_TITLE,
                f"A new version is available:  v{new_version}  (you have v{VERSION})\n\n"
                "Download and install it now?\n"
                "The app will restart automatically after updating.",
                icon="info"):
            return
        threading.Thread(target=self._download_and_replace, daemon=True).start()

    def _download_and_replace(self):
        import tempfile, shutil
        self.root.after(0, lambda: self.status_var.set("Downloading update…"))
        try:
            req = Request(GITHUB_RAW,
                          headers={"User-Agent": "ThenWeRoll/" + VERSION})
            with urlopen(req, timeout=30) as r:
                new_src = r.read()
            script_path = os.path.abspath(__file__)
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".py",
                                                dir=os.path.dirname(script_path))
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    f.write(new_src)
                shutil.move(tmp_path, script_path)
            except Exception:
                try: os.unlink(tmp_path)
                except Exception: pass
                raise
            self._download_data_updates()
            self.root.after(0, self._restart_after_update)
        except Exception as e:
            self.root.after(0, lambda: (
                self.status_var.set("Update failed."),
                messagebox.showerror(APP_TITLE,
                    f"Update download failed:\n{e}\n\n"
                    "You can update manually at:\n"
                    "https://github.com/ValoTypeDark/Ability-Randomiser")))

    def _download_data_updates(self):
        """Refresh shipped data files (ability/Pokémon caches, tab icons) from
        the repo so users get corrected data with the script update.
        Non-fatal: the script update still succeeds if these downloads fail,
        and per-user files (settings, bans, avatar) are never touched."""
        import tempfile, shutil

        shipped = [("data/abilities.json", ABILITIES_FILE, "json")]
        shipped += [("data/pokemon.json", POKEMON_FILE, "json")]
        shipped += [(f"data/icons/{os.path.basename(p)}", p, "png")
                    for p in TAB_ICONS.values()]

        base = GITHUB_RAW.rsplit("/", 1)[0]
        for rel_path, dest, kind in shipped:
            try:
                req = Request(f"{base}/{rel_path}", headers={
                    "User-Agent": "ThenWeRoll/" + VERSION})
                with urlopen(req, timeout=30) as r:
                    raw = r.read()
                # Only install files that look valid
                if kind == "json":
                    json.loads(raw.decode("utf-8"))
                elif kind == "png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                    continue
                tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(dest))
                try:
                    with os.fdopen(tmp_fd, "wb") as f:
                        f.write(raw)
                    shutil.move(tmp_path, dest)
                except Exception:
                    try: os.unlink(tmp_path)
                    except Exception: pass
                    raise
            except Exception:
                pass

    def _restart_after_update(self):
        messagebox.showinfo(APP_TITLE, "Update installed!\n\nThe app will now restart.")
        self.root.destroy()
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--update-abilities" in sys.argv:
        print("Fetching abilities from PokéAPI…")
        def _cli_progress(cur, tot, name):
            print(f"\r  {cur}/{tot}  {name:<40}", end="", flush=True)
        _abilities = fetch_all_abilities(progress_cb=_cli_progress)
        print(f"\nSaving {len(_abilities)} abilities to {ABILITIES_FILE}")
        save_abilities_json(_abilities)
        print("Done.")
        sys.exit(0)

    root = tk.Tk()
    AbilityRandomizerApp(root)
    root.mainloop()
