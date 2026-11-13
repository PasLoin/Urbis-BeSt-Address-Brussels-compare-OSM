# Accessibility

The map page aims at WCAG 2.1 level AA, in French, English and Dutch. This covers `templates/index.html.j2`, `style.css` and the modules in `js/`. The 404 page is not audited yet.

## Using the map with a keyboard

Tab moves through the map, the lasso button, the search button, the basemap and language buttons, the language banner when it is shown, the filter panel, the zoom buttons and the attribution links.

When the map has focus, a ring marks the centre of the view. The arrow keys move the map and `+` and `-` zoom, as in any MapLibre map. Enter or Space opens the popup of the address closest to the centre, and focus moves into it, so Tab reaches the Mapillary, Panoramax and JOSM links and the export button. Escape closes the popup and puts focus back on the map.

The freehand lasso needs a mouse or a finger. With a keyboard, turn the lasso on with its button, go back to the map and press Enter: every exportable address in the visible area is selected and focus moves to the export button. Escape closes the selection panel, and focus goes back to the lasso button if it was in the panel.

The search field follows the ARIA combobox pattern. The up and down arrows move through the results, Enter or Tab picks one, the first Escape closes the list and a second one folds the search and returns to the search button. The list also closes as soon as focus leaves the search area, so it never hides the buttons below it. When the search is folded, the field is out of the tab order.

The basemap and language buttons open a small panel that you reach with Tab. Escape closes it and puts focus back on its button, and so does moving focus out of the panel.

## Screen readers

The page has a visually hidden `h1` with its title and three landmarks: `main` for the map and its tools, a `nav` named after the language menu, and an `aside` for the filter panel. A screen reader user can jump straight to the filters without going through the map controls.

The page has one polite status region, `#a11y-status`. It announces the number of search results and the search messages, the lasso mode and the number of selected addresses, the copied INSPIRE ID, and "no address shown in this area" when Enter finds nothing near the centre. The visual toast that says the ID was copied is hidden from screen readers so the message is read once.

The map canvas is named "Address map" and described by a short text that lists the keys above. The MapLibre zoom, compass, attribution and popup close buttons use the page language. The coloured bar in the statistics is hidden from assistive technology because the rows below it give the same figures as text.

The lasso, search source and basemap buttons expose their state with `aria-pressed`. The language links mark the current page with `aria-current`.

## Changes made in November 2026

Small grey text failed 1.4.3 on a white or near-white background. These colours changed:

| Element | Before | After | Ratio after |
| --- | --- | --- | --- |
| Popup footer, search status rows | `#999` | `#595959` | 7.0:1 on white |
| Search placeholder | `#aaa` | `#6b6b6b` | 5.3:1 on white |
| Source dates in the panel | `#888` | `#595959` | 6.3:1 on `#f2f2f2` |
| Search source buttons | `#888` on `#f0f0f0` | `#4a4a4a` | 7.8:1 |
| Search clear button, banner close button | `#bbb`, `#888` | `#595959` | 7.0:1 on white |
| Second line of a search result | `#777` | `#595959` | 6.1:1 on the hover colour |
| OSM and UrbIS badges | white on `#4caf50` and `#4a90d9`, 75 % opacity | white on `#2e7d32` and `#1d4ed8` | 5.1:1 and 6.7:1 |
| Lasso export and cancel buttons | white on `#2ecc71` and `#e74c3c` | white on `#1e7e45` and `#c0392b` | 5.1:1 and 5.4:1 |
| `.osm` button in the popup | white on `#f39c12` | `#1a1a1a` on `#f39c12` | 7.9:1 |
| Attribution background | MapLibre default, 50 % white | 90 % white | link 5.4:1 over a black map |

Every focusable element now shows the same 3 px outline in `#1a3a8f` with a white halo, so it stays visible on light and dark basemaps. Inside the search bar the outline is drawn inside the button, and the field outlines the whole bar. The original `outline: none` on the search field is gone.

The address points were only reachable with a mouse, which failed 2.1.1. The keyboard access described above fixes that. The language menu used `role="menu"` without the arrow key behaviour that role promises, and the basemap menu used radio buttons the same way. Both are now plain disclosure panels with links and toggle buttons. The search results used a listbox with no combobox on the field and a databrussels.be link nested inside each option; the link now appears only in the popup of the selected result.

`#stats-rows` and `#urbis-date` are filled once when the page loads. A live region there would read the whole panel on every visit, so they stay ordinary text.

## Automated checks

`tests/test_accessibility.py` runs with the other Playwright tests, after the site is built:

```sh
python3 -m pytest tests/test_accessibility.py -v
```

It uses axe-core through `axe-playwright-python` and audits the page in several states: on load in each language, and in French with search results open, with a search message, with each menu open, with an address popup, with the lasso panel and with the copy toast. Before each audit the test hides the map canvas and puts black behind the semi-transparent panels, which is the worst background they can get over a real basemap. axe cannot read colours from the map tiles.

An axe violation fails the build when it belongs to one of the criteria this work fixed: 1.4.3, 1.4.11, 2.1.1, 2.1.2, 2.4.1, 2.4.7, 4.1.2 or 4.1.3. axe never reports a missing bypass as a violation, only as a check to review, so the test treats that `bypass` result as a failure too. Any other WCAG 2.1 A or AA violation, and any check axe could not finish for those criteria, appears as a pytest warning. The full results of each state go to `a11y-report/`, which the `Site` and `CI` workflows upload as the `a11y-report-<run id>` artifact. To make another criterion blocking, add its axe tag (for example `wcag131`) to `BLOCKING_TAGS`.

axe does not test keyboard use, so the same file checks it directly. The tests walk the whole tab order and fail if focus gets stuck or if an element has no visible focus. They also open an address popup with Enter, reach the JOSM link and close it with Escape. Other tests open and close each menu, use the search combobox, make a lasso selection from the keyboard and read what the status region announces. The placeholder contrast has its own test, because axe does not check placeholder text.

## Known gaps

On the map itself, statuses differ only by colour (1.4.1), and the contrast of the points against the basemap is not checked (1.4.11). The filter list and the popup give each status in words.

Several targets are smaller than 24 by 24 px. That is a WCAG 2.2 criterion (2.5.8), outside the current target.

Nobody has tested the changes with NVDA, JAWS or VoiceOver yet.

If something on the map does not work with your keyboard, screen reader or display settings, open an issue on GitHub with your browser, the assistive technology you use and the steps that fail.
