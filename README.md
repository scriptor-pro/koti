# koti

A small command-line tracker for daily rituals. It keeps a plain CSV journal of
what was done and when, and turns it into streaks, records, regularity rates,
a calendar and an average time of day, shown in the terminal and on a static
web page.

The interface, messages and identifiers are in French.

## How it works

- Code and data live in separate places. This repository holds the code; your
  rituals and journal live in a data directory, `~/.local/share/koti` by
  default.
- `taches.json` defines the rituals.
- `completions.csv` is the journal and the only source of truth: one line per
  completion.
- Every statistic is recomputed from the journal each time; nothing derived is
  stored.
- `gabarit.html` is the page template. Each run writes a self-contained
  `koti.html` into the data directory; its JavaScript only renders what Python
  computed.
- After each tick the page is regenerated and, if publishing is configured,
  uploaded to bunny.net.

Requirements: Python 3.11 or later, standard library only. Publishing also
needs `curl`; the optional journal backup needs `git`.

## Install

```bash
git clone https://github.com/scriptor-pro/koti.git
cd koti
ln -s "$PWD/koti.py" ~/.local/bin/koti

mkdir -p ~/.local/share/koti
cp taches.exemple.json ~/.local/share/koti/taches.json
```

Then edit `~/.local/share/koti/taches.json` to describe your own rituals.
`~/.local/bin` must exist and be on your `PATH`.

Optionally, install the Claude Code skill that drives the command:

```bash
ln -s "$PWD/skill" ~/.claude/skills/koti
```

The script resolves the symlink to find its modules, so the repository can
live anywhere. To keep the data elsewhere, set `KOTI_DONNEES`:

```bash
export KOTI_DONNEES=~/Documents/rituels
```

## Usage

```bash
koti                                  # today's list
koti fait lecture marche              # tick two rituals, now
koti fait lecture --heure 08:15       # tick with the actual time
koti fait marche --date 2026-10-12    # tick for a past day
koti page                             # regenerate and republish the page
koti --help                           # full help, including the list of rituals
```

A ritual can be named by its identifier, the start of its identifier, or words
from its title; accents and case are ignored. An unknown or ambiguous name
cancels the whole command and nothing is written.

| Option | Applies to | Effect |
|---|---|---|
| `--heure HH:MM` | `fait` | Time to record. Defaults to the time of the command. |
| `--date AAAA-MM-JJ` | `fait` | Tick for a past day. Without `--heure` the time is left empty. Future dates are refused. |
| `--no-upload` | `fait`, `page` | Regenerate the page without publishing it. |
| `--configure-cache` | `page` | Set the bunny.net Edge Rule that disables browser caching of the page. Run once. |

`koti fait` exits with status 1 in two cases:

- **Nothing to tick**: every named ritual was already ticked that day or is not
  yet allowed (see fixed time below). Nothing is written.
- **Publishing failed**: the journal line *is* written. Do not rerun
  `koti fait`; run `koti page` to publish again.

## Rules

- **Streak**: strict. A missed day resets it to zero. A ritual not yet done
  today does not break the streak; it counts up to yesterday until the day is
  over.
- **Record**: the longest run of consecutive days.
- **Regularity**: days done over days elapsed, for the last 7 days, the last
  30 days and since the ritual started. Today only counts once it is done.
- **Average time**: a circular mean, so 23:50 and 00:10 average to midnight,
  not noon. Completions without a time are left out. The recorded time is when
  the tick was declared, unless `--heure` says otherwise.
- **Fixed time**: a ritual with `heure_fixe` cannot be ticked for today before
  that time.

## Data

All of the following live in the data directory (`~/.local/share/koti`, or
`$KOTI_DONNEES`).

### `taches.json`

