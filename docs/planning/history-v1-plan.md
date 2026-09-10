# Anura — History V1

> **Historical document — pre-implementation plan (baseline `testing @ a52f4563`).**
> History V1 has since been implemented and merged on `testing`; the current
> normative reference is [../history-v1.md](../history-v1.md). This file is
> preserved unchanged as implementation history.

## Piano di implementazione aggiornato — baseline repository 28 agosto 2026 (`testing @ a52f4563`)

**Repository:** `D3M-Sudo/Anura`  
**Baseline:** `testing`  
**Baseline HEAD verificato:** `a52f4563bf0ff0e0d9078d440df877bcfc74045a`  
**Verifica baseline (28 agosto 2026):**

```text
Baseline verificata:
testing @ a52f4563

Include:
PR #381 — FEDC workflow fix (merge PR #381: fix flatpak-fedc-workflow, nessun impatto sui moduli applicativi)
```  
**Branch History V1:** NON presente attualmente  
**Reference branch:** `jules-7542566854136298361-5b384f6c`  
**Reference PR:** #343  
**Stato PR #343:** aperta, non mergiata  
**Regola:** `testing` NON deve essere modificato direttamente.

---

# 1. Executive Summary

L'implementazione History V1 deve essere ripresa come **nuova implementazione su un branch derivato dall'attuale `testing`**, non come merge/cherry-pick della PR #343.

La situazione attuale è importante:

- `testing` è a un commit molto più recente rispetto alla base della PR #343;
- il branch della PR #343 contiene due commit History, ma è **divergente** da `testing`;
- il branch `jules-7542566854136298361-5b384f6c` è indietro di 67 commit rispetto all'attuale `testing` e avanti di soli 2 commit;
- la sua implementazione è quindi una **reference implementation storica**, non una base tecnica da integrare direttamente;
- l'attuale `testing` possiede già una separazione `models / services / controllers`, un `ResultDispatcher`, un `SettingsService`, un `ScreenshotService`, `OcrResult` immutabile e infrastruttura UI Blueprint/GTK4;
- l'attuale `testing` NON contiene ancora `HistoryService`, `HistoryEntry` o una pagina History.

La strategia definitiva è quindi:

```text
testing @ a52f4563
       |
       +-- nuova branch feature-history-v1
                  |
                  +-- implementazione History V1
                  +-- test
                  +-- validation
                  +-- audit
                  |
                  +-- PR → testing
```

---

# 2. Repository State

## Branch presenti

Al controllo del 27 agosto 2026 risultano:

```text
development
main
testing
jules-7542566854136298361-5b384f6c
```

Non risulta presente:

```text
feature-history-v1
```

Pertanto il branch History V1 deve essere creato ex novo da `testing`.

## Baseline

`testing`:

```text
a52f4563bf0ff0e0d9078d440df877bcfc74045a
```

Commit più recente al momento della verifica:

```text
Merge pull request #381 from D3M-Sudo/feature/fix-flatpak-fedc-workflow
ci: fix ruff lint errors in fedc certifi scripts (FEDC workflow fix)
```

Il branch `testing` non è protetto da branch protection GitHub al momento del controllo. Questo NON modifica la regola di progetto: le feature devono comunque essere sviluppate su branch dedicati.

---

# 3. Stato della PR #343

PR:

```text
#343
Implement Navigable Capture History with Rich Metadata and Virtualized ListView
```

Head:

```text
jules-7542566854136298361-5b384f6c
41ed315bf336c4081bc0ae884a91a3e041a51127
```

Base dichiarata dalla PR:

```text
testing
b8b343733bc6464fcb253f38bab9619164e45aa3
```

Rispetto all'attuale `testing`, il branch della PR è:

```text
diverged
ahead: 2
behind: 67
```

I due commit della PR implementano principalmente:

1. History service;
2. modello `CaptureSession`;
3. UI History;
4. navigation/action;
5. OCR integration;
6. shutdown;
7. Blueprint compiler/CI;
8. test History.

Questa implementazione non deve essere portata avanti tramite merge della PR.

