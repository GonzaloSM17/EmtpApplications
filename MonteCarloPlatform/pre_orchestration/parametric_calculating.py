from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt
from random import Random
from typing import ClassVar

# =============================================================================
# Parameter ranges and configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class ParameterRange:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError("ParameterRange.minimum cannot be greater than maximum.")

    def sample(
        self,
        rng: Random,
    ) -> float:
        return rng.uniform(
            self.minimum,
            self.maximum,
        )


@dataclass(frozen=True, slots=True)
class ParameterConfig:
    """Ranges for the parameter groups included in a study.

    ``Kp`` and ``Ki`` are a single group because both are derived from the
    damping ratio and bandwidth. ``Kqv`` and ``Rrpw`` can be enabled
    independently by supplying their range.
    """

    damping_ratio_range: ParameterRange | None = None
    bandwidth_range: ParameterRange | None = None
    kqv_range: ParameterRange | None = None
    rrpw_range: ParameterRange | None = None

    GRID_VOLTAGE: ClassVar[float] = 1.0

    def __post_init__(self) -> None:
        has_kp_ki = (
            self.damping_ratio_range is not None
            or self.bandwidth_range is not None
        )
        if has_kp_ki and (
            self.damping_ratio_range is None or self.bandwidth_range is None
        ):
            raise ValueError(
                "Kp and Ki require both damping_ratio_range and bandwidth_range."
            )

        if not has_kp_ki and self.kqv_range is None and self.rrpw_range is None:
            raise ValueError("Select at least one parameter group to generate.")

        if self.damping_ratio_range is not None and not (
            0.0 < self.damping_ratio_range.minimum <= 1.0
            and 0.0 < self.damping_ratio_range.maximum <= 1.0
        ):
            raise ValueError("Damping ratio limits must satisfy 0 < xi <= 1.")

        if self.bandwidth_range is not None and self.bandwidth_range.minimum <= 0.0:
            raise ValueError("Bandwidth must be greater than zero.")

        if self.kqv_range is not None and self.kqv_range.minimum < 0.0:
            raise ValueError("Kqv cannot be negative.")

        if self.rrpw_range is not None and self.rrpw_range.minimum < 0.0:
            raise ValueError("Rrpw cannot be negative.")


# =============================================================================
# Parameter result
# =============================================================================


@dataclass(frozen=True, slots=True)
class Params:
    kp: float | None = None
    ki: float | None = None
    kqv: float | None = None
    rrpw: float | None = None


@dataclass(frozen=True, slots=True)
class ParameterResult:
    params: Params

    damping_ratio: float | None = None
    bandwidth_hz: float | None = None
    natural_frequency_rad_s: float | None = None


# =============================================================================
# Parameter generator
# =============================================================================


class ParameterGenerator:
    def __init__(
        self,
        config: ParameterConfig,
        rng: Random | None = None,
    ) -> None:
        self.config = config
        self.rng = rng or Random()

    def generate(
        self,
    ) -> ParameterResult:
        """
        Generate one parameter set.

        Independent stochastic variables:
        - damping ratio
        - bandwidth
        - Kqv
        - Rrpw

        Derived variables:
        - natural frequency
        - Kp
        - Ki
        """

        damping_ratio: float | None = None
        bandwidth_hz: float | None = None
        natural_frequency_rad_s: float | None = None
        kp: float | None = None
        ki: float | None = None
        kqv: float | None = None
        rrpw: float | None = None

        if self.config.damping_ratio_range is not None:
            damping_ratio = round(
                self.config.damping_ratio_range.sample(self.rng),
                3,
            )
            bandwidth_hz = round(
                self.config.bandwidth_range.sample(self.rng),
                2,
            )
            natural_frequency_rad_s = self._calculate_natural_frequency(
                damping_ratio=damping_ratio,
                bandwidth_hz=bandwidth_hz,
            )
            kp = round(
                2.0
                * damping_ratio
                * natural_frequency_rad_s
                / ParameterConfig.GRID_VOLTAGE,
                2,
            )
            ki = round(
                natural_frequency_rad_s**2 / ParameterConfig.GRID_VOLTAGE,
                2,
            )

        if self.config.kqv_range is not None:
            kqv = round(self.config.kqv_range.sample(self.rng), 1)

        if self.config.rrpw_range is not None:
            rrpw = round(self.config.rrpw_range.sample(self.rng), 1)

        params = Params(
            kp=kp,
            ki=ki,
            kqv=kqv,
            rrpw=rrpw,
        )

        return ParameterResult(
            params=params,
            damping_ratio=damping_ratio,
            bandwidth_hz=bandwidth_hz,
            natural_frequency_rad_s=(
                round(natural_frequency_rad_s, 2)
                if natural_frequency_rad_s is not None
                else None
            ),
        )

    @staticmethod
    def _calculate_bandwidth_factor(
        damping_ratio: float,
    ) -> float:
        return sqrt(
            1.0
            + 2.0 * damping_ratio**2
            + sqrt((1.0 + 2.0 * damping_ratio**2) ** 2 + 1.0)
        )

    def _calculate_natural_frequency(
        self,
        damping_ratio: float,
        bandwidth_hz: float,
    ) -> float:
        bandwidth_factor = self._calculate_bandwidth_factor(
            damping_ratio=damping_ratio,
        )

        return 2.0 * pi * bandwidth_hz / bandwidth_factor


# =============================================================================
# Print helper
# =============================================================================


def print_result(
    result: ParameterResult,
) -> None:
    if result.damping_ratio is not None:
        print(f"Damping ratio:      {result.damping_ratio:.3f}")
        print(f"Bandwidth:          {result.bandwidth_hz:.2f} Hz")
        print(f"Natural frequency:  {result.natural_frequency_rad_s:.2f} rad/s")
        print(f"Kp:                 {result.params.kp:.2f}")
        print(f"Ki:                 {result.params.ki:.2f}")

    if result.params.kqv is not None:
        print(f"Kqv:                {result.params.kqv:.1f}")

    if result.params.rrpw is not None:
        print(f"Rrpw:               {result.params.rrpw:.1f}")


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":

    config = ParameterConfig(
        damping_ratio_range=ParameterRange(
            minimum=0.6,
            maximum=1.0,
        ),
        bandwidth_range=ParameterRange(
            minimum=2.5,
            maximum=15.0,
        ),
        kqv_range=ParameterRange(
            minimum=1.0,
            maximum=2.0,
        ),
        rrpw_range=ParameterRange(
            minimum=0.1,
            maximum=1.0,
        ),
    )

    generator = ParameterGenerator(
        config=config,
    )

    result = generator.generate()

    print_result(
        result=result,
    )
