from dataclasses import dataclass
from datetime import datetime

DEFAULT_LATEST_TIME = datetime(2000, 12, 12, 12, 12, 12)


@dataclass
class FollowUser:
    """跨平台统一关注用户模型。"""
    userid: str
    username: str
    latest_time: datetime
    url = ''
    start_msg = ''
    end_msg = ''

    @classmethod
    def from_db_row(cls, userid, username, latest_time: str):
        if latest_time is None or latest_time == '':
            parsed = DEFAULT_LATEST_TIME
        elif isinstance(latest_time, datetime):
            parsed = latest_time
        else:
            parsed = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")
        return cls(userid=userid, username=username, latest_time=parsed)
