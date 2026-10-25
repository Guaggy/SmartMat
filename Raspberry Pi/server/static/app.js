"use strict";
// SmartMat dashboard. Plain JS, no build step. Everything that comes from the API is written with
// textContent / setAttribute / canvas, never innerHTML (names and rooms are typed in by people).

// ---------- text (Norwegian bokmaal first, English on toggle) ----------
const i18n = {
  nb: {
    unitFilter: "Filtrer på avdeling", allUnits: "Alle avdelinger", sortBy: "Sorter etter",
    sortRisk: "Risiko", sortRoom: "Rom", sortDevice: "Enhet", sortTime: "Tid i stilling",
    searchPh: "Søk rom, enhet, sete", alerts: "Varsler", help: "Hjelp", back: "Tilbake",
    colDevice: "Enhet", colRoom: "Rom", colSeat: "Sete", colOk: "Data OK", colStatus: "Status",
    theme: "Bytt mellom lys og mørk", langBtn: "EN", filterCount: "Filter ({n} av {m} matter)",
    details: "Detaljer", live: "sanntid", handleNow: "Handle nå", noOpenAlert: "Ingen åpne varsler for denne matten.",
    lgPosture: "Stilling", lgRisk: "Risiko",
    p_left: "Venstre side", p_right: "Høyre side", p_forward: "Lent fremover", p_centred: "Sentrert", p_none: "Ingen bruker",
    statusNone: "Ingen bruker i {t}", offline: "Frakoblet, ingen data", alertFlag: "Varsel",
    dataOk: "Data OK", dataLost: "Ingen data",
    risk_high: "Høy risiko", risk_medium: "Middels risiko", risk_low: "Lav risiko", risk_none: "Ingen bruker", risk_offline: "Frakoblet",
    h: "t", min: "min", ago: "{t} siden",
    pressureMap: "Trykkart", front: "Foran", low: "Lav", high: "Høy", edit: "Rediger", toList: "Til listen",
    layer: "Data", mode: "Visning", layer_pressure: "Trykk", layer_exposure: "Eksponering (trykk x tid)", layer_burden: "Belastning",
    layer_since_relief: "Tid siden avlastning", layer_loaded_time: "Belastet tid", view_live: "Sanntid", view_average: "Glattet (snitt over 5 bilder)",
    mapUnitLayer: "{n} {u} full farge", contactArea: "Kontaktflate", loadIndic: "Veiledende last", loadHint: "ca., ikke en veiing", loadNoSize: "Matstørrelse ikke satt",
    loadLow: "leses for lavt, celler ved sensorgrensen", defaultCurve: "standardkurve, ikke kalibrert", nCells: "{n} celler", sinceMove: "Tid siden bevegelse", never: "ingen ennå",
    balance: "Fordeling", balL: "Venstre", balR: "Høyre", balF: "Foran", balB: "Bak", copKey: "+ = trykktyngdepunkt", spotArea: "{n} celler", spotAreaCm: "{n} celler, {a} cm²",
    spotPeak: "{p} kPa", spotSel: "Marker hotspot {id}", noSpots: "Ingen hotspots nå.",
    screenSettings: "Denne skjermen", alertSound: "Lyd og blink ved nytt varsel", alertSoundHint: "Kort pip og et rødt blink når et nytt varsel kommer. Gjelder bare denne nettleseren og er av som standard. Nettleseren krever at du har trykket på siden først.", alertTest: "Test",
    highestPressure: "Høyeste trykk", highestRelative: "Høyeste signal", sinceRelief: "Tid siden avlastning",
    timeInPos: "Tid i stilling", lastData: "Siste data", hotspots: "Hotspots", indices: "Indikatorer", none: "Ingen",
    persistent: "vedvarende", activeFor: "aktiv {t}",
    idx_ok: "OK", idx_near: "Nær grensen", idx_over: "Over grensen",
    selectMat: "Velg en mat i listen for å se trykkart.", noMats: "Ingen matter funnet.",
    saturation: "{n} celler ved sensorgrensen: last og topp leses for lavt",
    uncal: "Ikke kalibrert: relativt signal, ikke trykk.",
    staleMat: "Ingen nye data på {t}. Bildet er gammelt.", offlineMat: "Matten er frakoblet. Bildet viser siste kjente data.",
    lostServer: "Ingen kontakt med serveren. Statusene under kan være gamle.",
    unoccupied: "Ingen bruker på matten.", mapUnit: "{n} kPa full farge", mapUnitRel: "relativt signal",
    noAlerts: "Ingen varsler.", kind_high_risk: "Høy risiko", kind_offline: "Frakoblet",
    raised: "utløst for {t} siden", st_open: "Åpen", st_acknowledged: "Bekreftet", st_ignored: "Ignorert", byUser: "av {u}",
    ack: "Bekreft", ignore: "Ignorer", pin: "PIN", cancel: "Avbryt", ok: "OK",
    dlgAck: "Bekreft varsel: {name}", dlgIgnore: "Ignorer varsel: {name}", dlgEdit: "Rediger mat",
    fName: "Navn", fRoom: "Rom", fSeat: "Sete", fUnit: "Avdeling",
    ackBy: "Bekreftet av {u}", ignBy: "Ignorert av {u}", savedBy: "Lagret av {u}", netErr: "Ingen kontakt med serveren.",
    tlTitle: "Siste {n} timer", lgNoData: "Ingen data", lgHandled: "Håndtert (bekreftet eller ignorert)", showMap: "Vis trykkart",
    handledBy: "Håndtert av {u}",
    users: "Brukere", close: "Lukk", addUser: "Ny bruker", disable: "Deaktiver", enable: "Aktiver", resetPin: "Ny PIN",
    roleAdmin: "Administrator", roleUser: "Sykepleier", userOff: "deaktivert", fRole: "Rolle",
    fNewPin: "Ny PIN (4-8 siffer)", fRepeatPin: "Gjenta PIN", adminPin: "Din PIN (administrator)",
    dlgFirst: "Opprett første bruker (admin)", firstHint: "Det finnes ingen brukere ennå. Denne personen blir administrator.",
    dlgAddUser: "Ny bruker", dlgDisable: "Deaktiver {n}", dlgEnable: "Aktiver {n}", dlgResetPin: "Ny PIN for {n}",
    pinMismatch: "PIN-kodene er ikke like.", userAdded: "Bruker {n} opprettet", userChanged: "Endret av {u}",
    settings: "Innstillinger", loading: "Laster …",
    setIntro: "Alle kan se innstillingene. Å endre noe krever PIN til en administrator. Endringene gjelder med en gang og logges med navn.",
    setMats: "Matter", setMatsHint: "Gi hver mat navn, rom, sete og avdeling. En mat som er tatt ut av bruk kan fjernes når den er frakoblet.",
    rm: "Fjern", restore: "Gjenopprett", removedMats: "Fjernede matter", noRemoved: "Ingen fjernede matter.",
    dlgRemove: "Fjern {name}?", dlgRestore: "Gjenopprett {name}?",
    rmHint: "Matten vises ikke lenger, og åpne varsler for den lukkes. Du kan gjenopprette den her. Bare frakoblede matter kan fjernes.",
    restoreHint: "Matten vises i listen igjen så snart den sender data.", removedBy: "Fjernet av {u}", restoredBy: "Gjenopprettet av {u}",
    g_alerts: "Varsler", g_risk: "Risikonivå", g_mats: "Sensor og tilkobling", g_data: "Lagring", g_posture: "Stilling",
    g_risk_h: "Disse to verdiene styrer hvor følsomme «Middels» og «Høy risiko» er. Endre dem bare etter avtale: de er ikke klinisk validert.",
    advanced: "Avansert (for ingeniører)", setDefault: "Standard: {v}", resetDefault: "Tilbakestill",
    setOn: "På", setOff: "Av", u_days: "dager", u_cells: "celler",
    errNumber: "Skriv et tall.", errWhole: "Bruk et helt tall.", errRange: "Må være mellom {min} og {max}.",
    saveChanges: "Lagre endringer", nChanges: "{n} endring(er) som ikke er lagret", noChanges: "Ingen endringer", fixErrors: "Rett feilene over først.",
    dlgSave: "Lagre innstillinger", savedSettings: "Innstillinger lagret av {u}",
    setUsersHint: "Administratorer og sykepleiere, hver med sin egen PIN.", openUsers: "Åpne brukere",
    s_alert_high_hold_s: "Tid med høy risiko før varsel",
    s_alert_high_hold_s_h: "Hvor lenge risikoen må være høy før et varsel utløses. Kortere gir raskere varsel, men flere falske.",
    s_alert_offline_s: "Tid frakoblet før varsel",
    s_alert_offline_s_h: "Hvor lenge en mat må være stille før det varsles om at den er frakoblet.",
    s_push_enabled: "Push-varsler til telefoner",
    s_push_enabled_h: "Slå av for å stoppe alle push-varsler. Varslene vises fortsatt i dashbordet.",
    s_relief_minutes: "Tid uten avlastning som regnes som full belastning",
    s_relief_minutes_h: "Et område regnes som fullt belastet etter så lang tid uten avlastning. Lavere verdi gir tidligere middels og høy risiko.",
    s_near_percent: "Middels risiko fra",
    s_near_percent_h: "Middels risiko vises når verdien når denne andelen av grensen for høy risiko.",
    s_stale_after_s: "Tid uten data før matten regnes som frakoblet",
    s_stale_after_s_h: "Hvor lenge matten kan være stille før raden blir «Frakoblet».",
    s_saturation_warn_cells: "Varsle om sensorgrense fra",
    s_saturation_warn_cells_h: "Antall celler ved sensorgrensen som utløser merknaden om at last og topp leses for lavt.",
    s_posture_hold_s: "Ny stilling må vare i",
    s_posture_hold_s_h: "Hvor lenge en ny stilling må holde seg før tiden i stilling starter på nytt.",
    s_posture_side_cells: "Sidestilling fra",
    s_posture_side_cells_h: "Hvor mange celler trykkets tyngdepunkt må ligge fra midten for å regnes som venstre eller høyre.",
    s_posture_forward_cells: "Lent fremover fra",
    s_posture_forward_cells_h: "Hvor mange celler tyngdepunktet må ligge foran midten for å regnes som lent fremover.",
    s_retention_days: "Oppbevar logg og tidslinje i",
    s_retention_days_h: "Eldre hendelser og tidslinje slettes automatisk.",
    analysis: "Analyse", siteDefaults: "Standard for hele stedet",
    siteDefaultsHint: "Gjelder alle matter som ikke har egne verdier. Hver mat kan overstyre dem under «Analyse».",
    matCfgTitle: "Analyseinnstillinger: {name}",
    ppTitle: "Matteoppsett lagret på matten (pass)", ppHint: "Kalibreringen følger matten: lagre den før frakt, bruk den igjen ved behov.",
    ppSerial: "Serienummer", ppEmpty: "tom", ppNone: "Matten svarer ikke på passet (offline eller eldre programvare).",
    ppSame: "samme som i bruk", ppDiffers: "avviker fra det som er i bruk", ppUse: "Bruk", ppFactory: "Fabrikk", ppCustom: "Tilpasset",
    ppSave: "Lagre dagens oppsett på matten", ppNote: "Notat (valgfritt)", dlgPpUse: "Bruke {slot}-passet?", dlgPpSave: "Lagre på matten?",
    ppUsed: "Passet er tatt i bruk av {u}", ppSaved: "Lagret på matten (versjon {v}) av {u}", ppAnalysis: "med analyseinnstillinger",
    matCfgIntro: "Verdier som ikke er satt for denne matten følger stedets standard, som igjen følger fabrikkverdiene. Hver endring blir en ny versjon som lagres med navn og begrunnelse.",
    cfgVersion: "Innstillingsversjon {v}", cfgShort: "innstillinger {v}",
    src_factory: "Fabrikk", src_site: "Stedet", src_mat: "Denne matten", setDefaultSite: "Stedets verdi: {v}", useSite: "Bruk stedets verdi",
    g_contact: "Kontakt", g_temporal: "Tidsanalyse", g_hotspots: "Hotspots", g_movement: "Bevegelse",
    idxBuiltin: "Innebygde risikoindekser", idxCustom: "Egendefinerte risikoindekser ({n})", errMin: "Må være minst {min}.",
    s_indices: "Risikoindekser", s_indices_h: "Egendefinerte indekser settes fra skrivebordsprogrammet. Her kan de settes tilbake til de innebygde.",
    reasonLabel: "Begrunnelse (valgfritt)", reasonPh: "Hvorfor endres dette?", saveForMat: "Lagre for denne matten",
    history: "Endringshistorikk", noHistory: "Ingen endringer ennå.", version: "Versjon", restoreVersion: "Gjenopprett v{v}",
    factoryVersion: "Fabrikkverdier (versjon 0)", dlgRollback: "Gjenopprett versjon {v}?", rolledBack: "Gjenopprettet av {u}",
    rollbackHint: "Innstillingene settes tilbake slik de var i denne versjonen. Det blir en ny versjon, og historikken beholdes.",
    histMode: "Historikk", histRange: "Periode", histView: "Visning", range_6: "Siste 6 timer", range_24: "Siste 24 timer", range_72: "Siste 3 dager", range_168: "Siste 7 dager",
    hLoading: "Henter historikk … {n} bilder", hOff: "Historikk er slått av på serveren.", hEmpty: "Ingen lagret historikk i denne perioden ennå. Bilder lagres ca. hvert 5. minutt mens matten er koblet til.",
    hError: "Kunne ikke hente historikk.", hCapped: "Viser de første {n} bildene. Velg en kortere periode for å se de nyeste.",
    hPlay: "Spill av", hPause: "Pause", hPrev: "Forrige bilde", hNext: "Neste bilde", hSpeed: "Avspillingsfart", spd_0: "Sakte", spd_1: "Normal", spd_2: "Rask",
    hInstant: "Øyeblikk", hPeakBtn: "{n} min topp", hPeakShort: "topp", hScrub: "Velg tidspunkt", hStripLabel: "Historikk: farge viser risiko, trekant og ring viser varsel utløst og avsluttet. Trykk for å hoppe.",
    hPrevAlert: "Forrige varsel", hNextAlert: "Neste varsel", hLgRaised: "varsel utløst", hLgCleared: "varsel avsluttet",
    hRaised: "Varsel utløst: {k}", hCleared: "Varsel avsluttet: {k}", hNoPeak: "Ingen toppbilde for dette øyeblikket: viser øyeblikksbildet.", hNoPicture: "Ingen bilde fra dette tidspunktet (matten var frakoblet).",
    hSpotsApprox: "Hotspot er tegnet som en ring rundt det lagrede sentrum. Formen er ikke lagret.", movesHour: "Bevegelser siste time",
    exportMenu: "Eksport", exHistory: "Historikk (CSV)", exRepos: "Omplassering (CSV)", exAudit: "Hendelseslogg (CSV)", exHint: "Gjelder perioden valgt under Historikk: {r}.",
    exportSet: "Eksport", exportSetHint: "Hendelseslogg med endringer av innstillinger, fjernede matter, håndterte varsler og brukere.",
    reposShow: "Vis omplasseringsinfo", reposHint: "Tid siden bevegelse i listen og antall bevegelser siste time. Gjelder bare denne nettleseren.", sinceMoveRow: "Tid siden bevegelse",
    forget: "Glem", forgetBtn: "Glem denne matten …", dlgForget: "Glem {name}?",
    forgetHint: "Matten fjernes fra dashbordet, og det den har lagret hos meldingsserveren (broker) tømmes, slik at den ikke dukker opp igjen. Historikken beholdes til den utløper. Du kan hente matten tilbake under «Fjernede matter». Bare frakoblede matter kan glemmes.",
    forgottenBy: "Glemt av {u}", forgetNoBroker: "Meldingsserveren (broker) kunne ikke nås. Matten kan dukke opp igjen hvis den fortsatt sender.",
    foot: "Ingeniørverktøy, ikke medisinsk utstyr. Stilling og risiko er heuristikker. Bruk sammen med vanlig klinisk vurdering.",
    help_: {
      title: "Hjelp",
      colours: ["Hva fargene betyr", [
        ["high", "Høy risiko", "Trykket er over grensen. Se til personen og avlast."],
        ["medium", "Middels risiko", "Trykket eller tiden i samme stilling nærmer seg grensen."],
        ["low", "Lav risiko", "Ingen grenser er nådd akkurat nå."],
        ["none", "Ingen bruker", "Matten sender data, men det sitter ingen på den."],
        ["offline", "Frakoblet", "Matten har sluttet å sende. Da vet vi ingenting om personen. En stille mat vises aldri som grønn."],
      ]],
      alert: ["Hva gjør jeg ved et varsel", [
        "Trykk på bjella øverst. Rødt tall viser antall åpne varsler.",
        "Gå til rommet og se til personen. Avlast eller hjelp til med å skifte stilling etter lokale rutiner.",
        "Trykk Bekreft og skriv inn din PIN når du har tatt hånd om det. Bruk Ignorer hvis varselet er feil eller ikke relevant.",
        "Navnet ditt lagres sammen med handlingen og vises som en rød markør i tidslinjen.",
        "Frakoblet mat: sjekk strøm og nettverk, og se til personen på vanlig måte.",
      ]],
      map: ["Trykkartet", [
        "Fargene viser trykk i kPa fra lav (lys) til høy (mørk rød). «Foran» er forkanten av sittefladen.",
        "Stiplet ramme markerer et hotspot, et område med høyt trykk over tid. Rammen følger formen på området. Trykk på rammen eller i listen for å merke det.",
        "Under «Data» kan kartet vise eksponering, belastning, tid siden avlastning eller belastet tid. «Visning» kan glatte bildet. Krysset er trykktyngdepunktet.",
        "Veiledende last i kg er et grovt anslag fra trykk og matstørrelse, ikke en veiing.",
        "«Celler ved sensorgrensen» betyr at sensoren metter. Last og toppverdi er da høyere enn det som vises.",
        "Tid siden avlastning er tiden siden trykket sist ble tydelig flyttet eller tatt av.",
        "Tidslinjen under en rad viser stilling og risiko de siste timene. Tomme felt betyr at vi ikke har data.",
      ]],
      hist: ["Historikk", [
        "Under «Historikk» i trykkartet spilles lagrede bilder av. Velg periode (6 timer til 7 dager), trykk på spill av, eller dra i tidslinjen for å hoppe.",
        "Fargene i tidslinjen viser risiko. Rød trekant er et varsel som ble utløst, ring er et varsel som ble avsluttet. «Forrige/Neste varsel» hopper mellom dem.",
        "«Øyeblikk» viser bildet slik det var, «topp» viser høyeste trykk per celle i de siste minuttene før bildet. Hotspot vises bare som ring rundt sentrum.",
        "Tall for veiledende last, kontaktflate og stilling er grove anslag, ikke målinger eller diagnoser. Demo-matter merkes med DEMO.",
        "«Eksport» laster ned historikk og omplassering som CSV. «Vis omplasseringsinfo» (Innstillinger, Denne skjermen) slår av tid siden bevegelse og bevegelser siste time.",
        "En mat som er tatt ut av bruk kan glemmes under Innstillinger når den er frakoblet. Den kan hentes tilbake under «Fjernede matter».",
      ]],
      note: ["Viktig", [
        "SmartMat er et ingeniørverktøy, ikke et medisinsk utstyr.",
        "Last i kg er et grovt estimat. Stilling og risiko er heuristikker som brukes til å teste måleløypa, ikke en diagnose og ikke en validert risikoscore.",
        "Bruk alltid sammen med vanlig klinisk vurdering og lokale rutiner. Demo-matter er innspilte data og viser ingen ekte person.",
      ]],
    },
  },
  en: {
    unitFilter: "Filter by unit", allUnits: "All units", sortBy: "Sort by",
    sortRisk: "Risk", sortRoom: "Room", sortDevice: "Device", sortTime: "Time in position",
    searchPh: "Search room, device, seat", alerts: "Alerts", help: "Help", back: "Back",
    colDevice: "Device", colRoom: "Room", colSeat: "Seat", colOk: "Data OK", colStatus: "Status",
    theme: "Switch between light and dark", langBtn: "NO", filterCount: "Filter ({n} of {m} mats)",
    details: "Details", live: "live", handleNow: "Act now", noOpenAlert: "No open alerts for this mat.",
    lgPosture: "Posture", lgRisk: "Risk",
    p_left: "Left side", p_right: "Right side", p_forward: "Leaning forward", p_centred: "Centred", p_none: "No user",
    statusNone: "No user for {t}", offline: "Offline, no data", alertFlag: "Alert",
    dataOk: "Data OK", dataLost: "No data",
    risk_high: "High risk", risk_medium: "Medium risk", risk_low: "Low risk", risk_none: "No user", risk_offline: "Offline",
    h: "h", min: "min", ago: "{t} ago",
    pressureMap: "Pressure map", front: "Front", low: "Low", high: "High", edit: "Edit", toList: "To the list",
    layer: "Data", mode: "View", layer_pressure: "Pressure", layer_exposure: "Exposure (pressure x time)", layer_burden: "Burden",
    layer_since_relief: "Time since relief", layer_loaded_time: "Loaded time", view_live: "Live", view_average: "Smoothed (average of 5 frames)",
    mapUnitLayer: "{n} {u} full colour", contactArea: "Contact area", loadIndic: "Indicative load", loadHint: "approx., not a weighing", loadNoSize: "Mat size not set",
    loadLow: "reads low, cells at the sensor limit", defaultCurve: "default curve, not calibrated", nCells: "{n} cells", sinceMove: "Time since movement", never: "none yet",
    balance: "Balance", balL: "Left", balR: "Right", balF: "Front", balB: "Back", copKey: "+ = centre of pressure", spotArea: "{n} cells", spotAreaCm: "{n} cells, {a} cm²",
    spotPeak: "{p} kPa", spotSel: "Highlight hotspot {id}", noSpots: "No hotspots right now.",
    screenSettings: "This screen", alertSound: "Sound and flash on a new alert", alertSoundHint: "A short beep and a red flash when a new alert comes in. Only for this browser, off by default. The browser needs a tap on the page first.", alertTest: "Test",
    highestPressure: "Highest pressure", highestRelative: "Highest signal", sinceRelief: "Time since relief",
    timeInPos: "Time in position", lastData: "Last data", hotspots: "Hotspots", indices: "Indices", none: "None",
    persistent: "persistent", activeFor: "active {t}",
    idx_ok: "OK", idx_near: "Near limit", idx_over: "Over limit",
    selectMat: "Pick a mat in the list to see its pressure map.", noMats: "No mats found.",
    saturation: "{n} cells at sensor limit: load and peak read low",
    uncal: "Not calibrated: relative signal, not pressure.",
    staleMat: "No new data for {t}. This picture is old.", offlineMat: "The mat is offline. The picture shows the last known data.",
    lostServer: "No contact with the server. The statuses below may be old.",
    unoccupied: "Nobody is on the mat.", mapUnit: "{n} kPa full colour", mapUnitRel: "relative signal",
    noAlerts: "No alerts.", kind_high_risk: "High risk", kind_offline: "Offline",
    raised: "raised {t} ago", st_open: "Open", st_acknowledged: "Acknowledged", st_ignored: "Ignored", byUser: "by {u}",
    ack: "Acknowledge", ignore: "Ignore", pin: "PIN", cancel: "Cancel", ok: "OK",
    dlgAck: "Acknowledge alert: {name}", dlgIgnore: "Ignore alert: {name}", dlgEdit: "Edit mat",
    fName: "Name", fRoom: "Room", fSeat: "Seat", fUnit: "Unit",
    ackBy: "Acknowledged by {u}", ignBy: "Ignored by {u}", savedBy: "Saved by {u}", netErr: "No contact with the server.",
    tlTitle: "Last {n} hours", lgNoData: "No data", lgHandled: "Handled (acknowledged or ignored)", showMap: "Show pressure map",
    handledBy: "Handled by {u}",
    users: "Users", close: "Close", addUser: "Add user", disable: "Disable", enable: "Enable", resetPin: "Reset PIN",
    roleAdmin: "Admin", roleUser: "Nurse", userOff: "disabled", fRole: "Role",
    fNewPin: "New PIN (4-8 digits)", fRepeatPin: "Repeat PIN", adminPin: "Your PIN (admin)",
    dlgFirst: "Create first user (admin)", firstHint: "There are no users yet. This person becomes the administrator.",
    dlgAddUser: "Add user", dlgDisable: "Disable {n}", dlgEnable: "Enable {n}", dlgResetPin: "Reset PIN for {n}",
    pinMismatch: "The PINs do not match.", userAdded: "User {n} added", userChanged: "Changed by {u}",
    settings: "Settings", loading: "Loading …",
    setIntro: "Anyone can see the settings. Changing anything needs an administrator's PIN. Changes take effect at once and are logged with the name.",
    setMats: "Mats", setMatsHint: "Give each mat a name, room, seat and unit. A mat taken out of use can be removed once it is offline.",
    rm: "Remove", restore: "Restore", removedMats: "Removed mats", noRemoved: "No removed mats.",
    dlgRemove: "Remove {name}?", dlgRestore: "Restore {name}?",
    rmHint: "The mat is no longer shown and its open alerts are closed. You can restore it here. Only offline mats can be removed.",
    restoreHint: "The mat shows in the list again as soon as it sends data.", removedBy: "Removed by {u}", restoredBy: "Restored by {u}",
    g_alerts: "Alerts", g_risk: "Risk level", g_mats: "Sensor and connection", g_data: "Storage", g_posture: "Posture",
    g_risk_h: "These two values set how sensitive Medium and High risk are. Change them only by agreement: they are not clinically validated.",
    advanced: "Advanced (for engineers)", setDefault: "Default: {v}", resetDefault: "Reset",
    setOn: "On", setOff: "Off", u_days: "days", u_cells: "cells",
    errNumber: "Enter a number.", errWhole: "Use a whole number.", errRange: "Must be between {min} and {max}.",
    saveChanges: "Save changes", nChanges: "{n} unsaved change(s)", noChanges: "No changes", fixErrors: "Fix the errors above first.",
    dlgSave: "Save settings", savedSettings: "Settings saved by {u}",
    setUsersHint: "Administrators and nurses, each with their own PIN.", openUsers: "Open users",
    s_alert_high_hold_s: "Time at high risk before an alert",
    s_alert_high_hold_s_h: "How long the risk must stay high before an alert is raised. Shorter is quicker but gives more false alerts.",
    s_alert_offline_s: "Time offline before an alert",
    s_alert_offline_s_h: "How long a mat must be silent before an offline alert is raised.",
    s_push_enabled: "Push notifications to phones",
    s_push_enabled_h: "Turn off to stop all push notifications. Alerts are still shown in the dashboard.",
    s_relief_minutes: "Time without relief that counts as full load",
    s_relief_minutes_h: "An area counts as fully loaded after this long without relief. A lower value gives medium and high risk sooner.",
    s_near_percent: "Medium risk starts at",
    s_near_percent_h: "Medium risk shows when the value reaches this share of the limit for high risk.",
    s_stale_after_s: "Time without data before a mat counts as offline",
    s_stale_after_s_h: "How long a mat can be silent before its row says Offline.",
    s_saturation_warn_cells: "Warn about the sensor limit from",
    s_saturation_warn_cells_h: "Number of cells at the sensor limit that trigger the note that load and peak read low.",
    s_posture_hold_s: "A new posture must last",
    s_posture_hold_s_h: "How long a new posture must hold before the time in position starts again.",
    s_posture_side_cells: "Side posture from",
    s_posture_side_cells_h: "How many cells the centre of pressure must be from the middle to count as left or right.",
    s_posture_forward_cells: "Leaning forward from",
    s_posture_forward_cells_h: "How many cells the centre of pressure must be in front of the middle to count as leaning forward.",
    s_retention_days: "Keep the log and timeline for",
    s_retention_days_h: "Older events and timeline are deleted automatically.",
    analysis: "Analysis", siteDefaults: "Defaults for the whole site",
    siteDefaultsHint: "Apply to every mat that has no values of its own. Each mat can override them under \"Analysis\".",
    matCfgTitle: "Analysis settings: {name}",
    ppTitle: "Setup kept on the mat (passport)", ppHint: "The calibration travels with the mat: save it before shipping, use it again when needed.",
    ppSerial: "Serial number", ppEmpty: "empty", ppNone: "The mat does not answer about its passport (offline or older firmware).",
    ppSame: "same as in use", ppDiffers: "differs from what is in use", ppUse: "Use", ppFactory: "Factory", ppCustom: "Custom",
    ppSave: "Save the current setup to the mat", ppNote: "Note (optional)", dlgPpUse: "Use the {slot} passport?", dlgPpSave: "Save to the mat?",
    ppUsed: "Passport taken into use by {u}", ppSaved: "Saved to the mat (version {v}) by {u}", ppAnalysis: "with analysis settings",
    matCfgIntro: "Values not set for this mat follow the site defaults, which follow the factory values. Every change is a new version, saved with the name and a reason.",
    cfgVersion: "Settings version {v}", cfgShort: "settings {v}",
    src_factory: "Factory", src_site: "Site", src_mat: "This mat", setDefaultSite: "Site value: {v}", useSite: "Use the site value",
    g_contact: "Contact", g_temporal: "Time analysis", g_hotspots: "Hotspots", g_movement: "Movement",
    idxBuiltin: "Built-in risk indices", idxCustom: "Custom risk indices ({n})", errMin: "Must be at least {min}.",
    s_indices: "Risk indices", s_indices_h: "Custom indices are set from the desktop app. Here they can be put back to the built-in ones.",
    reasonLabel: "Reason (optional)", reasonPh: "Why is this changed?", saveForMat: "Save for this mat",
    history: "Change history", noHistory: "No changes yet.", version: "Version", restoreVersion: "Restore v{v}",
    factoryVersion: "Factory values (version 0)", dlgRollback: "Restore version {v}?", rolledBack: "Restored by {u}",
    rollbackHint: "The settings are put back as they were in this version. That makes a new version, and the history stays.",
    histMode: "History", histRange: "Range", histView: "View", range_6: "Last 6 hours", range_24: "Last 24 hours", range_72: "Last 3 days", range_168: "Last 7 days",
    hLoading: "Loading history … {n} snapshots", hOff: "History is switched off on the server.", hEmpty: "No saved history in this range yet. A snapshot is saved about every 5 minutes while the mat is connected.",
    hError: "Could not load history.", hCapped: "Showing the first {n} snapshots. Pick a shorter range to see the newest.",
    hPlay: "Play", hPause: "Pause", hPrev: "Previous snapshot", hNext: "Next snapshot", hSpeed: "Playback speed", spd_0: "Slow", spd_1: "Normal", spd_2: "Fast",
    hInstant: "Instant", hPeakBtn: "{n}-min peak", hPeakShort: "peak", hScrub: "Pick a time", hStripLabel: "History: colour shows risk, triangle and ring show alert raised and cleared. Tap to jump.",
    hPrevAlert: "Previous alert", hNextAlert: "Next alert", hLgRaised: "alert raised", hLgCleared: "alert cleared",
    hRaised: "Alert raised: {k}", hCleared: "Alert cleared: {k}", hNoPeak: "No peak picture for this moment: showing the instant picture.", hNoPicture: "No picture from this moment (the mat was offline).",
    hSpotsApprox: "A hotspot is drawn as a ring around the saved centre. The shape is not saved.", movesHour: "Movements in the last hour",
    exportMenu: "Export", exHistory: "History (CSV)", exRepos: "Repositioning (CSV)", exAudit: "Event log (CSV)", exHint: "Uses the range chosen under History: {r}.",
    exportSet: "Export", exportSetHint: "Event log with settings changes, removed mats, handled alerts and users.",
    reposShow: "Show repositioning info", reposHint: "Time since movement in the list and the number of movements in the last hour. Only for this browser.", sinceMoveRow: "Time since movement",
    forget: "Forget", forgetBtn: "Forget this mat …", dlgForget: "Forget {name}?",
    forgetHint: "The mat is removed from the dashboard, and what it keeps on the message broker is emptied so it does not come back. The history is kept until it expires. You can bring the mat back under \"Removed mats\". Only offline mats can be forgotten.",
    forgottenBy: "Forgotten by {u}", forgetNoBroker: "The message broker could not be reached. The mat may reappear if it is still publishing.",
    foot: "Engineering aid, not a medical device. Posture and risk are heuristics. Use alongside normal clinical assessment.",
    help_: {
      title: "Help",
      colours: ["What the colours mean", [
        ["high", "High risk", "Pressure is over the limit. Check on the person and relieve the pressure."],
        ["medium", "Medium risk", "Pressure or time in the same position is getting close to the limit."],
        ["low", "Low risk", "No limits are reached right now."],
        ["none", "No user", "The mat is sending data, but nobody is sitting on it."],
        ["offline", "Offline", "The mat stopped sending. We know nothing about the person then. A silent mat is never shown as green."],
      ]],
      alert: ["What to do on an alert", [
        "Tap the bell at the top. The red number is the count of open alerts.",
        "Go to the room and check on the person. Relieve the pressure or help them change position, following local routines.",
        "Tap Acknowledge and enter your PIN once it is dealt with. Use Ignore if the alert is wrong or not relevant.",
        "Your name is saved with the action and shows as a red marker in the timeline.",
        "Offline mat: check power and network, and check on the person as usual.",
      ]],
      map: ["The pressure map", [
        "Colours show pressure in kPa from low (light) to high (dark red). \"Front\" is the front edge of the seat.",
        "A dashed outline marks a hotspot, an area of high pressure over time. The outline follows the shape of the area. Tap it, or its row in the list, to highlight it.",
        "Under 'Data' the map can show exposure, burden, time since relief or loaded time. 'View' can smooth the picture. The cross is the centre of pressure.",
        "Indicative load in kg is a rough estimate from pressure and mat size, not a weighing.",
        "\"Cells at sensor limit\" means the sensor saturates. Load and peak are then higher than shown.",
        "Time since relief is the time since the pressure was last clearly moved or taken off.",
        "The timeline under a row shows posture and risk for the last hours. Empty parts mean we have no data.",
      ]],
      hist: ["History", [
        "Under \"History\" in the pressure panel saved snapshots are played back. Pick a range (6 hours to 7 days), press play, or drag on the strip to jump.",
        "Colours in the strip show risk. A red triangle is an alert that was raised, a ring is an alert that was cleared. \"Previous/Next alert\" jump between them.",
        "\"Instant\" shows the picture as it was, \"peak\" shows the highest pressure per cell over the minutes before the snapshot. A hotspot is only shown as a ring around its centre.",
        "Indicative load, contact area and posture are rough estimates, not measurements or diagnoses. Demo mats are marked DEMO.",
        "\"Export\" downloads history and repositioning as CSV. \"Show repositioning info\" (Settings, This screen) turns off time since movement and movements in the last hour.",
        "A mat taken out of use can be forgotten under Settings once it is offline. It can be brought back under \"Removed mats\".",
      ]],
      note: ["Important", [
        "SmartMat is an engineering aid, not a medical device.",
        "Load in kg is a rough estimate. Posture and risk are heuristics for testing the pipeline, not a diagnosis and not a validated risk score.",
        "Always use alongside normal clinical assessment and local routines. Demo mats are recorded data and show no real person.",
      ]],
    },
  },
};

