"""Double-enveloping (globoidal) worm gearset design per ANSI/AGMA 6135-A02."""

# Re-export the public API so callers can write `from globoid import calculate`
# instead of reaching into the individual modules.
from .calculator import DesignError, DesignInput, calculate          # input handling + the design calculation
from .dxf_export import export_worm_wheel_dxf, write_worm_wheel_dxf  # worm wheel drawing as DXF text / file
from .equation_export import format_equations, write_equations_txt   # SolidWorks equation file as text / file

# Names exported by `from globoid import *`, and the documented surface of the package.
__all__ = [
    "DesignError", "DesignInput", "calculate",
    "export_worm_wheel_dxf", "write_worm_wheel_dxf",
    "format_equations", "write_equations_txt",
]