---

# 4. Perché NON riusare direttamente la #343

La PR #343 contiene alcune decisioni che oggi sono incompatibili con il contratto V1.

## Problema 1 — modello

La PR introduce:

```text
CaptureSession
```

come modello della History.

History V1 richiede invece:

```text
HistoryEntry
```

`CaptureSession` non deve diventare il modello persistente della History.

## Problema 2 — accoppiamento OCR/thumbnail

La PR modifica:

```text
OcrResult
```

aggiungendo:

```text
thumbnail_base64
```

Questo è da scartare.

La thumbnail è una responsabilità della History/persistence layer e non del modello OCR.

## Problema 3 — Base64

La PR persiste:

```text
thumbnail_base64
```

nel record JSON.

History V1 richiede file separati:

```text
history/
├── history.json
└── thumbnails/
    └── <entry-id>.png
```

## Problema 4 — API

La PR aggiunge direttamente a `_on_shot_done()`:

```text
get_history_service().add_session(...)
```

L'integrazione deve essere riprogettata in modo da preservare il confine:

```text
OCR result
    ↓
History eligibility
    ↓
HistoryEntry
    ↓
HistoryService
```

## Problema 5 — writer thread

La PR introduce una propria strategia di thread/lock/join.

Non deve essere copiata automaticamente.

Prima si deve verificare l'infrastruttura di `testing` e usare il minimo meccanismo necessario per garantire:

- UI non bloccata da I/O significativo;
- serializzazione delle scritture;
- shutdown deterministico;
- testabilità.

---

# 5. Current `testing` Architecture Relevant to History

## Modelli

`testing` possiede:

```text
anura/models/
├── context.py
├── download_state.py
├── language_item.py
└── ocr.py
```

`OcrResult` è un dataclass immutabile e contiene:

```text
words
raw_text
avg_confidence
```

Non deve essere esteso con dati persistenti della History.

## Controller

Esiste:

```text
anura/controllers/ocr_controller.py
```

Questo è il punto principale da analizzare per l'handoff OCR → History.

Esistono anche:

```text
dnd_controller.py
tts_controller.py
```

## Services

L'architettura attuale comprende:

```text
clipboard_service.py
language_manager.py
notification_service.py
result_dispatcher.py
screenshot_service.py
settings.py
share_service.py
...
```

Questo rende naturale introdurre:

```text
anura/services/history_service.py
```

ma senza introdurre un nuovo framework/service pattern.

## ResultDispatcher

`ResultDispatcher` è esplicitamente un servizio Python separato da UI/settings/side effects.

History NON deve essere inserita dentro `ResultDispatcher`.

## Screenshot

Esiste:

```text
anura/services/screenshot_service.py
```

e una relativa struttura:

```text
anura/services/screenshot/
```

La thumbnail deve riutilizzare le primitive di immagine/capture disponibili, evitando una seconda pipeline di cattura.

## Settings

Esiste:

```text
anura/services/settings.py
```

e lo schema:

```text
data/io.github.d3msudo.anura.gschema.xml
```

History deve integrarsi con questa infrastruttura.

## UI

`testing` utilizza:

```text
data/ui/*.blp
data/ui/*.ui
```

e:

```text
data/io.github.d3msudo.anura.gresource.xml
```

La nuova UI deve seguire questa convenzione.

---

# 6. Functional Contract — History V1

Queste decisioni sono congelate.

## Privacy

Default:

```text
history-enabled = false
```

Quando OFF:

- nessuna nuova entry;
- nessuna thumbnail;
- nessun I/O History non necessario.

Disabilitare History NON elimina la cronologia già presente.

Solo `Clear History` la elimina.

## Limit

Default:

```text
50
```

Range:

```text
1..100
```

Quando il limite viene superato:

```text
new entry
    ↓
evict oldest
    ↓
delete its thumbnail
```

## Entry

Nome:

```text
HistoryEntry
```

Campi minimi:

```text
id
timestamp
text
language
transformer
thumbnail reference/path
```

I nomi effettivi devono rispettare le convenzioni del repository.