// ---------- small helpers ----------
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const setText = (node, s) => { if (node.textContent !== s) node.textContent = s; };
const store = {
  get(k) { try { return localStorage.getItem("sm." + k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem("sm." + k, v); } catch (e) { /* private mode: just not remembered */ } },
};

let lang = store.get("lang") === "en" ? "en" : "nb";
const t = (key, vars) => {
  let s = i18n[lang][key] ?? i18n.nb[key] ?? key;
  for (const k in vars || {}) s = s.replace("{" + k + "}", vars[k]);
  return s;
};
const locale = () => (lang === "en" ? "en-GB" : "nb-NO");

// 45 s, 11:58 min, 58 min, 1 h 17 min (nb: 1 t 17 min)
function dur(s) {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  if (s < 60) return s + " s";
  if (s < 1200) return m + ":" + String(s % 60).padStart(2, "0") + " " + t("min");
  if (m < 60) return m + " " + t("min");
  return Math.floor(m / 60) + " " + t("h") + " " + (m % 60) + " " + t("min");
}
const clockSpan = (s) => { // 7:05 under an hour (m:ss), 2:30 over it (h:mm)
  s = Math.max(0, Math.round(s));
  return s < 3600 ? Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") : Math.floor(s / 3600) + ":" + String(Math.floor((s % 3600) / 60)).padStart(2, "0");
};
const num = (v, d = 1) => v.toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });

