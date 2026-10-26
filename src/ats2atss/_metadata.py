from dataclasses import astuple, dataclass, field, fields
from datetime import datetime, timezone

import math
from ._errors import AtsFormatError
import numpy as np

UNKNOWN_DATETIME = "1970-01-01T00:00:00"

def _f(code: str, offset: int):
    """A header field: its struct code and byte offset (the offset is documentation + test)."""
    return field(metadata={"fmt": code, "offset": offset})


@dataclass(frozen=True, slots=True)
class AtsHeader:
    """Raw values of an ATS header (version 80/81), as stored in the file.

    Strings are decoded (cut at the first NUL, stripped). No other cleaning is done:
    names such as ``SystemType="ADU08e"`` stay as recorded.
    """

    # --- format ---------------------------------------------------------------
    header_length: int = _f("H", 0x000)  # 1024; 33760 for CEA sliced files
    header_version: int = _f("h", 0x002)  # 80, 81; 1080 for CEA
    samples: int = _f("I", 0x004)  # 0xFFFFFFFF -> use samples_64bit
    sample_rate: float = _f("f", 0x008)  # Hz
    start: int = _f("I", 0x00C)  # Unix time, UTC
    lsbval: float = _f("d", 0x010)  # mV per count
    GMToffset: int = _f("i", 0x018)  # unused
    orig_sample_rate: float = _f("f", 0x01C)  # Hz as originally recorded

    # --- system / channel -----------------------------------------------------
    serial_number: int = _f("H", 0x020)  # logger serial
    serial_number_ADC_board: int = _f("H", 0x022)
    channel_number: int = _f("B", 0x024)
    chopper: int = _f("B", 0x025)  # 1 = on (LF mode), 0 = off (HF mode)
    channel_type: str = _f("2s", 0x026)  # Ex, Ey, Hx, Hy, Hz, ...
    sensor_type: str = _f("6s", 0x028)  # e.g. MFS07e (no hyphen)
    sensor_serial_number: int = _f("h", 0x02E)

    # --- electrode / sensor position [m] --------------------------------------
    x1: float = _f("f", 0x030)  # South negative
    y1: float = _f("f", 0x034)  # West negative
    z1: float = _f("f", 0x038)  # top / sky
    x2: float = _f("f", 0x03C)  # North positive
    y2: float = _f("f", 0x040)  # East positive
    z2: float = _f("f", 0x044)  # bottom / earth
    dipole_length: float = _f("f", 0x048)  # deprecated, use the positions
    azimuth: float = _f("f", 0x04C)  # deprecated ("angle"), use the positions

    # --- self-test ------------------------------------------------------------
    rho_probe_ohm: float = _f("f", 0x050)  # contact resistance
    DC_offset_voltage_mV: float = _f("f", 0x054)
    gain_stage1: float = _f("f", 0x058)
    gain_stage2: float = _f("f", 0x05C)

    # --- position / GPS -------------------------------------------------------
    iLat_ms: int = _f("i", 0x060)  # latitude, milliseconds of arc
    iLong_ms: int = _f("i", 0x064)  # longitude, milliseconds of arc
    iElev_cm: int = _f("i", 0x068)  # elevation, cm
    Lat_Long_TYPE: str = _f("1s", 0x06C)  # 'G' GPS, 'U' user
    coordinate_type: str = _f("1s", 0x06D)  # 'U' UTM
    ref_meridian: int = _f("h", 0x06E)
    Northing: float = _f("d", 0x070)
    Easting: float = _f("d", 0x078)
    gps_clock_status: str = _f("1s", 0x080)  # '-' unknown, 'N' no fix, 'C' full fix
    GPS_accuracy: int = _f("b", 0x081)
    offset_UTC: int = _f("h", 0x082)
    SystemType: str = _f("12s", 0x084)  # e.g. ADU08e

    # --- job ------------------------------------------------------------------
    survey_header_filename: str = _f("12s", 0x090)
    type_of_meas: str = _f("4s", 0x09C)  # MT, CSAMT, ...
    DCOffsetCorrValue: float = _f("d", 0x0A0)
    DCOffsetCorrOn: int = _f("b", 0x0A8)
    InputDivOn: int = _f("b", 0x0A9)  # 1 = DIV-8 (coils)
    bit_indicator: int = _f("h", 0x0AA)  # 0 = 32-bit, 1 = 64-bit samples
    result_selftest: str = _f("2s", 0x0AC)  # 'OK' / 'NO'
    numslices: int = _f("H", 0x0AE)

    # --- unused calibration fields --------------------------------------------
    cal_freqs: int = _f("h", 0x0B0)
    cal_entry_length: int = _f("h", 0x0B2)
    cal_version: int = _f("h", 0x0B4)
    cal_start_address: int = _f("h", 0x0B6)

    # --- filters / misc -------------------------------------------------------
    LF_filters: int = _f("b", 0x0B8)  # bit field, first byte of 8
    emptylf: str = _f("7s", 0x0B9)  # padding
    UTMZone: str = _f("12s", 0x0C0)
    system_cal_datetime: int = _f("I", 0x0CC)
    sensor_cal_filename: str = _f("12s", 0x0D0)  # "SENSOR.CAL", unused
    sensor_cal_datetime: int = _f("I", 0x0DC)
    powerline1: float = _f("f", 0x0E0)
    powerline2: float = _f("f", 0x0E4)
    HF_filters: int = _f("b", 0x0E8)  # bit field, first byte of 8
    emptyhf: str = _f("7s", 0x0E9)  # padding
    samples_64bit: int = _f("Q", 0x0F0)  # only used if samples == 0xFFFFFFFF
    external_gain: float = _f("f", 0x0F8)
    ADB_board_type: str = _f("4s", 0x0FC)  # LF, HF, MF, BB

    # --- comments (0x100) -----------------------------------------------------
    Client: str = _f("16s", 0x100)
    Contractor: str = _f("16s", 0x110)
    Area: str = _f("16s", 0x120)
    SurveyID: str = _f("16s", 0x130)
    Operator: str = _f("16s", 0x140)
    SiteName: str = _f("112s", 0x150)
    XmlHeader: str = _f("64s", 0x1C0)  # measdoc XML in the same folder
    Comments: str = _f("288s", 0x200)
    SiteNameRR: str = _f("112s", 0x320)
    SiteNameEMAP: str = _f("112s", 0x390)

    # ------------------------------------------------------------ derived values
    @property
    def n_samples(self) -> int:
        """Number of samples, using samples_64bit when the 32-bit counter overflowed."""
        return self.samples_64bit if self.samples == 0xFFFFFFFF else self.samples

    @property
    def start_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.start, tz=timezone.utc)

    @property
    def latitude(self) -> float:
        return self.iLat_ms / 3.6e6

    @property
    def longitude(self) -> float:
        return self.iLong_ms / 3.6e6

    @property
    def elevation(self) -> float:
        return self.iElev_cm / 100.0

    @property
    def dipole_length_from_positions(self) -> float:
        """Distance between the two positions in m; 0 below 1 mm (as MTHotel's pos2length)."""
        d = math.dist((self.x1, self.y1, self.z1), (self.x2, self.y2, self.z2))
        return 0.0 if d < 0.001 else d


