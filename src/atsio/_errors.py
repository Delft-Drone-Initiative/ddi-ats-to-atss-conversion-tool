class CalibrationError(ValueError):
    """The XML calibration is present but unusable."""


class Ats2AtssError(Exception):
    """Base class for all ats2atss errors."""


class AtsFormatError(Ats2AtssError, ValueError):
    """The file is not a readable .ats file."""


class ConversionError(RuntimeError):
    """One or more .ats files in a folder could not be converted."""
