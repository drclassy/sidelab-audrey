"""
AUDREY — Advanced Universal Diagnostic & Responsive Expert Yield
Sentra Artificial Intelligence × Google DeepMind
Architected by dr Ferdi Iskandar
"""

import json
import os
import re
import subprocess
import sys
import textwrap
import uuid
from datetime import datetime
from pathlib import Path

import math
from collections import defaultdict

from rich import box as rbox
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Telegram Notification (optional — safe to fail)
# ---------------------------------------------------------------------------
try:
    from audrey_notify.notification_gateway import gateway
    from audrey_notify.message_builder import format_message
except ImportError:
    class _NoOpGateway:
        def publish(self, text: str) -> None:
            pass
    gateway = _NoOpGateway()

    def format_message(text: str, pasien: dict, session_id: str) -> str:
        return text

try:
    from audrey_icd import handle_icd_command
    _ICD_AVAILABLE = True
except ImportError:
    _ICD_AVAILABLE = False

    def handle_icd_command(user_input: str, console: Console) -> None:
        console.print("  [!] audrey_icd tidak tersedia.", style="bright_red")

from audrey_llm import (
    AVAILABLE_DEEPSEEK_MODELS,
    DEFAULT_LOCAL_MODEL,
    build_provider,
    default_model_for_backend,
    render_mode_menu,
    resolve_backend_choice,
)
from audrey_llm.local_client import available_models as local_available_models

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Audio notification — fire-and-forget sound at end of each AI response
# ---------------------------------------------------------------------------
NOTIF_SOUND_PATH = BASE_DIR / "sounds" / "notif.mp3"

