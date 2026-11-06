# Translating the map

The map is available in French, English and Dutch. All the interface text lives in JSON files in `i18n/`, one per language, so you can fix or improve a translation without touching the code.

## Where the text lives

`i18n/fr.json` is the reference. The other files (`en.json`, `nl.json`) have exactly the same keys, with the text in their own language:

```json
"status.missing": "Missing from OSM",
"lasso.selected": { "one": "address selected", "other": "addresses selected" },
"search.networkError": "Network: {message}"
```

Keys are grouped by the part of the page they belong to. `meta.*` covers the page title and the preview shown when the link is shared. The filter panel uses `panel.*`, `status.*`, `stats.*` and `bar.*`. Then come `search.*`, `lasso.*`, `basemap.*`, `popup.*` for the address popup, `lang.*` and `banner.*` for the language menu and the banner that suggests another language, and a few small groups such as `versions.*`, `toast.*` or `attribution.*`. To see where a key appears, search for it in `templates/index.html.j2` and `js/`, or compare with the French page.

`i18n/languages.json` lists the languages the site is built in, with the URL path, locale and display name of each.

## Fixing or improving a translation

Change the text after the colon and leave the key alone. A few rules keep the checks passing:

- Keep the words in braces, such as `{message}` or `{label}`, exactly as they are. The page fills them in, and every language must use the same ones.
- A value with `one` and `other` is a plural. `one` is used for a count of 1 (and of 0 in French), `other` for the rest. If your language needs more forms, use the names defined by `Intl.PluralRules` (`few`, `many`…); `other` is always required.
- Do not translate product names: OpenStreetMap, OSM, UrbIS, JOSM, Mapillary, Panoramax, INSPIRE, ZinnekeTiles, databrussels.be.
- The `banner.*` texts are shown to people reading the site in another language, to offer them yours. Write them in your language, as you would say it to a speaker of it: "This map is also available in English."
- The search placeholder (`search.placeholder`) gets 147 pixels on every screen size, and a test fails if it does not fit. The Dutch text had to become "Straat… (huisnummer)" for that reason.
- The statistics labels (`stats.*`) share a line with a number, so abbreviations such as "Geverif. afwezig" are fine there. The full `status.*` labels are used in the filter list and in the popup.

If a key is missing from your file, the page falls back to the French text. `check-i18n.py` reports that as an error, so it cannot reach the live site.

Some text on the map does not come from these files. Street and municipality names come from UrbIS, which has a French and a Dutch name for each; the Dutch page shows the Dutch name first, the other pages the French one. The `.osm` export follows OpenStreetMap conventions and is the same in every language.

## Adding a language

Add an entry to `i18n/languages.json`:

```json
"de": { "path": "de/", "locale": "de-BE", "og": "de_BE", "name": "Deutsch", "data": "fr" }
```

`path` is the folder the page is published under and `locale` sets the number and date formats. `og` is the locale given to link previews on social networks, and `name` is how the language appears in the language menu, written in that language. `data` is the language used for street names and for the UrbIS address search, which only knows French (`fr`) and Dutch (`nl`).

Then copy `i18n/en.json` to `i18n/de.json` and translate the values.

The build generates `/de/` from these two files. It also adds the language to the menu, the `hreflang` links and the suggestion banner, and the tests cover it without any change. Links to databrussels.be keep no language prefix for a new language, because that site only has French, Dutch and English pages.

## Checking your changes

The quickest check needs only Python:

```sh
python3 check-i18n.py
```

It reports a missing or extra key, braces that differ from the French text, a plural without `other`, an empty value, a language declared without a file (or a file without a declaration), and French text written directly in the template or the JavaScript.

To see the result in a browser:

```sh
pip install -r requirements-dev.txt
python3 fetch-data.py
python3 build-site.py
python3 serve-local.py --dir _site
```

Then open `http://127.0.0.1:8000/` and your language's folder, for example `http://127.0.0.1:8000/nl/`. When served locally, the page writes an `[i18n] clé absente` warning in the browser console for every key it cannot find.

The full test suite also needs Node.js 22 or later:

```sh
npm test
python3 -m playwright install chromium
python3 -m pytest tests
```

## Sending your changes

You do not need a local setup to contribute. Open the JSON file on GitHub, click the pencil icon and propose your change: GitHub creates the fork and the pull request for you. Every pull request runs the checks above in GitHub Actions. The run also keeps screenshots of each language on desktop and mobile, under the `screenshots` artifact, so you can see your text on the page.

To point out a wording problem without editing anything, open an issue with the key, the current text and your suggestion.