## Eligibility

Una entry viene creata SOLO se:

```text
OCR success
+
text non vuoto
+
History enabled
```

Non salvare:

- OCR failure;
- testo vuoto;
- risultati intermedi;
- tentativi falliti.

## Search

NON implementare Search in V1.

---

# 7. Target Architecture

Target:

```text
                Capture
                   |
                   v
                 OCR
                   |
                   v
          successful result?
              /          \
            NO            YES
            |              |
            |        text non-empty?
            |              |
            |            NO
            |              |
            |             stop
            |
            v
           stop

YES
 |
 v
History enabled?
 /             \
NO              YES
|                |
stop              v
             HistoryEntry
                  |
                  v
            HistoryService
              /         \
             v           v
          memory     thumbnail
             |           |
             +-----+-----+
                   |
                   v
             atomic JSON
                   |
                   v
              History UI
```

Confini:

```text
OCR domain
    ≠
History domain
    ≠
Persistence
    ≠
UI
```

`OcrResult` non deve conoscere `HistoryService`.

`HistoryService` non deve conoscere dettagli GTK della UI oltre alle notifiche/segnali minimi necessari.

---

# 8. HistoryEntry

## Responsabilità

`HistoryEntry` rappresenta una singola voce della cronologia.

Deve essere:

- facilmente serializzabile;
- facilmente deserializzabile;
- indipendente da GTK, se possibile;
- adatta ai test unitari;
- priva di immagini embedded.

## Thumbnail

La entry deve conservare solo una reference/path relativo, ad esempio:

```text
thumbnails/<id>.png
```

Non:

```text
thumbnail_base64
```

## Timestamp

Usare una rappresentazione stabile e serializzabile.

Preferire un formato coerente con le convenzioni esistenti.

---

# 9. HistoryService

File target:

```text
anura/services/history_service.py
```

Responsabilità:

- load;
- lazy load;
- add;
- delete;
- clear;
- limit/eviction;
- persistence;
- thumbnail lifecycle;
- recovery;
- emissione di cambiamenti alla UI.

API minima indicativa:

```text
list_entries()
add(...)
delete(entry_id)
clear()
reload/load()
```

I nomi definitivi devono seguire le convenzioni di `testing`.

## Singleton

`testing` utilizza già:

```text
get_instance(...)
```

Il servizio deve preferibilmente seguire questa convenzione se il lifecycle dell'applicazione lo rende appropriato.

Non introdurre dependency injection o un container solo per History.

---

# 10. Persistence

Formato:

```text
JSON
```

Layout previsto:

```text
$XDG_STATE_HOME/anura/history/
├── history.json
└── thumbnails/
    ├── <id>.png
    └── ...
```

Il path deve essere verificato contro le convenzioni XDG effettive di `testing` prima dell'implementazione.

## Source of truth

Preferire:

```text
in-memory state
       ↓
serialization
       ↓
atomic write
```

## Atomic write

Non scrivere direttamente sul file finale.

Pattern:

```text
serialize
   ↓
temporary file
   ↓
flush/fsync se appropriato
   ↓
atomic replace
```

## Corruption

Se `history.json` è corrotto:

- Anura non deve crashare;
- preservare il file corrotto;
- creare uno stato vuoto recuperabile;
- loggare l'errore;
- non cancellare silenziosamente i dati originali.

Una strategia raccomandata è:

```text
history.json
     ↓
parse failure
     ↓
history.json.corrupt-<timestamp>
     ↓
empty in-memory history
```

La convenzione finale deve essere deterministica e testata.

---

# 11. Thumbnail Design

La thumbnail deve essere generata dalla cattura già disponibile.

Non acquisire una seconda screenshot.

Flusso:

```text
capture image
      |
      +----> OCR
      |
      +----> thumbnail generation
```

ma la thumbnail viene materialmente generata solo dopo:

```text
OCR success
+
non-empty
+
history enabled
```

Questo evita lavoro inutile quando History è OFF.

## Storage

PNG o formato già supportato dalle primitive esistenti.

