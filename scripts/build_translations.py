"""Write strings.json, translations/en.json and translations/da.json from one table.

Run after changing any UI text:
    .venv/bin/python scripts/build_translations.py
tests/test_translations.py fails when the files are out of date.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from custom_components.udespa_control.const import (
    ENTITY_KEYS,
    NUMBER_KEYS,
    PRESET_KEYS,
    SECTION_ENTITIES,
    SECTION_NUMBERS,
    SECTION_SOURCES,
    SECTION_TOGGLES,
    SOURCE_KEYS,
    TOGGLE_KEYS,
)

INTEGRATION = REPO / "custom_components" / "udespa_control"
EN, DA = 0, 1

# key: (English label, English help, Danish label, Danish help)
FIELDS: dict[str, tuple[str, str, str, str]] = {
    "spa": (
        "Spa",
        "The spa's climate entity. Its current temperature and setpoint drive every rule.",
        "Spa",
        "Spaens climate-entitet. Dens aktuelle temperatur og setpunkt styrer alle regler.",
    ),
    "circulation": (
        "Circulation pump",
        "On while the spa circulates water. The heat pump may only run while it is on.",
        "Cirkulationspumpe",
        "Tændt mens spaen cirkulerer vandet. Varmepumpen må kun køre, mens den er tændt.",
    ),
    "filter_cycle_1": (
        "Filter cycle 1",
        "Optional. Only used to name the cycle in Last action.",
        "Filtercyklus 1",
        "Valgfri. Bruges kun til at navngive cyklussen i Seneste handling.",
    ),
    "filter_cycle_2": (
        "Filter cycle 2",
        "Optional. Only used to name the cycle in Last action.",
        "Filtercyklus 2",
        "Valgfri. Bruges kun til at navngive cyklussen i Seneste handling.",
    ),
    "heat_pump": (
        "Heat pump",
        "The heat pump's climate entity. Its own state is never trusted; power confirms it.",
        "Varmepumpe",
        "Varmepumpens climate-entitet. Dens egen tilstand stoles aldrig på; strømmen bekræfter den.",
    ),
    "heat_pump_power": (
        "Heat pump power",
        "Power on the meter phase that carries only the heat pump.",
        "Varmepumpe strøm",
        "Effekt på den målerfase, der kun bærer varmepumpen.",
    ),
    "heater": (
        "Heater",
        "The switch for the electric heater, used for frost protection and as backup.",
        "Varmelegeme",
        "Kontakten til varmelegemet, brugt til frostsikring og som backup.",
    ),
    "heater_power": (
        "Heater power",
        "Power on the meter phase that carries only the heater.",
        "Varmelegeme strøm",
        "Effekt på den målerfase, der kun bærer varmelegemet.",
    ),
    "outdoor": (
        "Outdoor temperature",
        "Entity holding the outdoor temperature, in its state or in the attribute below.",
        "Udetemperatur",
        "Entitet med udetemperaturen, i sin tilstand eller i attributten nedenfor.",
    ),
    "outdoor_attribute": (
        "Outdoor temperature attribute",
        "Leave empty to use the entity's state.",
        "Attribut for udetemperatur",
        "Lad feltet stå tomt for at bruge entitetens tilstand.",
    ),
    "cleaning_pump": (
        "Cleaning pump",
        "The pump that runs the pipe-cleaning cycles.",
        "Rengøringspumpe",
        "Pumpen, der kører rørrengøringens cyklusser.",
    ),
    "notify": (
        "Notification service",
        "For example notify.mobile_app_thomas_iphone_15.",
        "Notifikationstjeneste",
        "For eksempel notify.mobile_app_thomas_iphone_15.",
    ),
    "off_delay_s": (
        "Switch-off delay after heat call",
        "How long the spa must report off before the heat pump is switched off.",
        "Sluk-forsinkelse efter varmekald",
        "Hvor længe spaen skal melde off, før varmepumpen slukkes.",
    ),
    "head_start_timeout_s": (
        "Head start timeout",
        ("Head start switches the heat pump off again if no heat call arrives within this "
        "time. Keep it below the compressor's start (85–96 s)."),
        "Hurtigstart timeout",
        ("Hurtigstart slukker varmepumpen igen, hvis der ikke kommer et varmekald inden for "
        "denne tid. Hold den under kompressorens start (85–96 s)."),
    ),
    "heat_pump_on_w": (
        "Heat pump running above",
        "Power that confirms the heat pump is running.",
        "Varmepumpe kører over",
        "Effekt, der bekræfter, at varmepumpen kører.",
    ),
    "heat_pump_off_w": (
        "Heat pump stopped below",
        "Power that confirms the heat pump has stopped. Must be lower than the running threshold.",
        "Varmepumpe stoppet under",
        "Effekt, der bekræfter, at varmepumpen er stoppet. Skal være lavere end kører-grænsen.",
    ),
    "retry_minutes": (
        "Retry window",
        "How long a switch-on or switch-off is retried and verified before it counts as failed.",
        "Retry-vindue",
        "Hvor længe et tænd eller sluk forsøges og verificeres, før det regnes som fejlet.",
    ),
    "backup_margin_c": (
        "Backup: margin below setpoint",
        "The backup heater only steps in when the water is this far below the setpoint.",
        "Backup: margin under setpunkt",
        "Backup-varmelegemet træder kun til, når vandet er så langt under setpunktet.",
    ),
    "backup_check_s": (
        "Backup: check the heater after",
        "How long after switching the heater on its power is checked for the alert.",
        "Backup: måling af varmelegeme efter",
        "Hvor længe efter varmelegemet tændes, dets effekt måles til notifikationen.",
    ),
    "heater_on_w": (
        "Heater running above",
        "Power that confirms the heater is heating.",
        "Varmelegeme kører over",
        "Effekt, der bekræfter, at varmelegemet varmer.",
    ),
    "watchdog_interval_min": (
        "Watchdog: interval",
        "How often the watchdog checks the heat pump.",
        "Vagthund: interval",
        "Hvor tit vagthunden tjekker varmepumpen.",
    ),
    "watchdog_circulation_min": (
        "Watchdog: circulation at least",
        "The watchdog only acts after circulation has run this long.",
        "Vagthund: cirkulation mindst",
        "Vagthunden handler først, når cirkulationen har kørt så længe.",
    ),
    "frost_limit_c": (
        "Frost limit",
        "Frost protection switches the heater on below this outdoor temperature and off above it.",
        "Frostgrænse",
        "Frostsikringen tænder varmelegemet under denne udetemperatur og slukker det over.",
    ),
    "in_use_threshold_c": (
        "In use above rest temperature",
        "Status is I brug when the setpoint is more than this above the rest temperature.",
        "I brug-grænse over hviletemperatur",
        "Status er I brug, når setpunktet ligger mere end dette over hviletemperaturen.",
    ),
    "cleaning_max_min": (
        "Cleaning: maximum per cycle",
        "Backstop if the spa never stops the cleaning pump itself (it normally does after 15 min).",
        "Rengøring: max pr. cyklus",
        "Sikkerhedsgrænse, hvis spaen ikke selv stopper rengøringspumpen (normalt efter 15 min).",
    ),
    "cleaning_estimate_min": (
        "Cleaning: display estimate",
        "Shown to dashboards as the expected cycle length.",
        "Rengøring: visnings-estimat",
        "Vises på dashboards som forventet cyklus-længde.",
    ),
    "preset_quiet": (
        "Preset for Lydløs",
        "The heat pump's preset for the Lydløs mode.",
        "Preset for Lydløs",
        "Varmepumpens preset for tilstanden Lydløs.",
    ),
    "preset_smart": (
        "Preset for Smart",
        "The heat pump's preset for the Smart mode.",
        "Preset for Smart",
        "Varmepumpens preset for tilstanden Smart.",
    ),
    "preset_turbo": (
        "Preset for Turbo",
        "The heat pump's preset for the Turbo mode.",
        "Preset for Turbo",
        "Varmepumpens preset for tilstanden Turbo.",
    ),
    "head_start": (
        "Head start in I brug",
        "Switch the heat pump on when circulation starts in I brug, before the spa calls for heat.",
        "Hurtigstart i I brug",
        "Tænd varmepumpen, når cirkulationen starter i I brug, før spaen kalder på varme.",
    ),
    "backup_heater": (
        "Backup heater on failure",
        "Switch the heater on when the heat pump fails and the water is cold.",
        "Backup-varmelegeme ved fejl",
        "Tænd varmelegemet, når varmepumpen fejler, og vandet er koldt.",
    ),
    "watchdog": (
        "Watchdog",
        "Check regularly that the heat pump runs while the water is cold.",
        "Vagthund",
        "Tjek jævnligt, at varmepumpen kører, mens vandet er koldt.",
    ),
    "notifications": (
        "Notifications",
        "Send alerts to the notification service.",
        "Notifikationer",
        "Send advarsler til notifikationstjenesten.",
    ),
    "fault_status": (
        "Status Fejl on heat pump failure",
        "Show Fejl as the status while a heat pump failure is open.",
        "Status Fejl ved varmepumpefejl",
        "Vis Fejl som status, mens en varmepumpefejl er åben.",
    ),
    "src_hp_outlet": ("Heat pump outlet temperature", "Source for the heat pump's outlet temperature. Also used for the temperature rise.", "Varmepumpe udløbstemperatur", "Kilde til varmepumpens udløbstemperatur. Bruges også til temperaturstigningen."),
    "src_hp_compressor": ("Heat pump compressor", "Source for the compressor strength.", "Varmepumpe kompressor", "Kilde til kompressorens styrke."),
    "src_hp_ambient": ("Heat pump ambient temperature", "Source for the air temperature at the heat pump.", "Varmepumpe omgivelsestemperatur", "Kilde til lufttemperaturen ved varmepumpen."),
    "src_hp_coil": ("Heat pump coil temperature", "Diagnostic.", "Varmepumpe spoletemperatur", "Diagnostik."),
    "src_hp_exhaust": ("Heat pump exhaust temperature", "Diagnostic.", "Varmepumpe afgangstemperatur", "Diagnostik."),
    "src_hp_ipm": ("Heat pump IPM temperature", "Diagnostic.", "Varmepumpe IPM-temperatur", "Diagnostik."),
    "src_hp_fan": ("Heat pump fan speed", "Diagnostic.", "Varmepumpe blæserhastighed", "Diagnostik."),
    "src_hp_eev": ("Heat pump EEV step", "Diagnostic.", "Varmepumpe EEV-trin", "Diagnostik."),
    "src_hp_compressor_current": ("Heat pump compressor current", "Diagnostic.", "Varmepumpe kompressorstrøm", "Diagnostik."),
    "src_circulation_power": ("Circulation power", "Power on the meter phase that carries only the circulation pump.", "Cirkulation effekt", "Effekt på den målerfase, der kun bærer cirkulationspumpen."),
    "src_water_ph": ("Water pH", "The pH value the dashboards show (the corrected one).", "Vand pH", "Den pH-værdi dashboards viser (den korrigerede)."),
    "src_water_orp": ("Water ORP", "Source for the ORP value.", "Vand ORP", "Kilde til ORP-værdien."),
    "src_water_tds": ("Water TDS", "Source for TDS, if you have one.", "Vand TDS", "Kilde til TDS, hvis du har en."),
    "src_ondilo_temperature": ("Ondilo temperature", "The Ondilo's water temperature. Display only; it updates hourly and no rule uses it.", "Ondilo temperatur", "Ondiloens vandtemperatur. Kun til visning; den opdateres hver time, og ingen regel bruger den."),
    "src_ondilo_battery": ("Ondilo battery", "Source for the Ondilo's battery level.", "Ondilo batteri", "Kilde til Ondiloens batteriniveau."),
}

SECTIONS: dict[str, tuple[str, str, str, str]] = {
    SECTION_SOURCES: (
        "Data sources",
        "The values gathered on the Udespa device. Leave a field empty for no copy.",
        "Datakilder",
        "Værdierne der samles på Udespa-enheden. Lad et felt stå tomt for ingen kopi.",
    ),
    SECTION_ENTITIES: (
        "Entities",
        "The devices Udespa Control works through. It never talks to hardware directly.",
        "Entiteter",
        "Enhederne, Udespa Control arbejder igennem. Den taler aldrig direkte med hardware.",
    ),
    SECTION_NUMBERS: (
        "Numbers",
        "Timings, thresholds and presets. The defaults are today's measured values.",
        "Tal",
        "Tider, grænser og presets. Standardværdierne er de målte værdier fra i dag.",
    ),
    SECTION_TOGGLES: (
        "On/off",
        "Switch individual rules on or off.",
        "Til/fra",
        "Slå enkelte regler til eller fra.",
    ),
}

SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    SECTION_ENTITIES: ENTITY_KEYS,
    SECTION_NUMBERS: (*NUMBER_KEYS, *PRESET_KEYS),
    SECTION_TOGGLES: TOGGLE_KEYS,
    SECTION_SOURCES: SOURCE_KEYS,
}

STEPS: dict[str, tuple[str, str, str, str]] = {
    "user": (
        "Udespa Control",
        ("Pick the devices and check the numbers. Active control starts off, so the "
        "integration only watches until you switch it on."),
        "Udespa Control",
        ("Vælg enhederne og tjek tallene. Aktiv styring starter slået fra, så "
        "integrationen kun overvåger, indtil du slår den til."),
    ),
    "reconfigure": (
        "Swap devices",
        "Change the devices without losing entity IDs or stored state.",
        "Skift enheder",
        "Skift enheder uden at miste entitets-id'er eller gemt tilstand.",
    ),
    "init": (
        "Udespa Control settings",
        "Every setting on one screen. Saving reloads the integration.",
        "Udespa Control indstillinger",
        "Alle indstillinger på én skærm. Gem genindlæser integrationen.",
    ),
}

ERRORS: dict[str, tuple[str, str]] = {
    "notify_not_found": (
        "That notification service does not exist.",
        "Den notifikationstjeneste findes ikke.",
    ),
    "power_thresholds": (
        "Heat pump stopped below must be lower than heat pump running above.",
        "Varmepumpe stoppet under skal være lavere end varmepumpe kører over.",
    ),
    "unknown_preset": (
        "A preset is not one of the heat pump's presets.",
        "En preset er ikke en af varmepumpens presets.",
    ),
}

ABORTS: dict[str, tuple[str, str]] = {
    "already_configured": ("This spa is already set up.", "Denne spa er allerede sat op."),
    "reconfigure_successful": ("The devices were changed.", "Enhederne er skiftet."),
}

ENTITY_NAMES: dict[str, dict[str, tuple[str, str]]] = {
    "select": {"heat_pump_mode": ("Heat pump mode", "Varmepumpe tilstand")},
    "number": {
        "rest_temperature": ("Rest temperature", "Hviletemperatur"),
        "heat_pump_offset": ("Heat pump offset", "Varmepumpe offset"),
    },
    "button": {
        "raise_temperature": ("Raise temperature", "Hæv temperatur"),
        "lower_temperature": ("Lower temperature", "Sænk temperatur"),
        "start_cleaning": ("Start cleaning", "Start rengøring"),
        "stop_cleaning": ("Stop cleaning", "Stop rengøring"),
        "reset_filter_timer": ("Reset filter timer", "Nulstil filter timer"),
        "reset_bath_water_timer": ("Reset bath water timer", "Nulstil badevand timer"),
    },
    "switch": {
        "frost_protection": ("Frost protection", "Frostsikring"),
        "active_control": ("Active control", "Aktiv styring"),
    },
    "sensor": {
        "status": ("Status", "Status"),
        "cleaning_phase": ("Cleaning phase", "Rengøringsfase"),
        "filter_timer": ("Filter timer", "Filter timer"),
        "bath_water_timer": ("Bath water timer", "Badevand timer"),
        "heating": ("Heating", "Varmer"),
        "last_action": ("Last action", "Seneste handling"),
        "temperature_sync": ("Temperature sync", "Temperatursynk"),
        "water_temperature": ("Water temperature", "Vandtemperatur"),
        "setpoint": ("Setpoint", "Setpunkt"),
        "heat_demand": ("Heat demand", "Varmebehov"),
        "hp_inlet": ("Heat pump inlet", "Varmepumpe indløb"),
        "hp_outlet": ("Heat pump outlet", "Varmepumpe udløb"),
        "hp_temperature_rise": ("Heat pump temperature rise", "Varmepumpe temperaturstigning"),
        "hp_compressor": ("Heat pump compressor", "Varmepumpe kompressor"),
        "hp_power": ("Heat pump power", "Varmepumpe effekt"),
        "hp_ambient": ("Heat pump ambient", "Varmepumpe omgivelse"),
        "heater_power": ("Heater power", "Varmelegeme effekt"),
        "circulation_power": ("Circulation power", "Cirkulation effekt"),
        "hp_coil": ("Heat pump coil", "Varmepumpe spole"),
        "hp_exhaust": ("Heat pump exhaust", "Varmepumpe afgang"),
        "hp_ipm": ("Heat pump IPM", "Varmepumpe IPM"),
        "hp_fan": ("Heat pump fan", "Varmepumpe blæser"),
        "hp_eev": ("Heat pump EEV", "Varmepumpe EEV"),
        "hp_compressor_current": ("Heat pump compressor current", "Varmepumpe kompressorstrøm"),
        "water_ph": ("Water pH", "Vand pH"),
        "water_orp": ("Water ORP", "Vand ORP"),
        "water_tds": ("Water TDS", "Vand TDS"),
        "ondilo_temperature": ("Ondilo temperature", "Ondilo temperatur"),
        "ondilo_battery": ("Ondilo battery", "Ondilo batteri"),
    },
    "binary_sensor": {
        "heat_pump_failure": ("Heat pump failure", "Varmepumpe fejl"),
        "circulation": ("Circulation", "Cirkulation"),
    },
}


def _step(step_id: str, sections: tuple[str, ...], lang: int) -> dict:
    title = STEPS[step_id][lang * 2]
    description = STEPS[step_id][lang * 2 + 1]
    return {
        "title": title,
        "description": description,
        "sections": {
            name: {
                "name": SECTIONS[name][lang * 2],
                "description": SECTIONS[name][lang * 2 + 1],
                "data": {key: FIELDS[key][lang * 2] for key in SECTION_FIELDS[name]},
                "data_description": {
                    key: FIELDS[key][lang * 2 + 1] for key in SECTION_FIELDS[name]
                },
            }
            for name in sections
        },
    }


def build(lang: int) -> dict:
    all_sections = (SECTION_ENTITIES, SECTION_NUMBERS, SECTION_TOGGLES, SECTION_SOURCES)
    errors = {key: texts[lang] for key, texts in ERRORS.items()}
    return {
        "config": {
            "step": {
                "user": _step("user", all_sections, lang),
                "reconfigure": _step("reconfigure", (SECTION_ENTITIES,), lang),
            },
            "error": errors,
            "abort": {key: texts[lang] for key, texts in ABORTS.items()},
        },
        "options": {
            "step": {"init": _step("init", all_sections, lang)},
            "error": errors,
        },
        "entity": {
            platform: {key: {"name": names[lang]} for key, names in keys.items()}
            for platform, keys in ENTITY_NAMES.items()
        },
    }


def render() -> dict[Path, str]:
    def text(data: dict) -> str:
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    english = text(build(EN))
    return {
        INTEGRATION / "strings.json": english,
        INTEGRATION / "translations" / "en.json": english,
        INTEGRATION / "translations" / "da.json": text(build(DA)),
    }


def main(check: bool = False) -> int:
    files = render()
    stale = [p for p, c in files.items() if not p.exists() or p.read_text() != c]
    if check:
        for path in stale:
            print(f"out of date: {path.relative_to(REPO)}")
        return 1 if stale else 0
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
