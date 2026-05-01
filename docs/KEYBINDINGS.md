# Keybindings Reference

> Auto-generated on 2026-05-01 05:09. Do not edit manually — run `python3 scripts/gen_keybindings.py` to update.

## Table of Contents

- [Caret Mode](#caret-mode-keybindings)
- [Command Mode](#command-mode-keybindings)
- [Hint Mode](#hint-mode-keybindings)
- [Insert Mode](#insert-mode-keybindings)
- [Normal Mode](#normal-mode-keybindings)
- [Prompt Mode](#prompt-mode-keybindings)
- [Conflicts](#conflicts)

### Caret Mode Keybindings

| Key        | Command             | Layer    |
| ---------- | ------------------- | -------- |
| `<Escape>` | `mode-leave`        | behavior |
| `Y`        | `yank selection -s` | behavior |
| `y`        | `yank selection`    | behavior |

### Command Mode Keybindings

| Key        | Command                      | Layer    |
| ---------- | ---------------------------- | -------- |
| `<Escape>` | `mode-enter normal`          | base     |
| `<ctrl-j>` | `completion-item-focus next` | behavior |
| `<ctrl-k>` | `completion-item-focus prev` | behavior |
| `<ctrl-n>` | `completion-item-focus next` | behavior |
| `<ctrl-p>` | `completion-item-focus prev` | behavior |

### Hint Mode Keybindings

| Key        | Command      | Layer    |
| ---------- | ------------ | -------- |
| `<Escape>` | `mode-leave` | behavior |

### Insert Mode Keybindings

| Key        | Command       | Layer    |
| ---------- | ------------- | -------- |
| `<Escape>` | `mode-leave`  | behavior |
| `<ctrl-e>` | `open-editor` | behavior |

### Normal Mode Keybindings

| Key        | Command                                                     | Layer    |
| ---------- | ----------------------------------------------------------- | -------- |
| `"`        | `cmd-set-text :quickmark-load -t `                          | behavior |
| `'`        | `cmd-set-text :quickmark-load `                             | behavior |
| `,D`       | `download-delete`                                           | behavior |
| `,N`       | `open -p -w`                                                | behavior |
| `,P`       | `open -t -- {primary}`                                      | behavior |
| `,Q`       | `quit --save`                                               | behavior |
| `,X`       | `undo`                                                      | behavior |
| `,Y`       | `yank -s`                                                   | behavior |
| `,c`       | `config-cycle content.cookies.accept all no-3rdparty never` | privacy  |
| `,d`       | `download-clear`                                            | behavior |
| `,e`       | `config-edit`                                               | behavior |
| `,i`       | `config-cycle content.images true false`                    | privacy  |
| `,j`       | `config-cycle content.javascript.enabled true false`        | privacy  |
| `,n`       | `open -w`                                                   | behavior |
| `,p`       | `open -p`                                                   | behavior |
| `,q`       | `quit`                                                      | behavior |
| `,r`       | `config-source`                                             | behavior |
| `,s`       | `open https://{host}`                                       | privacy  |
| `,t`       | `cmd-set-text :set tabs.position `                          | behavior |
| `,w`       | `window-only`                                               | behavior |
| `,x`       | `tab-close`                                                 | behavior |
| `,y`       | `yank`                                                      | behavior |
| `/`        | `cmd-set-text /`                                            | behavior |
| `;I`       | `hint images tab`                                           | behavior |
| `;Y`       | `hint links yank-primary`                                   | behavior |
| `;b`       | `hint all tab-bg`                                           | behavior |
| `;d`       | `hint links download`                                       | behavior |
| `;f`       | `hint all tab-fg`                                           | behavior |
| `;i`       | `hint images`                                               | behavior |
| `;o`       | `hint inputs`                                               | behavior |
| `;r`       | `hint --rapid links tab-bg`                                 | behavior |
| `;y`       | `hint links yank`                                           | behavior |
| `<alt-1>`  | `tab-focus 1`                                               | behavior |
| `<alt-2>`  | `tab-focus 2`                                               | behavior |
| `<alt-3>`  | `tab-focus 3`                                               | behavior |
| `<alt-4>`  | `tab-focus 4`                                               | behavior |
| `<alt-5>`  | `tab-focus 5`                                               | behavior |
| `<alt-6>`  | `tab-focus 6`                                               | behavior |
| `<alt-7>`  | `tab-focus 7`                                               | behavior |
| `<alt-8>`  | `tab-focus 8`                                               | behavior |
| `<alt-9>`  | `tab-focus -1`                                              | behavior |
| `<ctrl-d>` | `scroll-page 0 0.5`                                         | base     |
| `<ctrl-u>` | `scroll-page 0 -0.5`                                        | base     |
| `<ctrl-v>` | `mode-enter passthrough`                                    | base     |
| `?`        | `cmd-set-text ?`                                            | behavior |
| `B`        | `cmd-set-text :bookmark-load `                              | behavior |
| `F`        | `hint all tab`                                              | behavior |
| `G`        | `scroll-to-perc`                                            | base     |
| `H`        | `back`                                                      | behavior |
| `J`        | `tab-prev`                                                  | behavior |
| `K`        | `tab-next`                                                  | behavior |
| `L`        | `forward`                                                   | behavior |
| `N`        | `search-prev`                                               | behavior |
| `O`        | `cmd-set-text :open -t `                                    | base     |
| `R`        | `reload -f`                                                 | behavior |
| `V`        | `mode-enter caret ;; selection-toggle --line`               | behavior |
| `co`       | `tab-only`                                                  | base     |
| `d`        | `tab-close`                                                 | base     |
| `f`        | `hint`                                                      | behavior |
| `gD`       | `download --dest ~/Desktop/`                                | behavior |
| `gO`       | `cmd-set-text :open -t {url}`                               | base     |
| `gT`       | `tab-prev`                                                  | base     |
| `gd`       | `download`                                                  | behavior |
| `gg`       | `scroll-to-perc 0`                                          | base     |
| `go`       | `cmd-set-text :open {url}`                                  | base     |
| `gt`       | `tab-next`                                                  | base     |
| `m`        | `quickmark-save`                                            | behavior |
| `n`        | `search-next`                                               | behavior |
| `o`        | `cmd-set-text :open `                                       | base     |
| `r`        | `reload`                                                    | behavior |
| `tD`       | `tab-only --prev`                                           | behavior |
| `th`       | `tab-move -`                                                | behavior |
| `tl`       | `tab-move +`                                                | behavior |
| `tm`       | `tab-mute`                                                  | behavior |
| `tp`       | `tab-pin`                                                   | behavior |
| `u`        | `undo`                                                      | base     |
| `v`        | `mode-enter caret`                                          | behavior |
| `yt`       | `yank title`                                                | base     |
| `yy`       | `yank`                                                      | base     |

### Prompt Mode Keybindings

| Key        | Command                  | Layer    |
| ---------- | ------------------------ | -------- |
| `<Escape>` | `mode-leave`             | behavior |
| `<ctrl-n>` | `prompt-item-focus next` | behavior |
| `<ctrl-p>` | `prompt-item-focus prev` | behavior |

## Conflicts

_Conflicts are intentional — higher-priority layers override lower ones._

✓ No keybinding conflicts detected.