@dataclass
class ADUFFTdata:
    hx: np.ndarray | None = None
    hy: np.ndarray | None = None
    hz: np.ndarray | None = None
    nperseg: int = 1024
    nyquist: float | None = None
    fs: float | None = None
    cal_hx: np.ndarray | None = None
    cal_hy: np.ndarray | None = None
    cal_hz: np.ndarray | None = None
    fmin: int | float | None = None
    fmax: int | float | None = None


@dataclass
class AtssMeta:
    # --- identity (from the filename tags) ---
    serial: int
    system: str
    channel_no: int = 0
    channel_type: str = ""
    sample_rate: float = 0.0  # Hz  <-- time-series essential
    samples: int | None = None

    # --- acquisition (from the json header) ---
    datetime: str | None = None
    latitude: float = 0.0
    longitude: float = 0.0
    elevation: float = 0.0
    units: str = ""

    # --- calibration (from the json header) ---
    sensor: str = ""
    sensor_serial: int = 0
    chopper: int = 0
    cal_f: list = field(default_factory=list)
    cal_a: list = field(default_factory=list)
    cal_p: list = field(default_factory=list)

    @property
    def nyquist(self) -> float:
        return self.sample_rate / 2

    @property
    def is_magnetic(self) -> bool:
        return self.channel_type.startswith("H")

    @property
    def has_calibration(self) -> bool:
        return len(self.cal_f) >= 2

    @property
    def cal(self) -> dict:
        return {"f": self.cal_f, "a": self.cal_a, "p": self.cal_p}


@dataclass(frozen=True)
class Calibration:
    sensor: str
    serial: int
    chopper: int  # 1 = on, 0 = off
    channel_id: int | None = None
    datetime: str = UNKNOWN_DATETIME
    operator: str = ""
    f: list[float] = field(default_factory=list)  # Hz
    a: list[float] = field(default_factory=list)  # mV/nT
    p: list[float] = field(default_factory=list)  # degrees

    def to_json(self) -> dict:
        """The ``sensor_calibration`` block of an .atss JSON header."""
        return {
            "sensor": self.sensor,
            "serial": self.serial,
            "chopper": self.chopper,
            "units_frequency": "Hz",
            "units_amplitude": "mV/nT" if self.f else "mV",
            "units_phase": "degrees",
            "datetime": self.datetime,
            "Operator": self.operator,
            "f": self.f,
            "a": self.a,
            "p": self.p,
        }

