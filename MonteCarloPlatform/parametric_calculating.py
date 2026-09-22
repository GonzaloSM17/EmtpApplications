from __future__ import annotations

from dataclasses import dataclass
from math import log, pi, sqrt
from random import Random


@dataclass(frozen=True, slots=True)
class ParameterRange:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError("ParameterRange.minimum cannot be greater than maximum.")

    def sample(self, rng: Random) -> float:
        return rng.uniform(self.minimum, self.maximum)


@dataclass(frozen=True, slots=True)
class ParameterConfig:
    # Design-variable ranges
    settling_time_range: ParameterRange
    damping_ratio_range: ParameterRange
    kqv_range: ParameterRange

    # Fixed design values
    settling_tolerance: float = 0.05
    grid_voltage: float = 1.0

    # Bandwidth verification and search limits
    minimum_bandwidth_hz: float = 5.0
    stop_bandwidth_hz: float = 10.0
    maximum_bandwidth_hz: float = 100.0

    # Maximum search effort per generated instance
    maximum_attempts: int = 100

    def __post_init__(self) -> None:
        if self.settling_time_range.minimum <= 0.0:
            raise ValueError("Settling time must be greater than zero.")

        if not 0.0 < self.settling_tolerance < 1.0:
            raise ValueError("Settling tolerance must be between 0 and 1.")

        if not (
            0.0 < self.damping_ratio_range.minimum < 1.0
            and 0.0 < self.damping_ratio_range.maximum < 1.0
        ):
            raise ValueError("Damping ratio limits must be between 0 and 1.")

        if self.kqv_range.minimum < 0.0:
            raise ValueError("Kqv cannot be negative.")

        if self.grid_voltage <= 0.0:
            raise ValueError("Grid voltage must be greater than zero.")

        if not (
            0.0
            < self.minimum_bandwidth_hz
            < self.stop_bandwidth_hz
            <= self.maximum_bandwidth_hz
        ):
            raise ValueError(
                "Bandwidth limits must satisfy: " "0 < minimum < stop <= maximum."
            )

        if self.maximum_attempts <= 0:
            raise ValueError("Maximum attempts must be greater than zero.")


@dataclass(frozen=True, slots=True)
class Params:
    kp: float
    ki: float
    frt: int
    kqv: float


@dataclass(frozen=True, slots=True)
class ParameterResult:
    params: Params

    settling_time: float
    settling_tolerance: float
    damping_ratio: float

    natural_frequency_rad_s: float
    bandwidth_hz: float

    attempts: int
    stop_threshold_reached: bool


