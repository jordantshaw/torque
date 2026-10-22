# Adding a bike model

A bike model is an owner's manual typed into one YAML file in `bike_models/`.
No code changes are needed.

## Contents

- [Steps](#steps)
- [Example](#example)
- [Header fields](#header-fields)
- [Items](#items)
- [Intervals](#intervals)
- [Action codes](#action-codes)
- [Reading a manual](#reading-a-manual)
- [Variants](#variants)
- [Suspension](#suspension)
- [Descriptions](#descriptions)
- [Getting text out of a PDF](#getting-text-out-of-a-pdf)
- [Check your file](#check-your-file)
- [Go live](#go-live)
- [Mistakes to avoid](#mistakes-to-avoid)

## Steps

1. Find the service schedule in the manual and note its page numbers.
2. Decide the unit: engine hours, or kilometres.
3. Create `bike_models/<make>-<model>-<year>.yaml` with the header fields.
4. Add one item per row of the schedule.
5. Give each item a description and its manual page.
6. Put anything the app can't track in `notes`.
7. [Check the file](#check-your-file), then [go live](#go-live).

Real files to copy from: `beta-300-rr-race-2026.yaml` (a printed grid and
variants), `ktm-300-xcw-2017.yaml` (repeating rules), and
`surron-ultra-bee-2026.yaml` (kilometres).

## Example

```yaml
# example: valid
key: acme-250-2025
display_name: "2025 Acme 250 Enduro"
engine: "250 2T"
unit: hours
items:
  - key: gear_oil
    category: Engine
    name: Gear oil
    description: "Check the level through the sight glass. Drain it while the engine is warm and refill with the oil the manual specifies."
    schedule_page: "40"
    page: "52"
    actions: {3: S, 30: S, 60: S, 90: S}
  - key: spark_plug
    category: Engine
    name: Spark plug
    description: "Take it out with the engine cold. Clean the electrode, check the gap, and replace it if the insulator is cracked."
    schedule_page: "40"
    page: "61"
    every_hours: 30
    action: C
  - key: chain
    category: Drivetrain
    name: Chain and sprockets
    description: "Keep the chain clean and lubricated, and check the slack against the manual."
    schedule_page: "41"
    every_hours: 20
    once_at: [1]
    action: C/R

notes:
  - "After the first 100 km, recheck the rear sprocket and the brake discs."
  - "The brake fluid is changed every 12 months; the app counts hours, so keep an eye on the calendar."

suspension:
  settings:
    - name: Fork compression (clicks out)
      factory: "12"
      racing: "7"
      comfort: "9"
      soft: "11"
  fixed_values:
    Fork spring: "0.38 kg"
    Static sag: "25-45 mm"
  source: "Acme setting sheet, March 2025."

variants:
  - key: acme-200-2025
    display_name: "2025 Acme 200 Enduro"
    engine: "200 2T"
    overrides:
      spark_plug: {every_hours: 40, action: C}
```

## Header fields

| Field | Required | Meaning |
| --- | --- | --- |
| `key` | yes | Unique id, like `ktm-300-xcw-2017`. Bikes remember their model by it, so never change it once in use. |
| `display_name` | yes | The name shown in the "Add a bike" list. |
| `engine` | yes | A short engine description. |
| `unit` | no | `hours` (default) or `km`. |
| `upcoming_window` | no | How close counts as "coming up", in the model's unit. Default 5 hours or 50 km. |
| `items` | yes | The schedule. |
| `notes` | no | Text lines shown at the bottom of the Maintenance tab. |
| `suspension` | no | Reference settings. |
| `variants` | no | Related bikes that share this schedule. |

## Items

One item per row of the manual's schedule.

| Field | Required | Meaning |
| --- | --- | --- |
| `key` | yes | Unique id in `snake_case`. Completed services are stored against it, so never rename it. |
| `category` | yes | The system ("Engine", "Brakes", ...). Services are split by it. |
| `name` | yes | The row's name. |
| `description` | yes\* | One or two plain sentences: what to do. |
| `schedule_page` | yes\* | The page where the row is printed. |
| `page` | no | The page that explains how to do the job. |
| `actions` or `every_hours` | one of them | The intervals. |

\* Required by the tests for every model that ships with the app.

Categories are free text. A category only gets its own icon if it is listed in
`category_icon` in `app/templates/_icons.html`; otherwise it gets a wrench.

## Intervals

**A printed grid: `actions`.** Copy the marks exactly as the page shows them, as
`hour: code`. Hours are whole, positive numbers.

```yaml
actions: {3: C, 30: C, 60: S, 90: C}
```

**A stated rule: `every_hours`.** For "every 40 hours". (The name is the same
for km models; the number is then kilometres.)

```yaml
every_hours: 40
action: S
```

**Break-in checks: `once_at`.** For "once after 1 hour, then every 20". It needs
`every_hours` and must be an increasing list.

```yaml
every_hours: 20
once_at: [1, 5]
action: C
```

**Hours or distance.** For a distance manual, set `unit: km` and write every
interval in kilometres, even if the manual also prints miles. Riders can switch
a bike's display to miles; the app stores kilometres.

**Past the last point.** `every_hours` items repeat forever. `actions` items are
only projected further when the printed points repeat regularly. Otherwise the
item shows as "past the manual's schedule".

## Action codes

| Code | Shown as |
| --- | --- |
| `C` | Check |
| `S` | Replace |
| `P` | Clean |
| `T` | Tighten |
| `R` | Adjust |
| `C/P` | Check or clean |
| `C/S` | Check or replace |
| `C/R` | Check or adjust |

Use the code the manual prints. For a new one, add it to `VALID_ACTIONS` in
`app/bike_models.py` and `ACTION_LABELS` in `app/routes/bikes.py`.

## Reading a manual

| The manual says | Write |
| --- | --- |
| A grid with marks under 3, 30, 60 ... | `actions: {3: C, 30: C, 60: C}` |
| "Every 40 hours" | `every_hours: 40` and `action` |
| Marks under "after 1 hour" and "every 20 hours" | `every_hours: 20`, `once_at: [1]` |
| Marks under both "every 20" and "every 40" | `every_hours: 20` (it already covers 40) |
| Separate rows per engine (125/200 and 250/300) | The larger set as the base bike, the rest as [variants](#variants) |
| One row listing several parts | One item per part, each with the row's marks |
| "Every 12 months", "annually" | A line in `notes`: the app can't track time |
| "Check before every ride" | A line in `notes` |
| Normal and "motorsports" intervals | Normal in the items, the other in `notes` |

## Variants

When one manual covers related bikes, write the main bike in full and list the
others as `variants`. A variant inherits the items, notes and unit, and changes
only what differs:

```yaml
variants:
  - key: beta-125-rr-race-2026
    display_name: "2026 Beta 125 RR Race"
    engine: "125"
    omit: [battery_12v_check_recharge]      # items this bike lacks
    overrides:                              # a full replacement schedule
      piston_and_segments: {every_hours: 40, action: S}
    suspension: {}                          # replaces the base block; {} for none
```

An override replaces the item's whole schedule but keeps its description and
pages. To share one override between variants, write it once with a YAML anchor
(`&name`) and reuse it (`*name`), as `beta-300-rr-race-2026.yaml` does.

## Suspension

Add the maker's setting sheet if there is one. Each setting needs all five
fields:

```yaml
suspension:
  settings:
    - name: Fork compression (clicks out)
      factory: "9"
      racing: "7"
      comfort: "9"
      soft: "11"
  fixed_values:
    Fork spring: "0.38 kg"
  source: "Where the figures came from, with any caveat."
```

Settings named in `SUSPENSION_FIELD_BY_SETTING_NAME` (`app/routes/rides.py`)
prefill the ride form; others only show on the Suspension tab. With nothing to
show, write `suspension: {}`.

## Descriptions

A description is what you read when you expand an item. Write it for someone with
the bike in front of them.

- Say what to do and what to look for, in one or two sentences.
- Use the manual's own figures (gaps, minimums, torques, fluid levels) and say
  what to do when one is out of range.
- If the manual says nothing, keep to plain guidance and leave out `page`. Never
  invent a figure.
- `schedule_page` is where the row is printed. `page` is the how-to section, if
  you found one.

## Getting text out of a PDF

A PDF with a text layer:

```sh
uv run --with pypdf python -c "
from pypdf import PdfReader
for i, page in enumerate(PdfReader('manual.pdf').pages, 1):
    print(f'=====PAGE {i}====='); print(page.extract_text())
" > manual.txt
```

A scanned PDF (the command above prints nothing). Render the page as an image:

```sh
uv run --with pymupdf python -c "
import fitz
fitz.open('manual.pdf')[34].get_pixmap(dpi=150).save('page-35.png')  # pages count from 0
"
```

**Read the grid on the image.** Text extraction loses a table's columns, so
`C C S C` doesn't say which columns hold the marks.

## Check your file

**1. Is it valid?** The app and the tests both load every model:

```sh
uv run pytest tests/test_model_descriptions.py tests/test_bike_models.py
```

An error names the file and item, for example
`item 'chain' in bike_models/foo.yaml: action 'X' at hour 30 is not a valid action`.
It catches missing fields, duplicate keys, bad action codes, non-positive hours,
a bad `once_at`, an unknown `unit`, variants naming items that don't exist, and
items missing a description or `schedule_page`.

**2. Is it right?** A valid file can still be a wrong transcription. Write a test
that re-reads the manual's table in a different shape from the YAML (for a grid,
column by column) and asserts the two agree. Two independent readings rarely
make the same slip. Copy `tests/test_ultra_bee_model.py` (a grid) or
`tests/test_ktm_model.py` (repeating rules).

## Go live

```sh
docker compose up -d --build
```

The model then appears under **Add a bike**. To mount the folder instead of
rebuilding, see [Deploying](deploying.md#add-or-edit-bike-models).

## Mistakes to avoid

- **Renaming a `key` that bikes use.** Bikes lose their model; renamed items lose
  their history. Add a new model or item instead.
- **Editing printed hours after services are recorded.** A record belongs to a
  service point. If the point disappears, the record stays in the item's history
  but no longer counts as done.
- **Guessing a mark you can't read.** Check another copy of the manual, or leave
  the item out and say why in `notes`.
- **Putting a time rule in `actions`.** "12 months" is not 12 hours. Use `notes`.
