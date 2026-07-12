# 🎲 Then We Roll - Pokémon Randomizer

A desktop randomiser for "Then We Fight" style challenge content. Roll random **abilities**, **Pokémon**, **typings**, **stat spreads**, and **natures** - filtered to what's actually available in the game you're playing. Built with Python and tkinter, works fully offline.

> Formerly known as the *Pokémon Ability Randomizer* - it outgrew the name.

---

## Features

### ⚡ Abilities
- **Roll abilities** from any combination of generations (Gen III–IX), or pick a **game preset** and the generations set themselves
- **Pokémon Champions** preset includes the Champions-exclusive Mega abilities (Piercing Drill, Dragonize, Mega Sol, Spicy Spray, Eelevate, Fire Mane) - hidden from every other game
- **Ban / Cringe list** - mark abilities you never want to see, with **Ban & Reroll** mid-session
- **Ability browser** - search the full ability list with effect descriptions

### 🎲 Pokémon
- **Accurate per-game pools** - each game preset rolls only Pokémon actually obtainable in that game: its regional dex, wild/static encounters (post-game areas, roamers, ORAS soaring, USUM Ultra Wormholes), in-game gifts, and event distributions, expanded to whole evolution families
- **Include transfers toggle** - adds everything that can be brought *into* the game via Pokémon HOME / Pal Park / Poké Transfer / Bank, using each game's real compatibility list (664 species for Sword/Shield, 733 for Scarlet/Violet)
- **Pokémon Champions** roster pulled live from PokéAPI (current regulation, 208 species)
- **Alternate forms** - Deoxys forms, Galarian birds, Therian genies, Hoopa Unbound and more, each restricted to the games they exist in
- **Type filter** and **category filters** (Baby / Base / Stage 1 / Stage 2+ / Legendary / Mythical / Paradox)
- **Shiny chance** - configurable odds (1 in X or %) with shiny sprites

### 🎨 Typing & 📊 Stats
- Roll **type combinations** (single / dual / mixed / weighted), with type bans and optional **Tera type**
- Roll **stat spreads** - free roll, BST range, or fixed BST, with optional per-stat min/max, drawn on a radar chart
- Roll **natures** with boost/reduce display

### 🎭 Presentation
- **Dramatic Reveal mode** for every roll type - full-window fade-in reveals with customisable fonts, colours, outlines, glow, and background images
- **10 themes** (Pokédex, Charizard, Bulbasaur, Blastoise, Gengar, Pikachu, Glaceon, Umbreon, Sylveon, Team Rocket), switchable live
- **Profile card** with trainer name and avatar
- **Persistent settings** - everything is saved between sessions, with export/import

---

## Requirements

- **Python 3.8 or newer** with tkinter (included by default on Windows/macOS installers)
- **[Pillow](https://pypi.org/project/Pillow/)** - recommended: needed for Pokémon sprites, tab icons, avatars, and reveal backgrounds

### Installing Python (if you don't have it)

**Windows**
1. Download Python from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer and **tick "Add Python to PATH"** on the first screen
3. Open Command Prompt and install Pillow:
   ```
   pip install Pillow
   ```

**macOS**
1. Install Python from [python.org/downloads](https://www.python.org/downloads/) (the python.org installer includes tkinter - the Homebrew version does not by default)
2. In Terminal:
   ```
   pip3 install Pillow
   ```

**Linux (Debian/Ubuntu)**
```
sudo apt install python3 python3-tk python3-pip
pip3 install Pillow
```

To check everything is ready: `python --version` (or `python3 --version`) should print 3.8 or higher.

---

## Setup

**Option A: Download the release zip (recommended)**

The zip contains the script plus up-to-date ability and Pokémon data. Extract and run - no downloads needed:

```
python then_we_roll.py
```

**Option B: Script only**

If you only have `then_we_roll.py`, the app will offer to fetch its data from PokéAPI on first run:

- Abilities: click **🔄 Update from PokéAPI** on the Abilities tab (1–3 minutes)
- Pokémon: open **ℹ️ Pokémon Data** on the Pokémon tab and click **Fetch / Refresh** (a few minutes)

Both fetches overwrite any previously saved data - you'll be asked to confirm. They're not needed when using the zip, and updates ship with the app.

---

## File structure

```
then_we_roll.py
data/
  abilities.json        ← ability data (shipped in the zip)
  pokemon.json          ← Pokémon data: game pools, types, species (shipped in the zip)
  icons/                ← tab icons (shipped in the zip)
  settings.json         ← auto-saved preferences (created per user)
  avatar.png            ← your profile picture (created when you set one)
  pokemon_sprites/      ← sprite cache (downloaded as needed)
```

All data is stored relative to the script, so the whole folder is portable.

---

## How game pools work

Selecting a game preset on the Pokémon tab limits rolls to that game's availability:

- **In-game (default rules):** regional Pokédex + wild/static encounter data + in-game gifts and official event distributions - no trading with other games required. If you can catch it, breed it, or evolve it on that cartridge, it can be rolled.
- **Include transfers (checkbox, on by default):** additionally rolls everything that can be brought into the game - Pal Park, Poké Transfer, Bank/Transporter, Pokémon HOME, and Mystery Gift. Games with a dex cut (Sword/Shield, Scarlet/Violet) use their real compatibility lists, so nothing impossible ever shows up.
- **Pokémon Champions:** the current regulation roster, fixed regardless of the transfers toggle.
- **Custom:** every Pokémon.

---

## Dramatic Reveal

Every roll type has a **🎭 ROLL DRAMATICALLY** button that reveals results one at a time with a full-window fade-in. Customise fonts, sizes, colours, outlines, glow, and background images (global or per reveal type) on the Settings tab, with a live preview.

| Key | Action |
|-----|--------|
| `→` / `Space` / `Enter` | Next (or Done on last) |
| `←` | Previous |
| `Esc` | Skip reveal |

---

## Themes

Switch themes using the dropdown in the header. The theme is applied live and saved for next time.

| Theme | Vibe |
|-------|------|
| Pokédex (Default) | Dark navy with gold and electric blue |
| 🔥 Charizard | Deep orange and ember |
| 🌿 Bulbasaur | Dark green and lime |
| 💧 Blastoise | Deep blue and aqua |
| 👻 Gengar | Dark purple and lavender |
| ⚡ Pikachu | Dark yellow and gold |
| ❄️ Glaceon | Icy blue and frost |
| 🌙 Umbreon | Near-black with ring gold |
| 🌸 Sylveon | Dark pink and ribbon blue |
| 🖤 Team Rocket | Black and villain red |

---

## Auto-update

On launch, the app checks the [GitHub releases page](https://github.com/ValoTypeDark/Ability-Randomiser/releases) for a newer version. Accepting the update:

- Replaces the script and restarts the app
- Also refreshes the shipped data files (`abilities.json`, `pokemon.json`, tab icons) so pools stay accurate without a manual fetch
- Never touches your settings, ban lists, or avatar

If the download fails, the current version is left intact.

---

## Troubleshooting

**"No Pokémon data found" / "No ability cache found"** - you're running the script without the data files. Use the in-app fetch buttons (see Setup, Option B) or download the release zip.

**Sprites, icons, or avatar don't load** - install Pillow (`pip install Pillow`) and restart the app.

**tkinter not found** - on Linux you may need to install it separately: `sudo apt install python3-tk`

**A Pokémon/ability appears that shouldn't (or is missing)** - pool data is curated; open an issue on GitHub with the game and Pokémon and it can be fixed in the next update.

**PokéAPI fetch fails** - fetching requires an internet connection. The app works fully offline once data exists (the release zip includes everything).