class ParameterGenerator:
    def __init__(
        self,
        config: ParameterConfig,
        rng: Random | None = None,
    ) -> None:
        self.config = config
        self.rng = rng or Random()
        self._rad_s_to_hz = 1.0 / (2.0 * pi)

    def generate(self) -> ParameterResult:
        """
        Generate one valid parameter set.

        Rules:
        - Evaluate at most maximum_attempts candidates.
        - A candidate is valid when:

              minimum_bandwidth_hz
              < bandwidth_hz
              < maximum_bandwidth_hz

        - Retain the valid candidate with the lowest bandwidth.
        - Stop early when:

              bandwidth_hz <= stop_bandwidth_hz

        - If the stop threshold is not reached, return the valid
          candidate with the lowest bandwidth found.
        """

        best_result: ParameterResult | None = None

        for attempt in range(
            1,
            self.config.maximum_attempts + 1,
        ):
            result = self._generate_candidate(
                attempt=attempt,
            )

            if not self._is_valid_bandwidth(result.bandwidth_hz):
                continue

            if best_result is None or result.bandwidth_hz < best_result.bandwidth_hz:
                best_result = result

            if result.stop_threshold_reached:
                return result

        if best_result is None:
            raise RuntimeError(
                "No valid parameter set was found after "
                f"{self.config.maximum_attempts} attempts. "
                "Required bandwidth: "
                f"{self.config.minimum_bandwidth_hz:.2f} Hz "
                "< bandwidth < "
                f"{self.config.maximum_bandwidth_hz:.2f} Hz."
            )

        return best_result

    def _generate_candidate(
        self,
        attempt: int,
    ) -> ParameterResult:
        settling_time = round(
            self.config.settling_time_range.sample(self.rng),
            3,
        )

        damping_ratio = round(
            self.config.damping_ratio_range.sample(self.rng),
            3,
        )

        settling_tolerance = self.config.settling_tolerance

        envelope_factor = 1.0 / sqrt(1.0 - damping_ratio**2)

        bandwidth_factor = sqrt(
            1.0
            + 2.0 * damping_ratio**2
            + sqrt((1.0 + 2.0 * damping_ratio**2) ** 2 + 1.0)
        )

        natural_frequency_raw = log(envelope_factor / settling_tolerance) / (
            damping_ratio * settling_time
        )

        kp_raw = 2.0 * damping_ratio * natural_frequency_raw / self.config.grid_voltage

        ki_raw = natural_frequency_raw**2 / self.config.grid_voltage

        bandwidth_raw = natural_frequency_raw * bandwidth_factor * self._rad_s_to_hz

        params = Params(
            kp=round(kp_raw, 2),
            ki=round(ki_raw, 2),
            frt=self.rng.choice((0, 1)),
            kqv=round(
                self.config.kqv_range.sample(self.rng),
                2,
            ),
        )

        return ParameterResult(
            params=params,
            settling_time=settling_time,
            settling_tolerance=settling_tolerance,
            damping_ratio=damping_ratio,
            natural_frequency_rad_s=round(
                natural_frequency_raw,
                2,
            ),
            bandwidth_hz=round(
                bandwidth_raw,
                2,
            ),
            attempts=attempt,
            stop_threshold_reached=(self._stop_threshold_reached(bandwidth_raw)),
        )

    def _is_valid_bandwidth(
        self,
        bandwidth_hz: float,
    ) -> bool:
        return (
            self.config.minimum_bandwidth_hz
            < bandwidth_hz
            < self.config.maximum_bandwidth_hz
        )

    def _stop_threshold_reached(
        self,
        bandwidth_hz: float,
    ) -> bool:
        return (
            self.config.minimum_bandwidth_hz
            < bandwidth_hz
            <= self.config.stop_bandwidth_hz
        )


def print_result(
    result: ParameterResult,
) -> None:
    print(f"Settling time:      " f"{result.settling_time:.3f} s")
    print(f"Tolerance:          " f"{result.settling_tolerance:.2f}")
    print(f"Damping ratio:      " f"{result.damping_ratio:.3f}")
    print(f"Natural frequency:  " f"{result.natural_frequency_rad_s:.2f} rad/s")
    print(f"Bandwidth:          " f"{result.bandwidth_hz:.2f} Hz")
    print(f"Attempts:           " f"{result.attempts}")
    print(f"Stop threshold:     " f"{result.stop_threshold_reached}")
    print(f"Kp:                 " f"{result.params.kp:.2f}")
    print(f"Ki:                 " f"{result.params.ki:.2f}")
    print(f"FRT:                " f"{result.params.frt}")
    print(f"Kqv:                " f"{result.params.kqv:.2f}")


if __name__ == "__main__":

    config = ParameterConfig(
        settling_time_range=ParameterRange(
            minimum=0.010,
            maximum=0.150,
        ),
        damping_ratio_range=ParameterRange(
            minimum=0.5,
            maximum=0.9,
        ),
        kqv_range=ParameterRange(
            minimum=1.0,
            maximum=2.0,
        ),
        settling_tolerance=0.05,
        grid_voltage=1.0,
        minimum_bandwidth_hz=5.0,
        stop_bandwidth_hz=10.0,
        maximum_bandwidth_hz=100.0,
        maximum_attempts=100,
    )

    generator = ParameterGenerator(
        config=config,
    )

    result = generator.generate()

    print_result(
        result=result,
    )