// ---------- state ----------
const RISK_ORDER = { offline: 0, high: 1, medium: 2, low: 3, none: 4 };
const RISKS = ["high", "medium", "low", "none"];
const POSTURES = ["centred", "left", "right", "forward", "none"];
const KIOSK = new URLSearchParams(location.search).has("kiosk"); // the touchscreen's fullscreen browser
if (KIOSK) document.documentElement.classList.add("kiosk");

const S = {
  mats: [], openAlerts: 0, alerts: [], timeline: null, mat: null, offset: 0, lost: false,
  selected: null, open: false, bellOpen: false, needsAdmin: false, setupShown: false,
  sort: store.get("sort") || "risk", unit: store.get("unit") || "", q: "",
  ramp: [[0, [207, 230, 222]], [0.25, [126, 189, 168]], [0.5, [233, 196, 106]], [0.75, [224, 123, 57]], [0.9, [179, 38, 30]], [1, [107, 15, 26]]],
};
const rows = new Map(); // mat id -> {row, head, parts...}
const serverNow = () => Date.now() / 1000 + S.offset;

// ---------- API ----------
async function api(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw Object.assign(new Error(r.statusText), { status: r.status });
  return r.json();
}
// Writes always carry a PIN (except creating the very first user); the server answers {ok, user, ...} or {error}.
async function send(method, path, body) {
  try {
    const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    return r.ok ? Object.assign({ ok: true }, data) : { ok: false, error: data.error || r.statusText };
  } catch (e) {
    return { ok: false, error: t("netErr") };
  }
}
// Run fn every ms (not while the tab is hidden, never two at once). Returns a "run now" function.
function every(ms, fn) {
  let busy = false;
  const run = async () => {
    if (busy || document.hidden) return;
    busy = true;
    try { await fn(); } catch (e) { /* each fn handles its own errors */ } finally { busy = false; }
  };
  setInterval(run, ms);
  run();
  return run;
}