La dimensione deve essere piccola e adatta a una lista UI.

Non memorizzare l'immagine originale a piena risoluzione nella History.

---

# 12. OCR Integration

Punto da implementare:

```text
anura/controllers/ocr_controller.py
```

Prima di modificare `_on_shot_done()` occorre confermare il lifecycle dell'immagine catturata.

Il micro-audit precedente ha individuato proprio questo come vincolo architetturale:

```text
OCR completion
      ↓
History handoff
      ↓
source image cleanup
```

L'ordine deve garantire che la thumbnail possa essere derivata dalla cattura senza estendere `OcrResult`.

## Regola

History handoff deve essere effettuato:

```text
dopo OCR success
prima della distruzione definitiva dell'immagine sorgente
```

ma senza ritardare inutilmente il cleanup.

Se l'immagine non è più disponibile nel punto corretto, bisogna introdurre la minima modifica al lifecycle della capture necessaria per rendere disponibile una reference temporanea.

Non aggiungere `thumbnail_base64` a `OcrResult`.

---

# 13. Settings / GSettings

File principali:

```text
data/io.github.d3msudo.anura.gschema.xml
anura/services/settings.py
```

Aggiungere:

```text
history-enabled
history-limit
```

Valori:

```text
history-enabled = false
history-limit = 50
```

Range:

```text
1..100
```

La UI Preferences deve essere aggiornata usando il pattern già esistente.

Disabilitare History non deve cancellare i dati.

---

# 14. UI / Navigation

## Nuova pagina

Preferibilmente:

```text
data/ui/history_page.blp
data/ui/history_page.ui
```

e relativo codice Python secondo la struttura effettiva delle pagine esistenti.

La pagina deve supportare:

- empty state;
- lista;
- thumbnail;
- testo;
- timestamp;
- language/transformer se utile;
- Copy;
- Delete;
- Clear History.

## Row

La row deve essere separata se questo segue il pattern attuale:

```text
history_row.blp
history_row.ui
```

Non creare un modello GTK separato se il modello domain può essere adattato senza accoppiamento.

## Navigation

La History deve essere raggiungibile dalla navigation attuale.

La PR #343 propone:

```text
Ctrl+H
```

Prima di assegnarlo verificare il registry delle action.

Se libero:

```text
Ctrl+H → History
```

Se occupato:

- mantenere lo shortcut esistente;
- scegliere un'alternativa coerente;
- documentare la decisione.

## Menu

Aggiungere una voce History/Recent Captures solo se coerente con la navigation attuale.

---

# 15. Copy / Delete / Clear

## Copy

Deve essere direttamente accessibile dalla row.

Riutilizzare:

```text
ClipboardService
```

Non implementare una seconda clipboard abstraction.

## Delete

```text
delete entry
     ↓
delete thumbnail
     ↓
update memory
     ↓
persist
```

La cancellazione deve essere coerente anche se il file thumbnail non esiste più.

## Clear

```text
confirmation
     ↓
delete all entries
     ↓
delete thumbnails
     ↓
persist empty state
```

Dopo Clear:

```text
History = empty
```

Non devono rimanere thumbnail orfane.

---

# 16. Threading / Async

La strategia definitiva deve essere scelta dopo l'ispezione dell'infrastruttura corrente.

Requisiti:

- nessun blocco significativo del main/UI thread;
- una sola sequenza di write;
- nessuna race;
- shutdown deterministico;
- testabilità.

Priorità:

1. riutilizzare infrastruttura esistente;
2. usare serializzazione semplice se l'I/O è trascurabile;
3. introdurre un worker dedicato solo se necessario.

NON copiare automaticamente:

```text
writer thread
1.5s join
```

della #343.

---

# 17. Lazy Loading

La History non deve essere caricata allo startup se non necessaria.

Target:

```text
application startup
       ↓
HistoryService creato
       ↓
NO JSON read
       ↓
user opens History
       ↓
load once
```

Il servizio deve mantenere:

```text
loaded = false
```

o equivalente.

Una volta caricata:

```text
loaded = true
```

