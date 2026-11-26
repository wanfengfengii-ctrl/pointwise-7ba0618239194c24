from dataclasses import dataclass


@dataclass(frozen=True)
class Meter:
    beats: int

    def __post_init__(self) -> None:
        if type(self.beats) is not int or self.beats <= 0:
            raise ValueError('小节拍数必须是正整数')

    def positions(self) -> range:
        return range(self.beats)


def validate_beat(meter: Meter, beat: object) -> int:
    if type(beat) is not int or beat not in meter.positions():
        raise ValueError(f'拍位 {beat!r} 超出小节的 0 至 {meter.beats - 1} 拍位')
    return beat