// ---------- list ----------
const byTime = (a, b) => (b.time_in_position_s || 0) - (a.time_in_position_s || 0);
const byName = (a, b) => a.name.localeCompare(b.name, lang, { numeric: true });
const SORTS = {
  risk: (a, b) => (RISK_ORDER[a.risk] ?? 5) - (RISK_ORDER[b.risk] ?? 5) || byTime(a, b),
  room: (a, b) => (a.room || "").localeCompare(b.room || "", lang, { numeric: true }) || byName(a, b),
  device: byName,
  time: byTime,
};

function statusOf(m) {
  if (m.risk === "offline" || !m.online) return { cls: "offline", text: t("offline") };
  if (m.risk === "none" || m.posture === "none") return { cls: "none", text: t("statusNone", { t: dur(m.time_in_position_s) }) };
  const cls = RISKS.includes(m.risk) ? m.risk : "none"; // an unknown risk is never shown as green
  return { cls, text: t("p_" + m.posture) + " > " + dur(m.time_in_position_s) };
}

function makeRow(id) {
  const row = el("div", "row");
  const head = el("button", "head");
  head.type = "button";
  const chev = el("span", "c-chev"), dev = el("span", "c-dev"), name = el("b"), demo = el("span", "demo", "DEMO"), flag = el("span", "flag"), mv = el("span", "mv");
  chev.setAttribute("aria-hidden", "true");
  const chevIcon = svgEl("svg", { viewBox: "0 0 24 24" });
  chevIcon.append(svgEl("path", { d: "M6 9l6 6 6-6" }));
  chev.append(chevIcon);
  dev.append(name, demo, flag, mv);
  const room = el("span", "c-room"), seat = el("span", "c-seat"), ok = el("span", "c-ok"), cell = el("span", "c-st"), st = el("span", "status");
  cell.append(st);
  head.append(chev, dev, room, seat, ok, cell);
  const detail = el("div", "detail");
  detail.hidden = true;
  const cap = el("div", "cap"), capText = el("span"), toMap = el("button", "link only-narrow");
  toMap.type = "button";
  cap.append(capText, toMap);
  const tlHost = el("div");
  const legend = el("div", "legend");
  detail.append(cap, tlHost, legend);
  row.append(head, detail);
  head.addEventListener("click", () => select(id));
  toMap.addEventListener("click", () => $("pm").scrollIntoView());
  const r = { row, head, name, demo, flag, mv, room, seat, ok, st, detail, capText, toMap, tlHost, legend, legendKey: null };
  rows.set(id, r);
  return r;
}

function updateRow(r, m) {
  const sel = m.id === S.selected, st = statusOf(m);
  r.row.classList.toggle("sel", sel);
  r.head.setAttribute("aria-expanded", String(sel && S.open));
  r.head.title = m.id;
  setText(r.name, m.name);
  r.demo.hidden = !m.demo;
  r.flag.hidden = !(m.open_alerts > 0);
  setText(r.flag, t("alertFlag"));
  const since = reposOn() && m.online && m.since_movement_s != null ? m.since_movement_s : null;   // time since movement, m:ss or h:mm
  r.mv.hidden = since == null;
  r.mv.title = t("sinceMoveRow");
  if (since != null) setText(r.mv, "↻ " + clockSpan(since));
  setText(r.room, m.room || "");
  r.room.dataset.l = t("colRoom");
  setText(r.seat, m.seat || "");
  r.seat.dataset.l = t("colSeat");
  const good = m.online && !S.lost;
  r.ok.className = "c-ok " + (good ? "yes" : "no"); // the tick or cross is drawn by the stylesheet
  r.ok.setAttribute("role", "img");
  r.ok.setAttribute("aria-label", good ? t("dataOk") : t("dataLost"));
  setText(r.st, st.text);
  r.st.className = "status " + st.cls;
  const open = sel && S.open;
  r.detail.hidden = !open;
  if (open) {
    setText(r.capText, t("tlTitle", { n: 5 }));
    setText(r.toMap, t("showMap"));
    const key = lang + (m.open_alerts > 0); // the legend is rebuilt only when its text or the "act now" link changes
    if (r.legendKey !== key) { buildLegend(r.legend, m); r.legendKey = key; }
    drawTimeline(r.tlHost);
  }
}

function legendItem(swatch, label) {
  const item = el("span");
  item.append(swatch, document.createTextNode(label));
  return item;
}

function buildLegend(host, m) {
  host.textContent = "";
  const postures = el("div", "lg-row"), risks = el("div", "lg-row");
  for (const p of POSTURES) postures.append(legendItem(el("span", "sw p-" + p), t("p_" + p)));
  for (const k of ["low", "medium", "high"]) risks.append(legendItem(el("span", "sq " + k), t("risk_" + k)));
  risks.append(legendItem(el("span", "sq hollow"), t("lgNoData")), legendItem(el("span", "sq mk"), t("lgHandled")));
  if (m.open_alerts > 0) { // the slide's red "Handle nå": opens the acknowledge dialog of this mat's open alert
    const now = el("button", "act-now");
    now.type = "button";
    now.append(el("span", "sq high"), document.createTextNode(t("handleNow")));
    now.addEventListener("click", () => handleNow(m));
    postures.append(el("span", "grow"), now);
  }
  host.append(postures, risks);
}

async function handleNow(m) {
  let open = [];
  try { open = (await api("/api/alerts")).alerts.filter((a) => a.chip_id === m.id && a.state === "open"); }
  catch (e) { toast(t("netErr")); return; }
  if (open.length) handleAlert("ack", open[0]); else toast(t("noOpenAlert"));
}

function renderList() {
  const q = S.q.trim().toLowerCase();
  const shown = S.mats
    .filter((m) => !S.unit || m.unit === S.unit)
    .filter((m) => !q || [m.name, m.room, m.seat, m.id].some((v) => (v || "").toLowerCase().includes(q)))
    .sort(SORTS[S.sort] || SORTS.risk);
  const seen = new Set();
  const box = $("rows");
  shown.forEach((m, i) => {
    const r = rows.get(m.id) || makeRow(m.id);
    if (box.children[i] !== r.row) box.insertBefore(r.row, box.children[i] || null);
    updateRow(r, m); // after insertion: the timeline measures its width
    seen.add(m.id);
  });
  for (const [id, r] of rows) if (!seen.has(id)) { r.row.remove(); rows.delete(id); }
  $("empty").hidden = shown.length > 0;
  setText($("empty"), t("noMats"));
  setText($("unitL"), t("filterCount", { n: shown.length, m: S.mats.length }));
  // first load: show some mat in the pressure panel without opening its timeline
  if (!S.mats.some((m) => m.id === S.selected) && shown.length) { S.selected = shown[0].id; S.open = false; S.mat = null; renderList(); fetchMat(); }
}

function renderUnits() {
  const units = [...new Set(S.mats.map((m) => m.unit).filter(Boolean))].sort();
  const sel = $("unit");
  if ([...sel.options].slice(1).map((o) => o.value).join("|") === units.join("|")) return;
  while (sel.options.length > 1) sel.remove(1);
  for (const u of units) { const o = el("option", "", u); o.value = u; sel.append(o); }
  sel.value = units.includes(S.unit) ? S.unit : "";
}

function select(id) {
  if (S.selected === id) S.open = !S.open;
  else { histLeave(); S.selected = id; S.open = true; S.mat = null; S.timeline = null; S.spot = null; S.moves = null; if (S.hm) S.hm.reset(); fetchMoves(); }
  renderList();
  renderPanel();
  fetchMat();
  fetchTimeline();
}

// ---------- timeline (SVG) ----------
const SVGNS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs, cls) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (cls) e.setAttribute("class", cls);
  return e;
};

function drawTimeline(host) {
  host.textContent = "";
  const tl = S.timeline;
  if (!tl || tl.id !== S.selected) return;
  // like the slide: a time axis on top, a posture bar in the posture colours, a thin risk strip under it
  const W = Math.max(280, host.clientWidth), AX = 18, BAR = 24, GAP = 4, STRIP = 8, H = AX + BAR + GAP + STRIP + 8;
  const now = serverNow(), t0 = now - tl.hours * 3600;
  const x = (ts) => ((Math.max(t0, Math.min(now, ts)) - t0) / (now - t0)) * W;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" }, "tl");
  svg.setAttribute("aria-label", t("tlTitle", { n: tl.hours }));
  const clip = svgEl("clipPath", { id: "tlclip" });
  clip.append(svgEl("rect", { x: 0, y: AX, width: W, height: BAR + GAP + STRIP, rx: 6 }));
  svg.append(clip, svgEl("rect", { x: 0, y: AX, width: W, height: BAR, rx: 6 }, "tl-track"));
  const step = W / tl.hours >= 90 ? 1800 : 3600; // a label every half hour when there is room, else every hour
  for (let h = Math.ceil(t0 / step) * step; h < now; h += step) {
    const label = svgEl("text", { x: x(h), y: AX - 5, "text-anchor": x(h) > W - 20 ? "end" : x(h) < 20 ? "start" : "middle" });
    label.textContent = clock(h);
    svg.append(label);
  }
  const bars = svgEl("g", { "clip-path": "url(#tlclip)" });
  for (const s of tl.segments) {
    if (s.t_end <= t0) continue;
    const x1 = x(s.t_start), w = Math.max(1, x(s.t_end) - x1);
    const risk = RISKS.includes(s.risk) ? s.risk : "none", posture = POSTURES.includes(s.posture) ? s.posture : "none";
    const g = svgEl("g", {}, "seg");
    g.append(svgEl("rect", { x: x1, y: AX, width: w, height: BAR }, "pb p-" + posture),
             svgEl("rect", { x: x1, y: AX + BAR + GAP, width: w, height: STRIP }, "rs r-" + risk));
    const title = svgEl("title");
    title.textContent = `${t("p_" + posture)}, ${t("risk_" + risk)}, ${clock(s.t_start)} - ${clock(s.t_end)}`;
    g.append(title);
    bars.append(g);
  }
  svg.append(bars);
  for (const mk of tl.markers) {
    if (mk.t < t0) continue;
    const g = svgEl("g", {}, "mark");
    g.append(svgEl("line", { x1: x(mk.t), x2: x(mk.t), y1: AX - 2, y2: AX + BAR + GAP + STRIP + 2 }),
             svgEl("rect", { x: x(mk.t) - 3, y: AX + BAR + GAP + STRIP, width: 7, height: 7, rx: 2 }));
    const title = svgEl("title");
    title.textContent = t("handledBy", { u: mk.user }) + ", " + clock(mk.t);
    g.append(title);
    svg.append(g);
  }
  host.append(svg);
}

async function fetchTimeline() {
  const id = S.selected;
  if (!id || !S.open) return;
  try {
    const tl = await api("/api/mats/" + encodeURIComponent(id) + "/timeline?hours=5");
    if (id !== S.selected) return;
    S.timeline = Object.assign(tl, { id, hours: 5 });
    const r = rows.get(id);
    if (r && !r.detail.hidden) drawTimeline(r.tlHost);
  } catch (e) { /* keep the last drawing */ }
}

// ---------- pressure panel ----------
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

// The map itself (heat, hotspot outlines, motion) lives in heatmap.js; this part feeds it and builds the controls around it.
const LAYERS = ["pressure", "exposure", "burden", "since_relief", "loaded_time"];
const VIEWS = ["live", "average"];
S.layer = LAYERS.includes(store.get("layer")) ? store.get("layer") : "pressure";
S.view = VIEWS.includes(store.get("view")) ? store.get("view") : "live";
S.spot = null;     // the highlighted hotspot id (list and map)
S.mapKey = "";     // mat + layer + view of the picture on screen: a change redraws without a tween

function mapInit() {
  S.hm = HeatMap.create({ seat: $("seat"), canvas: $("map"), overlay: $("mapOv"), onPick: pickSpot });
  S.hm.setRamp(S.ramp);
}

// A grid, its hotspots and the centre of pressure in; the map tweens from the grid it shows now.
function drawMap(snap) {
  const key = [S.selected, snap.layer || "pressure", snap.view || "live"].join("|");
  $("seat").style.setProperty("--cols", snap.grid[0].length);
  $("seat").style.setProperty("--rows", snap.grid.length);
  $("seat").classList.toggle("pick", snap.hotspots.length > 0);
  const rel = snap.unit === "relative";
  S.hm.set({
    grid: snap.grid, scale: snap.scale_max, snap: key !== S.mapKey,
    spots: snap.hotspots.map((h) => ({ id: h.id, peak: rel ? null : h.peak_kpa, persistent: h.persistent, cells: h.cells })),
    cop: snap.cop || null,
  });
  S.mapKey = key;
  if (S.spot != null && !snap.hotspots.some((h) => h.id === S.spot)) pickSpot(null);
}