Le operazioni successive lavorano sulla memoria.

---

# 18. Test Strategy

Usare il framework già presente in `testing`.

NON introdurre un nuovo framework.

## Model tests

- valid entry;
- invalid entry;
- serialization;
- deserialization;
- missing field;
- malformed field;
- timestamp;
- thumbnail reference.

## Service tests

- History disabled;
- History enabled;
- valid add;
- empty text;
- failed OCR;
- limit 1;
- limit 50;
- limit 100;
- eviction;
- delete;
- clear;
- lazy load;
- reload;
- corrupted JSON;
- recovery backup;
- missing thumbnail;
- orphan thumbnail;
- atomic persistence;
- persistence failure.

## Thumbnail tests

- creation;
- resize;
- valid reference;
- deletion;
- eviction cleanup;
- clear cleanup;
- source image unavailable;
- History disabled → no thumbnail.

## OCR integration

Test:

```text
OCR success
→ History enabled
→ HistoryEntry
→ thumbnail
→ persistence
```

e:

```text
OCR failure
→ no History
```

```text
OCR empty
→ no History
```

```text
History disabled
→ no History I/O
```

## UI

- empty state;
- populated state;
- disabled banner/state;
- Copy;
- Delete;
- Clear;
- navigation;
- shortcut;
- reload persistence.

---

# 19. CI / Build / Resources

La PR #343 modifica `.github/workflows/main.yml` per:

- blueprint-compiler;
- compilazione `.blp`;
- esclusione di `test_history_service.py`.

Queste modifiche NON devono essere copiate automaticamente.

## Decisione attuale

### Blueprint compiler

**VERIFICARE**

Se `testing` già compila Blueprint in CI, non aggiungere nulla.

Se non lo fa, introdurre il minimo necessario.

### Generated `.ui`

Seguire la policy attuale del repository:

```text
.blp → .ui
```

Non modificare manualmente generated files se la policy corrente li rigenera.

### Test exclusion

La modifica della #343:

```text
--ignore=tests/test_history_service.py
```

deve essere considerata **DA SCARTARE** salvo prova concreta di incompatibilità.

Un nuovo test History deve entrare nella suite principale.

Non risolvere problemi di test con esclusioni CI.

---

# 20. File Plan

## Probabili file nuovi

```text
anura/models/history.py
anura/services/history_service.py
data/ui/history_page.blp
data/ui/history_page.ui
tests/test_history.py
tests/test_history_service.py
```

Eventualmente:

```text
anura/widgets/history_row.py
data/ui/history_row.blp
data/ui/history_row.ui
```

solo se la struttura UI corrente lo richiede.

## Probabili file modificati

```text
anura/controllers/ocr_controller.py
anura/main.py
anura/core/action_registry.py
anura/services/settings.py
anura/services/clipboard_service.py   # solo se necessario
data/io.github.d3msudo.anura.gschema.xml
data/io.github.d3msudo.anura.gresource.xml
data/ui/<pagina/navigation attuale>.blp
data/ui/<pagina/navigation attuale>.ui
data/ui/preferences_general.blp
```

La lista finale deve essere ridotta dopo l'audit dei file reali.

## File da NON creare

Non creare:

```text
anura/models/capture_session.py
```

salvo necessità architetturale emersa durante l'implementazione.

Non creare:

```text
history_database.py
history_repository.py
history_controller.py
```

solo per aumentare i layer.

V1 deve rimanere semplice.

---

# 21. Migration Matrix — PR #343 → History V1