```json
{
  "taches": [
    {
      "id": "marche",
      "titre": "Marche de midi",
      "debut": "2026-09-03",
      "heure_fixe": "12:00",
      "notes": "…"
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Short, stable identifier used in the journal and on the command line. |
| `titre` | yes | Display title. |
| `debut` | yes | Start date; the calendar and rates begin here. |
| `heure_fixe` | no | `"HH:MM"`, or `null`. |
| `notes` | no | Free text, shown in a collapsible block on the page. |
| `sans_serie` | no | `true` to track the ritual without streak, record, rates or missed days. |

The order of the array is the display order. To add a ritual, add an entry and
run `koti page`.

### Rituals without a streak

Some habits are better served by "did I touch it today" than by a score. With
`"sans_serie": true`, a ritual shows only its number of sessions, its average
time and a calendar where days without a session are neutral. Its streak,
record and rates are not computed into the published data at all, and it is
left out of the "N of M done" count.

### `completions.csv`

```csv
date,heure,tache
2026-10-12,,marche
2026-10-13,08:15,lecture
```

One line per completion, at most one per ritual per day. `heure` may be empty.
The file is created on the first tick. It is only ever appended to by
`koti fait`, and it can be corrected by hand: a malformed line is reported with
its line number and nothing is written or published until it is fixed.

### Backing up the journal

If the data directory is a git repository, koti commits `taches.json` and
`completions.csv` after every `koti fait` and `koti page`. It never creates the
repository itself; to turn the backup on:

```bash
cd ~/.local/share/koti
git init
printf '%s\n' 'koti.html' '.bunny_config.json' > .gitignore
git add .gitignore taches.json && git commit -m "Initial data"
```

Git needs an identity (`git config user.name` and `git config user.email`) for
the commits to succeed. A failing commit only prints a warning; the tick itself is never undone.

## Publishing

Publishing is optional. Without `.bunny_config.json` in the data directory,
koti works locally and says that publishing was skipped.

```bash
cp bunny_config.exemple.json ~/.local/share/koti/.bunny_config.json
chmod 600 ~/.local/share/koti/.bunny_config.json
```

Fill in the storage zone, the pull zone and the hostname, then
`storage_access_key` (the storage zone password) and
`token_auth_security_key` (the pull zone's token authentication key).

Each publication uploads `koti.html` to the storage zone, prints a signed URL
and purges the CDN cache. The purge and `--configure-cache` use a bunny.net API
key read from the `BUNNY_API_KEY` environment variable or from
`~/.config/koti/bunny.env` (a line `BUNNY_API_KEY=…`).

The pull zone must have token authentication enabled: the page is only
reachable through a signed URL. This is also why the Luciole font is embedded
in the page as base64 rather than served as separate files, which the browser
would request without a token.

When the page was generated on an earlier day, it says so and labels the
state it shows with that date instead of presenting it as today's.

## Layout

| File | Role |
|---|---|
| `koti.py` | Command line: name matching, ticking, day list, page generation. |
| `calculs.py` | Pure functions: streak, record, rates, calendar, average time. |
| `donnees.py` | Reading and validating `taches.json` and the journal; appending to the journal. |
| `sauvegarde.py` | Local git commit of the data directory. |
| `publication.py` | bunny.net upload, signed URL, cache purge, Edge Rule. |
| `gabarit.html` | The page template, without data. |
| `taches.exemple.json` | Example rituals to start from. |
| `bunny_config.exemple.json` | Publishing configuration template. |
| `skill/SKILL.md` | Claude Code skill (`/koti`) that drives the command. |
| `tests/` | Unit tests. |

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

The tests use temporary directories only. They never touch the real data
directory, the network or the publishing credentials.

## Privacy

Rituals, the journal and the generated page are personal data. They live in
the data directory, outside this repository, and `.gitignore` lists their file
names as a safeguard. Keep them out of any public repository, and keep the
published page behind token authentication.

## License

koti is free software, released under the GNU General Public License,
version 3 or (at your option) any later version. See [LICENSE](LICENSE).

The page is set in [Luciole](https://www.luciole-vision.com/), © Laurent
Bourcellier & Jonathan Perez, licensed under CC BY 4.0 (see
`licences/Luciole-LICENSE.txt`); the font is embedded in `gabarit.html`.
Newsreader and IBM Plex Mono are loaded from fonts.bunny.net.
