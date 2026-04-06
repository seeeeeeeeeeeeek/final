# stocknogs thinkorswim bridge

This browser extension lets a normal logged-in thinkorswim web tab talk to stocknogs without using DevTools console `fetch` calls.

## What It Does

- polls stocknogs for the next requested symbol
- switches the visible thinkorswim tab to that symbol
- reads selector-based page data
- posts the result back to stocknogs through the existing manual-session API

## Install

1. Open your browser's extensions page.
2. Turn on `Developer mode`.
3. Choose `Load unpacked`.
4. Select this folder:
   `extensions/stocknogs_thinkorswim_bridge`

## Use

1. Start stocknogs locally.
2. Open the stocknogs extension popup.
3. Click `Auto-detect` if the base URL field is empty.
4. Keep `Bridge enabled` on.
5. Open thinkorswim web in the same browser and log in.
6. Leave one thinkorswim tab open.
7. Back in stocknogs, click `Analyze`.

If the stocknogs-managed browser is broken or stuck, the app can queue the symbol for this extension bridge instead.
