# qutebrowser quick search

- [qutebrowser settings](https://qutebrowser.org/doc/help/settings.html)
- [qutebrowser config](https://qutebrowser.org/doc/help/configuring.html#configpy)

## All settings

```
Setting reference
All settings

Setting	Description
aliases

Aliases for commands.

auto_save.interval

Time interval (in milliseconds) between auto-saves of config/cookies/etc.

auto_save.session

Always restore open sites when qutebrowser is reopened.

backend

Backend to use to display websites.

bindings.commands

Keybindings mapping keys to commands in different modes.

bindings.default

Default keybindings. If you want to add bindings, modify bindings.commands instead.

bindings.key_mappings

Map keys to other keys, so that they are equivalent in all modes.

changelog_after_upgrade

When to show a changelog after qutebrowser was upgraded.

colors.completion.category.bg

Background color of the completion widget category headers.

colors.completion.category.border.bottom

Bottom border color of the completion widget category headers.

colors.completion.category.border.top

Top border color of the completion widget category headers.

colors.completion.category.fg

Foreground color of completion widget category headers.

colors.completion.even.bg

Background color of the completion widget for even rows.

colors.completion.fg

Text color of the completion widget.

colors.completion.item.selected.bg

Background color of the selected completion item.

colors.completion.item.selected.border.bottom

Bottom border color of the selected completion item.

colors.completion.item.selected.border.top

Top border color of the selected completion item.

colors.completion.item.selected.fg

Foreground color of the selected completion item.

colors.completion.item.selected.match.fg

Foreground color of the matched text in the selected completion item.

colors.completion.match.fg

Foreground color of the matched text in the completion.

colors.completion.odd.bg

Background color of the completion widget for odd rows.

colors.completion.scrollbar.bg

Color of the scrollbar in the completion view.

colors.completion.scrollbar.fg

Color of the scrollbar handle in the completion view.

colors.contextmenu.disabled.bg

Background color of disabled items in the context menu.

colors.contextmenu.disabled.fg

Foreground color of disabled items in the context menu.

colors.contextmenu.menu.bg

Background color of the context menu.

colors.contextmenu.menu.fg

Foreground color of the context menu.

colors.contextmenu.selected.bg

Background color of the context menu’s selected item.

colors.contextmenu.selected.fg

Foreground color of the context menu’s selected item.

colors.downloads.bar.bg

Background color for the download bar.

colors.downloads.error.bg

Background color for downloads with errors.

colors.downloads.error.fg

Foreground color for downloads with errors.

colors.downloads.start.bg

Color gradient start for download backgrounds.

colors.downloads.start.fg

Color gradient start for download text.

colors.downloads.stop.bg

Color gradient stop for download backgrounds.

colors.downloads.stop.fg

Color gradient end for download text.

colors.downloads.system.bg

Color gradient interpolation system for download backgrounds.

colors.downloads.system.fg

Color gradient interpolation system for download text.

colors.hints.bg

Background color for hints.

colors.hints.fg

Font color for hints.

colors.hints.match.fg

Font color for the matched part of hints.

colors.keyhint.bg

Background color of the keyhint widget.

colors.keyhint.fg

Text color for the keyhint widget.

colors.keyhint.suffix.fg

Highlight color for keys to complete the current keychain.

colors.messages.error.bg

Background color of an error message.

colors.messages.error.border

Border color of an error message.

colors.messages.error.fg

Foreground color of an error message.

colors.messages.info.bg

Background color of an info message.

colors.messages.info.border

Border color of an info message.

colors.messages.info.fg

Foreground color of an info message.

colors.messages.warning.bg

Background color of a warning message.

colors.messages.warning.border

Border color of a warning message.

colors.messages.warning.fg

Foreground color of a warning message.

colors.prompts.bg

Background color for prompts.

colors.prompts.border

Border used around UI elements in prompts.

colors.prompts.fg

Foreground color for prompts.

colors.prompts.selected.bg

Background color for the selected item in filename prompts.

colors.prompts.selected.fg

Foreground color for the selected item in filename prompts.

colors.statusbar.caret.bg

Background color of the statusbar in caret mode.

colors.statusbar.caret.fg

Foreground color of the statusbar in caret mode.

colors.statusbar.caret.selection.bg

Background color of the statusbar in caret mode with a selection.

colors.statusbar.caret.selection.fg

Foreground color of the statusbar in caret mode with a selection.

colors.statusbar.command.bg

Background color of the statusbar in command mode.

colors.statusbar.command.fg

Foreground color of the statusbar in command mode.

colors.statusbar.command.private.bg

Background color of the statusbar in private browsing + command mode.

colors.statusbar.command.private.fg

Foreground color of the statusbar in private browsing + command mode.

colors.statusbar.insert.bg

Background color of the statusbar in insert mode.

colors.statusbar.insert.fg

Foreground color of the statusbar in insert mode.

colors.statusbar.normal.bg

Background color of the statusbar.

colors.statusbar.normal.fg

Foreground color of the statusbar.

colors.statusbar.passthrough.bg

Background color of the statusbar in passthrough mode.

colors.statusbar.passthrough.fg

Foreground color of the statusbar in passthrough mode.

colors.statusbar.private.bg

Background color of the statusbar in private browsing mode.

colors.statusbar.private.fg

Foreground color of the statusbar in private browsing mode.

colors.statusbar.progress.bg

Background color of the progress bar.

colors.statusbar.url.error.fg

Foreground color of the URL in the statusbar on error.

colors.statusbar.url.fg

Default foreground color of the URL in the statusbar.

colors.statusbar.url.hover.fg

Foreground color of the URL in the statusbar for hovered links.

colors.statusbar.url.success.http.fg

Foreground color of the URL in the statusbar on successful load (http).

colors.statusbar.url.success.https.fg

Foreground color of the URL in the statusbar on successful load (https).

colors.statusbar.url.warn.fg

Foreground color of the URL in the statusbar when there’s a warning.

colors.tabs.bar.bg

Background color of the tab bar.

colors.tabs.even.bg

Background color of unselected even tabs.

colors.tabs.even.fg

Foreground color of unselected even tabs.

colors.tabs.indicator.error

Color for the tab indicator on errors.

colors.tabs.indicator.start

Color gradient start for the tab indicator.

colors.tabs.indicator.stop

Color gradient end for the tab indicator.

colors.tabs.indicator.system

Color gradient interpolation system for the tab indicator.

colors.tabs.odd.bg

Background color of unselected odd tabs.

colors.tabs.odd.fg

Foreground color of unselected odd tabs.

colors.tabs.pinned.even.bg

Background color of pinned unselected even tabs.

colors.tabs.pinned.even.fg

Foreground color of pinned unselected even tabs.

colors.tabs.pinned.odd.bg

Background color of pinned unselected odd tabs.

colors.tabs.pinned.odd.fg

Foreground color of pinned unselected odd tabs.

colors.tabs.pinned.selected.even.bg

Background color of pinned selected even tabs.

colors.tabs.pinned.selected.even.fg

Foreground color of pinned selected even tabs.

colors.tabs.pinned.selected.odd.bg

Background color of pinned selected odd tabs.

colors.tabs.pinned.selected.odd.fg

Foreground color of pinned selected odd tabs.

colors.tabs.selected.even.bg

Background color of selected even tabs.

colors.tabs.selected.even.fg

Foreground color of selected even tabs.

colors.tabs.selected.odd.bg

Background color of selected odd tabs.

colors.tabs.selected.odd.fg

Foreground color of selected odd tabs.

colors.tooltip.bg

Background color of tooltips.

colors.tooltip.fg

Foreground color of tooltips.

colors.webpage.bg

Background color for webpages if unset (or empty to use the theme’s color).

colors.webpage.darkmode.algorithm

Which algorithm to use for modifying how colors are rendered with dark mode.

colors.webpage.darkmode.contrast

Contrast for dark mode.

colors.webpage.darkmode.enabled

Render all web contents using a dark theme.

colors.webpage.darkmode.policy.images

Which images to apply dark mode to.

colors.webpage.darkmode.policy.page

Which pages to apply dark mode to.

colors.webpage.darkmode.threshold.background

Threshold for inverting background elements with dark mode.

colors.webpage.darkmode.threshold.foreground

Threshold for inverting text with dark mode.

colors.webpage.preferred_color_scheme

Value to use for prefers-color-scheme: for websites.

completion.cmd_history_max_items

Number of commands to save in the command history.

completion.delay

Delay (in milliseconds) before updating completions after typing a character.

completion.favorite_paths

Default filesystem autocomplete suggestions for :open.

completion.height

Height (in pixels or as percentage of the window) of the completion.

completion.min_chars

Minimum amount of characters needed to update completions.

completion.open_categories

Which categories to show (in which order) in the :open completion.

completion.quick

Move on to the next part when there’s only one possible completion left.

completion.scrollbar.padding

Padding (in pixels) of the scrollbar handle in the completion window.

completion.scrollbar.width

Width (in pixels) of the scrollbar in the completion window.

completion.show

When to show the autocompletion window.

completion.shrink

Shrink the completion to be smaller than the configured size if there are no scrollbars.

completion.timestamp_format

Format of timestamps (e.g. for the history completion).

completion.use_best_match

Execute the best-matching command on a partial match.

completion.web_history.exclude

A list of patterns which should not be shown in the history.

completion.web_history.max_items

Number of URLs to show in the web history.

confirm_quit

Require a confirmation before quitting the application.

content.autoplay

Automatically start playing <video> elements.

content.blocking.adblock.lists

List of URLs to ABP-style adblocking rulesets.

content.blocking.enabled

Enable the ad/host blocker

content.blocking.hosts.block_subdomains

Block subdomains of blocked hosts.

content.blocking.hosts.lists

List of URLs to host blocklists for the host blocker.

content.blocking.method

Which method of blocking ads should be used.

content.blocking.whitelist

A list of patterns that should always be loaded, despite being blocked by the ad-/host-blocker.

content.cache.appcache

Enable support for the HTML 5 web application cache feature.

content.cache.maximum_pages

Maximum number of pages to hold in the global memory page cache.

content.cache.size

Size (in bytes) of the HTTP network cache. Null to use the default value.

content.canvas_reading

Allow websites to read canvas elements.

content.cookies.accept

Which cookies to accept.

content.cookies.store

Store cookies.

content.default_encoding

Default encoding to use for websites.

content.desktop_capture

Allow websites to share screen content.

content.dns_prefetch

Try to pre-fetch DNS entries to speed up browsing.

content.frame_flattening

Expand each subframe to its contents.

content.fullscreen.overlay_timeout

Set fullscreen notification overlay timeout in milliseconds.

content.fullscreen.window

Limit fullscreen to the browser window (does not expand to fill the screen).

content.geolocation

Allow websites to request geolocations.

content.headers.accept_language

Value to send in the Accept-Language header.

content.headers.custom

Custom headers for qutebrowser HTTP requests.

content.headers.do_not_track

Value to send in the DNT header.

content.headers.referer

When to send the Referer header.

content.headers.user_agent

User agent to send.

content.hyperlink_auditing

Enable hyperlink auditing (<a ping>).

content.images

Load images automatically in web pages.

content.javascript.alert

Show javascript alerts.

content.javascript.can_close_tabs

Allow JavaScript to close tabs.

content.javascript.can_open_tabs_automatically

Allow JavaScript to open new tabs without user interaction.

content.javascript.clipboard

Allow JavaScript to read from or write to the clipboard.

content.javascript.enabled

Enable JavaScript.

content.javascript.legacy_touch_events

Enables the legacy touch event feature.

content.javascript.log

Log levels to use for JavaScript console logging messages.

content.javascript.log_message.excludes

Javascript messages to not show in the UI, despite a corresponding content.javascript.log_message.levels setting.

content.javascript.log_message.levels

Javascript message sources/levels to show in the qutebrowser UI.

content.javascript.modal_dialog

Use the standard JavaScript modal dialog for alert() and confirm().

content.javascript.prompt

Show javascript prompts.

content.local_content_can_access_file_urls

Allow locally loaded documents to access other local URLs.

content.local_content_can_access_remote_urls

Allow locally loaded documents to access remote URLs.

content.local_storage

Enable support for HTML 5 local storage and Web SQL.

content.media.audio_capture

Allow websites to record audio.

content.media.audio_video_capture

Allow websites to record audio and video.

content.media.video_capture

Allow websites to record video.

content.mouse_lock

Allow websites to lock your mouse pointer.

content.mute

Automatically mute tabs.

content.netrc_file

Netrc-file for HTTP authentication.

content.notifications.enabled

Allow websites to show notifications.

content.notifications.presenter

What notification presenter to use for web notifications.

content.notifications.show_origin

Whether to show the origin URL for notifications.

content.pdfjs

Display PDF files via PDF.js in the browser without showing a download prompt.

content.persistent_storage

Allow websites to request persistent storage quota via navigator.webkitPersistentStorage.requestQuota.

content.plugins

Enable plugins in Web pages.

content.prefers_reduced_motion

Request websites to minimize non-essentials animations and motion.

content.print_element_backgrounds

Draw the background color and images also when the page is printed.

content.private_browsing

Open new windows in private browsing mode which does not record visited pages.

content.proxy

Proxy to use.

content.proxy_dns_requests

Send DNS requests over the configured proxy.

content.register_protocol_handler

Allow websites to register protocol handlers via navigator.registerProtocolHandler.

content.site_specific_quirks.enabled

Enable quirks (such as faked user agent headers) needed to get specific sites to work properly.

content.site_specific_quirks.skip

Disable a list of named quirks.

content.tls.certificate_errors

How to proceed on TLS certificate errors.

content.unknown_url_scheme_policy

How navigation requests to URLs with unknown schemes are handled.

content.user_stylesheets

List of user stylesheet filenames to use.

content.webgl

Enable WebGL.

content.webrtc_ip_handling_policy

Which interfaces to expose via WebRTC.

content.xss_auditing

Monitor load requests for cross-site scripting attempts.

downloads.location.directory

Directory to save downloads to.

downloads.location.prompt

Prompt the user for the download location.

downloads.location.remember

Remember the last used download directory.

downloads.location.suggestion

What to display in the download filename input.

downloads.open_dispatcher

Default program used to open downloads.

downloads.position

Where to show the downloaded files.

downloads.prevent_mixed_content

Automatically abort insecure (HTTP) downloads originating from secure (HTTPS) pages.

downloads.remove_finished

Duration (in milliseconds) to wait before removing finished downloads.

editor.command

Editor (and arguments) to use for the edit-* commands.

editor.encoding

Encoding to use for the editor.

editor.remove_file

Delete the temporary file upon closing the editor.

fileselect.folder.command

Command (and arguments) to use for selecting a single folder in forms. The command should write the selected folder path to the specified file or stdout.

fileselect.handler

Handler for selecting file(s) in forms. If external, then the commands specified by fileselect.single_file.command, fileselect.multiple_files.command and fileselect.folder.command are used to select one file, multiple files, and folders, respectively.

fileselect.multiple_files.command

Command (and arguments) to use for selecting multiple files in forms. The command should write the selected file paths to the specified file or to stdout, separated by newlines.

fileselect.single_file.command

Command (and arguments) to use for selecting a single file in forms. The command should write the selected file path to the specified file or stdout.

fonts.completion.category

Font used in the completion categories.

fonts.completion.entry

Font used in the completion widget.

fonts.contextmenu

Font used for the context menu.

fonts.debug_console

Font used for the debugging console.

fonts.default_family

Default font families to use.

fonts.default_size

Default font size to use.

fonts.downloads

Font used for the downloadbar.

fonts.hints

Font used for the hints.

fonts.keyhint

Font used in the keyhint widget.

fonts.messages.error

Font used for error messages.

fonts.messages.info

Font used for info messages.

fonts.messages.warning

Font used for warning messages.

fonts.prompts

Font used for prompts.

fonts.statusbar

Font used in the statusbar.

fonts.tabs.selected

Font used for selected tabs.

fonts.tabs.unselected

Font used for unselected tabs.

fonts.tooltip

Font used for tooltips.

fonts.web.family.cursive

Font family for cursive fonts.

fonts.web.family.fantasy

Font family for fantasy fonts.

fonts.web.family.fixed

Font family for fixed fonts.

fonts.web.family.sans_serif

Font family for sans-serif fonts.

fonts.web.family.serif

Font family for serif fonts.

fonts.web.family.standard

Font family for standard fonts.

fonts.web.size.default

Default font size (in pixels) for regular text.

fonts.web.size.default_fixed

Default font size (in pixels) for fixed-pitch text.

fonts.web.size.minimum

Hard minimum font size (in pixels).

fonts.web.size.minimum_logical

Minimum logical font size (in pixels) that is applied when zooming out.

hints.auto_follow

When a hint can be automatically followed without pressing Enter.

hints.auto_follow_timeout

Duration (in milliseconds) to ignore normal-mode key bindings after a successful auto-follow.

hints.border

CSS border value for hints.

hints.chars

Characters used for hint strings.

hints.dictionary

Dictionary file to be used by the word hints.

hints.find_implementation

Which implementation to use to find elements to hint.

hints.hide_unmatched_rapid_hints

Hide unmatched hints in rapid mode.

hints.leave_on_load

Leave hint mode when starting a new page load.

hints.min_chars

Minimum number of characters used for hint strings.

hints.mode

Mode to use for hints.

hints.next_regexes

Comma-separated list of regular expressions to use for next links.

hints.padding

Padding (in pixels) for hints.

hints.prev_regexes

Comma-separated list of regular expressions to use for prev links.

hints.radius

Rounding radius (in pixels) for the edges of hints.

hints.scatter

Scatter hint key chains (like Vimium) or not (like dwb).

hints.selectors

CSS selectors used to determine which elements on a page should have hints.

hints.uppercase

Make characters in hint strings uppercase.

history_gap_interval

Maximum time (in minutes) between two history items for them to be considered being from the same browsing session.

input.escape_quits_reporter

Allow Escape to quit the crash reporter.

input.forward_unbound_keys

Which unbound keys to forward to the webview in normal mode.

input.insert_mode.auto_enter

Enter insert mode if an editable element is clicked.

input.insert_mode.auto_leave

Leave insert mode if a non-editable element is clicked.

input.insert_mode.auto_load

Automatically enter insert mode if an editable element is focused after loading the page.

input.insert_mode.leave_on_load

Leave insert mode when starting a new page load.

input.insert_mode.plugins

Switch to insert mode when clicking flash and other plugins.

input.links_included_in_focus_chain

Include hyperlinks in the keyboard focus chain when tabbing.

input.match_counts

Interpret number prefixes as counts for bindings.

input.media_keys

Whether the underlying Chromium should handle media keys.

input.mode_override

Mode to change to when focusing on a tab/URL changes.

input.mouse.back_forward_buttons

Enable back and forward buttons on the mouse.

input.mouse.rocker_gestures

Enable Opera-like mouse rocker gestures.

input.partial_timeout

Timeout (in milliseconds) for partially typed key bindings.

input.spatial_navigation

Enable spatial navigation.

keyhint.blacklist

Keychains that shouldn’t be shown in the keyhint dialog.

keyhint.delay

Time (in milliseconds) from pressing a key to seeing the keyhint dialog.

keyhint.radius

Rounding radius (in pixels) for the edges of the keyhint dialog.

logging.level.console

Level for console (stdout/stderr) logs. Ignored if the --loglevel or --debug CLI flags are used.

logging.level.ram

Level for in-memory logs.

messages.timeout

Duration (in milliseconds) to show messages in the statusbar for.

new_instance_open_target

How to open links in an existing instance if a new one is launched.

new_instance_open_target_window

Which window to choose when opening links as new tabs.

prompt.filebrowser

Show a filebrowser in download prompts.

prompt.radius

Rounding radius (in pixels) for the edges of prompts.

qt.args

Additional arguments to pass to Qt, without leading --.

qt.chromium.experimental_web_platform_features

Enables Web Platform features that are in development.

qt.chromium.low_end_device_mode

When to use Chromium’s low-end device mode.

qt.chromium.process_model

Which Chromium process model to use.

qt.chromium.sandboxing

What sandboxing mechanisms in Chromium to use.

qt.environ

Additional environment variables to set.

qt.force_platform

Force a Qt platform to use.

qt.force_platformtheme

Force a Qt platformtheme to use.

qt.force_software_rendering

Force software rendering for QtWebEngine.

qt.highdpi

Turn on Qt HighDPI scaling.

qt.workarounds.disable_accelerated_2d_canvas

Disable accelerated 2d canvas to avoid graphical glitches.

qt.workarounds.disable_accessibility

Disable accessibility to avoid crashes on Qt 6.10.1.

qt.workarounds.disable_hangouts_extension

Disable the Hangouts extension.

qt.workarounds.locale

Work around locale parsing issues in QtWebEngine 5.15.3.

qt.workarounds.remove_service_workers

Delete the QtWebEngine Service Worker directory on every start.

scrolling.bar

When/how to show the scrollbar.

scrolling.smooth

Enable smooth scrolling for web pages.

search.ignore_case

When to find text on a page case-insensitively.

search.incremental

Find text on a page incrementally, renewing the search for each typed character.

search.wrap

Wrap around at the top and bottom of the page when advancing through text matches using :search-next and :search-prev.

search.wrap_messages

Display messages when advancing through text matches at the top and bottom of the page, e.g. Search hit TOP.

session.default_name

Name of the session to save by default.

session.lazy_restore

Load a restored tab as soon as it takes focus.

spellcheck.languages

Languages to use for spell checking.

statusbar.padding

Padding (in pixels) for the statusbar.

statusbar.position

Position of the status bar.

statusbar.show

When to show the statusbar.

statusbar.widgets

List of widgets displayed in the statusbar.

tabs.background

Open new tabs (middleclick/ctrl+click) in the background.

tabs.close_mouse_button

Mouse button with which to close tabs.

tabs.close_mouse_button_on_bar

How to behave when the close mouse button is pressed on the tab bar.

tabs.favicons.scale

Scaling factor for favicons in the tab bar.

tabs.favicons.show

When to show favicons in the tab bar.

tabs.focus_stack_size

Maximum stack size to remember for tab switches (-1 for no maximum).

tabs.indicator.padding

Padding (in pixels) for tab indicators.

tabs.indicator.width

Width (in pixels) of the progress indicator (0 to disable).

tabs.last_close

How to behave when the last tab is closed.

tabs.max_width

Maximum width (in pixels) of tabs (-1 for no maximum).

tabs.min_width

Minimum width (in pixels) of tabs (-1 for the default minimum size behavior).

tabs.mode_on_change

When switching tabs, what input mode is applied.

tabs.mousewheel_switching

Switch between tabs using the mouse wheel.

tabs.new_position.related

Position of new tabs opened from another tab.

tabs.new_position.stacking

Stack related tabs on top of each other when opened consecutively.

tabs.new_position.unrelated

Position of new tabs which are not opened from another tab.

tabs.padding

Padding (in pixels) around text for tabs.

tabs.pinned.frozen

Force pinned tabs to stay at fixed URL.

tabs.pinned.shrink

Shrink pinned tabs down to their contents.

tabs.position

Position of the tab bar.

tabs.select_on_remove

Which tab to select when the focused tab is removed.

tabs.show

When to show the tab bar.

tabs.show_switching_delay

Duration (in milliseconds) to show the tab bar before hiding it when tabs.show is set to switching.

tabs.tabs_are_windows

Open a new window for every tab.

tabs.title.alignment

Alignment of the text inside of tabs.

tabs.title.elide

Position of ellipsis in truncated title of tabs.

tabs.title.format

Format to use for the tab title.

tabs.title.format_pinned

Format to use for the tab title for pinned tabs. The same placeholders like for tabs.title.format are defined.

tabs.tooltips

Show tooltips on tabs.

tabs.undo_stack_size

Number of closed tabs (per window) and closed windows to remember for :undo (-1 for no maximum).

tabs.width

Width (in pixels or as percentage of the window) of the tab bar if it’s vertical.

tabs.wrap

Wrap when changing tabs.

url.auto_search

What search to start when something else than a URL is entered.

url.default_page

Page to open if :open -t/-b/-w is used without URL.

url.incdec_segments

URL segments where :navigate increment/decrement will search for a number.

url.open_base_url

Open base URL of the searchengine if a searchengine shortcut is invoked without parameters.

url.searchengines

Search engines which can be used via the address bar.

url.start_pages

Page(s) to open at the start.

url.yank_ignored_parameters

URL parameters to strip when yanking a URL.

window.hide_decoration

Hide the window decoration.

window.title_format

Format to use for the window title. The same placeholders like for

window.transparent

Set the main window background to transparent.

zoom.default

Default zoom level.

zoom.levels

Available zoom levels.

zoom.mouse_divider

Number of zoom increments to divide the mouse wheel movements to.

zoom.text_only

Apply the zoom factor on a frame only to the text or to all content.

```