function pickSpot(id) { // a click on a hotspot (map or list) highlights it; the same again clears it
  S.spot = id === S.spot ? null : id;
  S.hm.select(S.spot);
  for (const [sid, r] of S.spotRows) r.classList.toggle("sel", sid === S.spot);
}

// Data and View dropdowns: what the server is asked for (/api/mats/<id>?layer=..&view=..)
function fillSelect(sel, values, prefix, current) {
  const sig = lang + values.join(",");
  if (sel.dataset.sig !== sig) {
    sel.dataset.sig = sig;
    sel.textContent = "";
    for (const v of values) { const o = el("option", "", t(prefix + v)); o.value = v; sel.append(o); }
  }
  sel.value = values.includes(current) ? current : values[0];
}
function renderControls(snap) {
  const rel = !snap || snap.unit === "relative" || !snap.layers;
  fillSelect($("layer"), rel ? ["pressure"] : snap.layers, "layer_", S.layer);
  fillSelect($("view"), VIEWS, "view_", S.view);
  $("layer").disabled = rel;
  $("view").disabled = rel || S.layer !== "pressure";
}
function onControl(key, sel) {
  S[key] = sel.value;
  store.set(key, S[key]);
  renderControls(S.mat && S.mat.snapshot);
  fetchMat();
}

// ---------- readouts ----------
function setBig(node, main, unit) { // "12" with a small unit after it
  node.textContent = main;
  if (unit) node.append(el("small", "", " " + unit));
}
function renderReadouts(snap, d, row, stale) {
  const rel = !snap || snap.unit === "relative", unocc = snap && snap.occupied === false;
  const has = snap && !rel && !unocc && !stale;
  const sat = d.saturated_cells || 0;
  const area = has && snap.contact_area_cm2 != null ? [num(snap.contact_area_cm2, 0), "cm²"] : has && snap.contact_cells != null ? [String(snap.contact_cells), t("nCells", { n: "" }).trim()] : ["–", ""];
  setBig($("areaV"), area[0], area[1]);
  setBig($("loadV"), has && snap.load_kg != null ? (sat > 0 ? "≥ " : "≈ ") + num(snap.load_kg, 0) : "–", has && snap.load_kg != null ? "kg" : "");
  const hint = snap && snap.cell_area_cm2 == null ? t("loadNoSize") : sat > 0 ? t("loadLow") : snap && snap.calibrated === false ? t("defaultCurve") : t("loadHint");
  const k = $("loadK");
  k.textContent = t("loadIndic");
  k.append(el("small", "", hint));
  renderBalance(has ? snap : null);
  setText($("copKey"), snap && snap.cop && !stale ? t("copKey") : "");
}
function balanceRow(left, right, pct) {
  const r = el("div", "bal-row"), bar = el("div", "bal-bar"), fill = el("i");
  fill.style.width = pct + "%";
  bar.append(fill);
  r.append(el("span", "", left + " " + num(pct, 0) + " %"), bar, el("span", "", right + " " + num(100 - pct, 0) + " %"));
  return r;
}
function renderBalance(snap) {
  const host = $("bal");
  host.hidden = !(snap && snap.left_percent != null);
  if (host.hidden) return;
  host.textContent = "";
  host.append(balanceRow(t("balL"), t("balR"), snap.left_percent), balanceRow(t("balF"), t("balB"), snap.front_percent));
}

// ---------- hotspot list: click a row to highlight the hotspot on the map ----------
S.spotRows = new Map();
function spotRow(id) {
  const b = el("button", "spot"), a = el("b"), p = el("span", "pk"), d = el("span", "muted"), sub = el("span", "sub");
  b.type = "button";
  b.append(a, p, d, sub);
  b.addEventListener("click", () => pickSpot(id));
  return Object.assign(b, { parts: { a, p, d, sub } });
}
function renderSpots(snap, cellCm2) {
  const host = $("pmSpots"), list = snap ? snap.hotspots : [], rel = snap && snap.unit === "relative";
  for (const [id, r] of S.spotRows) if (!list.some((h) => h.id === id)) { r.remove(); S.spotRows.delete(id); }
  list.forEach((h, i) => {
    let r = S.spotRows.get(h.id);
    if (!r) { r = spotRow(h.id); S.spotRows.set(h.id, r); }
    r.classList.toggle("sel", h.id === S.spot);
    r.title = t("spotSel", { id: h.id });
    const n = h.cells.length, cm = cellCm2 == null ? null : n * cellCm2;
    setText(r.parts.a, "#" + h.id);
    setText(r.parts.p, rel ? "" : t("spotPeak", { p: num(h.peak_kpa) }));
    setText(r.parts.d, t("activeFor", { t: dur(h.active_s) }) + (h.persistent ? ", " + t("persistent") : ""));
    setText(r.parts.sub, cm == null ? t("spotArea", { n }) : t("spotAreaCm", { n, a: num(cm, 0) }));
    if (host.children[i] !== r) host.insertBefore(r, host.children[i] || null);   // only moves a row when the order changed
  });
  const none = host.querySelector(".none");
  if (!list.length && !none) host.append(el("p", "none", t("noSpots")));
  else if (list.length && none) none.remove();
  else if (none) setText(none, t("noSpots"));
}

// "Movements in the last hour" for the live panel: counted from the saved snapshots (one small request a minute)
async function fetchMoves() {
  const id = S.selected;
  if (!id || !reposOn()) return;
  try {
    const now = serverNow(), d = await api("/api/mats/" + encodeURIComponent(id) + "/history?limit=60&from=" + (now - 3700) + "&to=" + now);
    if (id === S.selected) { S.moves = { id, n: d.enabled ? movesLastHour(d.snapshots, now) : null }; renderMoves(S.mats.find((m) => m.id === id)); }
  } catch (e) { /* the line just stays hidden */ }
}
function renderMoves(row) {
  const n = row && reposOn() && S.moves && S.moves.id === row.id ? S.moves.n : null;
  $("pmMoves").hidden = n == null;
  if (n != null) setText($("pmMoves"), t("movesHour") + ": " + n);
}

function kv(host, pairs, empty) {
  host.textContent = "";
  if (!pairs.length) pairs = [[empty, ""]];
  for (const [k, v] of pairs) {
    const wrap = el("div"), dt = el("dt"), dd = el("dd");
    if (k instanceof Node) dt.append(k); else dt.textContent = k;
    if (v instanceof Node) dd.append(v); else dd.textContent = v;
    wrap.append(dt, dd);
    host.append(wrap);
  }
}

function rampCaption(snap) { // what full colour means for the layer on screen
  if (snap.unit === "relative") return t("mapUnitRel");
  const layer = snap.layer || "pressure", n = snap.scale_max;
  if (layer === "pressure") return t("mapUnit", { n: num(n, 0) });
  return t("mapUnitLayer", { n: layer === "since_relief" || layer === "loaded_time" ? dur(n) : num(n, 0), u: layer === "burden" || layer === "since_relief" || layer === "loaded_time" ? "" : snap.unit }).replace(/\s+/g, " ");
}

function renderPanel() {
  const row = S.mats.find((m) => m.id === S.selected);
  $("editBtn").hidden = !row;
  $("pmBody").hidden = !row;
  if (!row) { histLeave(); setText($("pmSub"), t("selectMat")); return; }
  const d = S.mat && S.mat.id === row.id ? S.mat : row, snap = S.mat && S.mat.id === row.id ? S.mat.snapshot : null;
  const stale = S.lost || !row.online || (S.mat && S.mat.id === row.id && S.mat.stale);
  const sub = $("pmSub");
  sub.textContent = ([row.room, row.seat].filter(Boolean).join(", ") || row.name) + (H.on ? ", " + t("histMode").toLowerCase() : stale ? "" : ", " + t("live")) + " ";
  if (row.demo) sub.append(el("span", "demo", "DEMO"));
  $("pm").classList.toggle("stale", !!stale && !H.on);
  histChrome();
  renderExport();
  if (H.on) return;   // history mode draws only when its cursor moves, never from the live poll
  const age = S.mat && S.mat.id === row.id ? S.mat.age_s : null;
  const staleNote = $("pmStale");
  staleNote.hidden = !stale;
  setText(staleNote, S.lost ? t("lostServer") : !row.online ? t("offlineMat") : t("staleMat", { t: dur(age || 0) }));

  const rel = snap && snap.unit === "relative";
  const unocc = snap && snap.occupied === false;
  const sat = d.saturated_cells || 0;
  setText($("pmSat"), t("saturation", { n: sat }));
  $("pmSat").hidden = !(sat > 0);
  setText($("pmUncal"), unocc ? t("unoccupied") : t("uncal"));
  $("pmUncal").hidden = !(rel || unocc);
  renderControls(snap);
  if (snap) {
    drawMap(snap);
    setText($("rampUnit"), rampCaption(snap));
  }
  setText($("peakK"), rel ? t("highestRelative") : t("highestPressure"));
  const peak = snap && snap.peak_kpa != null && !unocc ? snap.peak_kpa : null;
  const hasPeak = peak != null && !rel;
  setText($("peakV"), hasPeak ? num(peak) : "–");
  if (hasPeak) { const u = el("small", "", " kPa"); $("peakV").append(u); }
  setText($("reliefV"), row.since_relief_s == null || stale ? "–" : dur(row.since_relief_s));

  renderReadouts(snap, d, row, stale);
  renderMoves(row);
  renderSpots(snap, snap ? snap.cell_area_cm2 : null);
  kv($("pmKv"), [
    [t("timeInPos"), stale ? "–" : dur(row.time_in_position_s)],
    [t("sinceMove"), stale ? "–" : d.since_movement_s == null ? t("never") : dur(d.since_movement_s)],
    [t("lastData"), age == null ? "–" : t("ago", { t: dur(age) })],
  ]);
  kv($("pmIdx"), (snap ? snap.indices : []).map((ix) => {
    const k = el("span");
    k.append(el("span", "sq " + ix.state), document.createTextNode(ix.name));
    return [k, (ix.value == null ? "–" : num(ix.value)) + " / " + ix.threshold + "  " + t("idx_" + ix.state)];
  }), t("none"));
}

async function fetchMat() {
  const id = S.selected;
  if (!id || H.on) return;
  try {
    const layer = S.layer, view = S.view;
    const query = (layer !== "pressure" ? "&layer=" + layer : "") + (view !== "live" ? "&view=" + view : "");
    const m = await api("/api/mats/" + encodeURIComponent(id) + (query ? "?" + query.slice(1) : ""));
    if (id !== S.selected || layer !== S.layer || view !== S.view || H.on) return;   // the person changed mat or layer meanwhile
    S.mat = m;
  } catch (e) {
    if (e.status === 404) { S.selected = null; S.mat = null; }
  }
  renderPanel();
}

// ---------- bell and alerts ----------
function renderBell() {
  const badge = $("badge");
  badge.hidden = !(S.openAlerts > 0);
  setText(badge, String(S.openAlerts));
  $("bell").setAttribute("aria-label", t("alerts") + ", " + S.openAlerts);
  $("bellpanel").hidden = !S.bellOpen;
  $("bell").setAttribute("aria-expanded", String(S.bellOpen));
  if (!S.bellOpen) return;
  const list = $("alertList");
  const sorted = [...S.alerts].sort((a, b) => (a.state === "open" ? 0 : 1) - (b.state === "open" ? 0 : 1) || b.t_raised - a.t_raised).slice(0, 30);
  // rebuild only on change (ages count in whole minutes), so a click is never lost to a refresh
  const sig = lang + sorted.map((a) => [a.id, a.state, a.by, Math.floor((serverNow() - a.t_raised) / 60)]).join("|");
  if (list.dataset.sig === sig) return;
  list.dataset.sig = sig;
  list.textContent = "";
  if (!sorted.length) list.append(el("li", "al muted", t("noAlerts")));
  for (const a of sorted) {
    const li = el("li", "al"), head = el("div"), meta = el("div", "muted");
    head.append(el("b", "", a.name), document.createTextNode(a.room ? " · " + a.room : ""));
    const sq = el("span", "sq " + (a.state === "open" ? (a.kind === "offline" ? "offline" : "high") : "none"));
    meta.append(sq, document.createTextNode(
      t("kind_" + a.kind) + " · " + t("raised", { t: dur(serverNow() - a.t_raised) }) + " · " + t("st_" + a.state) + (a.by ? " " + t("byUser", { u: a.by }) : "") + (a.config ? " · " + t("cfgShort", { v: a.config }) : "")));
    li.append(head, meta);
    if (a.state === "open") {
      const acts = el("div", "acts"), ack = el("button", "btn primary", t("ack")), ign = el("button", "btn", t("ignore"));
      ack.type = ign.type = "button";
      ack.addEventListener("click", () => handleAlert("ack", a));
      ign.addEventListener("click", () => handleAlert("ignore", a));
      acts.append(ack, ign);
      li.append(acts);
    }
    list.append(li);
  }
}

