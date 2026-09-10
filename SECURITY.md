# Security Policy

> Anura OCR takes security seriously. All processing happens locally — no data leaves your machine.  
> If you find a vulnerability, please follow the responsible disclosure process below.

---

## Reporting a Vulnerability

### Preferred — GitHub Security Advisories

**[Open a private Security Advisory →](https://github.com/d3msudo/anura/security/advisories/new)**

---

## Supported Versions

| Version | Supported |
| ------- | -------- |
| 0.1.x | ✅ Active |

---

## What to Report

### 🔴 High Priority

| Issue | Description |
| ------- | ----------- |
| **Tesseract Injection** | Unvalidated `lang_code` arguments passed to pytesseract or Tesseract |
| **Path Traversal** | Access to files outside intended directories (tessdata, TTS cache, downloads) |
| **Command Injection** | Insufficient sanitization of paths or user input in shell commands |
| **Flatpak Sandbox Bypass** | Circumvention of `--filesystem=xdg-download` or XDG portal restrictions |

### 🟡 Medium Priority

| Issue | Description |
| ------- | ----------- |
| **Denial of Service (DoS)** | Resource exhaustion from malformed images. Bypass of `MAX_IMAGE_SIZE_BYTES` checks. |
| **Race Conditions** | Inconsistencies in `AtomicTaskManager` execution or temporary file operations |
| **URI Injection** | Bypass of `uri_validator()` in `utils/validators.py` (homograph attacks, RTL spoofing) |
| **Text Injection** | Manipulation of terminal or UI via malformed OCR text (Control/Format character injection) |

### 🔍 Areas of Concern

| File | Area |
| ---- | ---- |
| `anura/config.py` | `lang_code` validation — used as Tesseract argument |
| `anura/utils/validators.py` | URI validation (`uri_validator`) and Text Sanitization (`sanitize_text`) |
| `anura/core/atomic_task_manager.py` | Concurrency and task versioning logic |
| `anura/services/screenshot_service.py` | Image size validation (DoS prevention) and Tesseract hand-off |
| `anura/services/language_manager.py` | Tessdata model download and atomic writing |
| `anura/services/share_service.py` | Dynamic URI scheme validation and Pango markup sanitization |
| `anura/services/notification_service.py` | Pango markup injection prevention in notifications |
| `anura/services/screenshot/legacy_provider.py` | Command building for the bundled `scrot` fallback |

---

## Implemented Security Features

| Feature | Implementation |
| ------- | ------------- |
| **DoS & OOM Prevention** | Strict `MAX_IMAGE_SIZE_BYTES` checks AND dynamic `Resource Guards` that block high-res processing if free RAM < 15% or available RAM < 500MB. |
| **Transactional Worker I/O** | All OCR worker artifacts are isolated in a `tempfile.TemporaryDirectory` with environment-level redirection (`TMPDIR`, `TEMP`, `TMP`) to prevent data leakage. |
| **Text Sanitization** | `validators.sanitize_text` strips Unicode Control (Cc), Format (Cf), Private Use (Co), and Surrogate (Cs) categories to prevent terminal injection and RTL spoofing. |
| **URI Validation** | `uri_validator()` blocks homograph attacks (mixed-script) and disallowed schemes before any browser launch. |
| **Pango Markup Injection Prevention** | Hardened notifications against Pango markup injection attacks to prevent UI spoofing. |
| **Local Storage Permission Hardening** | Enhanced directory permissions for sensitive data storage to prevent unauthorized access. |
| **Config Layer Leakage Protection** | Prevents unintended exposure of internal configuration through lifecycle-scoped access controls. |
| **Hierarchical ID Collision Prevention** | Guards against identifier conflicts that could lead to OCR pipeline instability and data cross-contamination. |
| **Dynamic URI Scheme Validation** | ShareService implements dynamic URI scheme validation to prevent protocol injection attacks. |
| **Atomic Task Management** | `AtomicTaskManager` prevents race conditions via single-slot execution and UUID versioning with `BrokenProcessPool` recovery. |
| **Secure Logging** | Offline rotary logging system with strict rotation and retention policies; strictly zero-telemetry. |
| **Automated Lifecycle** | Native GObject destruction hooks ensure complete signal disconnection and resource teardown. |
| **X11 Fallback Security** | Bundled `scrot` fallback used only when Portals fail on X11; Wayland strictly enforces Portal security. |
| **Atomic tessdata writes** | `tempfile` + `shutil.move` prevents partial file corruption. |
| **Flatpak sandbox** | Filesystem isolation with restricted XDG directory access. |
| **Privacy by design** | No telemetry, tracking, or analytics of any kind. |

---

## Contacts

| Channel | Link |
| ------- | ---- |
| Security vulnerabilities | [GitHub Security Advisories](https://github.com/d3msudo/anura/security/advisories) |
| General issues | [GitHub Issues](https://github.com/d3msudo/anura/issues) |
| Project | https://github.com/d3msudo/anura |
