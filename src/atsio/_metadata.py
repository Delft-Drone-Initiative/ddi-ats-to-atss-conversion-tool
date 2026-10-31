import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MIN_CAL_SIZE = 6  # MTHotel mt_base.hpp: fewer points are not interpolated

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


@dataclass(frozen=True)
class Calibration:
    sensor: str
    serial: int
    chopper: int  # 1 = on, 0 = off
    channel_id: int | None = None
    datetime: str = UNKNOWN_DATETIME
    operator: str = ("",)
    f: tuple[float, ...] = ()
    a: tuple[float, ...] = ()
    p: tuple[float, ...] = ()

    @property
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
            "f": list(self.f),
            "a": list(self.a),
            "p": list(self.p),
        }

    @property
    def has_table(self) -> bool:
        return len(self.f) >= MIN_CAL_SIZE  # 6, as MTHotel; you had >= 2


@dataclass(frozen=True, slots=True)
class AtssMeta:
    """One .atss stream: filename tags + JSON header + file size."""

    # identity (filename)
    serial: int
    system: str
    channel_number: int
    channel_type: str
    sample_rate: float  # Hz
    # acquisition (JSON)
    datetime: str
    latitude: float
    longitude: float
    elevation: float
    azimuth: float  # missing in your version
    tilt: float  # missing
    resistance: float  # missing
    units: str
    filter: str  # missing (the HF-HP-500Hz flag lives here)
    calibration: Calibration  # replaces sensor, sensor_serial, chopper, cal_f/a/p
    # derived (file size)
    samples: int
    id: str = ""
    source: str = ""

    @property
    def nyquist(self) -> float:
        return self.sample_rate / 2

    @property
    def is_magnetic(self) -> bool:
        return self.channel_type.startswith("H")

    def to_json(self) -> dict:
        """The .json header written next to the .atss (Metronix key order)."""
        return {
            "datetime": self.datetime,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation": self.elevation,
            "azimuth": self.azimuth,
            "tilt": self.tilt,
            "resistance": self.resistance,
            "units": self.units,
            "id": self.id,
            "filter": self.filter,
            "source": self.source,
            "sensor_calibration": self.calibration.to_json,
        }


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """What ``convert_ats_file`` did with one .ats file."""

    source: Path
    atss: Path
    json: Path
    meta: AtssMeta
    skipped: bool = False  # True if the output existed and overwrite was False


@dataclass(frozen=True, slots=True)
class DirResult:
    """What happened to one measurement folder."""

    source: Path
    out_dir: Path
    results: tuple[ConversionResult, ...] = ()  # converted + skipped files
    failures: dict[Path, Exception] = field(default_factory=dict)  # file -> its error
    error: Exception | None = None  # folder-level problem (no .ats, unreadable)

    @property
    def converted(self) -> int:
        return sum(not r.skipped for r in self.results)

    @property
    def skipped(self) -> int:
        return sum(r.skipped for r in self.results)

    @property
    def failed(self) -> int:
        return len(self.failures)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.failures

    def summary(self) -> str:
        if self.error is not None:
            return f"{self.source.name}: ERROR {self.error}"
        return (
            f"{self.source.name}: {self.converted} converted, {self.skipped} skipped, "
            f"{self.failed} failed -> {self.out_dir}"
        )


@dataclass(frozen=True, slots=True)
class SurveyResult:
    """What happened to a whole survey: one DirResult per measurement folder."""

    source: Path
    out_dir: Path
    dirs: tuple[DirResult, ...] = ()

    @property
    def ok(self) -> bool:
        return all(d.ok for d in self.dirs)

    @property
    def results(self) -> list[ConversionResult]:
        """Every file result of every folder."""
        return [r for d in self.dirs for r in d.results]

    @property
    def failures(self) -> dict[Path, Exception]:
        """Every failed file, plus every folder that could not be converted at all."""
        out: dict[Path, Exception] = {}
        for d in self.dirs:
            out.update(d.failures)
            if d.error is not None:
                out[d.source] = d.error
        return out

    def summary(self) -> str:
        """Readable report, one line per folder plus totals."""
        lines = [d.summary() for d in self.dirs]
        lines.append(
            f"total: {sum(d.converted for d in self.dirs)} converted, "
            f"{sum(d.skipped for d in self.dirs)} skipped, "
            f"{sum(d.failed for d in self.dirs)} failed files, "
            f"{sum(d.error is not None for d in self.dirs)} failed folders "
            f"in {len(self.dirs)} folder(s)"
        )
        return "\n".join(lines)