function setBell(open) {
  S.bellOpen = open;
  if (open) $("bellpanel").style.top = document.querySelector(".top").offsetHeight + "px";
  renderBell();
  if (open) loadAlerts();
}

function handleAlert(kind, a) {
  writeDialog({
    title: t(kind === "ack" ? "dlgAck" : "dlgIgnore", { name: a.name }),
    send: (v) => send("POST", "/api/alerts/" + encodeURIComponent(a.id) + "/" + kind, { pin: v.pin }),
    done: (res) => toast(t(kind === "ack" ? "ackBy" : "ignBy", { u: res.user })),
  });
}

// ---------- PIN dialog and toast ----------
let dialogJob = null;
// fields: {key, label, value, type: "password", options: [[value, text]]}; noPin hides the acting user's PIN box
function writeDialog({ title, fields = [], send, done, pinLabel, noPin, hint, extra = [] }) {
  $("dlgTitle").textContent = title;
  const box = $("dlgFields");
  box.textContent = "";
  if (hint) box.append(el("p", "muted", hint));
  for (const f of fields) {
    const label = el("label", "", f.label), input = el(f.options ? "select" : "input");
    for (const [v, text] of f.options || []) { const o = el("option", "", text); o.value = v; input.append(o); }
    if (f.type) input.type = f.type;
    if (f.type === "password") input.setAttribute("inputmode", "numeric");
    input.value = f.value || (f.options ? f.options[0][0] : "");
    input.name = f.key;
    input.autocomplete = "off";
    label.append(input);
    box.append(label);
  }
  for (const x of extra) { // a side action, e.g. "Forget this mat": closes this dialog and opens its own
    const b = el("button", "link", x.label);
    b.type = "button";
    b.addEventListener("click", () => { $("dlg").close(); x.run(); });
    box.append(b);
  }
  $("pinRow").hidden = !!noPin;
  $("pin").required = !noPin;
  $("pinLabel").textContent = pinLabel || t("pin");
  $("pin").value = "";
  $("dlgErr").textContent = "";
  dialogJob = { fields, send, done };
  $("dlg").showModal();
}
$("dlgForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const values = { pin: $("pin").value };
  for (const input of $("dlgFields").querySelectorAll("input, select")) values[input.name] = input.value;
  $("dlgOk").disabled = true;
  $("dlgErr").textContent = "";   // an old answer must not look like the new one
  const res = await dialogJob.send(values);
  $("dlgOk").disabled = false;
  if (res.ok) {
    $("dlg").close();
    dialogJob.done(res);
    loadOverview();
    loadAlerts();
    fetchMat();
    fetchTimeline();
  } else {
    $("dlgErr").textContent = res.error; // the server's own text, e.g. a wrong PIN
    ($("pinRow").hidden ? $("dlgFields").querySelector("input") : $("pin")).select();
  }
});
$("dlgCancel").addEventListener("click", () => $("dlg").close());

let toastTimer = 0;
function toast(msg, ms = 6000) {
  setText($("toast"), msg);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => setText($("toast"), ""), ms);
}

$("editBtn").addEventListener("click", () => {
  const m = S.mats.find((x) => x.id === S.selected);
  if (m) editMat(m);
});
function editMat(m) {
  writeDialog({
    title: t("dlgEdit"),
    fields: [
      { key: "name", label: t("fName"), value: m.name }, { key: "room", label: t("fRoom"), value: m.room },
      { key: "seat", label: t("fSeat"), value: m.seat }, { key: "unit", label: t("fUnit"), value: m.unit },
    ],
    send: (v) => send("PUT", "/api/mats/" + encodeURIComponent(m.id) + "/meta", v),
    done: (res) => toast(t("savedBy", { u: res.user })),
    extra: isOffline(m) ? [{ label: t("forgetBtn"), run: () => forgetDialog(m) }] : [],
  });
}
const isOffline = (m) => !m.online || m.risk === "offline";

// A retired mat: like Remove, and the broker's retained copy is emptied too (admin PIN, optional reason)
function forgetDialog(m) {
  writeDialog({
    title: t("dlgForget", { name: m.name }), hint: t("forgetHint"),
    fields: [{ key: "reason", label: t("reasonLabel") }],
    send: (v) => send("POST", "/api/mats/" + encodeURIComponent(m.id) + "/forget", { pin: v.pin, reason: v.reason.trim() }),
    done: async (res) => {
      if (H.id === m.id) histLeave();
      if (res.broker_cleared === false) SET.noBroker.add(m.id);
      toast(t("forgottenBy", { u: res.user }) + (res.broker_cleared === false ? ". " + t("forgetNoBroker") : ""), res.broker_cleared === false ? 12000 : 6000);
      await loadHidden();
      renderSettingsMats();
    },
  });
}

// ---------- users (PINs are per person; viewing needs no login, changes need an admin's PIN) ----------
const pinFields = () => [
  { key: "pin1", label: t("fNewPin"), type: "password" }, { key: "pin2", label: t("fRepeatPin"), type: "password" },
];
const samePin = (v) => (v.pin1 === v.pin2 ? null : { ok: false, error: t("pinMismatch") });

function firstUserDialog() {
  writeDialog({
    title: t("dlgFirst"), hint: t("firstHint"), noPin: true,
    fields: [{ key: "name", label: t("fName") }, ...pinFields()],
    send: async (v) => samePin(v) || send("POST", "/api/users", { name: v.name, role: "admin", new_pin: v.pin1 }),
    done: (res) => { S.needsAdmin = false; toast(t("userAdded", { n: res.created.name })); },
  });
}

async function renderUsers() {
  let data;
  try { data = await api("/api/users"); } catch (e) { toast(t("netErr")); return false; }
  const list = $("userList");
  list.textContent = "";
  for (const u of data.users) {
    const li = el("li"), acts = el("span", "acts");
    li.append(el("span", u.active ? "who" : "who off",
      u.name + " · " + t(u.role === "admin" ? "roleAdmin" : "roleUser") + (u.active ? "" : " · " + t("userOff"))));
    for (const [key, change] of [[u.active ? "disable" : "enable", { active: !u.active }], ["resetPin", null]]) {
      const b = el("button", "link", t(key));
      b.type = "button";
      b.addEventListener("click", () => writeDialog({
        title: t(change ? (u.active ? "dlgDisable" : "dlgEnable") : "dlgResetPin", { n: u.name }),
        fields: change ? [] : pinFields(), pinLabel: t("adminPin"),
        send: async (v) => (change ? null : samePin(v)) ||
          send("PUT", "/api/users/" + u.id, Object.assign({ pin: v.pin }, change || { new_pin: v.pin1 })),
        done: (res) => { renderUsers(); toast(t("userChanged", { u: res.user })); },
      }));
      acts.append(b);
    }
    li.append(acts);
    list.append(li);
  }
  return true;
}

async function openUsers() {
  if (S.needsAdmin) return firstUserDialog();
  if (await renderUsers()) $("usersDlg").showModal();
}

$("userAdd").addEventListener("click", () => writeDialog({
  title: t("dlgAddUser"), pinLabel: t("adminPin"),
  fields: [
    { key: "name", label: t("fName") },
    { key: "role", label: t("fRole"), options: [["user", t("roleUser")], ["admin", t("roleAdmin")]] },
    ...pinFields(),
  ],
  send: async (v) => samePin(v) || send("POST", "/api/users", { pin: v.pin, name: v.name, role: v.role, new_pin: v.pin1 }),
  done: (res) => { renderUsers(); toast(t("userAdded", { n: res.created.name })); },
}));
$("usersClose").addEventListener("click", () => $("usersDlg").close());

async function checkSetup() { // no users yet: ask for the first admin, once per page load
  const h = await api("/api/health");
  S.needsAdmin = !!h.needs_admin;
  if (KIOSK && S.build && h.build && h.build !== S.build) location.reload(); // the server restarted or was updated: fetch the new page
  S.build = h.build;
  if (S.needsAdmin && !S.setupShown && !$("dlg").open) { S.setupShown = true; firstUserDialog(); }
}

// ---------- settings pages (everyone can read; an admin's PIN saves) ----------
// Two pages share the code: the site layer (every mat) and one mat's own layer on top of it. A page state `st` holds what the
// server sent (items, version, history) and the draft: only what differs from the server, a value or null for "inherit again".
const newPage = (prefix) => ({ prefix, scope: "site", items: null, version: 0, stamp: "", draft: {}, bad: new Set(), history: [], failed: false, saveBtn: null, saveInfo: null, reason: null });
const SET = Object.assign(newPage("set_"), { hidden: [], matsBox: null, noBroker: new Set() });   // the site page
const MCFG = Object.assign(newPage("mset_"), { mat: null });                 // one mat's page; scope is the mat's id
const GROUPS = ["alerts", "risk", "mats", "data", "posture", "contact", "temporal", "hotspots", "movement"];
const maybeT = (key) => i18n[lang][key] ?? i18n.nb[key];   // like t(), but undefined for a key that does not exist
const fmtNum = (v) => v.toLocaleString(locale(), { maximumFractionDigits: 2 });
const unitText = (u) => maybeT("u_" + u) ?? u;
const labelOf = (key) => maybeT("s_" + key) ?? key.split(".").pop().replaceAll("_", " ");   // engineering keys have no translation
function fmtValue(it, v) {
  if (v === null || v === undefined) return it && it.type === "list" ? t("idxBuiltin") : "–";
  if (Array.isArray(v)) return t("idxCustom", { n: v.length });
  if (typeof v === "boolean") return t(v ? "setOn" : "setOff");
  if (typeof v === "number") return fmtNum(v) + (it && it.unit ? " " + unitText(it.unit) : "");
  return String(v);
}
const settingItem = (st, key) => st.items.find((i) => i.key === key);
const pageUrl = (st) => (st === SET ? "/api/settings" : "/api/mats/" + encodeURIComponent(st.scope) + "/config");

function problem(it, v) { // "" when the typed number is fine, else the sentence to show under the box
  if (it.type === "bool" || it.type === "choice") return "";
  if (!Number.isFinite(v)) return t("errNumber");
  if (it.type === "int" && !Number.isInteger(v)) return t("errWhole");
  if (it.max == null) return v < it.min ? t("errMin", { min: fmtNum(it.min) }) : "";
  if (v < it.min || v > it.max) return t("errRange", { min: fmtNum(it.min), max: fmtNum(it.max) });
  return "";
}

// the draft holds only what differs from what the server has: a value, or null for "inherit again"
function setDraft(st, it, v) {
  if (JSON.stringify(v) === JSON.stringify(it.value)) delete st.draft[it.key];      // what the server already has
  else if (v === it.default) st.draft[it.key] = null;                               // only reachable while an override exists
  else st.draft[it.key] = v;
}

function refreshSave(st) {
  if (!st.saveBtn) return;
  const n = Object.keys(st.draft).length;
  st.saveBtn.disabled = n === 0 || st.bad.size > 0;
  setText(st.saveInfo, st.bad.size ? t("fixErrors") : n ? t("nChanges", { n }) : t("noChanges"));
}

function settingRow(st, it) {
  const mat = st !== SET;
  const row = el("div", "setrow"), left = el("div"), right = el("div", "setctl");
  const has = it.key in st.draft, draft = st.draft[it.key];
  const shown = has ? (draft === null ? it.default : draft) : it.value;
  const label = el("label", "", labelOf(it.key)), err = el("div", "err"), meta = el("div", "muted small");
  const id = st.prefix + it.key;
  label.htmlFor = id;
  const src = el("span", "src " + it.source, t("src_" + it.source));
  left.append(label, src, el("div", "muted small", maybeT("s_" + it.key + "_h") || ""));
  const line = el("div", "setline");
  let control = null;
  if (it.type === "list") {   // the risk indices are edited from the desktop app; here they can be put back to the built-in ones
    line.append(el("span", "", fmtValue(it, has ? draft : it.value)));
  } else if (it.type === "bool") {
    control = el("input");
    control.type = "checkbox";
    control.checked = shown;
    control.addEventListener("change", () => { setDraft(st, it, control.checked); refreshSave(st); });
  } else if (it.type === "choice") {
    control = el("select");
    for (const c of it.choices) { const o = el("option", "", c); o.value = c; control.append(o); }
    control.value = shown;
    control.addEventListener("change", () => { setDraft(st, it, control.value); refreshSave(st); });
  } else {
    control = el("input");
    control.type = "number";
    control.step = it.type === "int" ? "1" : "any";
    if (it.min != null) control.min = it.min;
    if (it.max != null) control.max = it.max;
    control.setAttribute("inputmode", it.type === "int" ? "numeric" : "decimal");
    control.value = shown;
    control.addEventListener("input", () => {
      const raw = control.value.trim(), v = raw === "" ? NaN : Number(raw.replace(",", "."));
      const msg = problem(it, v);
      setText(err, msg);
      control.setAttribute("aria-invalid", String(!!msg));
      if (msg) st.bad.add(it.key);
      else { st.bad.delete(it.key); setDraft(st, it, v); }
      refreshSave(st);
    });
  }
  if (control) { control.id = id; line.append(control); }
  if (control && it.type !== "bool" && it.unit) line.append(el("span", "muted", unitText(it.unit)));
  meta.append(document.createTextNode(t(mat ? "setDefaultSite" : "setDefault", { v: fmtValue(it, it.default) })));
  if (it.changed) {
    const reset = el("button", "link", t(mat ? "useSite" : "resetDefault"));
    reset.type = "button";
    reset.addEventListener("click", () => {
      if (it.type === "list") st.draft[it.key] = null;
      else {
        if (control && it.type === "bool") control.checked = it.default; else if (control) control.value = it.default;
        st.bad.delete(it.key);
        setText(err, "");
        setDraft(st, it, it.default);
      }
      refreshSave(st);
      if (it.type === "list") setText(line, fmtValue(it, null));
    });
    meta.append(document.createTextNode(" · "), reset);
  }
  right.append(line, err, meta);
  row.append(left, right);
  return row;
}