| Componente #343 | Decisione | Motivazione |
|---|---|---|
| `CaptureSession` | DROP/REWRITE | V1 richiede `HistoryEntry` |
| `thumbnail_base64` in `OcrResult` | DROP | accoppiamento OCR/persistence |
| Base64 nel JSON | DROP | storage inefficiente; file separato richiesto |
| `HistoryService` concept | ADAPT | idea valida, API/lifecycle da riprogettare |
| JSON persistence | KEEP/ADAPT | formato V1 confermato |
| lock/thread writer | ADAPT | usare infrastruttura attuale |
| corruption recovery | ADAPT | mantenere requisito, semplificare dove possibile |
| GObject History model | REWRITE | preferire domain model indipendente da GTK |
| Gtk.ListView | KEEP/ADAPT | pattern appropriato per lista virtualizzata |
| History page | ADAPT | UI da riallineare a `testing` |
| `Ctrl+H` | ADAPT | verificare action registry corrente |
| menu Recent Captures | ADAPT | integrare con UI corrente |
| OCR hook | REWRITE/ADAPT | rispettare lifecycle immagine e eligibility |
| History shutdown | ADAPT | solo se il nuovo service possiede risorse da chiudere |
| Blueprint CI | VERIFY | non copiare se già presente |
| test exclusion | DROP | i test devono essere parte della suite |
| `blueprint-compiler` dependency | VERIFY | introdurre solo se mancante |
| generated UI | ADAPT | seguire policy attuale |
| PR #343 intera | DROP | branch troppo vecchio/divergente |

---

# 22. Ordered Implementation Plan

## PHASE 0 — Branch & baseline

### Obiettivo

Creare il punto di partenza corretto.

### Azioni

```text
git checkout testing
git pull
git checkout -b feature-history-v1
```

### Criteri

- branch creato da HEAD attuale di `testing`;
- `testing` invariato;
- working tree clean.

---

## PHASE 1 — Architecture confirmation

### Obiettivo

Chiudere prima dell'implementazione le decisioni tecniche ancora dipendenti dal codice corrente.

### Verificare

- lifecycle screenshot;
- punto esatto di `_on_shot_done()`;
- XDG state/data/config;
- navigation;
- action registry;
- SettingsService;
- ClipboardService;
- pattern delle pagine UI;
- test framework;
- eventuale task/background infrastructure.

### Output

Un breve audit interno nel branch:

```text
History V1 implementation assumptions
```

### Criterio

Nessuna decisione architetturale critica lasciata a supposizioni.

---

## PHASE 2 — HistoryEntry

### Obiettivo

Implementare il modello domain.

### Deliverable

```text
HistoryEntry
```

### Test

- construction;
- serialization;
- deserialization;
- invalid data.

### Criterio

Model completo e indipendente dalla UI.

---

## PHASE 3 — Persistence

### Obiettivo

Implementare storage robusto.

### Deliverable

```text
HistoryService
```

con:

- lazy load;
- JSON;
- atomic write;
- corruption recovery;
- in-memory state.

### Test

Tutti i test persistence.

### Criterio

HistoryService utilizzabile senza GTK UI.

---

## PHASE 4 — Limit + thumbnails

### Obiettivo

Chiudere il lifecycle completo dei dati.

### Implementare

- limit 1..100;
- default 50;
- eviction;
- thumbnail creation;
- thumbnail deletion;
- orphan cleanup.

### Criterio

Entry e thumbnail sempre coerenti.

---

## PHASE 5 — OCR integration

### Obiettivo

Collegare History alla pipeline reale.

### Implementare

```text
OCR success
+
non-empty
+
enabled
```

### Verificare

```text
capture lifetime
```

### Criterio

La History non modifica il contratto di `OcrResult`.

---

## PHASE 6 — Settings

### Implementare

```text
history-enabled
history-limit
```

### Criterio

Default e range corretti.

---

## PHASE 7 — UI

### Implementare

- History page;
- row;
- empty state;
- thumbnail;
- text;
- timestamp;
- Copy;
- Delete;
- Clear;
- disabled state.

### Criterio

UI funzionante senza accesso diretto alla persistence interna.

---

## PHASE 8 — Navigation

### Implementare

- action;
- menu;
- navigation;
- shortcut se disponibile.

### Criterio

History raggiungibile in modo coerente con l'app.

---

## PHASE 9 — Tests

### Completare

```text
unit
integration
UI smoke
persistence
OCR → History
thumbnail lifecycle
```

### Criterio

Nessuna esclusione CI per History.

---

## PHASE 10 — CI / Build

### Verificare