def _play_notification_sound() -> None:
    """Putar notif.mp3 secara async via PowerShell MediaPlayer.
    Fire-and-forget: gagal diam-diam, tidak pernah raise."""
    if not NOTIF_SOUND_PATH.exists():
        return
    if sys.platform != "win32":
        return
    try:
        uri = NOTIF_SOUND_PATH.resolve().as_uri()
        ps_cmd = (
            "Add-Type -AssemblyName PresentationCore;"
            "$p = New-Object System.Windows.Media.MediaPlayer;"
            f"$p.Open([Uri]'{uri}');"
            "$p.Play();"
            "Start-Sleep -Seconds 4"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AI_NAME       = "AUDREY"
DISPLAY_MODEL = "SENTRA-MED v1"
DEFAULT_MODEL = DEFAULT_LOCAL_MODEL
MAX_HISTORY   = 12
SEP           = "=" * 70

# Kate CLI palette — exact match
C_BORDER = "#003366"   # Oxford Blue  (border, frame)
C_NAME   = "#DC5014"   # Burnt Orange (title/name)
C_LABEL  = "#8C8C96"   # Grey-Blue    (labels)
C_VALUE  = "#E6E6EB"   # Near White   (values)
C_DIM    = "#50505A"   # Dark Grey    (secondary/dim)
C_PANEL  = "#0B1724"   # Deep ink blue
C_PANEL_ALT = "#102235"
C_INFO   = "#86B8D8"
C_SUCCESS = "#6D9D83"
C_WARN   = "#C7A35A"
C_ALERT  = "#C45A4E"
C_META   = "#B8C7D1"

# Palet section — medical journal aesthetic, kalem, hierarki klinis jelas
SECTION_STYLES = {
    "ANAMNESIS"           : C_INFO,      # soft blue
    "PEMERIKSAAN FISIK"   : C_INFO,      # soft blue
    "ANJURAN PEMERIKSAAN" : "#94B5C0",   # muted teal
    "DIAGNOSIS BANDING"   : "#B8860B",   # dark amber — diferensial
    "DIAGNOSIS KERJA"     : C_NAME,      # burnt orange — keputusan utama
    "TATALAKSANA"         : C_INFO,      # soft blue
    "FARMAKOLOGI"         : C_INFO,      # soft blue — sama bobot dengan tatalaksana
    "EDUKASI PASIEN"      : "#D4AF37",   # gold highlight — edukasi adalah pilar compliance
    "KRITERIA RUJUK"      : C_ALERT,     # muted red — peringatan, tidak garish
    "PROGNOSIS"           : C_LABEL,     # grey — outcome, bukan aksi
}

ITEM_STYLES = {}  # semua item plain white — hanya header section yang berwarna

# Warna judul AUDREY — monokromatik klinis (Oxford blue tegas)
_TITLE_COLOR = "#003366"

_BADGE_TONES = {
    "info": ("#0E1D2D", C_INFO),
    "success": ("#14261B", C_SUCCESS),
    "warn": ("#2A2114", C_WARN),
    "alert": ("#301817", C_ALERT),
    "muted": ("#182432", C_LABEL),
}

# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------
console = Console(highlight=False)


def _backend_label(backend: str) -> str:
    return "DeepSeek" if backend == "deepseek" else "Local"


def _print_backend_menu() -> str:
    console.print()
    console.print(Panel(
        render_mode_menu(),
        box=rbox.ROUNDED,
        border_style=C_INFO,
        padding=(1, 2),
        title=_panel_title("BACKEND INFERENCE"),
        style=f"on {C_PANEL}",
    ))
    choice = console.input("  Pilih mode [Enter=DeepSeek] > ").strip()
    backend = resolve_backend_choice(choice)
    console.print(f"  Mode aktif: {_backend_label(backend)}", style="dim grey50")
    console.print()
    return backend


def _get_backend_models(backend: str) -> list[str]:
    if backend == "local":
        models = local_available_models()
        return models or [DEFAULT_LOCAL_MODEL]
    return list(AVAILABLE_DEEPSEEK_MODELS)

# ---------------------------------------------------------------------------
# Markdown stripper
# ---------------------------------------------------------------------------
_MD_HEADING  = re.compile(r'^#{1,6}\s+(.+)$', re.MULTILINE)
_MD_BOLD     = re.compile(r'\*{1,3}(.+?)\*{1,3}')
_MD_CODE     = re.compile(r'`{1,3}(.+?)`{1,3}', re.DOTALL)
_MD_BULLET   = re.compile(r'^\s*[-*+]\s+', re.MULTILINE)
_MD_BLOCKQ   = re.compile(r'^\s*>\s+', re.MULTILINE)
_MD_HR       = re.compile(r'^[-*_]{3,}\s*$', re.MULTILINE)

def _strip_markdown(text: str) -> str:
    text = _MD_HEADING.sub(lambda m: m.group(1).upper() + ":", text)
    text = _MD_BOLD.sub(r'\1', text)
    text = _MD_CODE.sub(r'\1', text)
    text = _MD_BULLET.sub("  ", text)
    text = _MD_BLOCKQ.sub("  ", text)
    text = _MD_HR.sub("", text)
    return text

# ---------------------------------------------------------------------------
# Red flag detector
# ---------------------------------------------------------------------------
RED_FLAGS = [
    {
        "trigger"  : ["kaku leher", "neck stiff", "meningismus", "kaku kuduk"],
        "context"  : ["demam", "panas", "nyeri kepala", "sakit kepala", "muntah", "fotofobia"],
        "alert"    : "[!] RED FLAG: Kaku leher + demam/nyeri kepala — CURIGA MENINGITIS BAKTERIAL (emergensi). Periksa tanda Kernig & Brudzinski. Pertimbangkan rujukan segera.",
        "disease"  : "Meningitis Bakterial (G00)",
    },
    {
        "trigger"  : ["nyeri kepala mendadak", "nyeri kepala tiba-tiba", "thunderclap", "nyeri kepala terburuk", "kepala mau pecah"],
        "context"  : [],
        "alert"    : "[!] RED FLAG: Nyeri kepala onset mendadak/thunderclap — singkirkan SUBARACHNOID HEMORRHAGE (SAH). Rujukan emergensi ke RS.",
        "disease"  : "Subarachnoid Hemorrhage (I60)",
    },
    {
        "trigger"  : ["lumpuh", "paralisis", "hemiplegia", "tidak bisa bicara", "pelo", "afasia", "wajah perot", "mulut mencong", "lemah separuh tubuh"],
        "context"  : [],
        "alert"    : "[!] RED FLAG: Defisit neurologis fokal — CURIGA STROKE. Protokol FAST. Rujukan emergensi.",
        "disease"  : "Stroke (I64)",
    },
    {
        "trigger"  : ["nyeri dada"],
        "context"  : ["keringat dingin", "menjalar ke lengan", "menjalar ke rahang", "sesak", "mual", "pingsan"],
        "alert"    : "[!] RED FLAG: Nyeri dada + gejala penyerta — singkirkan ACS/STEMI. EKG segera.",
        "disease"  : "Acute Coronary Syndrome (I21)",
    },
    {
        "trigger"  : ["sesak napas berat", "sesak nafas berat", "tidak bisa bicara", "sianosis", "saturasi turun", "spo2 turun"],
        "context"  : [],
        "alert"    : "[!] RED FLAG: Distress respirasi — stabilisasi jalan napas segera. Pertimbangkan rujukan.",
        "disease"  : "Distress Respirasi",
    },
    {
        "trigger"  : ["kejang", "kejang-kejang"],
        "context"  : ["demam", "panas", "tidak sadar", "lumpuh setelah kejang"],
        "alert"    : "[!] RED FLAG: Kejang + demam/tidak sadar — pertimbangkan Ensefalitis atau status epileptikus.",
        "disease"  : "Ensefalitis (G04)",
    },
    # === TRAUMA ===
    {
        "trigger"  : ["kecelakaan", "tabrakan", "jatuh dari", "terjatuh", "terbentur",
                      "kepala terbentur", "kepala terkena", "trauma kepala", "head injury",
                      "kepala membentur", "kena aspal", "terlempar"],
        "context"  : [],
        "alert"    : "[!] RED FLAG: Trauma kepala — protokol ATLS. Cek GCS, pupil, defisit fokal. Curigai cedera otak (TBI). Pertimbangkan CT kepala dan rujukan emergensi.",
        "disease"  : "Cedera Otak Traumatik / Trauma Kapitis (S06)",
    },
    {
        "trigger"  : [
            # Otorrhea (darah/cairan dari telinga)
            "perdarahan telinga", "perdarahan di telinga", "darah dari telinga",
            "darah di telinga", "darah keluar dari telinga", "berdarah dari telinga",
            "telinga berdarah", "otorrhea", "otorea",
            # Rhinorrhea pasca trauma
            "rinorrhea cair", "cairan jernih dari hidung",
            # Frasa kombinasi telinga+hidung
            "telinga dan hidung", "hidung dan telinga",
            "perdarahan hidung dan telinga", "perdarahan di telinga dan hidung",
            "darah di hidung dan telinga", "darah dari telinga dan hidung",
            # Tanda klinis fraktur basis kranii
            "hemotimpanum", "battle sign", "raccoon eye", "raccoon eyes",
            "panda eye", "memar belakang telinga",
        ],
        "context"  : [],
        "alert"    : "[!] RED FLAG: Otorrhea/rhinorrhea pasca trauma — TANDA FRAKTUR BASIS KRANII. Emergensi mutlak. JANGAN tampon, JANGAN suction nasal. Posisi kepala 30°, NPO, profilaksis antibiotik, rujuk RS dengan CT scan dan bedah saraf.",
        "disease"  : "Fraktur Basis Kranii (S02.1)",
    },
    {
        "trigger"  : ["tidak sadar", "tidak sadarkan diri", "pingsan", "penurunan kesadaran",
                      "tidak respon", "koma", "gcs turun"],
        "context"  : ["kecelakaan", "tabrakan", "jatuh", "kepala", "trauma", "terbentur",
                      "perdarahan", "muntah proyektil", "kejang"],
        "alert"    : "[!] RED FLAG: Penurunan kesadaran + trauma/perdarahan — emergensi neurologis. Cek GCS, AVPU, jalan napas. Pertimbangkan TBI, stroke hemoragik, herniasi.",
        "disease"  : "Penurunan Kesadaran et causa suspek lesi intrakranial",
    },
    {
        "trigger"  : ["luka tembak", "luka tusuk", "perdarahan masif", "syok hipovolemik",
                      "fraktur terbuka", "amputasi"],
        "context"  : [],
        "alert"    : "[!] RED FLAG: Trauma berat — primary survey ABCDE, kontrol perdarahan, akses IV besar (2 jalur), resusitasi cairan. Rujuk RS dengan kemampuan trauma surgery.",
        "disease"  : "Trauma Mayor (T07)",
    },
]

def _detect_red_flags(query: str) -> list[str]:
    q = query.lower()
    alerts = []
    for rf in RED_FLAGS:
        trigger_hit = any(t in q for t in rf["trigger"])
        if not trigger_hit:
            continue
        if rf["context"]:
            context_hit = any(c in q for c in rf["context"])
            if not context_hit:
                continue
        alerts.append(rf["alert"])
    return alerts

def _red_flag_disease_context(query: str) -> str:
    q = query.lower()
    extra = []
    for rf in RED_FLAGS:
        trigger_hit = any(t in q for t in rf["trigger"])
        if not trigger_hit:
            continue
        if rf["context"] and not any(c in q for c in rf["context"]):
            continue
        extra.append(rf["disease"])
    if not extra:
        return ""
    return "\n=== DIAGNOSA RED FLAG — WAJIB DIPERTIMBANGKAN ===\n" + "\n".join(f"  {d}" for d in extra)

# ---------------------------------------------------------------------------
# Database loader
# ---------------------------------------------------------------------------
def _load_db() -> dict:
    db = {"diseases_full": [], "diseases_144": [], "obat": [], "stok": [],
          "chains": {}, "drug_map": []}
    try:
        with open(DATA_DIR / "penyakit.json", encoding="utf-8") as f:
            db["diseases_full"] = json.load(f).get("penyakit", [])
    except Exception:
        pass
    try:
        with open(DATA_DIR / "144_penyakit_puskesmas.json", encoding="utf-8") as f:
            db["diseases_144"] = json.load(f).get("diseases", [])
    except Exception:
        pass
    try:
        with open(DATA_DIR / "obat_data.json", encoding="utf-8") as f:
            db["obat"] = json.load(f)
    except Exception:
        pass
    try:
        with open(DATA_DIR / "stok_obat.json", encoding="utf-8") as f:
            db["stok"] = json.load(f).get("stok_obat", [])
    except Exception:
        pass
    try:
        with open(DATA_DIR / "clinical-chains.json", encoding="utf-8") as f:
            db["chains"] = json.load(f)
    except Exception:
        pass
    try:
        with open(DATA_DIR / "drug_mapping.json", encoding="utf-8") as f:
            db["drug_map"] = json.load(f).get("mappings", [])
    except Exception:
        pass
    return db

DB = _load_db()

# Index 144 diseases by id for quick pharma lookup
_D144_INDEX = {d["id"]: d for d in DB["diseases_144"] if "id" in d}


def _load_ranked_library() -> dict:
    try:
        with open(DATA_DIR / "top100_puskesmas_diseases.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"source": {}, "items": []}


RANKED_LIBRARY = _load_ranked_library()


def _load_library_supplemental() -> dict:
    try:
        with open(DATA_DIR / "library_supplemental_entries.json", encoding="utf-8") as f:
            return json.load(f).get("entries", {})
    except Exception:
        return {}


LIBRARY_SUPPLEMENTAL = _load_library_supplemental()


def _normalize_library_key(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("’", "'").replace("nafas", "napas")
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_FULL_BY_NAME = {
    _normalize_library_key(d.get("nama", "")): d
    for d in DB["diseases_full"]
    if d.get("nama")
}
_D144_BY_NAME = {
    _normalize_library_key(d.get("name", "")): d
    for d in DB["diseases_144"]
    if d.get("name")
}

_LIBRARY_DETAIL_OVERRIDES = {
    "rinitis akut": {
        "full_name": "Nasofaringitis Akut (Common Cold)",
    },
    "fraktur terbuka": {
        "d144_name": "Fraktur Terbuka Grade 1",
    },
    "fraktur tertutup": {
        "notes": ["Fraktur tertutup sangat sering membutuhkan X-ray dan penilaian ortopedi."],
    },
    "gangguan psikotik": {
        "full_name": "Skizofrenia",
    },
    "vertigo": {
        "full_name": "Vertigo (Benign paroxysmal positional vertigo)",
    },
    "demam dengue": {
        "d144_icd10": "A90",
    },
    "vulnus": {
        "full_name": "Vulnus laseratum, punctum",
    },
    "pioderma": {
        "full_name": "Abses folikel rambut atau kelenjar sebasea",
    },
    "gangguan anxietas": {
        "d144_name": "Gangguan Campuran Anxietas dan Depresi",
    },
    "tinea corporis": {
        "full_name": "Tinea korporis",
        "d144_name": "Dermatofitosis (Tinea Korporis/Kruris/Pedis)",
    },
    "tinea pedis": {
        "full_name": "Tinea pedis",
        "d144_name": "Dermatofitosis (Tinea Korporis/Kruris/Pedis)",
    },
    "tinea ungium": {
        "full_name": "Tinea unguium",
    },
    "bronkopneumonia": {
        "full_name": "Pneumonia, bronkopneumonia",
        "d144_name": "Pneumonia",
    },
    "tumor payudara": {
        "full_name": "Karsinoma Mammae (Kanker Payudara)",
    },
    "sinusitis akut": {
        "d144_name": "Sinusitis Akut",
    },
    "hiperurisemia gout arthritis": {
        "full_name": "Hiperurisemia",
    },
    "hiperurisemia gout athritis": {
        "full_name": "Hiperurisemia",
    },
    "benda asing di telinga": {
        "full_name": "Benda asing",
    },
    "rinitis vasomotor": {
        "primary_icd10": "J30.0",
    },
    "konjungtivitis infeksi": {
        "primary_icd10": "H10.9",
    },
    "pitiriasis versikolor": {
        "primary_icd10": "B36.0",
    },
    "refluks gastroesofageal": {
        "primary_icd10": "K21.9",
    },
    "otitis media akut": {
        "primary_icd10": "H65",
    },
    "angina pektoris stabil": {
        "primary_icd10": "I20.9",
    },
    "gagal jantung akut dan kronik": {
        "primary_icd10": "I50.9",
    },
    "low vision": {
        "primary_icd10": "H54",
    },
    "kejang demam": {
        "d144_icd10": "R56.0",
    },
    "kanker serviks": {
        "primary_icd10": "C53.9",
    },
    "mata kering": {
        "primary_icd10": "H04.1",
    },
    "stroke": {
        "primary_icd10": "I63.9",
    },
    "demam berdarah dengue": {
        "primary_icd10": "A91",
    },
    "gangguan campuran anxietas dan depresi": {
        "d144_name": "Gangguan Campuran Anxietas dan Depresi",
    },
    "varisela": {
        "full_name": "Varisela tanpa komplikasi",
        "d144_name": "Varisela (Cacar Air) tanpa Komplikasi",
    },
    "konjungtivitis alergi": {
        "full_name": "Konjungtivitis",
        "d144_name": "Konjungtivitis",
    },
    "konjungtivitis infeksi": {
        "full_name": "Konjungtivitis",
        "d144_name": "Konjungtivitis",
    },
    "tirotoksikosis": {
        "primary_icd10": "E05.9",
    },
    "fimosis": {
        "primary_icd10": "N47",
    },
    "hipoglikemia": {
        "primary_icd10": "E16.2",
    },
    "pielonefritis tanpa komplikasi": {
        "primary_icd10": "N10",
    },
    "perdarahan gastrointestinal": {
        "primary_icd10": "K92.9",
    },
    "konjungtivitis alergi": {
        "primary_icd10": "H10.1",
    },
    "retinopati diabetik": {
        "primary_icd10": "H36.0",
    },
    "otitis media supuratif kronik": {
        "notes": ["Database lokal belum memiliki entri OMSK yang eksplisit. Detail pustaka memakai data terdekat bila tersedia dan tetap perlu verifikasi klinis."],
    },
    "dermatitis kontak alergi": {
        "notes": ["Database lokal belum memiliki entri dermatitis kontak alergi yang berdiri sendiri. Gunakan ranking ini sebagai penanda prioritas kurasi berikutnya."],
    },
    "penyakit paru obstruktif kronis": {
        "notes": ["Database lokal belum memiliki entri PPOK yang berdiri sendiri di pustaka inti. Gunakan data ranking ini sebagai penanda prioritas kurasi berikutnya."],
    },
    "hipertrofi prostat": {
        "notes": ["Belum ada entri BPH atau hipertrofi prostat yang eksplisit di knowledge base lokal saat ini."],
    },
    "gangguan perkembangan dan perilaku pada anak dan remaja": {
        "notes": ["Entri ini masih bersifat programatik dan mewakili spektrum perkembangan atau perilaku anak. Perlu kurasi lanjutan bila ingin dijadikan pustaka klinis rinci."],
    },
    "pterygium": {
        "notes": ["Belum ada entri pterygium yang eksplisit di knowledge base lokal saat ini."],
    },
    "low vision": {
        "notes": ["Belum ada entri low vision yang eksplisit di knowledge base lokal saat ini."],
    },
    "tirotoksikosis": {
        "notes": ["Belum ada entri tirotoksikosis yang eksplisit di knowledge base lokal saat ini."],
        "primary_icd10": "E05.9",
    },
    "kanker serviks": {
        "notes": ["Belum ada entri kanker serviks yang eksplisit di knowledge base lokal saat ini."],
        "primary_icd10": "C53.9",
    },
    "katarak pada pasien dewasa": {
        "notes": ["Belum ada entri katarak dewasa yang eksplisit di knowledge base lokal saat ini."],
    },
    "liken simpleks kronik neurodermatitis sirkumripta": {
        "notes": ["Belum ada entri lichen simplex chronicus yang eksplisit di knowledge base lokal saat ini."],
    },
    "thalasemia": {
        "notes": ["Belum ada entri thalasemia yang eksplisit di knowledge base lokal saat ini."],
    },
    "kanker paru": {
        "notes": ["Belum ada entri kanker paru yang eksplisit di knowledge base lokal saat ini."],
    },
    "hepatitis b": {
        "notes": ["Belum ada entri hepatitis B yang eksplisit di knowledge base lokal saat ini."],
    },
    "hifema": {
        "notes": ["Belum ada entri hifema yang eksplisit di knowledge base lokal saat ini."],
    },
    "retinopati diabetik": {
        "notes": ["Belum ada entri retinopati diabetik yang eksplisit di knowledge base lokal saat ini."],
        "primary_icd10": "H36.0",
    },
}


def _find_full_by_icd(icd10: str) -> dict | None:
    icd = (icd10 or "").upper().strip()
    if not icd:
        return None
    prefix = icd.split(".")[0][:3]
    for d in DB["diseases_full"]:
        code = d.get("icd10", "").upper()
        code_prefix = code.split(".")[0][:3]
        if (
            code == icd
            or code.startswith(icd + ".")
            or icd.startswith(code + ".")
            or (prefix and code_prefix == prefix)
        ):
            return d
    return None


def _find_144_by_icd(icd10: str) -> dict | None:
    icd = (icd10 or "").upper().strip()
    if not icd:
        return None
    prefix = icd.split(".")[0][:3]
    for d in DB["diseases_144"]:
        code = d.get("icd10", "").upper()
        code_prefix = code.split(".")[0][:3]
        if (
            code == icd
            or code.startswith(icd + ".")
            or icd.startswith(code + ".")
            or (prefix and code_prefix == prefix)
        ):
            return d
    return None


def _resolve_library_entry(entry: dict) -> dict:
    key = _normalize_library_key(entry.get("normalized_name") or entry.get("source_name", ""))
    override = _LIBRARY_DETAIL_OVERRIDES.get(key, {})
    primary_icd10 = override.get("primary_icd10", entry.get("primary_icd10", ""))
    supplemental = LIBRARY_SUPPLEMENTAL.get(key, {})

    full = None
    d144 = None
    full_source = "missing"
    d144_source = "missing"

    full_name = override.get("full_name")
    if full_name:
        full = _FULL_BY_NAME.get(_normalize_library_key(full_name))
        if full:
            full_source = "core"
    if not full:
        full = _FULL_BY_NAME.get(_normalize_library_key(entry.get("normalized_name", "")))
        if full:
            full_source = "core"
    if not full:
        full = _FULL_BY_NAME.get(_normalize_library_key(entry.get("source_name", "")))
        if full:
            full_source = "core"
    if not full:
        full = _find_full_by_icd(primary_icd10)
        if full:
            full_source = "core"
    if not full and supplemental.get("full"):
        full = supplemental.get("full")
        full_source = "supplemental"

    d144_name = override.get("d144_name")
    if d144_name:
        d144 = _D144_BY_NAME.get(_normalize_library_key(d144_name))
        if d144:
            d144_source = "core"
    d144_icd10 = override.get("d144_icd10")
    if not d144 and d144_icd10:
        d144 = _find_144_by_icd(d144_icd10)
        if d144:
            d144_source = "core"
    if not d144:
        d144 = _D144_BY_NAME.get(_normalize_library_key(entry.get("normalized_name", "")))
        if d144:
            d144_source = "core"
    if not d144:
        d144 = _D144_BY_NAME.get(_normalize_library_key(entry.get("source_name", "")))
        if d144:
            d144_source = "core"
    if not d144:
        d144 = _find_144_by_icd(primary_icd10)
        if d144:
            d144_source = "core"
    if not d144 and supplemental.get("d144"):
        d144 = supplemental.get("d144")
        d144_source = "supplemental"

    return {
        "entry": entry,
        "full": full,
        "d144": d144,
        "notes": override.get("notes", []),
        "full_source": full_source,
        "d144_source": d144_source,
    }


def _library_lines(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, str):
                clean = item.strip()
                if clean:
                    lines.append(clean)
            elif isinstance(item, dict):
                compact = ", ".join(
                    f"{k}: {v}" for k, v in item.items()
                    if isinstance(v, str) and v.strip()
                )
                if compact:
                    lines.append(compact)
        return lines
    return []


def _library_pharma_lines(d144: dict | None) -> list[str]:
    if not d144:
        return []
    pharmacotherapy = d144.get("pharmacotherapy", {})
    lines: list[str] = []
    for key, label in [
        ("first_line", "Lini 1"),
        ("second_line", "Lini 2"),
        ("prophylaxis", "Profilaksis"),
    ]:
        for item in pharmacotherapy.get(key, [])[:4]:
            if not isinstance(item, dict):
                continue
            parts = [
                item.get("drug", ""),
                item.get("dose", ""),
                item.get("route", ""),
                item.get("frequency", ""),
                item.get("duration", ""),
            ]
            line = " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
            if line:
                lines.append(f"{label}: {line}")
    return lines


def _library_source_marker(resolved: dict) -> str:
    full_source = resolved["full_source"]
    d144_source = resolved["d144_source"]
    if full_source == "core" and d144_source == "core":
        return "[C]"
    if full_source == "supplemental" or d144_source == "supplemental":
        return "[S]"
    return "[M]"


def _library_system_bucket(entry: dict, resolved: dict) -> str:
    full = resolved["full"] or {}
    d144 = resolved["d144"] or {}
    key = _normalize_library_key(entry.get("normalized_name") or entry.get("source_name", ""))
    body = " ".join([
        str(full.get("body_system", "")),
        str(d144.get("system", "")),
        " ".join(str(tag) for tag in d144.get("tags", [])),
    ]).lower()

    if (
        "indera" in body or "mata" in body or key in {
            "low vision", "mata kering", "katarak pada pasien dewasa",
            "retinopati diabetik", "konjungtivitis alergi", "konjungtivitis infeksi",
            "hifema", "pterygium", "blefaritis", "hordeolum"
        }
    ):
        return "mata"
    if (
        "saraf" in body or "neurolog" in body or key in {
            "vertigo", "tension headache", "stroke", "bell palsy", "kejang demam"
        }
    ):
        return "saraf"
    if (
        "respirasi" in body or "paru" in body or key in {
            "penyakit paru obstruktif kronis", "bronkopneumonia", "kanker paru",
            "asma bronkial", "influenza", "faringitis akut", "sinusitis akut",
            "rinitis akut", "rinitis alergi", "rinitis vasomotor"
        }
    ):
        return "respirasi"
    if (
        "kardiovaskular" in body or "jantung" in body or key in {
            "hipertensi esensial", "infark miokard", "angina pektoris stabil",
            "gagal jantung akut dan kronik"
        }
    ):
        return "kardiovaskular"
    if (
        "digestif" in body or "pencernaan" in body or "digest" in body or key in {
            "gastritis", "gastroenteritis kolera dan giardiasis", "ulkus mulut",
            "demam tifoid", "refluks gastroesofageal", "perdarahan gastrointestinal"
        }
    ):
        return "digestif"
    if (
        "endokrin" in body or "metabol" in body or "nutrisi" in body or key in {
            "diabetes mellitus tipe 2", "diabetes mellitus tipe 1", "lipidemia",
            "hiperurisemia gout arthritis", "hiperurisemia gout athritis", "hipoglikemia",
            "tirotoksikosis", "malnutrisi energi protein"
        }
    ):
        return "endokrin"
    if (
        "integumen" in body or "kulit" in body or key in {
            "dermatitis atopik", "dermatitis kontak alergi", "dermatitis kontak iritan",
            "liken simpleks kronik neurodermatitis sirkumripta", "tinea corporis",
            "tinea pedis", "tinea ungium", "pitiriasis versikolor", "urtikaria",
            "pioderma", "impetigo", "luka bakar derajat i dan ii", "skabies",
            "milaria", "dermatitis popok", "dermatitis seboroik"
        }
    ):
        return "kulit"
    if (
        "reproduksi" in body or "obstetri" in body or "ginek" in body or key in {
            "mastitis", "kanker serviks", "tumor payudara", "anemia defisiensi besi pada kehamilan"
        }
    ):
        return "obgyn"
    if (
        "tht" in body or key in {
            "serumen prop", "otitis media supuratif kronik", "otitis eksterna",
            "otitis media akut", "epistaksis", "benda asing di telinga"
        }
    ):
        return "tht"
    if (
        "ginjal" in body or "urolog" in body or key in {
            "infeksi saluran kemih", "hipertrofi prostat", "fimosis", "pielonefritis tanpa komplikasi"
        }
    ):
        return "urologi"
    return "umum"


def _library_search_terms(entry: dict, resolved: dict) -> set[str]:
    full = resolved["full"] or {}
    d144 = resolved["d144"] or {}
    terms = {
        _normalize_library_key(entry.get("source_name", "")),
        _normalize_library_key(entry.get("normalized_name", "")),
        _normalize_library_key(entry.get("primary_icd10", "")),
        _normalize_library_key(entry.get("source_icd10", "")),
        _normalize_library_key(full.get("nama", "")),
        _normalize_library_key(d144.get("name", "")),
        _library_system_bucket(entry, resolved),
    }
    for tag in d144.get("tags", []):
        terms.add(_normalize_library_key(str(tag)))
    body_system = full.get("body_system")
    if body_system:
        terms.add(_normalize_library_key(str(body_system)))
    return {term for term in terms if term}


def _search_library_items(items: list[dict], query: str) -> list[dict]:
    q = _normalize_library_key(query)
    if not q:
        return items
    scored: list[tuple[int, int, dict]] = []
    q_tokens = q.split()
    for item in items:
        resolved = _resolve_library_entry(item)
        terms = _library_search_terms(item, resolved)
        score = 0
        for term in terms:
            if term == q:
                score = max(score, 120)
            elif q in term:
                score = max(score, 90)
            elif term in q:
                score = max(score, 75)
            else:
                overlap = sum(1 for token in q_tokens if token in term)
                if overlap:
                    score = max(score, overlap * 20)
        if score:
            scored.append((score, -item.get("total_cases", 0), item))
    scored.sort(key=lambda x: (-x[0], x[1], x[2].get("rank", 999)))
    return [item for _, _, item in scored]


def _filter_library_items(items: list[dict], system_filter: str | None) -> list[dict]:
    if not system_filter or system_filter == "all":
        return items
    filtered: list[dict] = []
    for item in items:
        resolved = _resolve_library_entry(item)
        if _library_system_bucket(item, resolved) == system_filter:
            filtered.append(item)
    return filtered


_LIBRARY_FILTER_OPTIONS = (
    "mata",
    "saraf",
    "respirasi",
    "kardiovaskular",
    "digestif",
    "endokrin",
    "kulit",
    "obgyn",
    "tht",
    "urologi",
    "all",
)


def _print_library_list(
    items: list[dict],
    title: str,
    page: int = 1,
    page_size: int = 50,
    system_filter: str | None = None,
    search_query: str | None = None,
) -> None:
    source = RANKED_LIBRARY.get("source", {})
    total_items = len(items)
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * page_size
    visible_items = items[start_idx:start_idx + page_size]

    console.print()
    console.print(Panel(
        Text(title, style="bold #7CB9E8"),
        box=rbox.ROUNDED,
        border_style="#274C77",
        padding=(0, 1),
        expand=True,
        style=f"on {C_PANEL}",
    ))
    if source:
        summary = Table.grid(expand=True)
        summary.add_column(ratio=1)
        summary.add_row(_kv_line([
            ("Sumber", str(source.get("sheet", "-"))),
            ("Periode", f"{source.get('period_from', '-')} s/d {source.get('period_to', '-')}")
        ]))
        summary.add_row(_kv_line([
            ("Halaman", f"{page}/{total_pages}"),
            ("Ranking", f"{start_idx + 1}-{start_idx + len(visible_items)} dari {total_items}")
        ]))
        if system_filter and system_filter != "all":
            summary.add_row(_kv_line([("Filter sistem", system_filter)]))
        if search_query:
            summary.add_row(_kv_line([("Pencarian", search_query)]))
        console.print(Panel(summary, box=rbox.ROUNDED, border_style=C_DIM, padding=(0, 1), style=f"on {C_PANEL_ALT}"))
        console.print()

    list_table = Table(
        box=rbox.SIMPLE_HEAVY,
        border_style=C_DIM,
        expand=True,
        show_header=True,
        header_style=f"bold {C_META}",
        pad_edge=False,
    )
    list_table.add_column("#", width=4, justify="right")
    list_table.add_column("Sumber", width=8, justify="center")
    list_table.add_column("Penyakit", ratio=5)
    list_table.add_column("ICD", width=8)
    list_table.add_column("Kasus", width=8, justify="right")
    list_table.add_column("Sistem", ratio=2)

    for item in visible_items:
        name = item.get("normalized_name") or item.get("source_name", "-")
        code = item.get("primary_icd10", "-")
        total = item.get("total_cases", 0)
        resolved = _resolve_library_entry(item)
        marker = _library_source_marker(resolved)
        system_bucket = _library_system_bucket(item, resolved)
        list_table.add_row(
            str(item.get("rank", 0)),
            marker,
            f"[{C_VALUE}]{name}[/]",
            f"[{C_META}]{code}[/]",
            f"[{C_VALUE}]{total}[/]",
            f"[{C_INFO}]{system_bucket}[/]",
        )
    console.print(Panel(list_table, box=rbox.ROUNDED, border_style=C_DIM, padding=(0, 1), style=f"on {C_PANEL}"))
    console.print()
    helper = Table.grid(expand=True)
    helper.add_column(ratio=1)
    helper.add_row(Text("Navigasi: nomor untuk buka | n halaman berikutnya | p halaman sebelumnya | Enter kembali", style="dim grey70"))
    helper.add_row(Text(f"Filter cepat: {' | '.join(_LIBRARY_FILTER_OPTIONS)}", style="dim grey70"))
    helper.add_row(Text("Pencarian cerdas: nama, ICD, tag, atau sistem klinis", style="dim grey70"))
    helper.add_row(Text("Marker sumber: [C]=core, [S]=supplemental terlibat, [M]=metadata only", style="dim grey70"))
    console.print(Panel(helper, box=rbox.ROUNDED, border_style=C_DIM, padding=(0, 1), style=f"on {C_PANEL_ALT}"))
    console.print()


def _print_library_detail(entry: dict) -> None:
    resolved = _resolve_library_entry(entry)
    full = resolved["full"]
    d144 = resolved["d144"]
    notes = resolved["notes"]
    full_source = resolved["full_source"]
    d144_source = resolved["d144_source"]

    title_name = entry.get("normalized_name") or entry.get("source_name", "Unknown")
    icd10 = entry.get("primary_icd10", "-")
    total = entry.get("total_cases", 0)
    system_bucket = _library_system_bucket(entry, resolved)
    if full_source == "core" and d144_source == "core":
        source_visual = "core/core"
    elif full_source == "supplemental" and d144_source == "supplemental":
        source_visual = "supplemental/supplemental"
    elif full_source == "missing" and d144_source == "missing":
        source_visual = "missing"
    else:
        source_visual = f"{full_source}/{d144_source}"

    sections: list[tuple[str, list[str]]] = [
        ("IDENTITAS PUSTAKA", [
            f"Ranking kasus: #{entry.get('rank', '-')}",
            f"Nama sumber: {entry.get('source_name', '-')}",
            f"Nama normalisasi: {title_name}",
            f"ICD-10 utama: {icd10}",
            f"Total kasus: {total}",
            f"Sistem klinis: {system_bucket}",
            f"Sumber detail: {source_visual}",
        ]),
    ]

    definisi_lines = _library_lines(full.get("definisi") if full else None)
    if definisi_lines:
        sections.append(("DEFINISI", definisi_lines[:2]))

    gejala_lines = _library_lines(full.get("gejala_klinis") if full else None)
    if gejala_lines:
        sections.append(("GAMBARAN KLINIS", gejala_lines[:8]))

    fisik_lines = _library_lines(full.get("pemeriksaan_fisik") if full else None)
    if fisik_lines:
        sections.append(("PEMERIKSAAN FISIK", fisik_lines[:6]))

    red_flag_lines = _library_lines(full.get("red_flags") if full else None)
    if red_flag_lines:
        sections.append(("RED FLAGS", red_flag_lines[:6]))

    non_pharma_lines = _library_lines(d144.get("non_pharmacotherapy") if d144 else None)
    if non_pharma_lines:
        sections.append(("TATALAKSANA NON-FARMAKOLOGI", non_pharma_lines[:6]))

    pharma_lines = _library_pharma_lines(d144)
    if pharma_lines:
        sections.append(("FARMAKOTERAPI", pharma_lines[:8]))

    referral_lines = []
    referral_lines.extend(_library_lines(full.get("kriteria_rujukan") if full else None))
    referral_lines.extend(_library_lines(d144.get("referral_criteria") if d144 else None))
    if referral_lines:
        deduped: list[str] = []
        seen: set[str] = set()
        for line in referral_lines:
            norm = _normalize_library_key(line)
            if norm and norm not in seen:
                seen.add(norm)
                deduped.append(line)
        sections.append(("KRITERIA RUJUK", deduped[:8]))

    if d144 and d144.get("tags"):
        sections.append(("TAGS", [", ".join(d144.get("tags", []))]))

    if notes:
        sections.append(("CATATAN KURASI", notes))

    if not full and not d144:
        sections.append((
            "STATUS DATA",
            ["Detail klinis lengkap belum ditemukan di database lokal AUDREY. Entri ini masih tampil karena termasuk top 50 beban kasus."],
        ))

    _print_template(
        f"LIBRARY 100 — {title_name.upper()} [{icd10}]",
        "#7CB9E8",
        sections,
    )


def _open_library(page: int = 1, page_size: int = 50, title: str = "PUSTAKA 100 PENYAKIT PRIORITAS PUSKESMAS") -> None:
    base_items = RANKED_LIBRARY.get("items", [])
    if not base_items:
        console.print("  Pustaka ranked diseases belum tersedia.", style="bright_red")
        console.print()
        return

    current_page = page
    current_filter = "all"
    current_query = ""
    while True:
        filtered_items = _filter_library_items(base_items, current_filter)
        if current_query:
            filtered_items = _search_library_items(filtered_items, current_query)
        _print_library_list(
            filtered_items,
            title=title,
            page=current_page,
            page_size=page_size,
            system_filter=current_filter,
            search_query=current_query,
        )
        choice = console.input("  Pilih nomor / cari nama (Enter untuk kembali): ").strip()
        if not choice:
            console.print()
            return

        if choice.lower() == "n":
            max_page = max((len(filtered_items) + page_size - 1) // page_size, 1)
            current_page = min(current_page + 1, max_page)
            console.print()
            continue
        if choice.lower() == "p":
            current_page = max(current_page - 1, 1)
            console.print()
            continue
        lowered_choice = choice.lower()
        if lowered_choice in _LIBRARY_FILTER_OPTIONS:
            current_filter = lowered_choice
            current_query = ""
            current_page = 1
            console.print()
            continue

        selected = None
        if choice.isdigit():
            idx = int(choice)
            selected = next((item for item in filtered_items if item.get("rank") == idx), None)
        else:
            current_query = choice
            current_page = 1
            matches = _search_library_items(_filter_library_items(base_items, current_filter), current_query)
            if len(matches) == 1:
                selected = matches[0]
            elif len(matches) > 1:
                console.print()
                console.print("  Ditemukan beberapa kandidat:", style="#7CB9E8")
                for item in matches[:8]:
                    console.print(
                        f"  {item.get('rank', 0):>2}. {item.get('normalized_name', item.get('source_name', '-'))}",
                        style="grey82",
                    )
                console.print()
                continue
            elif lowered_choice.endswith("i") and lowered_choice not in _LIBRARY_FILTER_OPTIONS:
                console.print(f"  Filter '{choice}' tidak dikenal. Gunakan salah satu: {' | '.join(_LIBRARY_FILTER_OPTIONS)}", style="bright_red")
                console.print()
                current_query = ""
                continue

        if not selected:
            console.print("  Entri tidak ditemukan.", style="bright_red")
            console.print()
            continue

        _print_library_detail(selected)
        back = console.input("  Tekan Enter untuk kembali ke daftar: ")
        if back is not None:
            console.print()

# ---------------------------------------------------------------------------
# RAG v3 — TF-IDF scoring (term specificity aware)
# ---------------------------------------------------------------------------
_STOP = {
    "yang", "dan", "atau", "pada", "dari", "dengan", "tidak", "ada",
    "untuk", "sudah", "sejak", "selama", "dalam", "lebih", "sangat",
    # konteks konsultasi & demografis — bukan gejala klinis
    "pasien", "pria", "wanita", "laki", "usia", "umur",
    "tahun", "hari", "minggu", "bulan", "jam", "menit",
    "datang", "keluhan", "mengeluh", "mengalami", "dirasakan",
    "beberapa", "satu", "dua", "tiga", "empat", "lima",
    "kali", "sudah", "baru", "lama", "mulai",
    # kata tindakan/kuantitas umum — tidak diskriminatif sebagai gejala
    "sering", "buang", "saat", "besar", "kecil",
    "sudah", "bisa", "baru", "juga", "masih", "pagi",
    "malam", "terasa", "terasa", "terjadi", "bila",
}

# Term generik yang tidak boleh dapat bonus nama penyakit
_GENERIC_TERMS = {"akut", "kronik", "berat", "ringan", "episodik", "primer",
                  "sekunder", "parah", "sedang", "tanpa", "dengan", "tidak"}

# Token gejala yang terlalu umum dan tidak boleh mendominasi ranking sendirian.
_WEAK_QUERY_TERMS = {
    "nyeri", "sakit", "pegal", "linu", "ngilu", "tekan", "panas", "demam",
    "pusing", "lemas", "mual", "muntah",
}

_ANATOMIC_TERMS = {
    "kepala", "mata", "telinga", "hidung", "tenggorok", "leher", "bahu",
    "dada", "punggung", "perut", "ulu", "epigastrium", "pinggang", "ginjal",
    "kemih", "kencing", "vagina", "rahim", "payudara", "paha", "lutut",
    "betis", "kaki", "tangan", "jari", "pergelangan", "sendi", "persendian",
    "otot", "siku", "tumit", "tumor", "kulit", "paru", "rlq", "ruq", "llq",
    "luq", "presinkop",
}

_QUERY_NORMALIZATION_MAP = {
    "persendian": "sendi",
    "per-sendi-an": "sendi",
    "nyeri persendian": "nyeri sendi",
    "sakit persendian": "nyeri sendi",
    "sendi-sendi": "sendi",
    "perut kanan bawah": "rlq",
    "kuadran kanan bawah": "rlq",
    "right lower quadrant": "rlq",
    "perut kanan atas": "ruq",
    "kuadran kanan atas": "ruq",
    "right upper quadrant": "ruq",
    "perut kiri bawah": "llq",
    "kuadran kiri bawah": "llq",
    "left lower quadrant": "llq",
    "perut kiri atas": "luq",
    "kuadran kiri atas": "luq",
    "left upper quadrant": "luq",
    "nyeri ulu hati": "nyeri epigastrium",
    "sakit ulu hati": "nyeri epigastrium",
    "ulu hati": "epigastrium",
    "kencing sakit": "disuria",
    "mau pingsan": "presinkop",
    "berkunang kunang": "presinkop",
    "berkunang-kunang": "presinkop",
    "serasa melayang": "presinkop",
    "pusing berputar": "vertigo",
    "kepala berputar": "vertigo",
}

_SHORT_QUERY_CANDIDATE_HINTS: dict[str, list[str]] = {
    "sendi": ["artritis", "osteoartritis", "gout", "mialgia"],
    "otot": ["mialgia", "fibromialgia", "myositis"],
    "kepala": ["headache", "migren", "vertigo", "stroke"],
    "epigastrium": ["dispepsia", "gastritis", "refluks", "ulkus"],
    "perut": ["dispepsia", "gastritis", "gastroenteritis", "appendisitis"],
    "rlq": ["appendisitis"],
    "ruq": ["hepatitis", "gastritis"],
    "llq": ["kolitis", "gastroenteritis"],
    "luq": ["gastritis", "dispepsia"],
    "dada": ["angina", "infark", "refluks", "mialgia"],
    "batuk": ["bronkitis", "pneumonia", "tuberkulosis", "asma"],
    "sesak": ["asma", "gagal jantung", "pneumonia", "ppok"],
    "pusing": ["vertigo", "sinkop", "hipoglikemia", "headache"],
    "vertigo": ["vertigo"],
    "presinkop": ["sinkop", "hipoglikemia", "anemia"],
    "mata": ["konjungtivitis", "mata kering", "hordeolum"],
    "kemih": ["sistitis", "pielonefritis", "batu"],
    "disuria": ["sistitis", "uretritis", "pielonefritis"],
}

_SHORT_QUERY_FOLLOWUPS: dict[str, list[str]] = {
    "sendi": [
        "sendi mana yang terkena",
        "satu sendi atau banyak sendi",
        "ada bengkak, kemerahan, atau rasa panas",
        "lebih nyeri saat gerak atau saat istirahat",
    ],
    "epigastrium": [
        "nyeri terkait makan atau saat lapar",
        "ada mual, muntah, kembung, atau rasa asam di mulut",
        "ada BAB hitam atau muntah darah",
        "nyeri menjalar ke dada atau punggung",
    ],
    "perut": [
        "lokasi nyeri perut paling dominan",
        "ada muntah, diare, konstipasi, atau demam",
        "nyeri menetap atau hilang timbul",
        "ada defans, distensi, atau BAB hitam",
    ],
    "rlq": [
        "nyeri mulai dari ulu hati atau sekitar pusar lalu pindah ke kanan bawah",
        "ada mual, muntah, atau demam",
        "nyeri bertambah saat berjalan, batuk, atau ditekan lepas",
        "ada defans atau perut tegang",
    ],
    "ruq": [
        "ada demam, ikterus, atau mual muntah",
        "nyeri setelah makan berlemak atau tidak",
        "nyeri menjalar ke bahu kanan atau punggung",
        "ada urin gelap atau feses pucat",
    ],
    "kepala": [
        "lokasi nyeri kepala dan sifat nyeri",
        "ada mual, fotofobia, defisit neurologis, atau demam",
        "mendadak sekali atau bertahap",
        "ada riwayat trauma atau hipertensi",
    ],
    "dada": [
        "nyeri seperti tertindih, terbakar, atau nyeri tekan lokal",
        "menjalar ke lengan kiri, rahang, atau punggung atau tidak",
        "dipicu aktivitas, napas, gerak, atau setelah makan",
        "ada sesak, keringat dingin, atau regurgitasi asam",
    ],
    "sesak": [
        "sejak kapan sesak muncul",
        "ada batuk, mengi, atau nyeri dada",
        "sesak saat aktivitas atau istirahat",
        "ada saturasi rendah atau napas cepat",
    ],
    "pusing": [
        "pusing berputar atau melayang",
        "ada mual, tinnitus, atau gangguan pendengaran",
        "ada lemas, pucat, atau sinkop",
        "ada defisit neurologis fokal",
    ],
    "vertigo": [
        "pusing berputar dipicu perubahan posisi atau tidak",
        "ada mual muntah, tinnitus, atau gangguan pendengaran",
        "ada nistagmus atau gangguan berjalan",
        "ada kelemahan anggota gerak atau bicara pelo",
    ],
    "presinkop": [
        "ada rasa melayang, gelap, atau mau pingsan",
        "dipicu berdiri lama, dehidrasi, atau terlambat makan",
        "ada berdebar, keringat dingin, atau pucat",
        "sempat sinkop atau hampir jatuh atau tidak",
    ],
}

_PHRASE_CANDIDATE_HINTS: dict[str, list[str]] = {
    "rlq": ["appendisitis"],
    "ruq": ["hepatitis", "gastritis"],
    "llq": ["kolitis", "gastroenteritis"],
    "luq": ["gastritis", "dispepsia"],
    "tertindih": ["angina", "infark"],
    "menjalar lengan": ["angina", "infark"],
    "lengan kiri": ["angina", "infark"],
    "keringat dingin": ["angina", "infark"],
    "regurgitasi": ["refluks", "dispepsia"],
    "asam": ["refluks", "dispepsia"],
    "terbakar": ["refluks"],
    "nyeri tekan": ["mialgia"],
    "saat ditekan": ["mialgia"],
    "saat gerak": ["mialgia"],
    "vertigo": ["vertigo"],
    "presinkop": ["sinkop", "hipoglikemia"],
    "nyeri kepala": ["headache", "migren"],
}

_PHRASE_SYNDROME_TAGS: dict[str, str] = {
    "rlq": "abdominal-rlq",
    "ruq": "abdominal-ruq",
    "llq": "abdominal-llq",
    "luq": "abdominal-luq",
    "epigastrium": "abdominal-epigastric",
    "tertindih": "chest-cardiac-like",
    "menjalar lengan": "chest-cardiac-like",
    "lengan kiri": "chest-cardiac-like",
    "keringat dingin": "chest-cardiac-like",
    "regurgitasi": "chest-gerd-like",
    "asam": "chest-gerd-like",
    "terbakar": "chest-gerd-like",
    "nyeri tekan": "chest-wall-like",
    "saat ditekan": "chest-wall-like",
    "saat gerak": "chest-wall-like",
    "vertigo": "dizziness-vertigo-like",
    "presinkop": "dizziness-presyncope-like",
    "nyeri kepala": "dizziness-headache-like",
}

_SYNDROME_SCORE_RULES: dict[str, dict[str, list[str]]] = {
    "abdominal-rlq": {
        "boost": ["appendisitis"],
        "penalize": ["gastritis", "dispepsia", "refluks"],
    },
    "abdominal-ruq": {
        "boost": ["hepatitis", "gastritis"],
        "penalize": ["appendisitis"],
    },
    "abdominal-epigastric": {
        "boost": ["dispepsia", "gastritis", "refluks"],
        "penalize": ["appendisitis", "ileus", "hernia"],
    },
    "chest-cardiac-like": {
        "boost": ["angina", "infark", "iskemik"],
        "penalize": ["refluks", "dispepsia", "mialgia"],
    },
    "chest-gerd-like": {
        "boost": ["refluks", "dispepsia", "gastritis"],
        "penalize": ["angina", "infark", "iskemik"],
    },
    "chest-wall-like": {
        "boost": ["mialgia"],
        "penalize": ["angina", "infark", "iskemik"],
    },
    "dizziness-vertigo-like": {
        "boost": ["vertigo"],
        "penalize": ["headache", "migren", "sinkop"],
    },
    "dizziness-presyncope-like": {
        "boost": ["sinkop", "hipoglik", "anemia"],
        "penalize": ["vertigo", "headache", "migren"],
    },
    "dizziness-headache-like": {
        "boost": ["headache", "migren"],
        "penalize": ["vertigo", "sinkop"],
    },
}

_SEVERE_DISEASE_NAME_TERMS = {
    "perdarahan", "hematemesis", "melena", "syok", "ruptur", "infark",
    "stroke", "meningitis", "anafilaksis", "ektopik", "ensefalitis",
    "karsinoma", "ileus", "obstruktif", "strangulata", "inkarserata",
}

_SEVERE_QUERY_CUES = {
    "darah", "perdarahan", "melena", "hematemesis", "pingsan", "sinkop",
    "sesak berat", "tidak sadar", "kelumpuhan", "afasia", "hemiplegia",
    "kejang", "syok", "kaku kuduk", "thunderclap",
}

# Context klinis → body system hint (query mengandung kata ini = konteks sistem tertentu)
_BODY_CONTEXT: dict[str, str] = {
    # OB/GYN
    "hamil": "SISTEM REPRODUKSI", "kehamilan": "SISTEM REPRODUKSI",
    "partus": "SISTEM REPRODUKSI", "persalinan": "SISTEM REPRODUKSI",
    "nifas": "SISTEM REPRODUKSI", "postpartum": "SISTEM REPRODUKSI",
    "gestasi": "SISTEM REPRODUKSI", "ektopik": "SISTEM REPRODUKSI",
    "menstruasi": "SISTEM REPRODUKSI", "haid": "SISTEM REPRODUKSI",
    "mens": "SISTEM REPRODUKSI", "keguguran": "SISTEM REPRODUKSI",
    "melahirkan": "SISTEM REPRODUKSI", "bersalin": "SISTEM REPRODUKSI",
    "lahir": "SISTEM REPRODUKSI", "bayi": "SISTEM REPRODUKSI",
    "janin": "SISTEM REPRODUKSI", "plasenta": "SISTEM REPRODUKSI",
    "trimester": "SISTEM REPRODUKSI", "gravida": "SISTEM REPRODUKSI",
    # Respirasi
    "batuk": "SISTEM RESPIRASI", "sesak": "SISTEM RESPIRASI",
    "napas": "SISTEM RESPIRASI", "paru": "SISTEM RESPIRASI",
    # GI
    "bab": "SALURAN PENCERNAAN", "feses": "SALURAN PENCERNAAN",
    "perut": "SISTEM DIGESTIF", "epigastrium": "SISTEM DIGESTIF",
    "rlq": "SISTEM DIGESTIF", "ruq": "SISTEM DIGESTIF",
    "llq": "SISTEM DIGESTIF", "luq": "SISTEM DIGESTIF",
    # Neurologi / kepala
    "kepala": "SISTEM SARAF", "migren": "SISTEM SARAF",
    "vertigo": "SISTEM SARAF", "kejang": "SISTEM SARAF",
    "presinkop": "SISTEM KARDIOVASKULAR",
    # Muskuloskeletal
    "sendi": "SISTEM MUSKULOSKELETAL", "persendian": "SISTEM MUSKULOSKELETAL",
    "otot": "SISTEM MUSKULOSKELETAL", "lutut": "SISTEM MUSKULOSKELETAL",
    "bahu": "SISTEM MUSKULOSKELETAL", "siku": "SISTEM MUSKULOSKELETAL",
    "pergelangan": "SISTEM MUSKULOSKELETAL", "jari": "SISTEM MUSKULOSKELETAL",
    "asam": "SISTEM MUSKULOSKELETAL", "gout": "SISTEM MUSKULOSKELETAL",
    "artritis": "SISTEM MUSKULOSKELETAL", "arthritis": "SISTEM MUSKULOSKELETAL",
    "pegal": "SISTEM MUSKULOSKELETAL", "ngilu": "SISTEM MUSKULOSKELETAL",
    # Indera — NEGATIF: kalau query tidak ada kata indera, kurangi skor penyakit indera
}

# Term patognomonik — langsung boost penyakit spesifik (bukan dari gejala_klinis)
# Hint adalah substring dari nama penyakit — harus cukup spesifik (minimal 6 karakter)
_PATHO_TERMS: dict[str, list[str]] = {
    "ikterus":    ["hepatitis", "leptospirosis", "sirosis", "kolestasis", "malaria"],
    "jaundice":   ["hepatitis", "leptospirosis"],
    "tenesmus":   ["disentri", "kolitis", "amoebiasis"],
    "mengi":      ["asma", "bronkitis"],
    "wheezing":   ["asma"],
    "trismus":    ["tetanus"],
    "disuria":    ["saluran kemih", "uretritis", "sistitis", "pielonefritis"],
    "hematuria":  ["saluran kemih", "batu saluran", "glomerulo", "nefritis"],
    "hemoptisis": ["tuberkulosis", "tb paru", "kanker paru"],
    "ptosis":     ["miastenia"],
    "afasia":     ["stroke"],
    "hemiplegia": ["stroke"],
}

# Kombinasi dua kata yang bersama-sama bersifat patognomonik
_PATHO_COMBOS: list[tuple[set[str], list[str]]] = [
    ({"batuk", "darah"},       ["tuberkulosis", "tb paru"]),
    ({"darah", "hemoptisis"},  ["tuberkulosis"]),
    ({"nyeri", "berkemih"},    ["saluran kemih", "sistitis", "pielonefritis"]),
    ({"kencing", "nyeri"},     ["saluran kemih", "sistitis"]),
    ({"tenggorok", "putih"},   ["tonsilitis", "faringitis"]),
    ({"tenggorok", "plak"},    ["tonsilitis"]),
    ({"tenggorok", "demam"},   ["tonsilitis", "faringitis", "difteri"]),
    ({"eksudat", "tonsil"},    ["tonsilitis"]),
    ({"berdenyut", "fotofobia"}, ["migren"]),
    ({"berdenyut", "sisi"},    ["migren"]),
    ({"fotofobia", "mual", "kepala"}, ["migren"]),
]

def _build_idf() -> dict[str, float]:
    """Hitung IDF untuk setiap term dari gejala_klinis di seluruh database."""
    N = len(DB["diseases_full"]) or 1
    doc_freq: dict[str, int] = defaultdict(int)
    for d in DB["diseases_full"]:
        terms_in_doc: set[str] = set()
        for gejala in d.get("gejala_klinis", []):
            g = gejala.lower().replace("nafas", "napas")
            for w in re.split(r"[\s,;./()>=<]+", g):
                if len(w) > 2:
                    terms_in_doc.add(w)
        for t in terms_in_doc:
            doc_freq[t] += 1
    return {t: math.log(N / f) for t, f in doc_freq.items()}

_IDF = _build_idf()

def _normalize_text(text: str) -> str:
    normalized = (text.lower()
                  .replace("nafas", "napas")
                  .replace("tenggorokan", "tenggorok")
                  .replace("mulutnya", "mulut")
                  .replace("badannya", "badan"))
    for raw, clean in _QUERY_NORMALIZATION_MAP.items():
        normalized = normalized.replace(raw, clean)
    return normalized

def _query_words(query: str) -> set[str]:
    return {w for w in _SPLIT.split(_normalize_text(query)) if len(w) > 2 and w not in _STOP}

_SPLIT = re.compile(r"[\s,;./()>=<\n\-]+")

def _text_to_words(text: str) -> set[str]:
    return {w for w in _SPLIT.split(_normalize_text(text)) if len(w) > 2 and w not in _STOP}

def _extract_query_profile(query: str) -> dict:
    normalized_query = _normalize_text(query)
    words = _query_words(query)
    body_hints = {_BODY_CONTEXT[w] for w in words if w in _BODY_CONTEXT}
    weak_terms = {w for w in words if w in _WEAK_QUERY_TERMS}
    anchor_terms = {w for w in words if w in _ANATOMIC_TERMS or w in _BODY_CONTEXT}
    specific_terms = words - weak_terms
    short_query = len(words) <= 3 or len(specific_terms) <= 2
    candidate_hints: set[str] = set()
    preferred_candidate_hints: set[str] = set()
    followups: list[str] = []
    syndrome_tags: set[str] = set()
    for term in anchor_terms | specific_terms:
        for hint in _SHORT_QUERY_CANDIDATE_HINTS.get(term, []):
            candidate_hints.add(hint)
        for followup in _SHORT_QUERY_FOLLOWUPS.get(term, []):
            if followup not in followups:
                followups.append(followup)
    for phrase, hints in _PHRASE_CANDIDATE_HINTS.items():
        if phrase in normalized_query:
            candidate_hints.update(hints)
    for phrase, tag in _PHRASE_SYNDROME_TAGS.items():
        if phrase in normalized_query:
            syndrome_tags.add(tag)
    if "dada" in anchor_terms and "chest-cardiac-like" not in syndrome_tags and "chest-gerd-like" not in syndrome_tags and "chest-wall-like" not in syndrome_tags:
        syndrome_tags.add("chest-undifferentiated")
    if "pusing" in words and not any(tag.startswith("dizziness-") for tag in syndrome_tags):
        syndrome_tags.add("dizziness-undifferentiated")
    for tag in syndrome_tags:
        rules = _SYNDROME_SCORE_RULES.get(tag, {})
        preferred_candidate_hints.update(rules.get("boost", []))
    severe_cues = {cue for cue in _SEVERE_QUERY_CUES if cue in normalized_query}
    return {
        "normalized_query": normalized_query,
        "words": words,
        "body_hints": body_hints,
        "weak_terms": weak_terms,
        "anchor_terms": anchor_terms,
        "specific_terms": specific_terms,
        "short_query": short_query,
        "candidate_hints": candidate_hints,
        "preferred_candidate_hints": preferred_candidate_hints,
        "followups": followups[:4],
        "syndrome_tags": syndrome_tags,
        "severe_cues": severe_cues,
        "generic_only": bool(words) and not anchor_terms and not (specific_terms - weak_terms),
    }

def _build_clinical_summary(query: str) -> str:
    profile = _extract_query_profile(query)
    lines = ["=== RINGKASAN KLINIS TERSTRUKTUR ==="]
    lines.append(f"Keluhan ternormalisasi: {profile['normalized_query']}")
    if profile["body_hints"]:
        lines.append("Sistem tubuh terdeteksi: " + ", ".join(sorted(profile["body_hints"])))
    if profile["anchor_terms"]:
        lines.append("Anchor klinis: " + ", ".join(sorted(profile["anchor_terms"])))
    if profile["specific_terms"]:
        lines.append("Token klinis spesifik: " + ", ".join(sorted(profile["specific_terms"])))
    if profile["candidate_hints"]:
        lines.append("Klaster kandidat awal: " + ", ".join(sorted(profile["candidate_hints"])))
    if profile["preferred_candidate_hints"]:
        lines.append("Prioritas kandidat: " + ", ".join(sorted(profile["preferred_candidate_hints"])))
    if profile["syndrome_tags"]:
        lines.append("Pola klinis awal: " + ", ".join(sorted(profile["syndrome_tags"])))
    if profile["generic_only"]:
        lines.append("Status data: keluhan masih terlalu umum, prioritaskan pertanyaan klarifikasi sebelum mengunci diagnosis.")
    elif profile["short_query"]:
        lines.append("Status data: informasi masih singkat, diagnosis kerja harus konservatif dan boleh berupa dugaan awal.")
    if profile["followups"]:
        lines.append("Klarifikasi prioritas: " + " | ".join(profile["followups"]))
    return "\n".join(lines)

def _disease_matches_candidate_hints(disease: dict, candidate_hints: set[str]) -> bool:
    if not candidate_hints:
        return False
    name_lower = disease.get("nama", "").lower().replace("nafas", "napas")
    return any(hint in name_lower for hint in candidate_hints)

def _prioritize_scored_candidates(scored: list[tuple[float, dict]], profile: dict) -> list[tuple[float, dict]]:
    if not scored:
        return scored
    preferred_hints = set(profile.get("preferred_candidate_hints", set()))
    general_hints = set(profile.get("candidate_hints", set()))
    if preferred_hints:
        preferred = [(s, d) for s, d in scored if _disease_matches_candidate_hints(d, preferred_hints)]
        if preferred:
            remainder = [(s, d) for s, d in scored if not _disease_matches_candidate_hints(d, preferred_hints)]
            return preferred + remainder
    if profile.get("short_query") and general_hints:
        preferred = [(s, d) for s, d in scored if _disease_matches_candidate_hints(d, general_hints)]
        if len(preferred) >= 2:
            remainder = [(s, d) for s, d in scored if not _disease_matches_candidate_hints(d, general_hints)]
            return preferred + remainder
    return scored

def _score_disease_tfidf(disease: dict, words: set[str],
                         body_hints: set[str] | None = None,
                         query_profile: dict | None = None) -> float:
    """TF-IDF score dengan tiga sumber:
    - gejala_klinis  : bobot penuh (1.0x)
    - pemeriksaan_fisik: bobot sedang (0.6x)
    - definisi       : bobot rendah (0.2x) — fallback
    + patho bonus    : term patognomonik langsung boost penyakit relevan
    + body context   : boost penyakit di sistem yang sesuai konteks query
    """
    score = 0.0
    name_lower = disease.get("nama", "").lower().replace("nafas", "napas")
    disease_system = disease.get("body_system", "")
    anchor_terms = {w for w in words if w in _ANATOMIC_TERMS or w in _BODY_CONTEXT}
    strong_terms = words - _WEAK_QUERY_TERMS
    location_terms = anchor_terms | (strong_terms - _WEAK_QUERY_TERMS)
    weak_match_score = 0.0
    strong_match_score = 0.0
    profile = query_profile or {}
    candidate_hints = set(profile.get("candidate_hints", set()))
    severe_cues = set(profile.get("severe_cues", set()))
    syndrome_tags = set(profile.get("syndrome_tags", set()))
    short_query = bool(profile.get("short_query"))

    # Body system context boost (sebelum scoring lain — efek aditif)
    if body_hints:
        if disease_system in body_hints:
            score += 12.0
        elif body_hints and disease_system not in body_hints:
            # Kalau ada konteks sistem yang kuat, penalti penyakit sistem lain
            # Hanya penalti jika ada 2+ hint word (konteks kuat)
            if len([w for w in words if _BODY_CONTEXT.get(w)]) >= 2:
                score -= 8.0

    # 1. gejala_klinis — bobot penuh
    for gejala in disease.get("gejala_klinis", []):
        g_words = _text_to_words(gejala)
        for w in words:
            if w in g_words:
                weight = _IDF.get(w, 5.0)
                if w in _WEAK_QUERY_TERMS:
                    weak_match_score += weight * 0.25
                else:
                    strong_match_score += weight

    # 2. pemeriksaan_fisik — bobot 0.6x
    for pf in disease.get("pemeriksaan_fisik", []):
        pf_words = _text_to_words(pf)
        for w in words:
            if w in pf_words:
                weight = _IDF.get(w, 5.0) * 0.6
                if w in _WEAK_QUERY_TERMS:
                    weak_match_score += weight * 0.25
                else:
                    strong_match_score += weight

    # 3. definisi — bobot 0.2x (diturunkan dari 0.3 untuk kurangi false positive)
    definisi = disease.get("definisi", "")
    if definisi:
        def_words = _text_to_words(definisi)
        for w in words:
            if w in def_words:
                weight = _IDF.get(w, 5.0) * 0.2
                if w in _WEAK_QUERY_TERMS:
                    weak_match_score += weight * 0.1
                else:
                    strong_match_score += weight

    score += strong_match_score + weak_match_score

    # 4a. Pathognomonic single-term bonus
    for patho, hints in _PATHO_TERMS.items():
        if patho in words:
            for hint in hints:
                if hint in name_lower:
                    score += 15.0
                    break

    # 4b. Pathognomonic combo bonus (dua kata bersama = indikator kuat)
    for combo_words, hints in _PATHO_COMBOS:
        if combo_words.issubset(words):
            for hint in hints:
                if hint in name_lower:
                    score += 12.0
                    break

    # 5. Bonus nama penyakit — threshold naik ke IDF > 3.5 (cegah false positive)
    for w in words:
        if w in name_lower and w not in _GENERIC_TERMS and _IDF.get(w, 0) > 3.5:
            score += _IDF.get(w, 3.5) * 2.0
            break

    # Bonus kandidat awal untuk keluhan pendek yang sudah punya anchor sistem/lokasi.
    if candidate_hints and any(hint in name_lower for hint in candidate_hints):
        score += 8.0 if short_query else 4.0

    # Bias berbasis pola klinis pendek seperti RLQ, chest pain subtype, dan tipe pusing.
    for tag in syndrome_tags:
        rules = _SYNDROME_SCORE_RULES.get(tag)
        if not rules:
            continue
        if any(hint in name_lower for hint in rules.get("boost", [])):
            score += 10.0 if short_query else 6.0
        if any(hint in name_lower for hint in rules.get("penalize", [])):
            score -= 8.0 if short_query else 5.0

    # Penalti bila kecocokan hanya digerakkan oleh token umum seperti "nyeri".
    if weak_match_score > 0 and strong_match_score == 0 and not anchor_terms:
        score -= 6.0

    # Penalti ekstra bila query punya anchor anatomi/sistem, tetapi penyakit tidak menyentuh anchor itu.
    if location_terms:
        disease_terms = set()
        for gejala in disease.get("gejala_klinis", []):
            disease_terms.update(_text_to_words(gejala))
        for pf in disease.get("pemeriksaan_fisik", []):
            disease_terms.update(_text_to_words(pf))
        disease_terms.update(_text_to_words(definisi))
        if not (location_terms & disease_terms) and disease_system not in (body_hints or set()):
            score -= 7.0

    # Penyakit berat tidak boleh mudah naik pada query singkat tanpa red flag pendukung.
    if short_query and not severe_cues:
        if any(term in name_lower for term in _SEVERE_DISEASE_NAME_TERMS):
            score -= 10.0

    return score

def _get_pharma_detail(icd10: str) -> dict | None:
    """Farmakologi dari 144_penyakit_puskesmas berdasarkan ICD-10 prefix 3 karakter."""
    prefix = icd10[:3].upper()
    for d in DB["diseases_144"]:
        if d.get("icd10", "").upper().startswith(prefix):
            return d.get("pharmacotherapy")
    return None

# ---------------------------------------------------------------------------
# RAG v4 — Chain-based architecture
# Prinsip: MedGemma tahu diagnosis, RAG inject operational context
# 1. Detect clinical entity dari chains (symptom key matching)
# 2. Ambil candidate disease names dari predictive_next chains
# 3. Fuzzy-match ke diseases_full → inject PPK + FORNAS + stok
# 4. TF-IDF sebagai fallback jika tidak ada chain match
# ---------------------------------------------------------------------------

def _normalize_name(s: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", s.lower().replace("nafas", "napas"))

def _name_match_score(disease_name: str, candidate: str) -> int:
    """Berapa kata dari candidate (>=4 char) yang ada di disease_name."""
    dn = _normalize_name(disease_name)
    cand_words = [w for w in _normalize_name(candidate).split() if len(w) >= 4]
    return sum(1 for w in cand_words if w in dn)

def _find_diseases_for_candidates(candidate_names: list[str]) -> list[dict]:
    """Fuzzy-match daftar nama dari predictive_next ke diseases_full."""
    found_ids: set[str] = set()
    results: list[tuple[int, dict]] = []

    for candidate in candidate_names:
        best_score = 0
        best_disease: dict | None = None
        for d in DB["diseases_full"]:
            did = d.get("id", d.get("nama", ""))
            if did in found_ids:
                continue
            s = _name_match_score(d.get("nama", ""), candidate)
            if s > best_score:
                best_score = s
                best_disease = d
        if best_disease and best_score >= 1:
            did = best_disease.get("id", best_disease.get("nama", ""))
            if did not in found_ids:
                found_ids.add(did)
                results.append((best_score, best_disease))

    results.sort(key=lambda x: -x[0])
    return [d for _, d in results]

def _build_disease_block(d: dict) -> list[str]:
    """Buat blok PPK untuk satu penyakit."""
    lines = [f"\n{d['nama']} [{d.get('icd10','')}]"]

    gejala = d.get("gejala_klinis", [])
    if gejala:
        clean = [g for g in gejala[:4] if isinstance(g, str) and len(g) < 120]
        if clean:
            lines.append("Gejala: " + ", ".join(clean))

    pf = d.get("pemeriksaan_fisik", [])
    if pf:
        clean = [p for p in pf[:3] if isinstance(p, str) and 5 < len(p) < 120]
        if clean:
            lines.append("Pem.fisik: " + " | ".join(clean))

    rf = d.get("red_flags", [])
    if rf:
        clean = [r for r in rf[:2] if isinstance(r, str) and 5 < len(r) < 120]
        if clean:
            lines.append("Red flags: " + " | ".join(clean))

    kr = d.get("kriteria_rujukan", "")
    if kr and isinstance(kr, str) and len(kr) > 10:
        lines.append(f"Rujukan: {kr[:150]}")

    pharma = _get_pharma_detail(d.get("icd10", ""))
    if pharma:
        fl = pharma.get("first_line", [])
        if fl:
            lines.append("Farmakoterapi lini 1:")
            for drug in fl[:3]:
                lines.append(f"  {drug.get('drug','')} {drug.get('dose','')} "
                             f"{drug.get('route','')} {drug.get('frequency','')}")

    return lines

def _retrieve_context(query: str) -> str:
    profile = _extract_query_profile(query)
    words = profile["words"]
    stok_map = {s["nama_obat"].lower(): s for s in DB["stok"]}
    body_hints: set[str] = profile["body_hints"]

    # === TF-IDF disease scoring ===
    scored: list[tuple[float, dict]] = []
    for d in DB["diseases_full"]:
        s = _score_disease_tfidf(d, words, body_hints if body_hints else None, profile)
        if s >= 3.5:
            scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    scored = _prioritize_scored_candidates(scored, profile)

    # Deduplikasi per ICD-10 prefix + nama awal
    seen_key: set[tuple] = set()
    top_diseases: list[dict] = []
    for _, d in scored:
        k = (d.get("icd10", "")[:3], d.get("nama", "")[:10].lower())
        if k not in seen_key:
            seen_key.add(k)
            top_diseases.append(d)
        if len(top_diseases) >= 3:
            break

    # === Build context ===
    lines: list[str] = [_build_clinical_summary(query)]

    if top_diseases:
        lines.append("=== REFERENSI KLINIS (SKDI / PPK IDI) ===")
        for d in top_diseases:
            lines.extend(_build_disease_block(d))

    # Stok obat: berdasarkan farmakoterapi penyakit yang ditemukan (bukan keyword)
    drug_names_to_check: list[str] = []
    for d in top_diseases:
        pharma = _get_pharma_detail(d.get("icd10", ""))
        if pharma:
            for drug in pharma.get("first_line", []) + pharma.get("second_line", []):
                nm = drug.get("drug", "").lower()
                if nm and nm not in drug_names_to_check:
                    drug_names_to_check.append(nm)

    stok_lines: list[str] = []
    seen_stok: set[str] = set()
    for drug_nm in drug_names_to_check[:12]:
        prefix = drug_nm[:6]
        for stok_nm, stok in stok_map.items():
            if prefix in stok_nm and stok_nm not in seen_stok:
                seen_stok.add(stok_nm)
                stok_lines.append(
                    f"  {stok['nama_obat']} {stok.get('kekuatan','')}"
                    f": stok {stok['stok_tersedia']} {stok['satuan']}"
                )
                break

    if stok_lines:
        lines.append("\n=== STOK OBAT ===")
        lines.extend(stok_lines[:8])

    # Red flag injection
    rf_ctx = _red_flag_disease_context(query)
    if rf_ctx:
        lines.append(rf_ctx)

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# System prompt — AUDREY Protocol v1
# ---------------------------------------------------------------------------
def _build_system(pasien: dict) -> str:
    pasien_str = ""
    if pasien:
        parts = []
        for key, label in [("nama","Nama"),("umur","Umur"),("jk","JK"),
                           ("bb","BB"),("tb","TB"),("alergi","Alergi")]:
            if pasien.get(key):
                suffix = " kg" if key == "bb" else (" cm" if key == "tb" else "")
                parts.append(f"{label}: {pasien[key]}{suffix}")
        if parts:
            pasien_str = "DATA PASIEN AKTIF:\n" + " | ".join(parts) + "\n\n"

    return f"""{pasien_str}Kamu adalah AUDREY, asisten klinis untuk dokter FKTP/Puskesmas Indonesia oleh Sentra AI.
Panduan: SKDI, FORNAS 2023, PPK IDI. Jawab dalam bahasa Indonesia formal.
Jika ada DATA REFERENSI gunakan sebagai acuan tambahan.

ATURAN KESELAMATAN — WAJIB DIPATUHI:
1. JIKA dalam DATA REFERENSI ada blok "DIAGNOSA RED FLAG — WAJIB DIPERTIMBANGKAN", maka penyakit di blok itu HARUS muncul di DIAGNOSIS BANDING dan biasanya menjadi DIAGNOSIS KERJA.
2. Konteks trauma (kecelakaan, terbentur, jatuh, perdarahan telinga/hidung pasca trauma, tidak sadar pasca benturan) TIDAK BOLEH didiagnosis sebagai infeksi/ISPA/furunkel — selalu pertimbangkan cedera otak/fraktur basis kranii sebagai prioritas.
3. Jangan menarik kesimpulan dari satu kata kunci anatomis (mis. "hidung") tanpa membaca konteks klinis lengkap.
4. Untuk pasien tidak sadar atau dengan trauma berat: DIAGNOSIS KERJA harus mencerminkan kondisi emergensi, KRITERIA RUJUK adalah rujuk emergensi.
5. Jika RINGKASAN KLINIS TERSTRUKTUR menyatakan data masih umum/singkat, jangan melompat ke diagnosis lintas sistem. Prioritaskan klarifikasi, gunakan diagnosis kerja konservatif, dan jangan memaksakan diagnosis spesifik tanpa bukti lokasi/anatomi.
6. Kata umum seperti nyeri, sakit, demam, lemas, pusing TIDAK cukup untuk memilih diagnosis tanpa lokasi, sistem tubuh, atau temuan pendukung.
7. Jika ada bagian "Klarifikasi prioritas" pada DATA REFERENSI, gunakan itu sebagai pertanyaan follow-up otomatis yang harus diprioritaskan sebelum mengunci diagnosis final.

Jika ditanya identitas: "Saya AUDREY oleh Sentra Artificial Intelligence."

FORMAT KETAT — wajib 8 bagian dengan judul KAPITAL diikuti titik dua. Setiap item satu baris penuh.
Pemisah nama dan alasan WAJIB pakai em-dash (—). Tidak ada bintang, hashtag, atau backtick.

DIAGNOSIS BANDING:
WAJIB MINIMAL 3 ALTERNATIF bila data cukup. Jika data belum cukup spesifik, tulis 2-3 diagnosis banding konservatif yang masih satu klaster sistem dan jangan membuat banding lintas sistem tanpa bukti. Setiap alternatif satu baris.
Format: [kode ICD-10] Nama penyakit — alasan ringkas berbasis bukti klinis
Contoh:
[M06] Artritis reumatoid — nyeri dan kaku sendi simetris
[M19] Osteoartritis — nyeri sendi mekanik pada aktivitas
[M79.1] Mialgia — nyeri muskuloskeletal tanpa inflamasi sendi jelas

DIAGNOSIS KERJA:
1 diagnosis utama. Format: [kode ICD-10] Nama — alasan pemilihan dibanding banding. Jika data belum cukup, boleh tulis diagnosis kerja sementara/dugaan awal dan nyatakan alasan keterbatasannya.

ANJURAN PEMERIKSAAN:
Setiap pemeriksaan satu baris. Format: Nama pemeriksaan — temuan yang dicari
Contoh: Darah lengkap — leukositosis menandakan infeksi bakteri

TATALAKSANA:
Manajemen non-farmakologi, satu langkah per baris.
Contoh: Tirah baring di ruang tenang dan gelap

FARMAKOLOGI:
Setiap obat ditulis 3 BARIS BERURUTAN — TIDAK BOLEH digabung satu baris:
Baris 1 (header obat): Nama dosis rute frekuensi durasi waktu
   Waktu = AC (sebelum makan) / PC (setelah makan) / HS (sebelum tidur) / dc (saat makan)
   Contoh: Paracetamol 500mg PO 3x1 5 hari PC
Baris 2: DDI: interaksi signifikan atau "tidak signifikan"
Baris 3: KI: kontraindikasi utama atau "tidak ada absolut"
Upayakan MINIMAL 3 obat bila data klinis dan diagnosis memungkinkan, dengan urutan prioritas:
  1. Obat utama / kausal / first-line sesuai diagnosis kerja
  2. Obat adjuvan / simptomatik untuk keluhan dominan
  3. Vitamin / supportive bila relevan dan rasional
Jika secara klinis tidak perlu 3 obat, JANGAN memaksakan polifarmasi; pilih yang paling rasional dan aman.
Jangan menambahkan vitamin/supportive bila tidak ada manfaat klinis yang jelas.
HANYA gunakan obat dari FORNAS 2023 atau yang ada di DATA REFERENSI.

EDUKASI PASIEN:
Satu poin per baris.

KRITERIA RUJUK:
WAJIB sebutkan algoritma/skor klinis yang relevan untuk DIAGNOSIS KERJA — gunakan sebagai alat objektif penentu rujukan.
Format tiap entri 1 baris. Tulis nama algoritma diikuti em-dash, lalu threshold/cutoff yang memicu rujukan.
Pilih algoritma yang sesuai diagnosis, contoh:
  Pneumonia      → CURB-65 — skor ≥2 rujuk RS, ≥3 ICU
  Sepsis         → qSOFA — ≥2 dari 3 (RR≥22, SBP≤100, GCS<15) rujuk segera
  Stroke         → NIHSS / FAST positif — onset <4.5 jam rujuk untuk trombolisis
  ACS / IMA      → TIMI risk score — ≥3 rujuk; EKG STEMI rujuk emergensi
  AF             → CHA2DS2-VASc — ≥2 rujuk untuk antikoagulan; HAS-BLED nilai risiko bleeding
  DBD            → WHO 2009 warning sign — ada warning sign / DSS rujuk
  PPOK eksaserbasi → kriteria GOLD — gagal napas / SpO2<90% rujuk
  Cedera kepala  → Canadian CT Head Rule — kriteria positif rujuk untuk CT
  Trauma         → Revised Trauma Score / GCS<13 rujuk
  Obstetri       → POGI rujukan — preeklampsia berat, HPP, gawat janin rujuk
  Anak           → kriteria MTBS / IMCI tanda bahaya umum rujuk
Tambahkan 1-2 baris kondisi klinis lain yang juga memicu rujukan (misal: tidak respon terapi 48-72 jam, komorbiditas berat, fasilitas tidak memadai).

PROGNOSIS:
Singkat, sebutkan faktor penentu prognosis."""

# ---------------------------------------------------------------------------
# Hanging indent printer
# ---------------------------------------------------------------------------
_NUM_PREFIX = re.compile(r"^(\d+\.\s+)")

def _section_line_rich(stripped: str, section: str) -> Text:
    """Title section: nomor dim+warna, judul bold+warna, ekor warna (tidak bold)."""
    esc = re.escape(section)
    m = re.match(
        rf"^(?P<pfx>\s*(?:\d+\.\s*)?)(?P<title>{esc})(?P<after>.*)$",
        stripped,
        re.IGNORECASE,
    )
    color = SECTION_STYLES[section]
    t = Text()
    if not m:
        t.append(stripped, style=f"bold {color}")
        return t
    pfx   = m.group("pfx") or ""
    title = m.group("title")
    after = m.group("after") or ""
    if pfx:
        t.append(pfx, style=f"dim {color}")
    t.append(title, style=f"bold {color}")
    if after:
        t.append(after, style=color)
    return t


def _print_hanging(text: str, style: str) -> None:
    m = _NUM_PREFIX.match(text)
    if m:
        prefix = m.group(1)
        subsequent = " " * len(prefix)
        width = (console.width or 80) - 1
        wrapped = textwrap.fill(
            text,
            width=width,
            initial_indent="",
            subsequent_indent=subsequent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        console.print(wrapped, style=style)
    else:
        console.print(text, style=style)


# ---------------------------------------------------------------------------
# Stateful stream renderer
# ---------------------------------------------------------------------------
_SUB_BRANCH = re.compile(
    r"^(?P<lbl>DDI|KI|Kontraindikasi|Indikasi|Dosis|Catatan|Note|Why|Alasan|Mekanisme)\s*[:\-—]\s*(?P<body>.+)$",
    re.IGNORECASE,
)

_ICD_HEAD = re.compile(r"^[A-Z]\d{1,3}(?:\.\d+)?\b")
_DRUG_HEAD = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ml|g|gr|iu|%)\b|\b\d+\s*x\s*\d+\b",
    re.IGNORECASE,
)

def _looks_like_header(text: str) -> bool:
    """Heuristik: apakah baris ini header item baru (bukan continuation prose)?"""
    # Normalisasi: buang prefix nomor "1. " dan kurung [G44.2] sebelum cek
    t = re.sub(r"^\s*\d+\.\s*", "", text)
    t = re.sub(r"^\s*\[([^\]]+)\]\s*", r"\1 ", t).strip()
    if _ICD_HEAD.match(t):
        return True
    if _DRUG_HEAD.search(t):
        return True
    first = t.split()[0] if t.split() else ""
    if len(first) >= 4 and first.isupper() and first.isalpha():
        return True
    return False

def _pure_color(style: str) -> str:
    """Strip 'bold ' prefix dari nilai SECTION_STYLES untuk dipakai sebagai foreground saja."""
    return style.replace("bold ", "").strip() or "bright_white"


def _highlight_sentiment(text: str, base_style: str = "") -> Text:
    """Highlight kata 'baik' → hijau bold, 'buruk' → merah bold."""
    t = Text(text, style=base_style or None)
    for m in re.finditer(r"(?i)\bbaik\b", text):
        t.stylize("bold bright_green", m.start(), m.end())
    for m in re.finditer(r"(?i)\bburuk\b", text):
        t.stylize("bold bright_red", m.start(), m.end())
    return t


_PHARMA_ROUTE_REPLACEMENTS = (
    (r"(?i)\bper oral\b", "PO"),
    (r"(?i)\boral\b", "PO"),
    (r"(?i)\bintravena\b", "IV"),
    (r"(?i)\bintravenous\b", "IV"),
    (r"(?i)\bintramuskular\b", "IM"),
    (r"(?i)\bintramuscular\b", "IM"),
    (r"(?i)\bsubkutan\b", "SC"),
    (r"(?i)\bsubcutaneous\b", "SC"),
    (r"(?i)\bsublingual\b", "SL"),
    (r"(?i)\brektal\b", "PR"),
    (r"(?i)\brectal\b", "PR"),
    (r"(?i)\btopikal\b", "TOP"),
    (r"(?i)\btopical\b", "TOP"),
)

_PHARMA_TIMING_REPLACEMENTS = (
    (r"(?i)\(?(sebelum makan\s*\+\s*sebelum tidur)\)?", "AC + HS"),
    (r"(?i)\(?(setelah makan\s*\+\s*sebelum tidur)\)?", "PC + HS"),
    (r"(?i)\(?(sebelum makan)\)?", "AC"),
    (r"(?i)\(?(sesudah makan|setelah makan)\)?", "PC"),
    (r"(?i)\(?(sebelum tidur)\)?", "HS"),
    (r"(?i)\(?(bila perlu|jika perlu|kalau perlu|prn)\)?", "PRN"),
    (r"(?i)\(?(segera|stat)\)?", "STAT"),
    (r"(?i)\(?(saat makan)\)?", "dc"),
)


def _normalize_pharma_conventions(text: str) -> str:
    normalized = text.strip()
    for pattern, replacement in _PHARMA_ROUTE_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized)
    for pattern, replacement in _PHARMA_TIMING_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+([,/])", r"\1", normalized)
    normalized = re.sub(r"([,/])\s+", r"\1", normalized)
    return normalized.strip()


def _format_obat_indonesia(line: str) -> str:
    """Ubah format obat LLM ke format Indonesia."""
    line = _normalize_pharma_conventions(line)

    # Pattern 1: dosis tunggal
    m = re.match(
        r"^([A-Za-z][A-Za-z\s]+?)\s+"
        r"(\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ml|g|gr|iu|%|tablet|kapsul|supp)?)"
        r"(?:\s+(?P<route>PO|IV|IM|SC|SL|PR|TOP))?"
        r"\s+(?:dosis\s+tunggal|single\s+dose)"
        r"(?:\s+(?P<tail>AC \+ HS|PC \+ HS|AC|PC|HS|PRN|STAT|dc))?$",
        line, re.IGNORECASE,
    )
    if m:
        nama = m.group(1).strip()
        dosis = m.group(2).strip()
        route = (m.group("route") or "").upper().strip()
        tail = (m.group("tail") or "").strip()
        pieces = [nama, f"1x{dosis}"]
        if route:
            pieces.append(route)
        pieces.append("Dosis Tunggal")
        if tail:
            pieces.append(tail)
        return _normalize_pharma_conventions(" ".join(pieces))

    # Pattern 2: frekuensi + durasi
    m = re.match(
        r"^(?P<name>[A-Za-z][A-Za-z\s]+?)\s+"
        r"(?P<dose>\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ml|g|gr|iu|%|tablet|kapsul|supp)?)"
        r"(?:\s+(?P<route>PO|IV|IM|SC|SL|PR|TOP))?"
        r"\s+(?P<freq>\d+x\d+)"
        r"\s+(?P<duration>\d+\s*(?:hari|minggu|bulan|h))",
        line, re.IGNORECASE,
    )
    if m:
        nama = m.group("name").strip()
        dosis = m.group("dose").strip()
        frek = m.group("freq").strip()  # e.g. "3x1"
        durasi = m.group("duration").strip()
        route = (m.group("route") or "").upper().strip()
        n = frek.split("x")[0]
        tail_match = re.search(r"\b(AC \+ HS|PC \+ HS|AC|PC|HS|PRN|STAT|dc)\b", line, re.IGNORECASE)
        tail = tail_match.group(1) if tail_match else ""
        pieces = [nama, f"{n}x{dosis}"]
        if route:
            pieces.append(route)
        pieces.append(durasi)
        if tail:
            pieces.append(tail)
        return _normalize_pharma_conventions(" ".join(pieces))

    return _normalize_pharma_conventions(line)


_PHARMA_META_RE = re.compile(
    r"^(?:[│├└─\s]+)?(DDI|KI|Kontraindikasi|Interaksi|Catatan)\s*[:\-—]\s*(.+)$",
    re.IGNORECASE,
)


def _is_pharma_meta_line(line: str) -> bool:
    return bool(_PHARMA_META_RE.match(line.strip()))


def _is_pharma_stock_line(line: str) -> bool:
    lowered = line.strip().lower()
    return "stok" in lowered and not _is_pharma_meta_line(line)


def _is_pharma_program_line(line: str) -> bool:
    lowered = line.strip().lower()
    return "(program)" in lowered or lowered.endswith("program")


def _is_pharma_meta_continuation(line: str) -> bool:
    clean = line.strip()
    if not clean or clean.strip("= ") == "":
        return False
    if _is_pharma_meta_line(clean) or _is_pharma_stock_line(clean) or _is_pharma_program_line(clean):
        return False
    if _match_pharma_drug_header(clean):
        return False
    if re.match(r"^[A-Z][A-Z\s/]+:$", clean):
        return False
    return True


def _looks_like_prescription_line(line: str) -> bool:
    clean = line.strip()
    if not clean or clean.endswith(":") or clean.strip("= ") == "":
        return False
    lowered = clean.lower()
    if "stok" in lowered or lowered.startswith("tidak ada obat"):
        return False
    has_schedule = bool(
        re.search(
            r"\b\d+\s*x\s*\d+(?:[.,]\d+)?(?:\s*(?:mg|mcg|µg|ml|g|gr|iu|%|tablet|kapsul|supp))?\b",
            clean,
            re.IGNORECASE,
        )
    )
    has_single = bool(re.search(r"\b(?:dosis\s+tunggal|single\s+dose)\b", clean, re.IGNORECASE))
    has_route = bool(re.search(r"\b(?:PO|IV|IM|SC|SL|PR|TOP|oral|per oral|rektal|rectal|sublingual|subkutan|topikal)\b", clean, re.IGNORECASE))
    has_duration = bool(re.search(r"\b\d+\s*(?:hari|minggu|bulan|h)\b", clean, re.IGNORECASE))
    return has_single or (has_schedule and (has_route or has_duration))


def _match_pharma_drug_header(line: str) -> re.Match[str] | None:
    clean = line.strip()
    if not _looks_like_prescription_line(clean):
        return None
    return re.match(r"^([A-Za-z][A-Za-z\s()/\-]+?)\s+\d", clean)


def _lookup_pharma_info(name_raw: str) -> dict | None:
    name_raw = name_raw.strip().lower()
    for key, data in _PHARMA_LOOKUP.items():
        if key in name_raw or name_raw.startswith(key):
            return data
    return None


def _extract_diagnosis_kerja_text(response: str) -> str:
    m = re.search(r"DIAGNOSIS KERJA:\s*\n(.*?)(?=\n[A-Z][A-Z\s/]+:\s*\n|$)", response, re.DOTALL)
    return m.group(1).strip() if m else ""


def _pick_supportive_pharma(response: str) -> tuple[str, dict, str] | tuple[None, None, None]:
    diagnosis_text = _extract_diagnosis_kerja_text(response).lower()
    if not diagnosis_text:
        return None, None, None
    for rule in _PHARMA_SUPPORTIVE_RULES:
        if any(keyword in diagnosis_text for keyword in rule["keywords"]):
            info = _PHARMA_LOOKUP.get(rule["lookup_key"])
            if info:
                return rule["line"], info, rule["lookup_key"]
    return None, None, None


def _get_pharma_cluster_rule(response: str) -> dict | None:
    diagnosis_text = _extract_diagnosis_kerja_text(response).lower()
    if not diagnosis_text:
        return None
    for rule in _PHARMA_CLUSTER_RULES:
        if any(keyword in diagnosis_text for keyword in rule["keywords"]):
            return rule
    return None


def _should_keep_pharma_candidate(name_raw: str, cluster_rule: dict | None) -> bool:
    if not cluster_rule:
        return True
    lowered = name_raw.lower()
    blocked = cluster_rule.get("blocked_drug_keywords", ())
    return not any(keyword in lowered for keyword in blocked)


class StreamRenderer:
    def __init__(self) -> None:
        self.current_section: str | None = None
        self.section_count   = 0
        self.last_was_blank  = True
        self.in_item         = False

    def _detect_section(self, line: str) -> str | None:
        upper = line.strip().upper()
        for s in sorted(SECTION_STYLES.keys(), key=len, reverse=True):
            if upper == s or upper.startswith(s + ":"):
                return s
            if upper.startswith(s + " —") or upper.startswith(s + " –") or upper.startswith(s + " -"):
                return s
            if re.match(rf"^\d+\.\s*{re.escape(s)}\s*[—:–\-]?", upper):
                return s
        return None

    def _maybe_blank(self) -> None:
        if not self.last_was_blank:
            console.print()
            self.last_was_blank = True

    def flush(self, buf: str) -> None:
        if not buf.strip():
            self._maybe_blank()
            return

        clean    = _strip_markdown(buf)
        stripped = clean.strip()
        section  = self._detect_section(clean)

        if section:
            if self.section_count > 0:
                self._maybe_blank()
            self.current_section = section
            self.section_count  += 1
            self.in_item         = False
            console.print(_section_line_rich(stripped, section))
            self.last_was_blank = False
            return

        if stripped.startswith("[!]"):
            console.print(stripped, style="bold bright_red")
            self.last_was_blank = False
            self.in_item        = False
            return

        sub = _SUB_BRANCH.match(stripped)
        if sub and self.in_item:
            self._render_sub_branch(sub.group("lbl").upper(), sub.group("body").strip())
            self.last_was_blank = False
            return

        # Continuation: di dalam section, baris tidak terlihat seperti header baru → jadi branch
        if self.current_section and self.in_item and not _looks_like_header(stripped):
            self._render_branch(stripped)
            self.last_was_blank = False
            return

        self._render_item(stripped)
        self.in_item        = True
        self.last_was_blank = False

    # ---- rendering helpers --------------------------------------------------
    def _section_color(self) -> str:
        sec = self.current_section
        return _pure_color(SECTION_STYLES.get(sec, "bright_white") if sec else "bright_white")

    def _render_item(self, line: str) -> None:
        head_raw = re.sub(r"^\s*\d+\.\s*", "", line)
        head_raw = re.sub(r"\[([^\]]+)\]", r"\1", head_raw)
        head_raw = head_raw.strip()

        head, tail = self._split_head_tail(head_raw)

        if tail:
            t = Text()
            t.append(head, style="bold bright_white")
            console.print(t)
            self._render_branch(tail)
        else:
            console.print(_highlight_sentiment(head_raw, "bold bright_white"))

    def _split_head_tail(self, text: str) -> tuple[str, str | None]:
        """Coba pisah jadi head + tail. Urutan separator: em-dash, en-dash, ' - ', ': '."""
        for pat in (r"\s+—\s+", r"\s+–\s+", r"\s+-\s+", r"\s*:\s+"):
            m = re.search(pat, text)
            if not m:
                continue
            head = text[:m.start()].strip()
            tail = text[m.end():].strip()
            if 2 <= len(head) <= 110 and tail:
                return head, tail
        return text, None

    def _render_sub_branch(self, label: str, body: str) -> None:
        # Label penting (KI = kontraindikasi, DDI = interaksi) → highlight ringan via warna section
        important = label.upper() in {"KI", "KONTRAINDIKASI", "DDI"}
        color = self._section_color() if important else "grey50"
        self._render_branch(body, branch_color=color, label=label, label_emphasize=important)

    def _render_branch(self, text: str, branch_color: str = "grey50",
                       label: str | None = None,
                       label_emphasize: bool = False) -> None:
        width        = (console.width or 80) - 1
        first_indent = "  └ "
        cont_indent  = "    "
        body         = f"{label}: {text}" if label else text
        wrapped      = textwrap.fill(
            body,
            width=width,
            initial_indent=first_indent,
            subsequent_indent=cont_indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        for i, ln in enumerate(wrapped.split("\n")):
            t = Text()
            if i == 0:
                t.append("  └ ", style=branch_color)
                content = ln[len(first_indent):]
                if label and content.upper().startswith(label.upper() + ":"):
                    cut = len(label) + 1
                    t.append(content[:cut], style=f"bold {branch_color}")
                    rest = content[cut:]
                    t.append(_highlight_sentiment(rest, "bright_white"))
                else:
                    t.append(_highlight_sentiment(content, "bright_white"))
            else:
                t.append(cont_indent, style=branch_color)
                t.append(_highlight_sentiment(ln[len(cont_indent):], "bright_white"))
            console.print(t)


def _title_audrey_colored() -> Text:
    t = Text()
    t.append("AUDREY", style=f"bold {C_VALUE}")
    return t


def _header_title_row() -> Text:
    t = _title_audrey_colored()
    t.append("  ", style=C_DIM)
    t.append("Clinical Command Console", style=f"italic {C_META}")
    return t


def _badge(label: str, tone: str = "muted") -> Text:
    bg, fg = _BADGE_TONES.get(tone, _BADGE_TONES["muted"])
    return Text(f" {label.upper()} ", style=f"bold {fg} on {bg}")


def _kv_line(pairs: list[tuple[str, str]]) -> Text:
    t = Text()
    for idx, (label, value) in enumerate(pairs):
        if idx:
            t.append("  •  ", style=C_DIM)
        t.append(f"{label}: ", style=C_LABEL)
        t.append(value, style=C_VALUE)
    return t


def _section_badge(section: str, color: str) -> Text:
    return Text(f" {section} ", style=f"bold {color} on {C_PANEL_ALT}")


def _panel_title(label: str, color: str = C_INFO) -> str:
    return f"[bold {color}]{label}[/]"


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
def _print_header(session_id: str, pasien: dict | None = None) -> None:
    now = datetime.now().strftime("%A, %d %b %Y  %H:%M")
    patient_label = pasien.get("nama") if pasien else "-"
    patient_mode = "PASIEN AKTIF" if pasien else "TANPA PASIEN"

    top = Text()
    top.append_text(_header_title_row())
    top.append("   ", style=C_DIM)
    top.append_text(_badge("online", "success"))
    top.append(" ", style=C_DIM)
    top.append_text(_badge(patient_mode, "info" if pasien else "muted"))

    meta1 = _kv_line([
        ("Model", DISPLAY_MODEL),
        ("Session", session_id),
        ("Waktu", now),
    ])
    meta2 = _kv_line([
        ("Pasien", patient_label),
        ("Architect", "dr Ferdi Iskandar"),
    ])

    grid = Table.grid(expand=True)
    grid.add_row(top)
    grid.add_row(Text(""))
    grid.add_row(meta1)
    grid.add_row(meta2)

    console.print()
    console.print(Panel(
        grid,
        box=rbox.ROUNDED,
        border_style=C_BORDER,
        padding=(1, 2),
        expand=True,
        title=_panel_title("SENTRA MEDICAL CONSOLE"),
        subtitle=f"[{C_DIM}]FKTP / Puskesmas Clinical Decision Support[/]",
        style=f"on {C_PANEL}",
    ))
    console.print()

def _print_command_footer() -> None:
    """Footer ringkas — daftar slash command, ditampilkan setelah tiap response."""
    klinis = ["/soap", "/triage", "/rujuk", "/edukasi"]
    pustaka = ["/library20", "/library50", "/library100", "/tree"]
    sistem = ["/pasien", "/next", "/save", "/history", "/send", "/model", "/clear", "/help", "/exit"]

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=4)
    grid.add_row(_badge("klinis", "info"), Text("  ".join(klinis), style="grey82"))
    grid.add_row(_badge("pustaka", "warn"), Text("  ".join(pustaka), style="grey82"))
    grid.add_row(_badge("sistem", "muted"), Text("  ".join(sistem), style="grey82"))

    console.print(Panel(
        grid,
        box=rbox.ROUNDED,
        border_style=C_DIM,
        padding=(0, 1),
        title=_panel_title("COMMANDS"),
        style=f"on {C_PANEL}",
    ))


def _print_help() -> None:
    console.print()
    table = Table.grid(expand=True)
    table.add_column(style="bold #86B8D8", width=14)
    table.add_column(style="grey82")
    cmds = [
        ("/soap",    "Template SOAP note kosong"),
        ("/triage",  "Template triage ESI 5 level"),
        ("/rujuk",   "Pohon kriteria rujukan (emergensi/urgent/elektif)"),
        ("/edukasi", "Pohon topik edukasi pasien"),
        ("/library20", "Shortcut 20 penyakit tersering untuk akses cepat harian"),
        ("/library50", "Pustaka ranking 1-50 dengan filter sistem dan search cerdas"),
        ("/library100", "Pustaka ranking 1-100 dengan navigasi, filter, dan search"),
        ("/tree",    "Directory tree project AUDREY"),
        ("/pasien",  "Input data pasien aktif"),
        ("/next",    "Kasus baru — reset pasien dan riwayat"),
        ("/history", "Tampilkan riwayat percakapan"),
        ("/save",    "Simpan sesi ke file"),
        ("/send",    "Kirim output terakhir ke Telegram"),
        ("/icd",     "Kamus ICD-10 Indonesia — contoh: /icd I10 atau /icd hipertensi"),
        ("/model",   "Ganti model Ollama"),
        ("/clear",   "Bersihkan layar"),
        ("/help",    "Tampilkan bantuan ini"),
        ("/exit",    "Keluar"),
    ]
    for cmd, desc in cmds:
        table.add_row(cmd, desc)
    console.print(Panel(
        table,
        box=rbox.ROUNDED,
        border_style=C_DIM,
        padding=(1, 2),
        title=_panel_title("PERINTAH TERSEDIA"),
        style=f"on {C_PANEL}",
    ))
    console.print()


# ---------------------------------------------------------------------------
# Static clinical templates (tree-style printers)
# ---------------------------------------------------------------------------
def _print_template(title: str, title_color: str,
                    sections: list[tuple[str, list[str]]]) -> None:
    """Print template blocks with calmer, more legible command-center styling."""
    console.print()
    console.print(Panel(
        Text(title, style=f"bold {title_color}"),
        box=rbox.ROUNDED,
        border_style=title_color,
        padding=(0, 1),
        expand=True,
        style=f"on {C_PANEL}",
    ))
    for sec_name, items in sections:
        console.print()
        console.print(_section_badge(sec_name, title_color))
        for item in items:
            t = Text()
            t.append("  · ", style=C_DIM)
            t.append(item, style=C_VALUE)
            console.print(t)
    console.print()
    console.print(Rule(style=C_DIM, characters="─"))
    console.print()


def _print_soap_template() -> None:
    _print_template("SOAP NOTE — TEMPLATE", "#7CB9E8", [
        ("S — SUBJECTIVE", [
            "Keluhan utama (CC):",
            "Riwayat penyakit sekarang (HPI):",
            "Riwayat penyakit dahulu (PMH):",
            "Riwayat keluarga / sosial:",
            "Alergi / pengobatan saat ini:",
        ]),
        ("O — OBJECTIVE", [
            "Vital sign: TD ___/___ HR ___ RR ___ T ___ SpO2 ___",
            "Keadaan umum / GCS:",
            "Pemeriksaan fisik per sistem:",
            "Hasil penunjang (lab/imaging):",
        ]),
        ("A — ASSESSMENT", [
            "Diagnosis kerja (ICD-10):",
            "Diagnosis banding:",
            "Severity / staging:",
        ]),
        ("P — PLAN", [
            "Pemeriksaan tambahan:",
            "Tatalaksana non-farmakologi:",
            "Farmakoterapi:",
            "Edukasi pasien:",
            "Kontrol / follow-up:",
            "Kriteria rujuk bila:",
        ]),
    ])


def _print_triage_template() -> None:
    _print_template("TRIAGE — ESI (Emergency Severity Index)", "#C44536", [
        ("ESI-1  RESUSITASI  (life-threatening, intervensi segera)", [
            "Henti napas / henti jantung",
            "Tidak sadar berat (GCS <8)",
            "Distress respirasi berat / sianosis",
            "Syok (hipoperfusi sistemik)",
            "Trauma multipel berat",
        ]),
        ("ESI-2  EMERGENT  (high risk, tunggu maks 10 menit)", [
            "Nyeri dada suspect ACS / aritmia berat",
            "Stroke onset akut (FAST positif)",
            "Sepsis / suspek meningitis",
            "Confused, letargi, disorientasi baru",
            "Nyeri berat (skala ≥7/10)",
            "Asma berat / SpO2 90-94%",
        ]),
        ("ESI-3  URGENT  (≥2 resources)", [
            "Butuh lab + imaging + IV / observasi",
            "Vital sign borderline (HR/RR/TD)",
            "Demam tinggi tanpa fokus jelas",
            "Nyeri sedang (4-6/10)",
        ]),
        ("ESI-4  LESS URGENT  (1 resource)", [
            "Butuh 1 pemeriksaan penunjang saja",
            "Laserasi sederhana, perlu hecting",
        ]),
        ("ESI-5  NON URGENT  (tidak butuh resource)", [
            "Pemeriksaan klinis sederhana",
            "Resep ulang / kontrol rutin",
        ]),
    ])


def _print_rujuk_tree() -> None:
    _print_template("KRITERIA RUJUKAN — PPK 1 → RUMAH SAKIT", "#C44536", [
        ("EMERGENSI  (rujuk segera setelah stabilisasi)", [
            "Distress respirasi / SpO2 <90% persisten",
            "Nyeri dada cardiac / suspek ACS / STEMI",
            "Stroke akut window <4.5 jam (kandidat trombolisis)",
            "Trauma kapitis + penurunan kesadaran",
            "Perdarahan masif tidak terkontrol",
            "Keracunan berat / overdosis",
            "Persalinan dengan komplikasi (perdarahan, eklampsia)",
            "Status epileptikus",
            "Syok dari sebab apapun",
        ]),
        ("URGENT  (rujuk dalam 24 jam)", [
            "Demam tifoid dengan komplikasi",
            "DBD dengan warning sign / DSS",
            "Infeksi berat butuh IV antibiotik prolonged",
            "DKA / HHS / hipoglikemia berulang",
            "Hipertensi krisis tanpa target organ damage",
            "Pneumonia berat (CURB-65 ≥2)",
            "Kehamilan risiko tinggi",
        ]),
        ("ELEKTIF  (rujuk berjadwal)", [
            "Diagnosis tidak tegas setelah evaluasi PPK 1",
            "Butuh pemeriksaan spesialistik (USG, endoskopi, CT)",
            "Butuh tindakan / pembedahan elektif",
            "Penyakit kronis untuk evaluasi spesialis",
            "Tidak respon terapi standar 2 minggu",
            "Permintaan second opinion atas indikasi",
        ]),
    ])


def _print_edukasi_tree() -> None:
    _print_template("TOPIK EDUKASI PASIEN", "#7CB9E8", [
        ("GAYA HIDUP", [
            "Pola makan seimbang (Isi Piringku Kemenkes)",
            "Aktivitas fisik minimal 150 menit/minggu",
            "Berhenti merokok dan paparan asap rokok",
            "Batasi alkohol",
            "Tidur cukup 7-8 jam, kelola stres",
        ]),
        ("KEPATUHAN PENGOBATAN", [
            "Minum obat sesuai dosis, frekuensi, dan waktu",
            "Jangan berhenti obat tanpa konsultasi dokter",
            "Lapor segera jika ada efek samping",
            "Simpan obat di tempat aman, jauh dari anak",
            "Bawa daftar obat saat kontrol",
        ]),
        ("TANDA BAHAYA  (segera kembali ke fasyankes)", [
            "Demam tinggi persisten / menggigil hebat",
            "Nyeri memburuk atau menyebar",
            "Sesak napas / sulit bicara dalam kalimat",
            "Penurunan kesadaran / linglung",
            "Perdarahan tidak normal",
            "Muntah persisten / tidak bisa makan minum",
        ]),
        ("PENCEGAHAN", [
            "Cuci tangan 6 langkah dengan sabun",
            "Etika batuk dan bersin",
            "Imunisasi sesuai jadwal Kemenkes",
            "Pemeriksaan kesehatan berkala (skrining)",
            "Pakai masker bila gejala ISPA",
        ]),
        ("KONTROL ULANG", [
            "Datang sesuai jadwal yang ditentukan",
            "Bawa kartu kontrol, obat, hasil pemeriksaan",
            "Catat keluhan yang muncul antar kunjungan",
            "Hubungi fasyankes bila tidak bisa hadir",
        ]),
    ])


def _print_dir_tree() -> None:
    """Tampilkan directory tree project AUDREY."""
    import os
    console.print()
    console.print(SEP, style="grey50")
    console.print(f"DIRECTORY TREE — {BASE_DIR.name}/", style=f"bold {C_NAME}")
    console.print(SEP, style="grey50")
    console.print()

    def _walk(path: Path, prefix: str = "") -> None:
        try:
            entries = sorted(
                path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return
        # Skip hidden + cache dirs
        entries = [e for e in entries
                   if not e.name.startswith(".")
                   and e.name not in {"__pycache__", "sessions"}]
        for i, entry in enumerate(entries):
            last = (i == len(entries) - 1)
            connector = "└── " if last else "├── "
            t = Text()
            t.append(prefix, style="grey50")
            t.append(connector, style="grey50")
            if entry.is_dir():
                t.append(entry.name + "/", style=f"bold {C_NAME}")
            else:
                t.append(entry.name, style="bright_white")
            console.print(t)
            if entry.is_dir():
                ext = "    " if last else "│   "
                _walk(entry, prefix + ext)

    t = Text()
    t.append(BASE_DIR.name + "/", style=f"bold {C_NAME}")
    console.print(t)
    _walk(BASE_DIR)
    console.print()
    console.print(SEP, style="grey50")
    console.print()

def _input_pasien() -> dict:
    console.print()
    console.print(SEP, style="grey50")
    console.print("INPUT DATA PASIEN  (kosongkan untuk skip)", style="#7CB9E8")
    console.print(SEP, style="grey50")
    fields = [("nama","Nama      "),("umur","Umur      "),("jk","JK (L/P)  "),
              ("bb","BB (kg)   "),("tb","TB (cm)   "),("alergi","Alergi    ")]
    pasien = {}
    for key, label in fields:
        val = console.input(f"  {label}: ").strip()
        if val:
            pasien[key] = val.upper() if key == "jk" else val
    console.print(SEP, style="grey50")
    console.print()
    return pasien

def _save_session(history: list, pasien: dict, session_id: str) -> None:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = SESSIONS_DIR / f"audrey_{ts}_{session_id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"AUDREY Session {session_id}\n")
        f.write(f"Tanggal: {datetime.now().strftime('%d %B %Y %H:%M')}\n")
        if pasien:
            f.write("Pasien: " + " | ".join(f"{k}: {v}" for k, v in pasien.items()) + "\n")
        f.write("\n" + "=" * 60 + "\n\n")
        for msg in history:
            role = "DOKTER" if msg["role"] == "user" else "AUDREY"
            f.write(f"{role}:\n{msg['content']}\n\n")
    console.print(f"  Tersimpan: {filename}", style="dim grey50")

# ---------------------------------------------------------------------------
# Dual-line uplink animation
# ---------------------------------------------------------------------------
def _show_uplink_animation() -> None:
    """Dual progress bar — Algorithm Run + Uplink Connected, mengalir."""
    import sys, time

    width  = 36
    frames = 28

    label1 = "Sentra Algorithm Run"
    label2 = "Sentra Uplink Connected"

    # Soft blue + burnt orange (sesuai palet Kate CLI)
    c1 = "\033[38;2;124;185;232m"
    c2 = "\033[38;2;220;80;20m"
    dim_lbl = "\033[2;38;2;160;160;170m"
    dim_trk = "\033[38;2;60;60;70m"
    rst = "\033[0m"

    fill_ch  = "▰"
    track_ch = "▱"

    label_w = max(len(label1), len(label2))

    # Reserve 2 lines
    sys.stdout.write("\n\n")

    for f in range(frames):
        # Bar 1 mulai dari frame 0; bar 2 lag 5 frame
        p1 = min(f / max(frames - 8, 1), 1.0)
        p2 = min(max(f - 5, 0) / max(frames - 8, 1), 1.0)

        n1 = int(p1 * width)
        n2 = int(p2 * width)

        bar1 = f"{c1}{fill_ch * n1}{rst}{dim_trk}{track_ch * (width - n1)}{rst}"
        bar2 = f"{c2}{fill_ch * n2}{rst}{dim_trk}{track_ch * (width - n2)}{rst}"

        # Cursor up 2 lines, redraw kedua baris
        sys.stdout.write("\033[2A\r")
        sys.stdout.write(f"  {bar1}  {dim_lbl}{label1:<{label_w}}{rst}\n")
        sys.stdout.write(f"\r  {bar2}  {dim_lbl}{label2:<{label_w}}{rst}\n")
        sys.stdout.flush()
        time.sleep(0.06)

    # Biarkan kedua bar tetap terlihat (full filled), pindah ke baris baru
    sys.stdout.write("\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Streaming chat
# ---------------------------------------------------------------------------
def _chat(prompt: str, history: list, pasien: dict, model: str, backend: str) -> str:
    # Red flag check — tampilkan sebelum model menjawab
    alerts = _detect_red_flags(prompt)
    if alerts:
        console.print()
        console.print(SEP, style="bright_red")
        for alert in alerts:
            console.print(alert, style="bold bright_red")
        console.print(SEP, style="bright_red")

    ctx = _retrieve_context(prompt)
    augmented = f"{prompt}\n\n[DATA REFERENSI]\n{ctx}" if ctx else prompt

    history.append({"role": "user", "content": augmented})
    # Trim by count
    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]
    # Trim by total char length — cegah context bloat dari response panjang
    while sum(len(m["content"]) for m in history) > 8000 and len(history) > 2:
        history[:] = history[2:]  # buang pasangan user+assistant terlama

    messages = [{"role": "system", "content": _build_system(pasien)}] + history

    console.print()
    _show_uplink_animation()
    console.print()

    full_response = ""

    try:
        provider = build_provider(backend, api_key=os.getenv("DEEPSEEK_API_KEY"))
        renderer = StreamRenderer()
        line_buf = ""
        in_farma = False

        for token in provider.stream_chat(messages, model=model):
            full_response += token
            for char in token:
                if char == "\n":
                    stripped = line_buf.strip()
                    # Deteksi section FARMAKOLOGI
                    if stripped.upper().startswith("FARMAKOLOGI"):
                        in_farma = True
                    elif re.match(r"^[A-Z][A-Z\s/]+:$", stripped):
                        in_farma = False

                    # Jika kita sudah auto-inject DDI/KI lokal, jangan cetak meta line model lagi.
                    if in_farma and _is_pharma_meta_line(stripped):
                        line_buf = ""
                        continue

                    if in_farma and stripped.strip("= ") == "":
                        line_buf = ""
                        continue

                    # Format obat Indonesia sebelum flush
                    if in_farma and stripped and not stripped.upper().startswith("FARMAKOLOGI"):
                        match = _match_pharma_drug_header(stripped)
                        if match:
                            cluster_rule = _get_pharma_cluster_rule(full_response)
                            name_raw = match.group(1).strip().lower()
                            if not _should_keep_pharma_candidate(name_raw, cluster_rule):
                                line_buf = ""
                                continue
                            line_buf = _format_obat_indonesia(line_buf.strip())

                    renderer.flush(line_buf)

                    # Real-time FARMAKOLOGI tree injection
                    if in_farma and stripped and not stripped.upper().startswith("FARMAKOLOGI"):
                        match = _match_pharma_drug_header(stripped)
                        if match:
                            name_raw = match.group(1).strip().lower()
                            cluster_rule = _get_pharma_cluster_rule(full_response)
                            if not _should_keep_pharma_candidate(name_raw, cluster_rule):
                                line_buf = ""
                                continue
                            found = _lookup_pharma_info(name_raw)
                            if found:
                                console.print("│", style="grey50")
                                t = Text()
                                t.append("├─ DDI: ", style="bright_yellow")
                                t.append(found['ddi'], style="bright_white")
                                console.print(t)
                                t = Text()
                                t.append("└─ Kontraindikasi: ", style="bold bright_red")
                                t.append(found['ki'], style="bright_white")
                                console.print(t)
                            else:
                                console.print("│", style="grey50")
                                t = Text()
                                t.append("├─ DDI: ", style="dim grey50")
                                t.append("Tidak tersedia di database lokal", style="bright_white")
                                console.print(t)
                                t = Text()
                                t.append("└─ Kontraindikasi: ", style="dim grey50")
                                t.append("Tidak tersedia di database lokal", style="bright_white")
                                console.print(t)
                    renderer.last_was_blank = False
                    renderer.in_item = True

                    line_buf = ""
                else:
                    line_buf += char

        # Flush sisa baris terakhir
        if line_buf:
            if in_farma:
                if _is_pharma_meta_line(line_buf.strip()) or line_buf.strip("= ") == "":
                    line_buf = ""
                match = _match_pharma_drug_header(line_buf.strip()) if line_buf else None
                if match:
                    cluster_rule = _get_pharma_cluster_rule(full_response)
                    name_raw = match.group(1).strip().lower()
                    if not _should_keep_pharma_candidate(name_raw, cluster_rule):
                        line_buf = ""
                    else:
                        line_buf = _format_obat_indonesia(line_buf.strip())
            if line_buf:
                renderer.flush(line_buf)
            if in_farma and line_buf:
                match = _match_pharma_drug_header(line_buf.strip())
                if match:
                    name_raw = match.group(1).strip().lower()
                    cluster_rule = _get_pharma_cluster_rule(full_response)
                    if not _should_keep_pharma_candidate(name_raw, cluster_rule):
                        line_buf = ""
                        match = None
                if match:
                    found = _lookup_pharma_info(name_raw)
                    if found:
                        console.print("│", style="grey50")
                        t = Text()
                        t.append("├─ DDI: ", style="bright_yellow")
                        t.append(found['ddi'], style="bright_white")
                        console.print(t)
                        t = Text()
                        t.append("└─ Kontraindikasi: ", style="bold bright_red")
                        t.append(found['ki'], style="bright_white")
                        console.print(t)
                    else:
                        console.print("│", style="grey50")
                        t = Text()
                        t.append("├─ DDI: ", style="dim grey50")
                        t.append("Tidak tersedia di database lokal", style="bright_white")
                        console.print(t)
                        t = Text()
                        t.append("└─ Kontraindikasi: ", style="dim grey50")
                        t.append("Tidak tersedia di database lokal", style="bright_white")
                        console.print(t)
                    renderer.last_was_blank = False
                    renderer.in_item = True

    except Exception as e:
        console.print(f"[!] Error: {e}", style="bright_red")
        return ""

    # ── Post-process untuk history (tidak ditampilkan ulang) ──
    full_response = _deduplicate_differential(full_response, prompt)
    full_response = _format_farmakologi_tree(full_response)

    console.print()
    _print_command_footer()
    console.print()

    history[-1]["content"] = prompt
    history.append({"role": "assistant", "content": full_response})
    _play_notification_sound()
    return full_response


# ---------------------------------------------------------------------------
# Pharmacology tree formatter
# ---------------------------------------------------------------------------
_PHARMA_LOOKUP: dict[str, dict] = {
    "paracetamol": {
        "ddi": "Warfarin ↑ INR; alkohol kronis ↑ hepatotoksisitas",
        "ki": "Gagal hati berat, alergi paracetamol",
    },
    "parasetamol": {
        "ddi": "Warfarin ↑ INR; alkohol kronis ↑ hepatotoksisitas",
        "ki": "Gagal hati berat, alergi parasetamol",
    },
    "ibuprofen": {
        "ddi": "Aspirin ↓ efektivitas; antikoagulan ↑ risiko perdarahan; ACE-I/ARB/diuretik ↓ efek antihipertensi",
        "ki": "Asma NSAID-sensitif, ulkus peptikum aktif, gagal ginjal berat, hamil trimester 3",
    },
    "amitriptyline": {
        "ddi": "MAOI ↑ risiko serotonin syndrome; CNS depressants ↑ sedasi; antikolinergik ↑ efek AC",
        "ki": "Infark miokard akut, aritmia, glaukoma sudut sempit, retensi urine",
    },
    "amitriptilin": {
        "ddi": "MAOI ↑ risiko serotonin syndrome; CNS depressants ↑ sedasi; antikolinergik ↑ efek AC",
        "ki": "Infark miokard akut, aritmia, glaukoma sudut sempit, retensi urine",
    },
    "methylergometrine": {
        "ddi": "⚠ Oksitosin (sinergis — risiko tetani uterus); CYP3A4 inhibitors ↑ kadar ergot; MAOI ↑ risiko krisis hipertensi",
        "ki": "Hipertensi, preeklampsia/eclampsia, penyakit jantung iskemik, sepsis, alergi ergot",
    },
    "methylergometrin": {
        "ddi": "⚠ Oksitosin (sinergis — risiko tetani uterus); CYP3A4 inhibitors ↑ kadar ergot; MAOI ↑ risiko krisis hipertensi",
        "ki": "Hipertensi, preeklampsia/eclampsia, penyakit jantung iskemik, sepsis, alergi ergot",
    },
    "amoxicillin": {
        "ddi": "⚠ Allopurinol ↑ risiko rash; probenesid ↑ kadar amoksisilin; antikoagulan oral ↑ INR; metotreksat ↑ toksisitas",
        "ki": "Hipersensitivitas penisilin/beta-laktam, mononukleosis, asma dengan riwayat alergi antibiotik",
    },
    "amoxicillin-clavulanate": {
        "ddi": "⚠ Allopurinol ↑ risiko rash; probenesid ↑ kadar amoksisilin; antikoagulan oral ↑ INR; metotreksat ↑ toksisitas",
        "ki": "Hipersensitivitas penisilin/beta-laktam, gangguan hati terkait amoksiklav, mononukleosis",
    },
    "amoksisilin-klavulanat": {
        "ddi": "⚠ Allopurinol ↑ risiko rash; probenesid ↑ kadar amoksisilin; antikoagulan oral ↑ INR; metotreksat ↑ toksisitas",
        "ki": "Hipersensitivitas penisilin/beta-laktam, gangguan hati terkait amoksiklav, mononukleosis",
    },
    "amoksisilin": {
        "ddi": "⚠ Allopurinol ↑ risiko rash; probenesid ↑ kadar amoksisilin; antikoagulan oral ↑ INR; metotreksat ↑ toksisitas",
        "ki": "Hipersensitivitas penisilin/beta-laktam, mononukleosis, asma dengan riwayat alergi antibiotik",
    },
    "kotrimoksazol": {
        "ddi": "⚠ Warfarin ↑ INR; metotreksat ↑ toksisitas; ACE-I/ARB ↑ hiperkalemia; diuretik ↑ hiperkalemia",
        "ki": "Alergi sulfa, kehamilan trimester 3, defisiensi G6PD, anemia megaloblastik",
    },
    "cotrimoxazole": {
        "ddi": "⚠ Warfarin ↑ INR; metotreksat ↑ toksisitas; ACE-I/ARB ↑ hiperkalemia; diuretik ↑ hiperkalemia",
        "ki": "Alergi sulfa, kehamilan trimester 3, defisiensi G6PD, anemia megaloblastik",
    },
    "trimethoprim": {
        "ddi": "⚠ Warfarin ↑ INR; metotreksat ↑ toksisitas; ACE-I/ARB ↑ hiperkalemia",
        "ki": "Alergi sulfa, kehamilan trimester 3, defisiensi G6PD, anemia megaloblastik",
    },
    "sulfamethoxazole": {
        "ddi": "⚠ Warfarin ↑ INR; metotreksat ↑ toksisitas; ACE-I/ARB ↑ hiperkalemia",
        "ki": "Alergi sulfa, kehamilan trimester 3, defisiensi G6PD, anemia megaloblastik",
    },
    "fe": {
        "ddi": "⚠ Antasida/PPI/H2-blocker ↓ absorpsi; levotiroksin ↓ absorpsi; tetrasiklin/quinolone (khelasi Fe ↓ efektivitas)",
        "ki": "Hemokromatosis, talasemia major, anemia hemolitik, ulkus GI aktif berdarah",
    },
    "ferrous": {
        "ddi": "⚠ Antasida/PPI/H2-blocker ↓ absorpsi; levotiroksin ↓ absorpsi; tetrasiklin/quinolone (khelasi Fe ↓ efektivitas)",
        "ki": "Hemokromatosis, talasemia major, anemia hemolitik, ulkus GI aktif berdarah",
    },
    "albendazol": {
        "ddi": "⚠ Cimetidine/praziquantel ↑ kadar albendazol; dexamethasone/antikonvulsan (fenitoin, karbamazepin, fenobarbital) ↓ kadar albendazol",
        "ki": "Kehamilan trimester 1, hipersensitivitas benzimidazol, kerusakan retina (neurocysticercosis)",
    },
    "albendazole": {
        "ddi": "⚠ Cimetidine/praziquantel ↑ kadar albendazol; dexamethasone/antikonvulsan (fenitoin, karbamazepin, fenobarbital) ↓ kadar albendazol",
        "ki": "Kehamilan trimester 1, hipersensitivitas benzimidazol, kerusakan retina (neurocysticercosis)",
    },
    "diethylcarbamazine": {
        "ddi": "⚠ Ivermectin (↑ risiko encephalopathy jika ko-infeksi Loa loa); alkohol/CNS depressants ↑ sedasi",
        "ki": "Kehamilan, riwayat epilepsi, infeksi Loa loa, gagal ginjal berat, hipertensi tak terkontrol",
    },
    "dec": {
        "ddi": "⚠ Ivermectin (↑ risiko encephalopathy jika ko-infeksi Loa loa); alkohol/CNS depressants ↑ sedasi",
        "ki": "Kehamilan, riwayat epilepsi, infeksi Loa loa, gagal ginjal berat, hipertensi tak terkontrol",
    },
    "vitamin c": {
        "ddi": "Aluminium antasida ↑ absorpsi aluminium; warfarin dapat mengubah INR bila dosis tinggi",
        "ki": "Nefrolitiasis oksalat berulang, hemokromatosis relatif, hipersensitivitas",
    },
    "asam askorbat": {
        "ddi": "Aluminium antasida ↑ absorpsi aluminium; warfarin dapat mengubah INR bila dosis tinggi",
        "ki": "Nefrolitiasis oksalat berulang, hemokromatosis relatif, hipersensitivitas",
    },
    "zinc": {
        "ddi": "Quinolone/tetrasiklin ↓ absorpsi (khelasi); penicillamine ↓ kadar zinc",
        "ki": "Hipersensitivitas, penggunaan jangka panjang dosis tinggi berisiko defisiensi tembaga",
    },
    "vitamin b kompleks": {
        "ddi": "Levodopa tanpa carbidopa dapat ↓ efek karena pyridoxine; chloramphenicol dapat ↓ respons hematologis folat/B12",
        "ki": "Hipersensitivitas, neuropati sensorik pada pyridoxine dosis tinggi jangka panjang",
    },
    "b complex": {
        "ddi": "Levodopa tanpa carbidopa dapat ↓ efek karena pyridoxine; chloramphenicol dapat ↓ respons hematologis folat/B12",
        "ki": "Hipersensitivitas, neuropati sensorik pada pyridoxine dosis tinggi jangka panjang",
    },
}

_PHARMA_SUPPORTIVE_RULES: tuple[dict, ...] = (
    {
        "keywords": ("nasofaringitis", "influenza", "common cold", "ispa", "faringitis", "tonsilitis"),
        "line": "Vitamin C 1x500 mg PO 5 hari PC",
        "lookup_key": "vitamin c",
    },
    {
        "keywords": ("osteoartritis", "osteoarthritis", "mialgia", "low back pain", "nyeri muskuloskeletal"),
        "line": "Vitamin B kompleks 1x1 PO 5 hari PC",
        "lookup_key": "vitamin b kompleks",
    },
)

_PHARMA_CLUSTER_RULES: tuple[dict, ...] = (
    {
        "keywords": ("osteoartritis", "osteoarthritis", "mialgia", "artritis reumatoid", "nyeri muskuloskeletal"),
        "blocked_drug_keywords": (
            "amoxic",
            "amoks",
            "clavulan",
            "augmentin",
            "metronid",
            "cotrim",
            "trimeth",
            "albend",
            "diethyl",
            "dec",
        ),
        "defaults": (
            "Ibuprofen 400 mg PO 3x1 5 hari PC",
            "Vitamin B kompleks 1x1 PO 5 hari PC",
        ),
    },
    {
        "keywords": ("nasofaringitis", "influenza", "common cold", "ispa", "faringitis viral"),
        "blocked_drug_keywords": (
            "amoxic",
            "amoks",
            "clavulan",
            "augmentin",
            "metronid",
            "cotrim",
            "trimeth",
        ),
        "defaults": (
            "Vitamin C 1x500 mg PO 5 hari PC",
        ),
    },
)


def _format_farmakologi_tree(response: str) -> str:
    """
    Parse section FARMAKOLOGI, deteksi nama obat per baris,
    dan reformat menjadi tree ASCII dengan DDI + Kontraindikasi.
    """
    section_pat = re.compile(
        r"((?:FARMAKOLOGI|Farmakologi):\s*\n)(.*?)(?=\n[A-Z][A-Z\s/]+:\s*\n|$)",
        re.DOTALL,
    )
    m = section_pat.search(response)
    if not m:
        return response

    header = m.group(1)
    raw_body = m.group(2)
    lines = [ln.strip() for ln in raw_body.splitlines() if ln.strip()]

    tree_lines: list[str] = [header.rstrip()]
    cluster_rule = _get_pharma_cluster_rule(response)
    drug_names_seen: set[str] = set()
    body_entries: list[tuple[str, str, dict | None]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _match_pharma_drug_header(line)
        if not match:
            lowered = line.strip().lower()
            if (
                not _is_pharma_meta_line(line)
                and not _is_pharma_meta_continuation(line)
                and not _is_pharma_stock_line(line)
                and not line.endswith(":")
                and line.strip("= ") != ""
                and not lowered.startswith("tidak ada obat")
            ):
                body_entries.append(("raw", line, None))
            i += 1
            continue

        formatted_line = _format_obat_indonesia(line)
        name_raw = match.group(1).strip().lower()
        found = _lookup_pharma_info(name_raw)

        # Konsumsi meta line model yang mengikuti obat ini agar tidak dobel.
        j = i + 1
        while j < len(lines) and (_is_pharma_meta_line(lines[j]) or _is_pharma_meta_continuation(lines[j])):
            j += 1
        if _should_keep_pharma_candidate(name_raw, cluster_rule):
            body_entries.append(("drug", formatted_line, found))
            drug_names_seen.add(name_raw)
        i = j

    if cluster_rule:
        for default_line in cluster_rule.get("defaults", ()):
            if sum(1 for kind, _, _ in body_entries if kind == "drug") >= 3:
                break
            default_match = _match_pharma_drug_header(default_line)
            if not default_match:
                continue
            default_name = default_match.group(1).strip().lower()
            if any(default_name in key or key in default_name for key in drug_names_seen):
                continue
            body_entries.append(("drug", _format_obat_indonesia(default_line), _lookup_pharma_info(default_name)))
            drug_names_seen.add(default_name)

    drug_count = sum(1 for kind, _, _ in body_entries if kind == "drug")

    if 0 < drug_count < 3:
        supportive_line, supportive_info, supportive_key = _pick_supportive_pharma(response)
        if supportive_line and supportive_info and supportive_key:
            if not any(supportive_key in key or key in supportive_key for key in drug_names_seen):
                body_entries.append(("drug", _format_obat_indonesia(supportive_line), supportive_info))
                drug_names_seen.add(supportive_key)

    for kind, line_text, found in body_entries:
        if kind == "raw":
            tree_lines.append(line_text)
            continue
        formatted_line = line_text
        tree_lines.append(formatted_line)
        tree_lines.append("│")
        if not found:
            tree_lines.append("├─ DDI: Tidak tersedia di database lokal")
            tree_lines.append("└─ Kontraindikasi: Tidak tersedia di database lokal")
            tree_lines.append("")
            continue
        tree_lines.append(f"├─ DDI: {found['ddi']}")
        tree_lines.append(f"└─ Kontraindikasi: {found['ki']}")
        tree_lines.append("")

    new_section = "\n".join(tree_lines).rstrip() + "\n\n"
    return response[:m.start()] + new_section + response[m.end():]


# ---------------------------------------------------------------------------
# Deduplication engine for DIAGNOSIS BANDING
# ---------------------------------------------------------------------------
_ICD_RE = re.compile(r"\b([A-Z]\d{2,3}(?:\.\d+)?)\b")


def _deduplicate_differential(response: str, query: str) -> str:
    """
    Parse section DIAGNOSIS BANDING, hapus duplikat berdasarkan kode ICD-10,
    dan inject fallback dari database lokal bila hasil < 3 item.
    """
    # 1. Cari section DIAGNOSIS BANDING
    section_pat = re.compile(
        r"DIAGNOSIS BANDING:\s*\n(.*?)\n(?=[A-Z][A-Z\s/]+:\s*\n|$)",
        re.DOTALL,
    )
    m = section_pat.search(response)
    if not m:
        return response

    raw_section = m.group(1)
    lines = raw_section.strip().splitlines()

    # 2. Ekstrak baris unik berdasarkan kode ICD-10
    seen_icd: set[str] = set()
    unique_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        icd_match = _ICD_RE.search(line)
        icd = icd_match.group(1).upper() if icd_match else ""
        if icd:
            if icd in seen_icd:
                continue
            seen_icd.add(icd)
        unique_lines.append(line)

    # 3. Fallback ke database lokal bila < 3 diagnosis
    if len(unique_lines) < 3:
        profile = _extract_query_profile(query)
        words = profile["words"]
        body_hints = profile["body_hints"]
        scored: list[tuple[float, dict]] = []
        for d in DB["diseases_full"]:
            s = _score_disease_tfidf(d, words, body_hints if body_hints else None, profile)
            if s >= 3.5:
                if body_hints and d.get("body_system", "") not in body_hints:
                    continue
                scored.append((s, d))
        scored.sort(key=lambda x: -x[0])
        scored = _prioritize_scored_candidates(scored, profile)

        for _, d in scored:
            icd = d.get("icd10", "")
            if icd and icd.upper() in seen_icd:
                continue
            # Buat baris diagnosis banding standar
            nama = d.get("nama", "")
            gejala = d.get("gejala_klinis", [])
            alasan = gejala[0] if gejala else "sesuai kriteria klinis"
            baris = f"[{icd}] {nama} — {alasan}"
            unique_lines.append(baris)
            if icd:
                seen_icd.add(icd.upper())
            target_count = 2 if profile["generic_only"] else 3
            if len(unique_lines) >= target_count:
                break

    # 4. Reconstruct section
    new_section = "DIAGNOSIS BANDING:\n" + "\n".join(unique_lines) + "\n\n"
    cleaned = response[:m.start()] + new_section + response[m.end():]
    return cleaned


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    session_id = uuid.uuid4().hex[:8].upper()
    history: list = []
    pasien: dict = {}
    last_response: str = ""

    _print_header(session_id)
    backend = _print_backend_menu()
    model = default_model_for_backend(backend)
    if backend == "local" and not local_available_models():
        console.print(
            "  [i] Ollama atau model lokal belum terdeteksi. Mode Local akan gagal sampai tersedia.",
            style="bright_yellow",
        )
    if backend == "deepseek" and not os.getenv("DEEPSEEK_API_KEY", "").strip():
        console.print(
            "  [i] DEEPSEEK_API_KEY belum diisi. Lengkapi .env agar DeepSeek bisa dipakai.",
            style="bright_yellow",
        )
    console.print(
        f"  Mode aktif: {_backend_label(backend)} | Model: {model}",
        style="dim grey50",
    )
    console.print(
        "  Ketik keluhan pasien atau /help untuk daftar perintah.",
        style="dim grey50",
    )
    console.print()

    while True:
        try:
            user_input = console.input(f"[bold {C_NAME}]INPUT DOKTER >[/bold {C_NAME}] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n  Keluar.", style="dim grey50")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd == "/exit":
            console.print("  Keluar.", style="dim grey50")
            break
        elif cmd == "/help":
            _print_help()
        elif cmd == "/soap":
            _print_soap_template()
        elif cmd == "/triage":
            _print_triage_template()
        elif cmd == "/rujuk":
            _print_rujuk_tree()
        elif cmd == "/edukasi":
            _print_edukasi_tree()
        elif cmd == "/library50":
            _open_library(page=1, page_size=50, title="PUSTAKA 50 PENYAKIT PRIORITAS PUSKESMAS")
        elif cmd == "/library20":
            _open_library(page=1, page_size=20, title="TOP 20 PENYAKIT TERSERING PUSKESMAS")
        elif cmd == "/library100":
            _open_library(page=1, page_size=50, title="PUSTAKA 100 PENYAKIT PRIORITAS PUSKESMAS")
        elif cmd == "/tree":
            _print_dir_tree()
        elif cmd == "/clear":
            console.clear()
            _print_header(session_id)
        elif cmd == "/next":
            history.clear()
            pasien = {}
            session_id = uuid.uuid4().hex[:8].upper()
            last_response = ""
            console.clear()
            _print_header(session_id)
            console.print("  Kasus baru dimulai.", style="dim grey50")
            console.print()
        elif cmd == "/pasien":
            pasien = _input_pasien()
            if pasien:
                console.print("  Data pasien tersimpan.", style="dim grey50")
                console.print()
        elif cmd == "/history":
            console.print()
            console.print(SEP, style="grey50")
            console.print("RIWAYAT PERCAKAPAN", style="#7CB9E8")
            console.print(SEP, style="grey50")
            for msg in history:
                label = "DOKTER" if msg["role"] == "user" else "AUDREY"
                style = "bright_cyan" if msg["role"] == "user" else "bright_yellow"
                preview = msg["content"][:150].replace("\n", " ")
                console.print(f"  {label}: {preview}", style=style)
            console.print(SEP, style="grey50")
            console.print()
        elif cmd == "/save":
            _save_session(history, pasien, session_id)
            gateway.publish(f"💾 Session saved: `{session_id}`")
        elif cmd == "/send":
            if not last_response:
                console.print("  Belum ada output untuk dikirim.", style="dim grey50")
                console.print()
                continue
            msg = format_message(last_response, pasien, session_id)
            gateway.publish(msg)
            console.print("  Terkirim ke Telegram.", style="dim grey50")
            console.print()
        elif cmd == "/model":
            try:
                available = _get_backend_models(backend)
                console.print()
                for i, m in enumerate(available, 1):
                    marker = "  <-- aktif" if m == model else ""
                    console.print(f"  {i}. {m}{marker}", style="grey82")
                choice = console.input("Pilih nomor (Enter batal): ").strip()
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(available):
                        model = available[idx]
                        console.print(f"  Model diganti.", style="dim grey50")
                console.print()
            except Exception as e:
                console.print(f"  [!] Gagal: {e}", style="bright_red")
        elif cmd == "/icd" or cmd.startswith("/icd "):
            handle_icd_command(user_input, console)
        else:
            last_response = _chat(user_input, history, pasien, model, backend)


if __name__ == "__main__":
    main()