function renderGroups(page, st) {
  for (const g of GROUPS) {
    const items = st.items.filter((i) => i.group === g);
    if (!items.length) continue;
    const adv = items.filter((i) => i.advanced);
    if (adv.length === items.length) { // a group for engineers only is one fold-out with its own title
      const d = el("details", "adv");
      d.open = adv.some((i) => i.key in st.draft);
      d.append(el("summary", "", t("g_" + g) + " – " + t("advanced")));
      for (const it of adv) d.append(settingRow(st, it));
      page.append(d);
      continue;
    }
    page.append(el("h2", "", t("g_" + g)));
    if (maybeT("g_" + g + "_h")) page.append(el("p", "muted", t("g_" + g + "_h")));
    for (const it of items.filter((i) => !i.advanced)) page.append(settingRow(st, it));
    if (adv.length) {
      const d = el("details", "adv");
      d.open = adv.some((i) => i.key in st.draft);
      d.append(el("summary", "", t("advanced")));
      for (const it of adv) d.append(settingRow(st, it));
      page.append(d);
    }
  }
}

function renderHistory(page, st) { // every version of this layer: who, when, why, what changed, and a way back
  page.append(el("h2", "", t("history")));
  const list = el("ul", "ulist hist");
  if (!st.history.length) list.append(el("li", "muted", t("noHistory")));
  st.history.forEach((h, index) => {
    const li = el("li"), who = el("span", "who"), acts = el("span", "acts");
    const when = new Date(h.t * 1000).toLocaleString(locale(), { dateStyle: "short", timeStyle: "short" });
    who.append(el("b", "", t("version") + " " + h.version), document.createTextNode(" · " + when + " · " + (h.user || "–") + (h.reason ? " · " + h.reason : "")));
    const lines = el("div", "muted small");
    for (const [key, [from, to]] of Object.entries(h.changes || {})) {
      const it = st.items && settingItem(st, key);
      lines.append(el("div", "", labelOf(key) + ": " + fmtValue(it, from) + " → " + fmtValue(it, to)));
    }
    who.append(lines);
    if (index > 0) { // the newest version is what is in force; older ones can be put back
      const back = el("button", "link", t("restoreVersion", { v: h.version }));
      back.type = "button";
      back.addEventListener("click", () => rollbackDialog(st, h.version));
      acts.append(back);
    }
    li.append(who, acts);
    list.append(li);
  });
  if (st.history.length) {
    const li = el("li"), acts = el("span", "acts"), back = el("button", "link", t("restoreVersion", { v: 0 }));
    back.type = "button";
    back.addEventListener("click", () => rollbackDialog(st, 0));
    acts.append(back);
    li.append(el("span", "who muted", t("factoryVersion")), acts);
    list.append(li);
  }
  page.append(list);
}

function rollbackDialog(st, version) {
  writeDialog({
    title: t("dlgRollback", { v: version }), hint: t("rollbackHint"),
    fields: [{ key: "reason", label: t("reasonLabel") }],
    send: (v) => send("POST", "/api/config/rollback", { pin: v.pin, scope: st.scope, version, reason: v.reason }),
    done: async (res) => { st.items = res.settings; st.version = res.version; st.stamp = res.stamp; st.draft = {}; st.bad.clear(); await loadHistory(st); renderPage(st); toast(t("rolledBack", { u: res.user })); },
  });
}

function savebar(page, st) {
  const reasonLabel = el("label", "reason", t("reasonLabel"));
  st.reason = el("input");
  st.reason.maxLength = 200;
  st.reason.placeholder = t("reasonPh");
  reasonLabel.append(st.reason);
  const bar = el("div", "savebar");
  st.saveInfo = el("span", "muted");
  st.saveBtn = el("button", "btn primary", t(st === SET ? "saveChanges" : "saveForMat"));
  st.saveBtn.type = "button";
  st.saveBtn.addEventListener("click", () => saveSettings(st));
  bar.append(st.saveInfo, st.saveBtn);
  page.append(reasonLabel, bar);
  refreshSave(st);
}

function saveSettings(st) {
  const changes = Object.entries(st.draft).map(([key, v]) => {
    const it = settingItem(st, key);
    return labelOf(key) + ": " + fmtValue(it, it.value) + " → " + fmtValue(it, v === null ? it.default : v);
  });
  const reason = st.reason ? st.reason.value.trim() : "";
  writeDialog({
    title: t("dlgSave"), hint: changes.join("; "),
    send: (v) => send("PUT", pageUrl(st), { pin: v.pin, values: st.draft, reason }),
    done: async (res) => {
      st.items = res.settings; st.version = res.version; st.stamp = res.stamp; st.draft = {}; st.bad.clear();
      await loadHistory(st);
      renderPage(st);
      toast(t("savedSettings", { u: res.user }));
    },
  });
}

async function loadHistory(st) {
  try { st.history = (await api("/api/config/history?scope=" + encodeURIComponent(st.scope))).history; } catch (e) { /* the banner already says so */ }
}
async function loadHidden() {
  try { SET.hidden = (await api("/api/hidden-mats")).mats; } catch (e) { /* the banner already says so */ }
}

function renderSettingsMats() { // rebuilt only when something shown changed, so a click is never lost to the 2 s refresh
  const box = SET.matsBox;
  if (!box || !SET.items) return;
  const sig = lang + JSON.stringify(S.mats.map((m) => [m.id, m.name, m.room, m.seat, m.unit, m.online, m.risk])) +
    JSON.stringify(SET.hidden.map((h) => [h.id, h.name, SET.noBroker.has(h.id)]));
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.textContent = "";
  const action = (label, fn) => { const b = el("button", "link", label); b.type = "button"; b.addEventListener("click", fn); return b; };
  const list = el("ul", "ulist");
  for (const m of [...S.mats].sort(byName)) {
    const li = el("li"), who = el("span", "who"), acts = el("span", "acts");
    const offline = isOffline(m);
    who.append(el("span", "sq " + (offline ? "offline" : "low")), el("b", "", m.name));
    if (m.demo) who.append(document.createTextNode(" "), el("span", "demo", "DEMO"));
    const details = [m.room, m.seat, m.unit, offline ? t("risk_offline") : ""].filter(Boolean).join(" · ");
    if (details) who.append(el("span", "muted", " · " + details));
    acts.append(action(t("edit"), () => editMat(m)), action(t("analysis"), () => openMatConfig(m)));
    if (offline) acts.append(action(t("forget"), () => forgetDialog(m)));
    if (offline) acts.append(action(t("rm"), () => writeDialog({
      title: t("dlgRemove", { name: m.name }), hint: t("rmHint"),
      send: (v) => send("POST", "/api/mats/" + encodeURIComponent(m.id) + "/hide", { pin: v.pin }),
      done: async (res) => { toast(t("removedBy", { u: res.user })); await loadHidden(); renderSettingsMats(); },
    })));
    li.append(who, acts);
    list.append(li);
  }
  if (!S.mats.length) list.append(el("li", "muted", t("noMats")));
  box.append(list, el("h3", "", t("removedMats")));
  const gone = el("ul", "ulist");
  for (const h of SET.hidden) {
    const li = el("li"), acts = el("span", "acts");
    const who = el("span", "who", h.name + (h.room ? " · " + h.room : ""));
    if (SET.noBroker.has(h.id)) who.append(el("div", "muted small", t("forgetNoBroker")));
    li.append(who, acts);
    acts.append(action(t("restore"), () => writeDialog({
      title: t("dlgRestore", { name: h.name }), hint: t("restoreHint"),
      send: (v) => send("POST", "/api/mats/" + encodeURIComponent(h.id) + "/show", { pin: v.pin }),
      done: async (res) => { toast(t("restoredBy", { u: res.user })); await loadHidden(); renderSettingsMats(); },
    })));
    gone.append(li);
  }
  if (!SET.hidden.length) gone.append(el("li", "muted", t("noRemoved")));
  box.append(gone);
}

function renderPage(st) {
  if (st === SET) renderSettings(); else renderMatConfig();
}

function renderSettings() {
  const page = $("settings");
  page.textContent = "";
  SET.saveBtn = SET.saveInfo = SET.matsBox = null;
  const top = el("p"), back = el("button", "link", "← " + t("back"));
  back.type = "button";
  back.addEventListener("click", () => showView("dash"));
  top.append(back);
  page.append(top, el("h1", "", t("settings")), el("p", "muted", t("setIntro")));
  renderScreenSettings(page);
  if (!SET.items) { page.append(el("p", "muted", SET.failed ? t("netErr") : t("loading"))); return; }
  page.append(el("p", "muted small", t("cfgVersion", { v: SET.stamp })));

  page.append(el("h2", "", t("setMats")), el("p", "muted", t("setMatsHint")));
  SET.matsBox = el("div");
  page.append(SET.matsBox);
  renderSettingsMats();

  page.append(el("h2", "", t("siteDefaults")), el("p", "muted", t("siteDefaultsHint")));
  renderGroups(page, SET);

  page.append(el("h2", "", t("users")), el("p", "muted", t("setUsersHint")));
  const users = el("button", "btn", t("openUsers"));
  users.type = "button";
  users.addEventListener("click", openUsers);
  page.append(users);
  renderHistory(page, SET);
  const audit = el("a", "btn", t("exAudit"));
  audit.href = "/api/export/audit.csv";
  audit.download = "";
  page.append(el("h2", "", t("exportSet")), el("p", "muted", t("exportSetHint")), audit);
  savebar(page, SET);
}

function setRepos(on) { // "Show repositioning info": hides time since movement, movements per hour and the repositioning export everywhere
  store.set("repos", on ? "1" : "0");
  S.moves = null;
  if (on) fetchMoves();
  for (const r of rows.values()) r.row.remove();
  rows.clear();
  renderList();
  $("exportBox").dataset.sig = "";
  renderPanel();
  if (H.on) histShow();
}

function renderScreenSettings(page) { // this browser only (localStorage), no PIN
  const line = el("label", "setline"), box = el("input"), test = el("button", "btn", t("alertTest"));
  box.type = "checkbox";
  box.checked = cue.on;
  box.addEventListener("change", () => setCue(box.checked));
  line.append(box, document.createTextNode(t("alertSound")));
  test.type = "button";
  test.addEventListener("click", () => { unlockAudio(true); alertCue(true); });
  const row = el("div", "setline");
  row.append(line, test);
  page.append(el("h2", "", t("screenSettings")), row, el("p", "muted small", t("alertSoundHint")));
  const rep = el("label", "setline"), rbox = el("input");
  rbox.type = "checkbox";
  rbox.checked = reposOn();
  rbox.addEventListener("change", () => setRepos(rbox.checked));
  rep.append(rbox, document.createTextNode(t("reposShow")));
  page.append(rep, el("p", "muted small", t("reposHint")));
}

function renderMatConfig() {
  const page = $("matcfg"), st = MCFG;
  page.textContent = "";
  st.saveBtn = st.saveInfo = null;
  const top = el("p"), back = el("button", "link", "← " + t("settings"));
  back.type = "button";
  back.addEventListener("click", () => showView("settings"));
  top.append(back);
  const name = st.mat ? st.mat.name : st.scope;
  page.append(top, el("h1", "", t("matCfgTitle", { name })), el("p", "muted", t("matCfgIntro")));
  if (!st.items) { page.append(el("p", "muted", st.failed ? t("netErr") : t("loading"))); return; }
  page.append(el("p", "muted small", t("cfgVersion", { v: st.stamp })));
  renderGroups(page, st);
  renderHistory(page, st);
  renderPassport(page, st);
  savebar(page, st);
}