- Blueprint;
- GResource;
- test discovery;
- lint;
- package build;
- Flatpak.

### Criterio

Tutta la pipeline verde.

---

## PHASE 11 — Final audit

Confrontare:

```text
feature-history-v1
        vs
testing
```

Verificare:

- solo file previsti;
- nessun codice #343 portato accidentalmente;
- nessuna modifica non correlata;
- nessun `thumbnail_base64`;
- nessun `CaptureSession` usato impropriamente;
- History OFF di default;
- limit 50/1..100;
- no search;
- atomic persistence;
- corruption recovery;
- orphan cleanup.

---

# 23. Definition of Done

History V1 è completa solo quando:

```text
[ ] branch feature-history-v1 deriva dall'attuale testing
[ ] testing non è stato modificato direttamente
[ ] HistoryEntry implementato
[ ] HistoryService implementato
[ ] lazy load funzionante
[ ] JSON persistence funzionante
[ ] atomic write
[ ] corrupted JSON recovery
[ ] history-enabled=false default
[ ] history-limit=50 default
[ ] range 1..100
[ ] oldest eviction
[ ] thumbnail separata
[ ] nessun Base64
[ ] nessun thumbnail_base64 in OcrResult
[ ] OCR failure non salva
[ ] OCR empty non salva
[ ] History disabled non produce I/O History
[ ] Delete elimina thumbnail
[ ] Clear elimina tutte le thumbnail
[ ] orphan handling
[ ] Copy
[ ] History UI
[ ] navigation
[ ] shortcut verificato
[ ] unit tests
[ ] integration tests
[ ] UI tests/smoke
[ ] CI verde
[ ] build verde
[ ] Flatpak validation verde
[ ] final diff audit vs testing
```

---

# 24. Risks

## R1 — Capture lifetime

**Priorità: ALTA**

Il rischio maggiore è che l'immagine originale venga rilasciata prima dell'handoff History.

Mitigazione:

```text
OCR completion
→ History handoff
→ source cleanup
```

senza inserire immagini dentro `OcrResult`.

## R2 — UI blocking

**Priorità: MEDIA**

JSON e thumbnail devono evitare blocchi significativi del main loop.

## R3 — Corrupted persistence

**Priorità: MEDIA**

Recovery deve essere esplicita e testata.

## R4 — Orphan thumbnails

**Priorità: MEDIA**

Delete/eviction/clear devono essere transazioni logiche coerenti.

## R5 — Regression in navigation

**Priorità: MEDIA**

Verificare `Ctrl+H` prima di usarlo.

## R6 — Generated UI/CI

**Priorità: MEDIA**

Seguire le convenzioni già presenti in `testing`; non copiare il workflow della #343.

---

# 25. Explicit Non-Goals for V1

NON implementare:

```text
search
cloud sync
database SQLite
full-resolution image archive
OCR result versioning
editing of historical OCR
tags
folders
export/import
cross-device synchronization
new test framework
new DI framework
new persistence abstraction stack
```

History V1 deve rimanere una cronologia locale, recente e limitata.

---

# 26. Final Recommendation

La situazione attuale rende **sbagliato** procedere con la PR #343 così com'è.

La decisione raccomandata è:

```text
KEEP
    History concept
    JSON persistence
    ListView UI concept
    navigation concept
    settings concept

ADAPT
    HistoryService
    OCR integration
    UI
    threading
    corruption recovery
    CI/build integration

REWRITE
    HistoryEntry
    persistence API
    thumbnail lifecycle
    capture/History handoff

DROP
    CaptureSession as History model
    thumbnail_base64
    Base64 persistence
    CI test exclusion
    obsolete PR-specific changes
```

Il prossimo lavoro deve quindi partire da:

```text
testing @ a52f4563
        ↓
feature-history-v1
        ↓
PHASE 1 — Architecture confirmation
        ↓
PHASE 2 — HistoryEntry
        ↓
...
        ↓
PR → testing
```

**Non effettuare merge/cherry-pick della #343.**

La PR #343 rimane esclusivamente una reference implementation da consultare durante l'implementazione.
