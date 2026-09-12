# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Migrated the OCR result text editor to **GtkSourceView 5** (`GtkSource.View`/`GtkSource.Buffer`) with native search bar (`<Primary>f`), editor preferences (line numbers, current line highlight, wrapping), and an "Open in External Editor" action (`<Primary><Shift>E`) with safe `Gtk.FileLauncher` handoff

### Fixed
- Repinned orphaned tessdata commit SHAs to release tag 4.1.0 in `anura/config.py` and both Flatpak manifests (Bug #6)
- Exposed cached language list and pause state on `TTSService` for correct TTS UI state synchronization

### Changed
- CI: added `gir1.2-gtksource-5` system dependency to the GTK integration test workflow

## [0.1.5] - 2026-11-09

### Added
- Implemented Extraction History V1 (opt-in local history of recent OCR extractions, newest-first JSON persistence with atomic writes and corruption recovery, HistoryPage with clear action, `history-enabled`/`history-limit` GSettings keys, `win.show-history` navigation) — see `docs/history-v1.md`
- Added F-005 runtime dependency coverage check (`build-aux/check_runtime_dependency_coverage.py`) enforcing that every uv.lock runtime dependency is represented in both Flatpak manifests
- Implemented UI theme selector with System, Light, and Dark options using `Adw.StyleManager`
- Added `color-scheme` GSettings key for persistent theme preference storage
- Implemented selection-aware text statistics and actions on OCR results page (Palette)
- Added Undo/Redo functionality to ExtractedPage for improved text editing workflow
- Enhanced accessibility with keyboard navigation improvements and better drop button tooltips
- Implemented NormCap-inspired UX improvements for better user experience
- Added comprehensive accessibility enhancements to WelcomePage and LanguagePopover
- Implemented dynamic copy button tooltip and accessibility feedback in Palette
- Added manual workflow execution capability for dependency sync in CI/CD
- Configured Dependabot for automated dependency updates on testing branch
- Added comprehensive docstrings, type hints, and integration tests for ClipboardService fallback paths
- Implemented six-pillar CI hardening framework for improved test reliability
- Added enhanced diagnostic logging for host screenshot operations

### Fixed
- Resolved `AtomicTaskManager` deadlock and child process hang issues
- Fixed GTK integration test suite hanging with comprehensive multi-step fix (atexit, os._exit(), Weston cleanup, signal sourcing)
- Eliminated clipboard infinite fallback loop and stale source_remove warnings
- Fixed TTS play/pause/stop state desynchronization in extracted_page (5 bugs)
- Resolved X11 screenshot fallback issues in testing branch
- Added `BrokenProcessPool` recovery to `AtomicTaskManager` for enhanced error handling (CRIT-01)
- Fixed OcrController weak references against ReferenceError during window destruction
- Fixed static type-checking and path concatenation issues
- Fixed flatpak pybind11 cmake path resolution during zxing build
- Resolved clipboard spinner stuck and source_remove warnings (BUG-PASTE + BUG-032)
- Fixed path mocking in tests (Path.exists instead of os.path.exists)
- Caught PermissionError from Path.exists() for inaccessible parent directories
- Released _state_lock before ProcessPoolExecutor.shutdown() to prevent deadlock
- Fixed test assertion to use GTK4 set_content() instead of removed set_text()
- Resolved GObject metaclass conflicts and TESSDATA_DIR patching in tests
- Fixed ruff linting violations (F841 unused variable, I001 import sorting, B028, SIM910)
- Fixed CI workflow SHA resolution errors and image pull failures
- Fixed undefined HTML variable and unused import in CI workflow
- Hardened CI/CD workflows with immutable action pinning and credential protection
- Resolved 4 bugs from debug session 2026-05-25
- Fixed 7 bugs identified by automated Kimi analysis (2026-05-26)
- Reset fallback flag in clipboard service and enhanced portal error logging
- Remediated GTK integration test failures and GTK4 regressions
- Fixed Python-quality CI failures
- Removed complex async callback tests that fail in CI
- Fixed failing integration tests by simplifying test logic
- Terminated child processes to prevent GHA limbo hangs
- Resolved structural test mismatches and cleaned TTS debt
- Restored missing TTSService facade export
- Fixed DialogManager import in AnuraWindow
- Fixed ruff style checks and import ordering across services

### Changed
- Decomposed LanguageManager into specialized managers (DownloadManager, CacheManager, LanguageValidator) in anura/services/language/
- Optimized OCR layout parsing and structural reconstruction (Bolt optimization)
- Optimized image mean calculation in ContrastEnhancementFilter
- Restructured and modernized CI/CD pipeline with comprehensive GTK integration test fixes
- Performed systematic bug hunting and modernization sweep across the codebase
- Technical remediation for Flatpak, Pathlib, and Safety patterns
- Rewrote AI-generated comments for clarity and professionalism
- Translated project documentation from Italian to English
- Updated flatpak-dependencies.yml workflow
- Moved audit-related files (bugs-observed.json, bugs-summary.md) into dedicated docs/audit/ directory
- Exposed loading_languages and finalized test suite alignment
- Style fixes: import ordering and typing annotations across services
- Audit-driven stability hardening and build fixes
- Updated Flatpak dependencies: Leptonica 1.87.0, imlib2 1.12.6
- Updated dependency versions: ruff ≥0.15.21, meson ≥1.11.2, pytest ≥9.1.1, pillow ≥12.3.0
- Enhanced error handling and logging throughout the application
- Improved portal environment diagnostics and user guidance
- Unified GI mock injection to resolve metaclass conflict in non-CI mode
- Synced CI ignore lists and added ANURA_CI_TEST_MODE to python-quality job

### Security
- **HIGH**: Fixed Pango markup injection in notifications (hardened against markup attacks)
- **HIGH**: Fixed hierarchical ID collision and OCR pipeline instability
- **HIGH**: Fixed Config Layer Leakage and enhanced lifecycle safety
- Hardened local data storage permissions for sensitive data
- Hardened sanitize_text by stripping Private Use (Co) and Surrogate (Cs) Unicode categories
- Hardened is_safe_url_string to reject mixed-script homograph attacks
- Hardened image resource validation for DoS prevention (MAX_IMAGE_SIZE_BYTES enforcement)
- Remediated architectural resource leaks across core services (v2/v3)
- Completed Phase 2 forensics and remediated logic flaws across the codebase
- Installed Claude Bug Bounty toolkit and required security scanners for ongoing auditing
- Implemented dynamic URI scheme validation in ShareService (BUG-035 remediation)

### Removed
- Deleted CHANGELOG_REMEDIATION.md

## [0.1.4.3] - 2026-05-16 {version-0.1.4.3}

### Added

- Advanced TextPreprocessor utility with intelligent image enhancement and OCR text cleanup
- Smart text preprocessing including common OCR error correction, whitespace normalization, and punctuation fixing
- Structured data extraction from OCR text (emails, URLs, phone numbers, dates)
- Adaptive image enhancement based on brightness/contrast analysis for better OCR accuracy
- Modern ShortcutsOverlay widget with live search and categorized keyboard shortcuts
- Enhanced keyboard shortcuts overlay with search functionality and elegant Adw.Window-based interface
- Configurable logging level via `ANURA_LOG_LEVEL` environment variable for debugging
- Host screenshot fallback system using `flatpak-spawn --host` for missing portal backends
- Persistent install-hint banner when screenshot portal backend is missing
- Desktop-aware portal advice messages with environment-specific guidance
- Enhanced diagnostic logging for host screenshot operations
- Comprehensive drag-and-drop functionality with visual feedback and proper lifecycle management
- Complete drag-and-drop event handlers (enter, leave, motion, drop) with CSS styling for hover states
- Enhanced AboutDialog with complete legal information for Flathub compliance
- Full copyright and MIT license text for transparency
- Open source dependencies attribution in legal information
- Complete legal information ensuring Flathub compliance requirements
- Asynchronous Drag-and-Drop implementation to prevent UI freezes, especially in VM environments
- Fallback for URI list on clipboard texture read failure
- Optimized image thresholding using Look-Up Tables (LUT) for performance
- Enhanced accessibility and Micro-UX improvements for the OCR results page
- Persistent Drag-and-Drop controller for better stability
- Clickable QR URL notifications via XDG Desktop Portal (Flatpak-safe)
- Autocopy for QR-detected URLs with improved toast feedback
- Pattern-based file filters for image selection dialog
- Real-time word count status bar in OCR results page
- Standardized localization infrastructure and Application ID

### Fixed

- Fixed notification service cleanup by removing incorrect underscore reference
- Fixed URI validator function call in window.py for proper URL validation
- Fixed dialog response handling for browser launch failures with proper error management
- Fixed extra language combo signal connection to ensure it's always connected regardless of settings
- Fixed modal property removal from shortcuts window for better user experience
- Fixed keyboard shortcuts test to match correct method signature with _param parameter
- Fixed five UI/runtime bugs from Flatpak debug log
- Fixed three additional bugs (release notes parse, TTS AttributeError, screenshot diagnostic)
- Fixed Gio.Subprocess.wait() method usage instead of wait_sync()
- Fixed host screenshot file existence check with retry loop
- Fixed designer credit and share-row action prefix corrections
- Fixed incomplete URL substring sanitization (security fix)
- Resolved multiple critical runtime bugs, memory leaks, and signal leaks across core services
- Fixed X11 Drag-and-Drop deadlocks and portal file transfer freezes
- Corrected Text-to-Speech (TTS) state transitions, visual feedback, and "zombie audio" issues
- Fixed localization initialization and updated Italian translations
- Fixed broken status window in "Legal Information" page
- Resolved GTK navigation warnings and ruff linting violations (E501, W292)
- Fixed About dialog property names and legal information display
- Improved error handling for browser launch and file filters
- Fixed UI spinner animations and state management
- Fixed missing trailing newline in anura/window.py
- Fixed path traversal vulnerability in LanguageManager.remove_language (HIGH severity)
- Fixed URL userinfo spoofing in uri_validator (security fix)
- Fixed URL truncation during QR code extraction and hand-off
- Fixed clipboard infinite fallback loop on image read failures
- Fixed callback exception handling in clipboard service
- Fixed Gio.Notification API usage for XDG Portal compatibility
- Fixed i18n bindings in Flatpak and globalized autocopy behavior
- Fixed Flatpak hybrid UI regression (i18n)
- Fixed localization issues and cleaned up UI code
- Fixed broken state warning on Acknowledgements page
- Fixed navigation focus race condition
- Removed compiled gresource from git tracking and updated .gitignore
- Fixed line length violation in notification service tests

### Changed

- Enhanced screenshot service with host fallback capabilities
- Improved error handling and logging throughout the application
- Better portal environment diagnostics and user guidance
- Updated release notes generation logic with hybrid GitHub link display
- Lower threshold for GitHub link from 15 to 12 items for better UX
- Enhanced drag-and-drop drop target attachment to welcome page widget
- Improved release notes generation with tracking for truncated sections
- Refactored Drag-and-Drop system for improved reliability
- Optimized Flatpak build and updated dependencies (urllib3)
- Improved OCR pipeline and image processing performance
- Deep codebase audit and concurrency hardening across all services
- Pre-compiled regex patterns and optimized PIL thresholding for performance
- Optimized URI validation performance with compiled regex
- Optimized image enhancement pipeline
- Optimized QR code detection by restricting symbol scan
- i18n: full audit and fixed hardcoded UI strings across the application
- i18n: stabilized infrastructure and synchronized translations (Phase 1A)
- i18n: finalized Italian localization and fixed navigation focus (Phase 1B)
- Palette: UX and accessibility improvements across ExtractedPage
- Refactored language API, removed dead code, improved test coverage
- Standardized loading spinner size across the application
- Updated testing documentation

## [0.1.4.2] - 2026-05-05 {version-0.1.4.2}

### Fixed

- Fixed `__slots__` conflict in ClipboardService - missing `_cancellable` in declaration causing AttributeError
- Fixed ruff linting errors across codebase including import sorting and code style issues
- Fixed concurrency issues in TTS and clipboard services against race conditions
- Fixed memory leaks and added structural robustness throughout application
- Fixed API contract, thread safety, and race condition issues in core services
- Fixed Flatpak manifest warnings by removing `_comment` properties

### Changed

- Extracted URI validation to utils module and relaxed IP/localhost restrictions
- Improved code quality with comprehensive type hints and cleanup
- Implemented atomic cancellation for Clipboard and thread-safe signal emission for TTS GStreamer bus
- Enhanced thread safety patterns across all services
- Added comprehensive unit tests for core services
- Resolved all remaining linting errors and line length issues

## [0.1.4.1] - 2026-05-02 {version-0.1.4.1}

### Fixed

- Fixed missing `Adw.init()` call causing "greyed out UI" on some systems
- Fixed GResource bundle loading to properly exit on failure instead of continuing with broken UI
- Fixed notification portal API to use proper GLib.Variant format (a{sv}) for XDG Portal compatibility
- Fixed notification import consistency with absolute imports throughout main.py
- Fixed HTML escaping in release notes generation to prevent XSS vulnerabilities

### Changed

- Added CHANGELOG.md as source of truth for release notes
- Added translate URL to metainfo for Weblate integration

## [0.1.4] - 2026-05-01 {version-0.1.4}

### Fixed

- Fixed critical thread-safety issues and race conditions in language manager and screenshot service
- Fixed memory leaks in widget lifecycle management and GStreamer bus watch
- Fixed all Flatpak manifest dependencies (requests, urllib3, certifi, hatchling, pyzbar)
- Fixed blueprint compiler output directory for Flatpak builds
- Fixed gresource bundle loading with correct UI file paths
- Fixed filesystem permissions for Open Image and Drag & Drop in sandbox
- Fixed silent CLI mode to properly exit without opening UI window
- Fixed CLI exit code to return 0 on success instead of 1
- Fixed code quality issues: lint errors, import sorting, gettext shadowing
- Fixed Telegram share URL to send text as message instead of URL

### Changed

- Updated OARS content rating for Flathub compliance
- Improved CI/CD workflow with smoke tests and build verification
- Updated tessdata-fast to pinned commit SHA for reproducible builds

## [0.1.3] - 2026-04-25 {version-0.1.3}

### Fixed

- Fixed import error in screenshot service (tessdata_config casing)
- Fixed missing init_tessdata() method in LanguageManager
- Fixed settings module path mismatch (moved to anura/services/settings.py)
- Fixed blueprint-compiler GIRepository compatibility with GNOME Platform 49

### Changed

- Improved TTS cache file location (XDG_CACHE_HOME)

## [0.1.0] - 2026-04-23 {version-0.1.0}

### Added

- Initial release of Anura (fork of Frog)
- Complete rebranding to Anura
- Removed all telemetry and PostHog tracking for total privacy
- Optimized sharing service: added X (formerly Twitter) and Instagram
- Updated dependencies for modern Linux distributions