// The calibration kept on the mat itself: look at both slots, take one into use, save the current setup to the custom slot
function renderPassport(page, st) {
  const box = el("section", "card");
  box.append(el("h2", "", t("ppTitle")), el("p", "muted small", t("ppHint")));
  const p = st.passport;
  if (!p) { box.append(el("p", "muted", st.passportFailed ? t("ppNone") : t("loading"))); page.append(box); return; }
  box.append(el("p", "small", t("ppSerial") + ": " + (p.serial || "–")));
  for (const slot of ["factory", "custom"]) {
    const info = p.slots[slot], row = el("div", "row");
    row.append(el("strong", "", t(slot === "factory" ? "ppFactory" : "ppCustom") + ": "));
    if (!info) row.append(el("span", "muted", t("ppEmpty")));
    else if (info.error) row.append(el("span", "muted", info.error));
    else {
      row.append(el("span", "", info.info + (info.has_analysis ? " – " + t("ppAnalysis") : "") + " – " + t(info.same_as_now ? "ppSame" : "ppDiffers")));
      const use = el("button", "btn", t("ppUse"));
      use.type = "button";
      use.addEventListener("click", () => writeDialog({
        title: t("dlgPpUse", { slot: t(slot === "factory" ? "ppFactory" : "ppCustom") }), hint: info.info,
        send: (v) => send("POST", "/api/mats/" + encodeURIComponent(st.scope) + "/passport/adopt", { pin: v.pin, slot, reason: "passport " + slot }),
        done: async (res) => { toast(t("ppUsed", { u: res.user })); await openMatConfig(st.mat); },
      }));
      row.append(use);
    }
    box.append(row);
  }
  const note = el("input"), save = el("button", "btn primary", t("ppSave"));
  note.type = "text"; note.maxLength = 120; note.placeholder = t("ppNote");
  save.type = "button";
  save.addEventListener("click", () => writeDialog({
    title: t("dlgPpSave"), hint: note.value,
    send: (v) => send("POST", "/api/mats/" + encodeURIComponent(st.scope) + "/passport/write", { pin: v.pin, note: note.value }),
    done: async (res) => { toast(t("ppSaved", { v: res.version, u: res.user })); await loadPassport(st); renderMatConfig(); },
  }));
  box.append(el("div", "row", ""), note, save);
  page.append(box);
}

async function loadPassport(st) {
  st.passport = null; st.passportFailed = false;
  try { st.passport = await api("/api/mats/" + encodeURIComponent(st.scope) + "/passport"); } catch (e) { st.passportFailed = true; }
}

async function openSettings() {
  SET.draft = {};
  SET.bad.clear();
  SET.failed = false;
  showView("settings");
  renderSettings();
  try {
    const page = await api("/api/settings");
    Object.assign(SET, { items: page.settings, version: page.version, stamp: page.stamp });
    await Promise.all([loadHidden(), loadHistory(SET)]);
  } catch (e) { SET.failed = true; }
  renderSettings();
}

async function openMatConfig(m) {
  Object.assign(MCFG, { scope: m.id, mat: m, items: null, history: [], draft: {}, failed: false, passport: null, passportFailed: false });
  MCFG.bad.clear();
  showView("matcfg");
  renderMatConfig();
  try {
    const page = await api("/api/mats/" + encodeURIComponent(m.id) + "/config");
    Object.assign(MCFG, { items: page.settings, version: page.version, stamp: page.stamp });
    await loadHistory(MCFG);
  } catch (e) { MCFG.failed = true; }
  renderMatConfig();
  await loadPassport(MCFG);   // slower than the page (the mat answers over MQTT): it fills in when it arrives
  if (MCFG.scope === m.id && !$("matcfg").hidden) renderMatConfig();
}

// ---------- help page ----------
function renderHelp() {
  const h = i18n[lang].help_, page = $("help");
  page.textContent = "";
  const top = el("p");
  const back = el("button", "link", "← " + t("back"));
  back.type = "button";
  back.addEventListener("click", () => showHelp(false));
  top.append(back);
  page.append(top, el("h1", "", h.title));
  page.append(el("h2", "", h.colours[0]));
  for (const [cls, name, text] of h.colours[1]) {
    const row = el("div", "legend-row"), chip = el("span", "chip status " + cls, name);
    row.append(chip, document.createTextNode(text));
    page.append(row);
  }
  const list = (key, tag) => {
    page.append(el("h2", "", h[key][0]));
    const ul = el(tag);
    for (const item of h[key][1]) ul.append(el("li", "", item));
    page.append(ul);
  };
  list("alert", "ol");
  list("map", "ul");
  list("hist", "ul");
  list("note", "ul");
}
function showView(name) { // "dash", "help", "settings" or "matcfg" (one mat's analysis settings)
  $("dash").hidden = name !== "dash";
  $("help").hidden = name !== "help";
  $("settings").hidden = name !== "settings";
  $("matcfg").hidden = name !== "matcfg";
  window.scrollTo(0, 0);
}
function showHelp(on) { showView(on ? "help" : "dash"); }

// ---------- language, theme ----------
function applyLang() {
  document.documentElement.lang = lang === "en" ? "en" : "nb";
  for (const n of document.querySelectorAll("[data-i]")) n.textContent = t(n.dataset.i);
  for (const n of document.querySelectorAll("[data-i-ph]")) n.placeholder = t(n.dataset.iPh);
  for (const n of document.querySelectorAll("[data-i-label]")) n.setAttribute("aria-label", t(n.dataset.iLabel));
  for (const n of document.querySelectorAll("[data-i-title]")) n.title = t(n.dataset.iTitle);
  setText($("langBtn"), t("langBtn"));
  $("langBtn").title = lang === "en" ? "Norsk" : "English";
  setText($("foot"), t("foot"));
  $("bellpanel").setAttribute("aria-label", t("alerts"));
  for (const r of rows.values()) r.row.remove();
  rows.clear();
  applyTheme(document.documentElement.dataset.theme, false);
  renderHelp();
  if (!$("settings").hidden) renderSettings();
  if (!$("matcfg").hidden) renderMatConfig();
  renderList();
  renderBell();
  renderPanel();
  if (H.on) histRender();
}

function applyTheme(mode, save = true) {
  const dark = mode === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  if (S.hm) S.hm.refreshColors();
  if (save) store.set("theme", dark ? "dark" : "light");
  for (const [id, kind] of [["logo", "lockup"], ["logoMark", "mark"]]) $(id).src = `img/logo_${kind}_${dark ? "dark" : "light"}.png`;
  document.querySelector('meta[name="theme-color"]').content = cssVar("--brandbar") || "#FFFFFF";
  const snap = S.mat && S.mat.snapshot;
  if (snap && save) renderPanel();
  if (H.on) histRender();
}

// ---------- kiosk alert cue: a short beep and a red flash on a new alert (off by default, per screen) ----------
const cue = { on: store.get("alertcue") === "1", ctx: null };
function unlockAudio(force = false) { // browsers only start audio after a tap or key press on the page
  if (!cue.on && !force) return;
  try {
    if (!cue.ctx) { const AC = window.AudioContext || window.webkitAudioContext; if (AC) cue.ctx = new AC(); }
    if (cue.ctx && cue.ctx.state === "suspended") cue.ctx.resume();
  } catch (e) { /* no audio: the flash still works */ }
}
for (const ev of ["pointerdown", "keydown", "touchend"]) document.addEventListener(ev, () => unlockAudio(), { passive: true });
function beep() {
  const c = cue.ctx;
  if (!c || c.state !== "running") return;
  const now = c.currentTime;
  for (const [k, hz] of [[0, 880], [0.22, 1175]]) {
    const o = c.createOscillator(), g = c.createGain();
    o.type = "sine";
    o.frequency.value = hz;
    g.gain.setValueAtTime(0.0001, now + k);
    g.gain.exponentialRampToValueAtTime(0.25, now + k + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, now + k + 0.18);
    o.connect(g).connect(c.destination);
    o.start(now + k);
    o.stop(now + k + 0.2);
  }
}
function alertCue(force = false) {
  if (!cue.on && !force) return;
  const f = $("flash");
  f.classList.remove("on");
  void f.offsetWidth;   // restart the animation
  f.classList.add("on");
  beep();
}
function setCue(on) {
  cue.on = on;
  store.set("alertcue", on ? "1" : "0");
  unlockAudio();
}

// ---------- wiring ----------
$("sort").value = SORTS[S.sort] ? S.sort : "risk";
$("sort").addEventListener("change", () => { S.sort = $("sort").value; store.set("sort", S.sort); renderList(); });
$("unit").addEventListener("change", () => { S.unit = $("unit").value; store.set("unit", S.unit); renderList(); });
$("search").addEventListener("input", () => { S.q = $("search").value; renderList(); });
$("bell").addEventListener("click", () => setBell(!S.bellOpen));
$("helpBtn").addEventListener("click", () => showHelp($("help").hidden));
$("settingsBtn").addEventListener("click", () => ($("settings").hidden ? openSettings() : showView("dash")));
$("langBtn").addEventListener("click", () => { lang = lang === "nb" ? "en" : "nb"; store.set("lang", lang); applyLang(); });
$("themeBtn").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("toList").addEventListener("click", () => $("list").scrollIntoView());
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && S.bellOpen) { setBell(false); $("bell").focus(); } });
document.addEventListener("click", (ev) => {
  if (S.bellOpen && !ev.target.closest("#bellpanel, #bell, dialog")) setBell(false);
});
window.addEventListener("resize", () => { const r = rows.get(S.selected); if (r && !r.detail.hidden) drawTimeline(r.tlHost); });

function setLost(lost) {
  S.lost = lost;
  document.body.classList.toggle("lost", lost);
  $("banner").hidden = !lost;
  setText($("banner"), t("lostServer"));
}

async function loadOverview() {
  try {
    const d = await api("/api/overview");
    S.mats = d.mats;
    if (S.overviewSeen && d.open_alerts > S.openAlerts) alertCue();   // a new alert since the last look
    S.overviewSeen = true;
    S.openAlerts = d.open_alerts;
    S.offset = d.server_time - Date.now() / 1000;
    setLost(false);
  } catch (e) {
    setLost(true); // keep the last rows, but they no longer look healthy
  }
  renderUnits();
  renderList();
  renderBell();
  renderPanel();
  if (S.bellOpen) loadAlerts();
  renderSettingsMats(); // no-op unless the settings page is open
}

async function loadAlerts() {
  try { S.alerts = (await api("/api/alerts")).alerts; renderBell(); } catch (e) { /* the banner already says so */ }
}

async function loadTheme() { // colour ramp shared with the desktop app; the built-in one stays if this fails
  try {
    const stops = (await api("/api/theme")).heatmap_stops;
    if (Array.isArray(stops) && stops.length > 1) S.ramp = stops.map(([v, c]) => [Number(v), c.map(Number)]);
    const g = S.ramp.map(([v, c]) => `rgb(${c[0]},${c[1]},${c[2]}) ${Math.round(v * 100)}%`).join(",");
    $("ramp").style.background = `linear-gradient(90deg, ${g})`;
    S.hm.setRamp(S.ramp);
    renderPanel();
  } catch (e) { /* fallback ramp */ }
}

// The logo is "home": back to the dashboard with the selected mat's pressure map open
function goHome() {
  setBell(false);
  showView("dash");
  if (S.selected && !S.open) select(S.selected);
  window.scrollTo(0, 0);
}

// Touchscreen kiosk (/?kiosk): hold the logo 3 s, or tap it 5 times within 4 s, to close the browser (the server only obeys the Pi itself)
let taps = [], held = null;
const exitKiosk = () => fetch("/api/kiosk/exit", { method: "POST" }).catch(() => {});
const brand = document.querySelector(".brand"); // the whole logo link, so a tap beside the image does not reload the page
brand.addEventListener("click", (e) => {
  e.preventDefault();
  goHome();
  if (!KIOSK) return;
  taps = [...taps.filter((t) => Date.now() - t < 4000), Date.now()];
  if (taps.length >= 5) exitKiosk();
});
if (KIOSK) {
  brand.addEventListener("contextmenu", (e) => e.preventDefault());
  brand.addEventListener("pointerdown", () => { held = setTimeout(exitKiosk, 3000); });
  for (const ev of ["pointerup", "pointercancel", "pointerleave"]) brand.addEventListener(ev, () => clearTimeout(held));
}

mapInit();
histInit();
$("layer").addEventListener("change", () => onControl("layer", $("layer")));
$("view").addEventListener("change", () => onControl("view", $("view")));
applyLang();
$("ramp").style.background = "linear-gradient(90deg," + S.ramp.map(([v, c]) => `rgb(${c.join(",")}) ${Math.round(v * 100)}%`).join(",") + ")";
loadTheme();
every(2000, loadOverview);
every(500, fetchMat);
every(5000, fetchTimeline);
every(10000, checkSetup);
every(60000, fetchMoves);
